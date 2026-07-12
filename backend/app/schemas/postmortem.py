"""Schemas for postmortem API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PostmortemGenerateRequest(BaseModel):
    resolution_notes: str | None = Field(
        default=None,
        description="Optional resolution notes from the responder.",
    )


class PostmortemSectionsOut(BaseModel):
    summary: str
    impact: str
    timeline: list[dict]
    root_cause: dict
    resolution: str
    prevention_items: list[dict]
    incident_duration_minutes: int | None = None
    postmortem_source: str
    assumptions: list[str] = []


class PostmortemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    incident_id: uuid.UUID
    investigation_run_id: uuid.UUID | None
    title: str
    content: str | None
    sections: dict | None = Field(
        default=None,
        validation_alias="sections_",
        serialization_alias="sections",
    )
    status: str
    postmortem_source: str
    incident_duration_minutes: int | None
    created_at: datetime


class PostmortemGenerateResponse(BaseModel):
    postmortem: PostmortemOut
    tracking: dict | None = None
