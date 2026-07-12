import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AlertIngest(BaseModel):
    source: str = Field(
        ..., description="Monitoring tool that fired the alert (e.g. datadog, pagerduty)."
    )
    title: str
    description: str | None = None
    fired_at: datetime | None = None
    raw_payload: dict | None = Field(
        default=None,
        description="Non-secret alert metadata: service, alert_type, environment, region, etc.",
    )


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    incident_id: uuid.UUID | None
    source: str
    title: str
    status: str
    correlation_key: str | None
    correlation_confidence: float | None
    fired_at: datetime | None


class CorrelationResultOut(BaseModel):
    alert: AlertOut
    incident_id: uuid.UUID
    confidence: float
    method: str
    created_incident: bool
