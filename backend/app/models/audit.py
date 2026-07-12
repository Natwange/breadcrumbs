"""Audit logging."""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    OrganizationScopedMixin,
    TimestampMixin,
    UUIDMixin,
)
from app.db.types import GUID, JSONType


class AuditLog(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("user_profiles.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(100), index=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(GUID, index=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONType)
