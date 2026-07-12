"""Build a budgeted, redacted evidence pack for incident reasoning."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    Evidence,
    Incident,
    InvestigationPlan,
    InvestigationRun,
    TimelineEvent,
)
from app.services.investigation_engine.knowledge_context_builder import (
    InvestigationContext,
    KnowledgeContextBuilder,
)
from app.services.knowledge_builder.secret_redactor import redact_secrets
from app.services.vector_search.similarity_service import SimilarityContext, SimilarityService

# Approximate token budget via characters (~4 chars per token).
DEFAULT_BUDGET_CHARS = 24_000
HIGH_BUDGET_RATIO = 0.60
MEDIUM_BUDGET_RATIO = 0.30
UNCERTAIN_BUDGET_RATIO = 0.10


@dataclass
class EvidencePackItem:
    evidence_id: str
    source: str
    evidence_type: str
    title: str
    content: str
    relevance_label: str
    observed_at: str | None = None
    summarized: bool = False


@dataclass
class EvidencePack:
    incident: dict[str, Any]
    alerts: list[dict[str, Any]]
    context: dict[str, Any]
    plan: dict[str, Any]
    evidence_groups: dict[str, list[dict[str, Any]]]
    timeline: list[dict[str, Any]]
    similarity: dict[str, Any]
    valid_evidence_ids: set[str] = field(default_factory=set)
    budget_summary: dict[str, Any] = field(default_factory=dict)


def _char_len(item: EvidencePackItem) -> int:
    return len(item.title) + len(item.content) + len(item.evidence_id) + 40


def _to_item(row: Evidence) -> EvidencePackItem:
    redacted = redact_secrets(row.content or "").redacted_text
    observed = row.observed_at.isoformat() if row.observed_at else None
    return EvidencePackItem(
        evidence_id=str(row.id),
        source=row.source,
        evidence_type=row.evidence_type,
        title=row.title or "",
        content=redacted,
        relevance_label=(row.relevance_label or "uncertain").lower(),
        observed_at=observed,
    )


def _sort_key(item: EvidencePackItem) -> tuple:
    # Prefer recent evidence within a relevance tier.
    ts = item.observed_at or ""
    return (ts, item.evidence_id)


def _fit_budget(
    items: list[EvidencePackItem],
    budget_chars: int,
    *,
    preserve_contradictions: list[EvidencePackItem] | None = None,
) -> tuple[list[EvidencePackItem], bool]:
    """Return items that fit budget; summarize if needed. ``bool`` = any summarized."""
    if not items:
        return [], False

    sorted_items = sorted(items, key=_sort_key, reverse=True)
    kept: list[EvidencePackItem] = []
    used = 0
    summarized_any = False

    must_keep = {i.evidence_id for i in (preserve_contradictions or [])}
    for item in sorted_items:
        need = _char_len(item)
        if used + need <= budget_chars or item.evidence_id in must_keep:
            kept.append(item)
            used += need
            continue
        # Summarize to fit remaining budget.
        remaining = budget_chars - used
        if remaining < 120:
            break
        short = EvidencePackItem(
            evidence_id=item.evidence_id,
            source=item.source,
            evidence_type=item.evidence_type,
            title=item.title,
            content=(item.content[: max(remaining - len(item.title) - 20, 80)] + "…"),
            relevance_label=item.relevance_label,
            observed_at=item.observed_at,
            summarized=True,
        )
        kept.append(short)
        used += _char_len(short)
        summarized_any = True

    return kept, summarized_any


def _items_to_dicts(items: list[EvidencePackItem]) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": i.evidence_id,
            "source": i.source,
            "evidence_type": i.evidence_type,
            "title": i.title,
            "content": i.content,
            "relevance_label": i.relevance_label,
            "observed_at": i.observed_at,
            "summarized": i.summarized,
        }
        for i in items
    ]


class EvidencePackBuilder:
    def __init__(
        self,
        context_builder: KnowledgeContextBuilder | None = None,
        similarity_service: SimilarityService | None = None,
        budget_chars: int = DEFAULT_BUDGET_CHARS,
    ) -> None:
        self._context_builder = context_builder or KnowledgeContextBuilder()
        self._similarity = similarity_service or SimilarityService()
        self._budget_chars = budget_chars

    def build(
        self,
        db: Session,
        organization_id: uuid.UUID,
        investigation_run_id: uuid.UUID,
        *,
        similarity: SimilarityContext | None = None,
    ) -> EvidencePack:
        run = db.scalar(
            select(InvestigationRun).where(
                InvestigationRun.id == investigation_run_id,
                InvestigationRun.organization_id == organization_id,
            )
        )
        if run is None or run.incident_id is None:
            raise ValueError("Investigation run not found")

        incident = db.scalar(
            select(Incident).where(
                Incident.id == run.incident_id,
                Incident.organization_id == organization_id,
            )
        )
        if incident is None:
            raise ValueError("Incident not found")

        alerts = list(
            db.scalars(
                select(Alert)
                .where(
                    Alert.organization_id == organization_id,
                    Alert.incident_id == incident.id,
                )
                .order_by(Alert.fired_at.desc())
            ).all()
        )
        plan = db.scalar(
            select(InvestigationPlan).where(
                InvestigationPlan.investigation_run_id == run.id,
                InvestigationPlan.organization_id == organization_id,
            )
        )
        evidence_rows = list(
            db.scalars(
                select(Evidence)
                .where(
                    Evidence.investigation_run_id == run.id,
                    Evidence.organization_id == organization_id,
                )
                .order_by(Evidence.observed_at.desc())
            ).all()
        )
        timeline_rows = list(
            db.scalars(
                select(TimelineEvent)
                .where(
                    TimelineEvent.investigation_run_id == run.id,
                    TimelineEvent.organization_id == organization_id,
                )
                .order_by(TimelineEvent.event_time.desc())
            ).all()
        )

        context = self._context_builder.build(db, organization_id, incident, alerts)
        if similarity is None:
            try:
                similarity = self._similarity.find_for_incident(db, organization_id, incident)
            except Exception:  # noqa: BLE001
                similarity = SimilarityContext()

        # Deduplicate by evidence id (stable) and deduplication_key.
        seen_keys: set[str] = set()
        unique_items: list[EvidencePackItem] = []
        for row in evidence_rows:
            key = row.deduplication_key or str(row.id)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique_items.append(_to_item(row))

        grouped: dict[str, list[EvidencePackItem]] = {
            "high": [],
            "medium": [],
            "uncertain": [],
            "low": [],
        }
        for item in unique_items:
            label = item.relevance_label
            if label not in grouped:
                label = "uncertain"
            grouped[label].append(item)

        high_budget = int(self._budget_chars * HIGH_BUDGET_RATIO)
        medium_budget = int(self._budget_chars * MEDIUM_BUDGET_RATIO)
        uncertain_budget = int(self._budget_chars * UNCERTAIN_BUDGET_RATIO)

        high_kept, high_sum = _fit_budget(grouped["high"], high_budget)
        medium_kept, med_sum = _fit_budget(grouped["medium"], medium_budget)
        uncertain_kept, unc_sum = _fit_budget(grouped["uncertain"], uncertain_budget)

        # Low: sample at most 2 recent items if they add signal (e.g. contradict).
        low_sample: list[EvidencePackItem] = []
        if grouped["low"]:
            low_sorted = sorted(grouped["low"], key=_sort_key, reverse=True)[:2]
            low_kept, _ = _fit_budget(low_sorted, 800)
            low_sample = low_kept

        valid_ids = {i.evidence_id for i in unique_items}
        budget_summary = {
            "total_budget_chars": self._budget_chars,
            "high_included": len(high_kept),
            "medium_included": len(medium_kept),
            "uncertain_included": len(uncertain_kept),
            "low_sample_included": len(low_sample),
            "summarized": high_sum or med_sum or unc_sum,
            "total_evidence": len(unique_items),
        }

        return EvidencePack(
            incident={
                "id": str(incident.id),
                "title": incident.title,
                "status": incident.status,
                "severity": incident.severity,
                "description": incident.description,
            },
            alerts=[
                {"source": a.source, "title": a.title, "description": a.description}
                for a in alerts
            ],
            context={
                "affected_service": context.affected_service,
                "direct_dependencies": context.direct_dependencies,
                "indirect_dependencies": context.indirect_dependencies,
                "external_providers": context.external_providers,
                "possible_blast_radius": context.possible_blast_radius,
                "architecture_summary": context.architecture_summary,
                "relevant_runbooks": context.relevant_runbooks,
            },
            plan=plan.steps if plan and plan.steps else {},
            evidence_groups={
                "high": _items_to_dicts(high_kept),
                "medium": _items_to_dicts(medium_kept),
                "uncertain": _items_to_dicts(uncertain_kept),
                "low_sample": _items_to_dicts(low_sample),
            },
            timeline=[
                {
                    "event_time": (
                        t.event_time.isoformat() if t.event_time else None
                    ),
                    "title": t.title,
                    "description": (t.description or "")[:500],
                    "source": t.source,
                }
                for t in timeline_rows[:20]
            ],
            similarity={
                "similar_incidents": [
                    {
                        "title": m.title,
                        "score": m.score,
                        "object_id": str(m.object_id) if m.object_id else None,
                    }
                    for m in similarity.similar_incidents
                ],
                "relevant_runbooks": [
                    {"title": m.title, "score": m.score} for m in similarity.relevant_runbooks
                ],
                "related_postmortems": [
                    {"title": m.title, "score": m.score}
                    for m in similarity.related_postmortems
                ],
            },
            valid_evidence_ids=valid_ids,
            budget_summary=budget_summary,
        )
