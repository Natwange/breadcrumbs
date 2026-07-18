"""FastAPI dependencies for auth and tenant scoping.

Security model
--------------
* The caller's identity comes exclusively from a cryptographically verified
  Supabase JWT (see ``app.core.security``). Nothing about the user is trusted
  from the request body or arbitrary headers.
* ``organization_id`` is NEVER read from the request body. The active
  organization is resolved from the user's verified memberships. An optional
  ``X-Organization-Id`` header may *select* among the user's organizations, but
  it is always validated against membership before use.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

# Re-export role constants for convenience in route modules.
from app.core.roles import (  # noqa: F401
    CAN_MANAGE_ORG,
    CAN_READ,
    CAN_WRITE_CONTENT,
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_VIEWER,
)
from app.core.logging import get_logger
from app.core.security import AuthError, JWTVerifier, TokenClaims, get_verifier
from app.db.session import get_db
from app.models import Organization, OrganizationMember, UserProfile
from app.services.provisioning import get_or_provision_user

logger = get_logger(__name__)

# auto_error=False so we can return a consistent 401 with a WWW-Authenticate
# header rather than FastAPI's default 403 for a missing credential.
_bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_verifier_dep() -> JWTVerifier:
    return get_verifier()


def get_token_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    verifier: Annotated[JWTVerifier, Depends(get_verifier_dep)],
) -> TokenClaims:
    if credentials is None or not credentials.credentials:
        raise _UNAUTHORIZED
    try:
        return verifier.verify(credentials.credentials)
    except AuthError as exc:
        logger.warning("token verification failed: %s", exc)
        raise _UNAUTHORIZED from None


def get_current_user(
    claims: Annotated[TokenClaims, Depends(get_token_claims)],
    db: Annotated[Session, Depends(get_db)],
) -> UserProfile:
    user = get_or_provision_user(db, claims)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled"
        )
    return user


def get_current_organization(
    user: Annotated[UserProfile, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    x_organization_id: Annotated[str | None, Header()] = None,
) -> Organization:
    """Resolve the active organization from the user's verified memberships.

    If ``X-Organization-Id`` is supplied it must correspond to an active
    membership for this user; otherwise the request is rejected. Without the
    header, the user's (first) active membership is used.
    """
    stmt = (
        select(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(
            OrganizationMember.user_id == user.id,
            OrganizationMember.status == "active",
            Organization.deleted_at.is_(None),
        )
    )

    if x_organization_id is not None:
        try:
            requested = uuid.UUID(x_organization_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Organization-Id",
            ) from None
        org = db.scalar(stmt.where(Organization.id == requested))
        if org is None:
            # User is not a member of the requested org: deny (do not leak).
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of the requested organization",
            )
        return org

    org = db.scalars(stmt.order_by(OrganizationMember.created_at.asc())).first()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no active organization",
        )
    return org


def get_current_membership(
    user: Annotated[UserProfile, Depends(get_current_user)],
    organization: Annotated[Organization, Depends(get_current_organization)],
    db: Annotated[Session, Depends(get_db)],
) -> OrganizationMember:
    """Return the caller's active membership in the current organization."""
    membership = db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization.id,
            OrganizationMember.user_id == user.id,
            OrganizationMember.status == "active",
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organization",
        )
    return membership


def require_org_role(*allowed_roles: str):
    """Dependency factory that enforces role-based access within the org.

    Usage::

        @router.post("/incidents")
        def create_incident(
            _membership: Annotated[
                OrganizationMember,
                Depends(require_org_role("owner", "admin", "member")),
            ],
            ...
        ):
    """
    allowed = frozenset(allowed_roles)

    def _check(
        membership: Annotated[OrganizationMember, Depends(get_current_membership)],
    ) -> OrganizationMember:
        if membership.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return membership

    return _check


CurrentUser = Annotated[UserProfile, Depends(get_current_user)]
CurrentOrganization = Annotated[Organization, Depends(get_current_organization)]
CurrentMembership = Annotated[OrganizationMember, Depends(get_current_membership)]
DbSession = Annotated[Session, Depends(get_db)]
