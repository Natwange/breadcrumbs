"""Alert ingestion API for demo and external monitoring sources."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.roles import CAN_WRITE_CONTENT
from app.deps import CurrentOrganization, DbSession, require_org_role
from app.schemas.investigation_engine import AlertIngestRequest, AlertIngestResponse
from app.services.alert_correlation import AlertCorrelationService, AlertSignal
from app.services.alert_ingest import build_alert_signal_fields, validate_alert_ingest

router = APIRouter(prefix="/api/alerts", tags=["alert-ingest"])

_write = require_org_role(*CAN_WRITE_CONTENT)


@router.post("/ingest", response_model=AlertIngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_alert(
    payload: AlertIngestRequest,
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_write)],
) -> AlertIngestResponse:
    try:
        validate_alert_ingest(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    fields = build_alert_signal_fields(payload)
    signal = AlertSignal.from_payload(
        organization_id=organization.id,
        source=fields["source"],
        title=fields["title"],
        description=fields["description"],
        fired_at=fields["fired_at"],
        raw_payload=fields["raw_payload"],
    )
    result = AlertCorrelationService().ingest(db, signal)
    return AlertIngestResponse(
        alert_id=result.alert.id,
        incident_id=result.incident.id,
    )
