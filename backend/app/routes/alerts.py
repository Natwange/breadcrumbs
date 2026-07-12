"""Alert ingestion with correlation."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.roles import CAN_WRITE_CONTENT
from app.deps import CurrentOrganization, DbSession, require_org_role
from app.schemas.alerts import AlertIngest, AlertOut, CorrelationResultOut
from app.services.alert_correlation import AlertCorrelationService, AlertSignal

router = APIRouter(prefix="/alerts", tags=["alerts"])

_write = require_org_role(*CAN_WRITE_CONTENT)


@router.post("", response_model=CorrelationResultOut, status_code=status.HTTP_201_CREATED)
def ingest_alert(
    payload: AlertIngest,
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_write)],
) -> CorrelationResultOut:
    signal = AlertSignal.from_payload(
        organization_id=organization.id,
        source=payload.source,
        title=payload.title,
        description=payload.description,
        fired_at=payload.fired_at,
        raw_payload=payload.raw_payload,
    )
    result = AlertCorrelationService().ingest(db, signal)
    return CorrelationResultOut(
        alert=AlertOut.model_validate(result.alert),
        incident_id=result.incident.id,
        confidence=result.confidence,
        method=result.method,
        created_incident=result.created_incident,
    )
