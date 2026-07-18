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


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    evidence_type: str
    title: str | None
    content: str | None
    relevance_score: float | None
    relevance_label: str | None
    relevance_confidence: str | None
    relevance_reason: str | None
    observed_at: datetime | None


class TimelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_time: datetime | None
    title: str
    description: str | None
    source: str | None
    event_type: str | None


class SuggestedActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    action_type: str | None
    status: str
    requires_human_approval: bool


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    title: str
    description: str | None
    status: str
    severity: str | None
    fired_at: datetime | None


class IncidentImpactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    impact_type: str
    description: str | None
    severity: str | None
    affected_services: dict | None
    metrics: dict | None


class IncidentWorkspaceOut(BaseModel):
    """Aggregated incident view for the frontend workspace shell."""

    incident: "IncidentWorkspaceIncidentOut"
    alerts: list[AlertOut]
    runs: list[InvestigationRunStartOut]
    run: InvestigationRunDetailOut | None = None
    evidence: list[EvidenceOut] = []
    timeline: list[TimelineEventOut] = []
    hypotheses: list[HypothesisOut] = []
    suggested_actions: list[SuggestedActionOut] = []
    impacts: list[IncidentImpactOut] = []
    postmortem: "PostmortemSummaryOut | None" = None


class IncidentWorkspaceIncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    status: str
    severity: str | None
    created_at: datetime


class PostmortemSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    title: str
    status: str
    postmortem_source: str
    sections: dict | None = Field(
        default=None,
        validation_alias="sections_",
        serialization_alias="sections",
    )
    created_at: datetime
