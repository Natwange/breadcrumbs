"""Investigation workflow models: runs, plans, collectors, evidence, and output."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    OrganizationScopedMixin,
    TimestampMixin,
    UUIDMixin,
)
from app.db.types import GUID, JSONType


class InvestigationRun(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "investigation_runs"

    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("incidents.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False, index=True)
    trigger: Mapped[str | None] = mapped_column(String(100))
    summary: Mapped[str | None] = mapped_column(Text)
    # Observability for the evidence-relevance judging batch (Phase 8):
    # prompt/model/schema versions, latency, token usage, cost, source.
    relevance_tracking: Mapped[dict | None] = mapped_column(JSONType)
    # Phase 9 incident reasoning output.
    executive_summary: Mapped[str | None] = mapped_column(Text)
    reasoning_status: Mapped[str | None] = mapped_column(String(50), index=True)
    reasoning_tracking: Mapped[dict | None] = mapped_column(JSONType)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvestigationPlan(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "investigation_plans"

    investigation_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("investigation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    steps: Mapped[dict | None] = mapped_column(JSONType)


class CollectorRun(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "collector_runs"

    investigation_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("investigation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collector_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class Evidence(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "evidence"

    investigation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("investigation_runs.id", ondelete="CASCADE"), index=True
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("incidents.id", ondelete="SET NULL"), index=True
    )
    collector_run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("collector_runs.id", ondelete="SET NULL"), index=True
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str | None] = mapped_column(Text)
    # Stable hash/key used to avoid ingesting duplicate evidence.
    deduplication_key: Mapped[str | None] = mapped_column(String(255), index=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONType)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    # Categorical relevance judgment (Phase 8): relevance/confidence labels and
    # whether the judgment came from Claude or the deterministic fallback.
    relevance_label: Mapped[str | None] = mapped_column(String(20))
    relevance_confidence: Mapped[str | None] = mapped_column(String(20))
    relevance_source: Mapped[str | None] = mapped_column(String(50), index=True)
    relevance_reason: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TimelineEvent(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "timeline_events"

    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("incidents.id", ondelete="CASCADE"), index=True
    )
    investigation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("investigation_runs.id", ondelete="SET NULL"), index=True
    )
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(100))
    event_type: Mapped[str | None] = mapped_column(String(100))


class Hypothesis(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "hypotheses"

    investigation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("investigation_runs.id", ondelete="CASCADE"), index=True
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("incidents.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="proposed", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer)
    supporting_evidence_ids: Mapped[list | None] = mapped_column(JSONType)
    contradicting_evidence_ids: Mapped[list | None] = mapped_column(JSONType)
    reasoning_source: Mapped[str | None] = mapped_column(String(50))


class SuggestedAction(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "suggested_actions"

    investigation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("investigation_runs.id", ondelete="CASCADE"), index=True
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("incidents.id", ondelete="SET NULL"), index=True
    )
    hypothesis_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("hypotheses.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    action_type: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    requires_human_approval: Mapped[bool] = mapped_column(default=False, nullable=False)
    reasoning_source: Mapped[str | None] = mapped_column(String(50))
    supporting_evidence_ids: Mapped[list | None] = mapped_column(JSONType)
    # Approval / rejection workflow fields.
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("user_profiles.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("user_profiles.id", ondelete="SET NULL")
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)


class SlackDraft(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "slack_drafts"

    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("incidents.id", ondelete="SET NULL"), index=True
    )
    investigation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("investigation_runs.id", ondelete="SET NULL"), index=True
    )
    channel: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    reasoning_source: Mapped[str | None] = mapped_column(String(50))
