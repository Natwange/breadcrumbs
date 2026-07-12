"""User/organization provisioning on first authenticated request."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import TokenClaims
from app.models import Organization, OrganizationMember, OrganizationSettings, UserProfile
from app.services.audit import AUDIT_ORGANIZATION_CREATED, record_audit

_SLUG_CLEAN = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    slug = _SLUG_CLEAN.sub("-", value.lower()).strip("-")
    return slug or "org"


def _unique_slug(db: Session, base: str) -> str:
    """Return a slug unique across organizations, adding a suffix if needed."""
    candidate = base
    while db.scalar(select(Organization.id).where(Organization.slug == candidate)):
        candidate = f"{base}-{uuid.uuid4().hex[:6]}"
    return candidate


def get_or_provision_user(db: Session, claims: TokenClaims) -> UserProfile:
    """Return the ``UserProfile`` for the token subject, creating it on first
    login along with a default owned ``Organization`` and owner membership.

    The Supabase auth user id (``sub``) is used directly as the ``UserProfile``
    primary key so identities map one-to-one and cannot be spoofed by the
    client (the id comes only from the verified token).
    """
    user_id = uuid.UUID(claims.subject)

    user = db.get(UserProfile, user_id)
    if user is not None:
        return user

    email = claims.email or f"{user_id}@users.noreply.breadcrumbs"

    user = UserProfile(id=user_id, email=email)
    db.add(user)

    local_part = email.split("@", 1)[0]
    org = Organization(
        name=f"{local_part}'s Organization",
        slug=_unique_slug(db, _slugify(local_part)),
        onboarding_status="pending",
    )
    db.add(org)
    db.flush()

    membership = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role="owner",
        status="active",
    )
    db.add(membership)

    settings = OrganizationSettings(organization_id=org.id)
    db.add(settings)

    record_audit(
        db,
        organization_id=org.id,
        action=AUDIT_ORGANIZATION_CREATED,
        actor_id=user.id,
        resource_type="organization",
        resource_id=org.id,
        metadata={"slug": org.slug},
    )

    db.commit()
    db.refresh(user)
    return user
