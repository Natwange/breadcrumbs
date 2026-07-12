"""Vector embedding bookkeeping.

The raw vector storage strategy (pgvector, external store, etc.) is decided in
a later phase. This model tracks *which* content has been embedded and with
which model/version, so re-embedding and lookups are reproducible.
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    OrganizationScopedMixin,
    TimestampMixin,
    UUIDMixin,
)
from app.db.types import GUID, JSONType


class EmbeddingRecord(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "embedding_records"

    # Polymorphic reference to the embedded source object.
    source_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(GUID, index=True)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("incidents.id", ondelete="SET NULL"), index=True
    )
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(100), nullable=False)
    dimensions: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONType)
