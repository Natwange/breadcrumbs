from fastapi import APIRouter

from app.deps import CurrentOrganization, CurrentUser
from app.schemas.auth import CurrentUserOut, OrganizationOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=CurrentUserOut)
def read_current_user(user: CurrentUser, organization: CurrentOrganization) -> CurrentUserOut:
    """Return the authenticated user and their active organization.

    On first call for a new user this also provisions a default organization
    and an owner membership (handled by ``get_current_user``).
    """
    return CurrentUserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        organization=OrganizationOut.model_validate(organization),
    )
