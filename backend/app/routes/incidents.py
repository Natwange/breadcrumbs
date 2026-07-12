import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentOrganization, DbSession
from app.models import Incident
from app.schemas.resources import IncidentCreate, IncidentOut

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentOut])
def list_incidents(organization: CurrentOrganization, db: DbSession) -> list[Incident]:
    stmt = (
        select(Incident)
        .where(Incident.organization_id == organization.id)
        .order_by(Incident.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("", response_model=IncidentOut, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreate, organization: CurrentOrganization, db: DbSession
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
    incident_id: uuid.UUID, organization: CurrentOrganization, db: DbSession
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
