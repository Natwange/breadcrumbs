"""Phase 11 integrations API: list connections and test real providers.

Credentials never cross this boundary. The test endpoints report only a
boolean success and a non-secret detail string.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.roles import CAN_MANAGE_ORG, CAN_READ
from app.deps import CurrentOrganization, DbSession, require_org_role
from app.schemas.integrations import (
    IntegrationsListOut,
    IntegrationTestOut,
    ProviderStatusOut,
)
from app.schemas.resources import IntegrationConnectionOut
from app.services.integrations.integration_service import IntegrationService

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

_read = require_org_role(*CAN_READ)
_manage = require_org_role(*CAN_MANAGE_ORG)


def get_integration_service() -> IntegrationService:
    return IntegrationService()


IntegrationServiceDep = Annotated[IntegrationService, Depends(get_integration_service)]


@router.get("", response_model=IntegrationsListOut)
def list_integrations(
    organization: CurrentOrganization,
    db: DbSession,
    service: IntegrationServiceDep,
    _membership: Annotated[object, Depends(_read)],
) -> IntegrationsListOut:
    connections = service.list_connections(db, organization.id)
    return IntegrationsListOut(
        connections=[IntegrationConnectionOut.model_validate(c) for c in connections],
        providers=[ProviderStatusOut(**p) for p in service.provider_status()],
    )


@router.post("/github/test", response_model=IntegrationTestOut)
def test_github_integration(
    service: IntegrationServiceDep,
    _membership: Annotated[object, Depends(_manage)],
) -> IntegrationTestOut:
    return IntegrationTestOut(**service.test_github())


@router.post("/render/test", response_model=IntegrationTestOut)
def test_render_integration(
    service: IntegrationServiceDep,
    _membership: Annotated[object, Depends(_manage)],
) -> IntegrationTestOut:
    return IntegrationTestOut(**service.test_render())
