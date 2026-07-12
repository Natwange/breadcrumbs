import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.roles import CAN_READ, CAN_WRITE_CONTENT
from app.deps import CurrentOrganization, DbSession, require_org_role
from app.models import Incident
from app.schemas.resources import IncidentCreate, IncidentOut

router = APIRouter(prefix="/incidents", tags=["incidents"])

_read = require_org_role(*CAN_READ)
_write = require_org_role(*CAN_WRITE_CONTENT)


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_read)],
) -> list[Incident]:
    stmt = (
        select(Incident)
        .where(Incident.organization_id == organization.id)
        .order_by(Incident.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("", response_model=IncidentOut, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreate,
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_write)],
) -> Incident:
    incident = Incident(
        organization_id=organization.id,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        status=payload.status,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(
    incident_id: uuid.UUID,
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_read)],
) -> Incident:
    incident = db.scalar(
        select(Incident).where(
            Incident.id == incident_id,
            Incident.organization_id == organization.id,
        )
    )
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return incident
