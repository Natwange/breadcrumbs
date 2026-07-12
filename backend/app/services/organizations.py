"""Organization tenancy: invitations, settings, members, soft-delete."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.roles import ALL_ROLES, CAN_MANAGE_ORG
from app.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMember,
    OrganizationSettings,
    UserProfile,
)
from app.services.audit import (
    AUDIT_MEMBER_INVITED,
    AUDIT_MEMBER_REMOVED,
    AUDIT_MEMBER_ROLE_CHANGED,
    record_audit,
)

_INVITE_TTL_DAYS = 7


def get_or_create_settings(db: Session, organization_id: uuid.UUID) -> OrganizationSettings:
    settings = db.scalar(
        select(OrganizationSettings).where(
            OrganizationSettings.organization_id == organization_id
        )
    )
    if settings is None:
        settings = OrganizationSettings(organization_id=organization_id)
        db.add(settings)
        db.flush()
    return settings


def update_settings(
    db: Session,
    organization_id: uuid.UUID,
    *,
    timezone: str | None = None,
    default_severity: str | None = None,
    preferences: dict | None = None,
    notes: str | None = None,
) -> OrganizationSettings:
    settings = get_or_create_settings(db, organization_id)
    if timezone is not None:
        settings.timezone = timezone
    if default_severity is not None:
        settings.default_severity = default_severity
    if preferences is not None:
        settings.preferences = preferences
    if notes is not None:
        settings.notes = notes
    db.commit()
    db.refresh(settings)
    return settings


def soft_delete_organization(
    db: Session,
    organization: Organization,
    actor_id: uuid.UUID,
) -> Organization:
    """Mark an organization as deleted without removing rows."""
    organization.deleted_at = datetime.now(tz=timezone.utc)
    record_audit(
        db,
        organization_id=organization.id,
        action="organization_deleted",
        actor_id=actor_id,
        resource_type="organization",
        resource_id=organization.id,
    )
    db.commit()
    db.refresh(organization)
    return organization


def create_invitation(
    db: Session,
    *,
    organization_id: uuid.UUID,
    email: str,
    role: str,
    invited_by: uuid.UUID,
) -> OrganizationInvitation:
    if role not in ALL_ROLES:
        raise ValueError(f"Invalid role: {role}")

    invitation = OrganizationInvitation(
        organization_id=organization_id,
        email=email.lower().strip(),
        role=role,
        status="pending",
        token=secrets.token_urlsafe(32),
        invited_by=invited_by,
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=_INVITE_TTL_DAYS),
    )
    db.add(invitation)
    record_audit(
        db,
        organization_id=organization_id,
        action=AUDIT_MEMBER_INVITED,
        actor_id=invited_by,
        resource_type="organization_invitation",
        resource_id=invitation.id,
        metadata={"email": invitation.email, "role": role},
    )
    db.commit()
    db.refresh(invitation)
    return invitation


def list_invitations(
    db: Session, organization_id: uuid.UUID, *, status: str = "pending"
) -> list[OrganizationInvitation]:
    stmt = (
        select(OrganizationInvitation)
        .where(
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.status == status,
        )
        .order_by(OrganizationInvitation.created_at.desc())
    )
    return list(db.scalars(stmt).all())


def change_member_role(
    db: Session,
    *,
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    new_role: str,
    actor_id: uuid.UUID,
) -> OrganizationMember:
    if new_role not in ALL_ROLES:
        raise ValueError(f"Invalid role: {new_role}")

    member = db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == "active",
        )
    )
    if member is None:
        raise LookupError("Member not found")

    old_role = member.role
    member.role = new_role
    record_audit(
        db,
        organization_id=organization_id,
        action=AUDIT_MEMBER_ROLE_CHANGED,
        actor_id=actor_id,
        resource_type="organization_member",
        resource_id=member.id,
        metadata={"user_id": str(member.user_id), "from": old_role, "to": new_role},
    )
    db.commit()
    db.refresh(member)
    return member


def remove_member(
    db: Session,
    *,
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> OrganizationMember:
    member = db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == "active",
        )
    )
    if member is None:
        raise LookupError("Member not found")

    member.status = "removed"
    record_audit(
        db,
        organization_id=organization_id,
        action=AUDIT_MEMBER_REMOVED,
        actor_id=actor_id,
        resource_type="organization_member",
        resource_id=member.id,
        metadata={"user_id": str(member.user_id), "role": member.role},
    )
    db.commit()
    db.refresh(member)
    return member


def list_members(db: Session, organization_id: uuid.UUID) -> list[OrganizationMember]:
    stmt = (
        select(OrganizationMember)
        .where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == "active",
        )
        .order_by(OrganizationMember.created_at.asc())
    )
    return list(db.scalars(stmt).all())
