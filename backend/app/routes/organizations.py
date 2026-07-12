"""Organization tenancy routes: settings, members, invitations."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.roles import CAN_MANAGE_ORG, CAN_READ, ROLE_OWNER
from app.deps import (
    CurrentOrganization,
    CurrentUser,
    DbSession,
    require_org_role,
)
from app.schemas.organizations import (
    InvitationCreate,
    InvitationOut,
    MemberRoleUpdate,
    OrganizationMemberOut,
    OrganizationSettingsOut,
    OrganizationSettingsUpdate,
)
from app.services import organizations as org_service

router = APIRouter(prefix="/organizations", tags=["organizations"])

_manage = require_org_role(*CAN_MANAGE_ORG)
_read = require_org_role(*CAN_READ)
_owner = require_org_role(ROLE_OWNER)


@router.get("/settings", response_model=OrganizationSettingsOut)
def get_settings(
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_read)],
) -> OrganizationSettingsOut:
    return org_service.get_or_create_settings(db, organization.id)


@router.patch("/settings", response_model=OrganizationSettingsOut)
def update_settings(
    payload: OrganizationSettingsUpdate,
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_manage)],
) -> OrganizationSettingsOut:
    return org_service.update_settings(
        db,
        organization.id,
        timezone=payload.timezone,
        default_severity=payload.default_severity,
        preferences=payload.preferences,
        notes=payload.notes,
    )


@router.get("/members", response_model=list[OrganizationMemberOut])
def list_members(
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_read)],
) -> list[OrganizationMemberOut]:
    return org_service.list_members(db, organization.id)


@router.patch("/members/{member_id}/role", response_model=OrganizationMemberOut)
def update_member_role(
    member_id: uuid.UUID,
    payload: MemberRoleUpdate,
    organization: CurrentOrganization,
    user: CurrentUser,
    db: DbSession,
    _membership: Annotated[object, Depends(_manage)],
) -> OrganizationMemberOut:
    try:
        return org_service.change_member_role(
            db,
            organization_id=organization.id,
            member_id=member_id,
            new_role=payload.role,
            actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/members/{member_id}", response_model=OrganizationMemberOut)
def remove_member(
    member_id: uuid.UUID,
    organization: CurrentOrganization,
    user: CurrentUser,
    db: DbSession,
    _membership: Annotated[object, Depends(_manage)],
) -> OrganizationMemberOut:
    try:
        return org_service.remove_member(
            db,
            organization_id=organization.id,
            member_id=member_id,
            actor_id=user.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/invitations", response_model=InvitationOut, status_code=status.HTTP_201_CREATED)
def create_invitation(
    payload: InvitationCreate,
    organization: CurrentOrganization,
    user: CurrentUser,
    db: DbSession,
    _membership: Annotated[object, Depends(_manage)],
) -> InvitationOut:
    try:
        return org_service.create_invitation(
            db,
            organization_id=organization.id,
            email=payload.email,
            role=payload.role,
            invited_by=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/invitations", response_model=list[InvitationOut])
def list_invitations(
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_manage)],
) -> list[InvitationOut]:
    return org_service.list_invitations(db, organization.id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(
    organization: CurrentOrganization,
    user: CurrentUser,
    db: DbSession,
    _membership: Annotated[object, Depends(_owner)],
) -> None:
    org_service.soft_delete_organization(db, organization, actor_id=user.id)
