"""Declarative base and shared mixins for all models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    declared_attr,
    mapped_column,
)

from app.db.types import GUID


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class UUIDMixin:
    """Adds a UUID primary key generated on the Python side."""

    id: Mapped[uuid.UUID] = mapped_column(
        GUID, primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    """Adds created/updated timestamps managed by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OrganizationScopedMixin:
    """Adds a required, indexed ``organization_id`` foreign key.

    Every organization-owned model mixes this in so tenant scoping is
    consistent and enforced at the schema level (NOT NULL + FK + index).
    """

    @declared_attr
    def organization_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            GUID,
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
