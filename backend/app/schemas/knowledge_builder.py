"""Schemas for the knowledge builder API."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ArtifactType = Literal[
    "readme",
    "package.json",
    "prisma_schema",
    "openapi",
    "render_metadata",
    "runbook",
    "architecture_notes",
]


class ArtifactIngestRequest(BaseModel):
    title: str
    artifact_type: ArtifactType
    content: str
    source: str | None = None
    metadata: dict[str, Any] | None = None


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    artifact_type: str
    source: str | None
    content: str | None
    created_at: datetime


class ArtifactIngestResponse(BaseModel):
    artifact: ArtifactOut
    proposal_id: uuid.UUID | None = None


class BuildRequest(BaseModel):
    artifact_id: uuid.UUID


class ServiceNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    service_type: str | None
    description: str | None


class GraphDependencyOut(BaseModel):
    id: uuid.UUID
    upstream_service_id: uuid.UUID
    downstream_service_id: uuid.UUID
    upstream_name: str
    downstream_name: str
    dependency_type: str | None


class RunbookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    content: str | None
    service_id: uuid.UUID | None


class KnowledgeGraphOut(BaseModel):
    services: list[ServiceNodeOut]
    dependencies: list[GraphDependencyOut]
    runbooks: list[RunbookOut]


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    proposal_type: str
    status: str
    confidence: float | None
    payload: dict[str, Any] | None
    proposed_by: uuid.UUID | None
    reviewed_by: uuid.UUID | None
    created_at: datetime


class ManualUpdateRequest(BaseModel):
    """Apply a validated payload directly (admin) or re-run drift detection."""

    payload: dict[str, Any]
    apply: bool = False


class ManualUpdateResponse(BaseModel):
    drift: list[dict[str, Any]]
    applied: bool
    result: dict[str, Any] | None = None


class ApplyResultOut(BaseModel):
    services_created: int
    services_updated: int
    dependencies_created: int
    runbooks_created: int
    errors: list[str] = Field(default_factory=list)
