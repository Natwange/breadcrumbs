"""Organization and membership models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    OrganizationScopedMixin,
    TimestampMixin,
    UUIDMixin,
)
from app.db.types import GUID, JSONType


class Organization(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    onboarding_status: Mapped[str] = mapped_column(
        String(50), default="pending", nullable=False
    )
    # Soft-delete marker; NULL means the organization is active.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrganizationMember(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(50), default="member", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)


class OrganizationInvitation(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "organization_invitations"

    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), default="member", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    # Opaque invite token (a random lookup value, not a secret credential).
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("user_profiles.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrganizationSettings(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "organization_settings"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_org_settings"),
    )

    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    default_severity: Mapped[str | None] = mapped_column(String(50))
    preferences: Mapped[dict | None] = mapped_column(JSONType)
    notes: Mapped[str | None] = mapped_column(Text)
