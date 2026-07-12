"""Minimal request/response schemas for the Phase 3 protected resources.

These endpoints exist to demonstrate authenticated, organization-scoped access.
Richer schemas are added in later phases. Note that ``organization_id`` is
deliberately absent from every create schema: it is always derived server-side
from the authenticated context, never accepted from the client.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IncidentCreate(BaseModel):
    title: str
    description: str | None = None
    severity: str | None = None
    status: str = "open"


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    description: str | None
    status: str
    severity: str | None
    created_at: datetime


class KnowledgeArtifactCreate(BaseModel):
    title: str
    artifact_type: str
    source: str | None = None
    content: str | None = None


class KnowledgeArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    artifact_type: str
    source: str | None
    created_at: datetime


class InvestigationRunCreate(BaseModel):
    incident_id: uuid.UUID | None = None
    trigger: str | None = None
    summary: str | None = None


class InvestigationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    incident_id: uuid.UUID | None
    status: str
    trigger: str | None
    created_at: datetime


class IntegrationConnectionCreate(BaseModel):
    provider: str
    name: str | None = None
    external_account_id: str | None = None
    config: dict | None = None


class IntegrationConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    provider: str
    name: str | None
    status: str
    created_at: datetime
