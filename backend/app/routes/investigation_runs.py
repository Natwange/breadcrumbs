import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.roles import CAN_READ, CAN_WRITE_CONTENT
from app.deps import CurrentOrganization, DbSession, require_org_role
from app.models import Incident, InvestigationRun
from app.schemas.resources import InvestigationRunCreate, InvestigationRunOut

router = APIRouter(prefix="/investigation-runs", tags=["investigation-runs"])

_read = require_org_role(*CAN_READ)
_write = require_org_role(*CAN_WRITE_CONTENT)


@router.get("", response_model=list[InvestigationRunOut])
def list_runs(
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_read)],
) -> list[InvestigationRun]:
    stmt = (
        select(InvestigationRun)
        .where(InvestigationRun.organization_id == organization.id)
        .order_by(InvestigationRun.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("", response_model=InvestigationRunOut, status_code=status.HTTP_201_CREATED)
def create_run(
    payload: InvestigationRunCreate,
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_write)],
) -> InvestigationRun:
    if payload.incident_id is not None:
        incident = db.scalar(
            select(Incident).where(
                Incident.id == payload.incident_id,
                Incident.organization_id == organization.id,
            )
        )
        if incident is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found"
            )

    run = InvestigationRun(
        organization_id=organization.id,
        incident_id=payload.incident_id,
        trigger=payload.trigger,
        summary=payload.summary,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.get("/{run_id}", response_model=InvestigationRunOut)
def get_run(
    run_id: uuid.UUID,
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_read)],
) -> InvestigationRun:
    run = db.scalar(
        select(InvestigationRun).where(
            InvestigationRun.id == run_id,
            InvestigationRun.organization_id == organization.id,
        )
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return run
