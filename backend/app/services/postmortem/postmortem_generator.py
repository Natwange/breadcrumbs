"""Generate and approve structured incident postmortems."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import (
    Alert,
    Evidence,
    Hypothesis,
    Incident,
    IncidentImpact,
    InvestigationPlan,
    InvestigationRun,
    Postmortem,
    SlackDraft,
    SuggestedAction,
    TimelineEvent,
)
from app.services.audit import AUDIT_POSTMORTEM_GENERATED, record_audit
from app.services.investigation_engine.knowledge_context_builder import KnowledgeContextBuilder
from app.services.knowledge_builder.secret_redactor import redact_secrets
from app.services.postmortem.postmortem_fallback import build_fallback
from app.services.postmortem.postmortem_prompt_builder import PROMPT_VERSION, build_prompt
from app.services.postmortem.postmortem_schema import (
    SCHEMA_VERSION,
    SOURCE_CLAUDE,
    PostmortemSchemaError,
    PostmortemSections,
    parse_postmortem_response,
)
from app.services.vector_search.embedding_queue import EmbeddingQueue

RESOLVED_STATUSES = frozenset({"resolved"})


class PostmortemLLMClient(Protocol):
    @property
    def enabled(self) -> bool: ...

    def generate(self, system: str, user: str) -> tuple[str, dict[str, int], str]: ...


class ClaudePostmortemClient:
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.anthropic_api_key
        self._model = settings.anthropic_model

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def generate(self, system: str, user: str) -> tuple[str, dict[str, int], str]:
        if not self._api_key:
            raise RuntimeError("Anthropic API key is not configured")
        with httpx.Client(timeout=90.0) as client:
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": 8192,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            response.raise_for_status()
            data = response.json()
        text_blocks = [
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        ]
        raw = "\n".join(text_blocks).strip()
        usage = data.get("usage", {}) or {}
        token_usage = {
            "input_tokens": int(usage.get("input_tokens", 0)),
            "output_tokens": int(usage.get("output_tokens", 0)),
        }
        return raw, token_usage, data.get("model", self._model)


@dataclass
class PostmortemGenerateResult:
    postmortem: Postmortem
    sections: PostmortemSections
    tracking: dict[str, Any]


def calculate_duration_minutes(incident: Incident) -> int | None:
    start = incident.started_at or incident.detected_at or incident.created_at
    end = incident.resolved_at
    if start is None or end is None:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    delta = end - start
    return max(int(delta.total_seconds() / 60), 0)


class PostmortemGenerator:
    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: PostmortemLLMClient | None = None,
        embedder: EmbeddingQueue | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._llm = llm_client or ClaudePostmortemClient(self._settings)
        self._embedder = embedder or EmbeddingQueue()
        self._context_builder = KnowledgeContextBuilder()

    def generate(
        self,
        db: Session,
        organization_id: uuid.UUID,
        incident_id: uuid.UUID,
        *,
        actor_id: uuid.UUID | None = None,
        resolution_notes: str | None = None,
    ) -> PostmortemGenerateResult:
        incident = db.scalar(
            select(Incident).where(
                Incident.id == incident_id,
                Incident.organization_id == organization_id,
            )
        )
        if incident is None:
            raise ValueError("Incident not found")
        if incident.status not in RESOLVED_STATUSES:
            raise ValueError("Postmortem can only be generated for resolved incidents")

        duration = calculate_duration_minutes(incident)
        context = self._gather_context(
            db, organization_id, incident, resolution_notes=resolution_notes
        )
        context["incident_duration_minutes"] = duration

        sections, tracking = self._produce_sections(context, duration)

        existing = db.scalar(
            select(Postmortem).where(
                Postmortem.incident_id == incident.id,
                Postmortem.organization_id == organization_id,
            )
        )
        run_id = context.get("investigation_run_id")
        if existing:
            existing.title = f"Postmortem: {incident.title}"
            existing.content = sections.render_paragraphs()
            existing.sections_ = sections.to_dict()
            existing.postmortem_source = sections.postmortem_source
            existing.incident_duration_minutes = duration
            existing.investigation_run_id = run_id
            existing.status = "draft"
            postmortem = existing
        else:
            postmortem = Postmortem(
                organization_id=organization_id,
                incident_id=incident.id,
                investigation_run_id=run_id,
                title=f"Postmortem: {incident.title}",
                content=sections.render_paragraphs(),
                sections_=sections.to_dict(),
                status="draft",
                postmortem_source=sections.postmortem_source,
                incident_duration_minutes=duration,
            )
            db.add(postmortem)

        db.flush()
        record_audit(
            db,
            organization_id=organization_id,
            action=AUDIT_POSTMORTEM_GENERATED,
            actor_id=actor_id,
            resource_type="postmortem",
            resource_id=postmortem.id,
            metadata={
                "incident_id": str(incident.id),
                "postmortem_source": sections.postmortem_source,
            },
        )
        db.commit()
        db.refresh(postmortem)

        return PostmortemGenerateResult(
            postmortem=postmortem,
            sections=sections,
            tracking=tracking,
        )

    def approve_and_embed(
        self,
        db: Session,
        organization_id: uuid.UUID,
        postmortem_id: uuid.UUID,
    ) -> Postmortem:
        postmortem = db.scalar(
            select(Postmortem).where(
                Postmortem.id == postmortem_id,
                Postmortem.organization_id == organization_id,
            )
        )
        if postmortem is None:
            raise ValueError("Postmortem not found")

        postmortem.status = "approved"
        self._embedder.embed_postmortem(db, postmortem)
        db.commit()
        db.refresh(postmortem)
        return postmortem

    def _produce_sections(
        self, context: dict[str, Any], duration: int | None
    ) -> tuple[PostmortemSections, dict[str, Any]]:
        if getattr(self._llm, "enabled", False):
            result = self._call_claude(context)
            if result is not None:
                sections, tracking = result
                sections.incident_duration_minutes = duration
                return sections, tracking

        sections = build_fallback(context, duration)
        tracking = {
            "prompt_version": PROMPT_VERSION,
            "model_version": "rule_based_fallback",
            "schema_version": SCHEMA_VERSION,
            "reasoning_source": sections.postmortem_source,
            "success": True,
        }
        return sections, tracking

    def _call_claude(
        self, context: dict[str, Any]
    ) -> tuple[PostmortemSections, dict[str, Any]] | None:
        prompt = build_prompt(context)
        start = time.perf_counter()
        try:
            raw, token_usage, model_version = self._llm.generate(prompt.system, prompt.user)
            sections = parse_postmortem_response(raw)
            sections.postmortem_source = SOURCE_CLAUDE
        except (PostmortemSchemaError, httpx.HTTPError, RuntimeError, ValueError):
            return None
        except Exception:  # noqa: BLE001
            return None

        latency_ms = int((time.perf_counter() - start) * 1000)
        tracking = {
            "prompt_version": prompt.prompt_version,
            "model_version": model_version,
            "schema_version": prompt.schema_version,
            "latency_ms": latency_ms,
            "token_usage": token_usage,
            "postmortem_source": SOURCE_CLAUDE,
            "success": True,
        }
        return sections, tracking

    def _gather_context(
        self,
        db: Session,
        organization_id: uuid.UUID,
        incident: Incident,
        *,
        resolution_notes: str | None,
    ) -> dict[str, Any]:
        alerts = list(
            db.scalars(
                select(Alert).where(
                    Alert.organization_id == organization_id,
                    Alert.incident_id == incident.id,
                )
            ).all()
        )
        run = db.scalars(
            select(InvestigationRun)
            .where(
                InvestigationRun.organization_id == organization_id,
                InvestigationRun.incident_id == incident.id,
            )
            .order_by(InvestigationRun.created_at.desc())
            .limit(1)
        ).first()
        plan = None
        evidence_rows: list[Evidence] = []
        timeline_rows: list[TimelineEvent] = []
        hypotheses: list[Hypothesis] = []
        actions: list[SuggestedAction] = []
        impacts: list[IncidentImpact] = []
        slack_drafts: list[SlackDraft] = []

        if run:
            plan = db.scalar(
                select(InvestigationPlan).where(
                    InvestigationPlan.investigation_run_id == run.id,
                    InvestigationPlan.organization_id == organization_id,
                )
            )
            evidence_rows = list(
                db.scalars(
                    select(Evidence).where(
                        Evidence.investigation_run_id == run.id,
                        Evidence.organization_id == organization_id,
                    )
                ).all()
            )
            timeline_rows = list(
                db.scalars(
                    select(TimelineEvent).where(
                        TimelineEvent.investigation_run_id == run.id,
                        TimelineEvent.organization_id == organization_id,
                    )
                ).all()
            )
            hypotheses = list(
                db.scalars(
                    select(Hypothesis).where(
                        Hypothesis.investigation_run_id == run.id,
                        Hypothesis.organization_id == organization_id,
                    )
                ).all()
            )
            actions = list(
                db.scalars(
                    select(SuggestedAction).where(
                        SuggestedAction.investigation_run_id == run.id,
                        SuggestedAction.organization_id == organization_id,
                    )
                ).all()
            )
            slack_drafts = list(
                db.scalars(
                    select(SlackDraft).where(
                        SlackDraft.investigation_run_id == run.id,
                        SlackDraft.organization_id == organization_id,
                    )
                ).all()
            )

        impacts = list(
            db.scalars(
                select(IncidentImpact).where(
                    IncidentImpact.incident_id == incident.id,
                    IncidentImpact.organization_id == organization_id,
                )
            ).all()
        )

        inv_context = self._context_builder.build(db, organization_id, incident, alerts)

        def _redact(text: str | None) -> str:
            if not text:
                return ""
            return redact_secrets(text).redacted_text

        return {
            "incident": {
                "title": incident.title,
                "status": incident.status,
                "severity": incident.severity,
                "description": _redact(incident.description),
            },
            "resolution_notes": _redact(resolution_notes),
            "investigation_run_id": run.id if run else None,
            "investigation_context": {
                "affected_service": inv_context.affected_service,
                "direct_dependencies": inv_context.direct_dependencies,
                "possible_blast_radius": inv_context.possible_blast_radius,
            },
            "alerts": [
                {"source": a.source, "title": a.title, "description": _redact(a.description)}
                for a in alerts
            ],
            "plan": plan.steps if plan and plan.steps else {},
            "evidence": [
                {
                    "evidence_id": str(e.id),
                    "source": e.source,
                    "evidence_type": e.evidence_type,
                    "title": e.title,
                    "content": _redact(e.content),
                    "relevance_label": e.relevance_label,
                }
                for e in evidence_rows
            ],
            "timeline": [
                {
                    "event_time": (
                        t.event_time.isoformat() if t.event_time else None
                    ),
                    "title": t.title,
                    "description": _redact(t.description),
                }
                for t in timeline_rows
            ],
            "hypotheses": [
                {
                    "title": h.title,
                    "description": _redact(h.description),
                    "supporting_evidence_ids": h.supporting_evidence_ids or [],
                }
                for h in hypotheses
            ],
            "actions": [
                {
                    "title": a.title,
                    "description": _redact(a.description),
                    "action_type": a.action_type,
                }
                for a in actions
            ],
            "impacts": [
                {
                    "impact_type": i.impact_type,
                    "description": _redact(i.description),
                    "severity": i.severity,
                }
                for i in impacts
            ],
            "slack_drafts": [
                {"content": _redact(s.content)} for s in slack_drafts
            ],
        }
