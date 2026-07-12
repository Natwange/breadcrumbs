import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentOrganization, DbSession
from app.models import IntegrationConnection
from app.schemas.resources import (
    IntegrationConnectionCreate,
    IntegrationConnectionOut,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationConnectionOut])
def list_integrations(
    organization: CurrentOrganization, db: DbSession
) -> list[IntegrationConnection]:
    stmt = (
        select(IntegrationConnection)
        .where(IntegrationConnection.organization_id == organization.id)
        .order_by(IntegrationConnection.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post(
    "", response_model=IntegrationConnectionOut, status_code=status.HTTP_201_CREATED
)
def create_integration(
    payload: IntegrationConnectionCreate,
    organization: CurrentOrganization,
    db: DbSession,
) -> IntegrationConnection:
    # SECURITY: ``config`` is non-secret metadata only. Never persist API keys
    # or tokens here; secrets belong in a dedicated secret manager.
    connection = IntegrationConnection(
        organization_id=organization.id,
        provider=payload.provider,
        name=payload.name,
        external_account_id=payload.external_account_id,
        config=payload.config,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


@router.get("/{connection_id}", response_model=IntegrationConnectionOut)
def get_integration(
    connection_id: uuid.UUID, organization: CurrentOrganization, db: DbSession
) -> IntegrationConnection:
    connection = db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.organization_id == organization.id,
        )
    )
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return connection
