"""Alert-to-incident correlation.

Alerts are *signals* from monitoring tools. Incidents are the real-world
problems they represent. This service groups related alerts under a single
open incident when correlation confidence is high enough.

Rules
-----
* Only **open** incidents are considered for attachment — resolved/closed
  incidents are never silently merged into.
* If no candidate exceeds the confidence threshold, a **new** incident is
  created for the alert.
* Every correlation decision is recorded in ``AlertCorrelation`` and audited.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, AlertCorrelation, Incident
from app.services.audit import AUDIT_ALERT_CORRELATED, record_audit

# Incident statuses eligible for correlation (not resolved/closed).
_OPEN_STATUSES = frozenset({"open", "investigating", "identified", "monitoring"})

# Minimum weighted score (0..1) to attach to an existing incident.
_CORRELATION_THRESHOLD = 0.55

# Alerts within this window of an incident are more likely related.
_TIME_WINDOW = timedelta(minutes=30)

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


@dataclass
class AlertSignal:
    """Normalized alert input for correlation."""

    organization_id: uuid.UUID
    source: str
    title: str
    description: str | None = None
    alert_type: str | None = None
    service: str | None = None
    environment: str | None = None
    region: str | None = None
    fired_at: datetime | None = None
    raw_payload: dict | None = None

    @classmethod
    def from_payload(
        cls,
        organization_id: uuid.UUID,
        source: str,
        title: str,
        *,
        description: str | None = None,
        fired_at: datetime | None = None,
        raw_payload: dict | None = None,
    ) -> AlertSignal:
        payload = raw_payload or {}
        return cls(
            organization_id=organization_id,
            source=source,
            title=title,
            description=description,
            alert_type=payload.get("alert_type") or payload.get("type"),
            service=payload.get("service") or payload.get("service_name"),
            environment=payload.get("environment") or payload.get("env"),
            region=payload.get("region"),
            fired_at=fired_at,
            raw_payload=payload,
        )


@dataclass
class CorrelationResult:
    alert: Alert
    incident: Incident
    confidence: float
    method: str
    created_incident: bool = False
    factors: dict[str, float] = field(default_factory=dict)


class AlertCorrelationService:
    """Skeleton correlation engine with explicit, testable scoring."""

    def ingest(self, db: Session, signal: AlertSignal) -> CorrelationResult:
        fired_at = signal.fired_at or datetime.now(tz=timezone.utc)

        best_incident, score, factors = self._find_best_open_incident(db, signal, fired_at)

        if best_incident is not None and score >= _CORRELATION_THRESHOLD:
            incident = best_incident
            method = "attached_to_open_incident"
            created = False
            confidence = score
        else:
            incident = self._create_incident(db, signal, fired_at)
            method = "created_new_incident"
            created = True
            confidence = 1.0
            factors = {"new_incident": 1.0}

        correlation_key = self._correlation_key(signal)
        alert = Alert(
            organization_id=signal.organization_id,
            incident_id=incident.id,
            source=signal.source,
            title=signal.title,
            description=signal.description,
            status="firing",
            correlation_key=correlation_key,
            correlation_confidence=confidence,
            fired_at=fired_at,
            raw_payload=signal.raw_payload,
        )
        db.add(alert)
        db.flush()

        correlation = AlertCorrelation(
            organization_id=signal.organization_id,
            alert_id=alert.id,
            incident_id=incident.id,
            correlation_key=correlation_key,
            correlation_confidence=confidence,
            method=method,
        )
        db.add(correlation)

        record_audit(
            db,
            organization_id=signal.organization_id,
            action=AUDIT_ALERT_CORRELATED,
            resource_type="alert",
            resource_id=alert.id,
            metadata={
                "incident_id": str(incident.id),
                "method": method,
                "confidence": confidence,
                "source": signal.source,
                "factors": factors,
            },
        )

        db.commit()
        db.refresh(alert)
        db.refresh(incident)

        return CorrelationResult(
            alert=alert,
            incident=incident,
            confidence=confidence,
            method=method,
            created_incident=created,
            factors=factors,
        )

    def _find_best_open_incident(
        self,
        db: Session,
        signal: AlertSignal,
        fired_at: datetime,
    ) -> tuple[Incident | None, float, dict[str, float]]:
        stmt = (
            select(Incident)
            .where(
                Incident.organization_id == signal.organization_id,
                Incident.status.in_(_OPEN_STATUSES),
            )
            .order_by(Incident.created_at.desc())
        )
        candidates = list(db.scalars(stmt).all())

        best: Incident | None = None
        best_score = 0.0
        best_factors: dict[str, float] = {}

        for incident in candidates:
            score, factors = self._score_incident(db, signal, incident, fired_at)
            if score > best_score:
                best = incident
                best_score = score
                best_factors = factors

        return best, best_score, best_factors

    def _score_incident(
        self,
        db: Session,
        signal: AlertSignal,
        incident: Incident,
        fired_at: datetime,
    ) -> tuple[float, dict[str, float]]:
        factors: dict[str, float] = {}

        # Same organization is a hard filter (already applied); weight as 1.0.
        factors["same_organization"] = 1.0

        # Time window: compare against incident start/detect time or sibling alerts.
        ref_time = incident.detected_at or incident.started_at or incident.created_at
        if ref_time is not None:
            if ref_time.tzinfo is None:
                ref_time = ref_time.replace(tzinfo=timezone.utc)
            delta = abs(fired_at - ref_time)
            if delta <= _TIME_WINDOW:
                factors["close_time_window"] = 1.0 - (delta.total_seconds() / _TIME_WINDOW.total_seconds())
            else:
                factors["close_time_window"] = 0.0

        # Service match: incident metadata or existing alerts on the incident.
        incident_service = (incident.metadata_ or {}).get("service")
        if signal.service and incident_service:
            factors["same_service"] = (
                1.0 if signal.service.lower() == str(incident_service).lower() else 0.0
            )
        elif signal.service:
            sibling_services = self._sibling_alert_services(db, incident.id)
            if signal.service.lower() in sibling_services:
                factors["related_service"] = 0.8

        # Alert type similarity against sibling alerts.
        if signal.alert_type:
            sibling_types = self._sibling_alert_types(db, incident.id)
            if signal.alert_type.lower() in sibling_types:
                factors["similar_alert_type"] = 1.0

        # Message/title similarity.
        msg_score = self._message_similarity(signal.title, incident.title)
        if signal.description and incident.description:
            msg_score = max(
                msg_score, self._message_similarity(signal.description, incident.description)
            )
        if msg_score > 0.4:
            factors["similar_message"] = msg_score

        # Environment / region from metadata.
        meta = incident.metadata_ or {}
        if signal.environment and meta.get("environment"):
            factors["same_environment"] = (
                1.0
                if signal.environment.lower() == str(meta["environment"]).lower()
                else 0.0
            )
        if signal.region and meta.get("region"):
            factors["same_region"] = (
                1.0 if signal.region.lower() == str(meta["region"]).lower() else 0.0
            )

        # Organization is already enforced as a filter; time proximity alone is not
        # enough to merge alerts into unrelated incidents.
        substantive = {
            k: v
            for k, v in factors.items()
            if k not in ("same_organization", "close_time_window") and v > 0
        }
        if not substantive:
            return 0.0, factors

        # Weighted average of available factors.
        weights = {
            "same_organization": 0.15,
            "close_time_window": 0.25,
            "same_service": 0.2,
            "related_service": 0.15,
            "similar_alert_type": 0.15,
            "similar_message": 0.2,
            "same_environment": 0.1,
            "same_region": 0.1,
        }
        total_weight = sum(weights[k] for k in factors)
        score = sum(factors[k] * weights.get(k, 0.1) for k in factors) / total_weight
        return min(score, 1.0), factors

    def _sibling_alert_services(self, db: Session, incident_id: uuid.UUID) -> set[str]:
        alerts = db.scalars(
            select(Alert).where(Alert.incident_id == incident_id)
        ).all()
        services: set[str] = set()
        for a in alerts:
            payload = a.raw_payload or {}
            svc = payload.get("service") or payload.get("service_name")
            if svc:
                services.add(str(svc).lower())
        return services

    def _sibling_alert_types(self, db: Session, incident_id: uuid.UUID) -> set[str]:
        alerts = db.scalars(
            select(Alert).where(Alert.incident_id == incident_id)
        ).all()
        types: set[str] = set()
        for a in alerts:
            payload = a.raw_payload or {}
            at = payload.get("alert_type") or payload.get("type")
            if at:
                types.add(str(at).lower())
        return types

    @staticmethod
    def _message_similarity(a: str, b: str) -> float:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    @staticmethod
    def _correlation_key(signal: AlertSignal) -> str:
        parts = [
            signal.organization_id.hex,
            (signal.service or "").lower(),
            (signal.alert_type or "").lower(),
            _TOKEN_SPLIT.sub(" ", signal.title.lower()).strip(),
        ]
        digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
        return f"corr:{digest}"

    def _create_incident(
        self, db: Session, signal: AlertSignal, fired_at: datetime
    ) -> Incident:
        metadata: dict = {}
        if signal.service:
            metadata["service"] = signal.service
        if signal.environment:
            metadata["environment"] = signal.environment
        if signal.region:
            metadata["region"] = signal.region

        incident = Incident(
            organization_id=signal.organization_id,
            title=signal.title,
            description=signal.description,
            status="open",
            detected_at=fired_at,
            metadata_=metadata or None,
        )
        db.add(incident)
        db.flush()
        return incident
