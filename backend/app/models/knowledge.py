"""Knowledge graph, service topology, and runbook models."""

import uuid

from sqlalchemy import Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    OrganizationScopedMixin,
    TimestampMixin,
    UUIDMixin,
)
from app.db.types import GUID, JSONType


class KnowledgeArtifact(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_artifacts"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONType)


class ServiceNode(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "service_nodes"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_service_node_name"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    service_type: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    owner_team: Mapped[str | None] = mapped_column(String(255))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONType)


class ServiceDependency(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "service_dependencies"
    __table_args__ = (
        UniqueConstraint(
            "upstream_service_id",
            "downstream_service_id",
            name="uq_service_dependency",
        ),
    )

    upstream_service_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("service_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    downstream_service_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("service_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dependency_type: Mapped[str | None] = mapped_column(String(100))


class KnowledgeGraphProposal(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_graph_proposals"

    proposal_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONType)
    confidence: Mapped[float | None] = mapped_column(Float)
    proposed_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("user_profiles.id", ondelete="SET NULL")
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("user_profiles.id", ondelete="SET NULL")
    )


class Runbook(UUIDMixin, OrganizationScopedMixin, TimestampMixin, Base):
    __tablename__ = "runbooks"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("service_nodes.id", ondelete="SET NULL"), index=True
    )
    tags: Mapped[dict | None] = mapped_column(JSONType)
