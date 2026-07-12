"""Schemas for the investigation engine API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InvestigationRunStartOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    incident_id: uuid.UUID | None
    status: str
    trigger: str | None
    summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    evidence_count: int = 0
    timeline_count: int = 0


class InvestigationPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    steps: dict | None


class HypothesisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    status: str
    confidence: float | None


class SlackDraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    channel: str | None
    content: str | None
    status: str


class InvestigationRunDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    incident_id: uuid.UUID | None
    status: str
    trigger: str | None
    summary: str | None
    started_at: datetime | None
    completed_at: datetime | None
    plan: InvestigationPlanOut | None = None
    evidence_count: int = 0
    timeline_count: int = 0
    hypothesis: HypothesisOut | None = None
    slack_draft: SlackDraftOut | None = None
    relevance_tracking: dict | None = None
    executive_summary: str | None = None
    reasoning_status: str | None = None
    reasoning_tracking: dict | None = None


DemoAlertSource = Literal["datadog", "render", "new_relic", "manual_demo"]


class AlertIngestRequest(BaseModel):
    source: DemoAlertSource = Field(
        ..., description="Alert source: datadog, render, new_relic, or manual_demo."
    )
    title: str
    description: str | None = None
    fired_at: datetime | None = None
    raw_payload: dict | None = Field(
        default=None,
        description="Source-specific metadata (service, alert_type, environment, etc.).",
    )


class AlertIngestResponse(BaseModel):
    alert_id: uuid.UUID
    incident_id: uuid.UUID
