import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.roles import CAN_MANAGE_ORG, CAN_READ
from app.deps import CurrentOrganization, DbSession, require_org_role
from app.models import IntegrationConnection
from app.schemas.resources import (
    IntegrationConnectionCreate,
    IntegrationConnectionOut,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])

_read = require_org_role(*CAN_READ)
_manage = require_org_role(*CAN_MANAGE_ORG)


@router.get("", response_model=list[IntegrationConnectionOut])
def list_integrations(
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_read)],
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
    _membership: Annotated[object, Depends(_manage)],
) -> IntegrationConnection:
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
    connection_id: uuid.UUID,
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_read)],
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
