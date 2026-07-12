"""Third-party integration connections.

IMPORTANT: This table stores only *non-secret* connection metadata (provider,
account identifiers, display config, status). API keys, OAuth tokens, and other
secrets must never be persisted here — they belong in a dedicated secret
manager. The ``config`` column is JSON for non-sensitive settings only.
"""

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


class IntegrationConnection(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "integration_connections"

    provider: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="disconnected", nullable=False)
    # Non-secret external identifier (e.g. workspace/team id), never a token.
    external_account_id: Mapped[str | None] = mapped_column(String(255))
    # Non-secret metadata only. Do NOT store credentials here.
    config: Mapped[dict | None] = mapped_column(JSONType)
    connected_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("user_profiles.id", ondelete="SET NULL")
    )
