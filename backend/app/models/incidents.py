"""Incident, alerting, and postmortem models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    OrganizationScopedMixin,
    TimestampMixin,
    UUIDMixin,
)
from app.db.types import GUID, JSONType


class Incident(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "incidents"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="open", nullable=False, index=True)
    severity: Mapped[str | None] = mapped_column(String(50), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONType)


class Alert(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "alerts"

    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("incidents.id", ondelete="SET NULL"), index=True
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="firing", nullable=False)
    severity: Mapped[str | None] = mapped_column(String(50))
    # Correlation grouping key and the confidence (0..1) that this alert
    # belongs to its correlated group.
    correlation_key: Mapped[str | None] = mapped_column(String(255), index=True)
    correlation_confidence: Mapped[float | None] = mapped_column(Float)
    fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_payload: Mapped[dict | None] = mapped_column(JSONType)


class AlertCorrelation(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "alert_correlations"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("incidents.id", ondelete="SET NULL"), index=True
    )
    correlation_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    correlation_confidence: Mapped[float | None] = mapped_column(Float)
    method: Mapped[str | None] = mapped_column(String(100))


class IncidentImpact(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "incident_impacts"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    impact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(String(50))
    affected_services: Mapped[dict | None] = mapped_column(JSONType)
    metrics: Mapped[dict | None] = mapped_column(JSONType)


class Postmortem(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "postmortems"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    # Whether the postmortem was authored by a human or generated.
    postmortem_source: Mapped[str] = mapped_column(
        String(50), default="manual", nullable=False
    )
    incident_duration_minutes: Mapped[int | None] = mapped_column(Integer)
