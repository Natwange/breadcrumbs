"""Organization role constants and permission groupings.

Roles
-----
owner   Full control, including destructive org actions.
admin   Manage integrations, members, invitations, and approvals.
member  Create incidents, run investigations, upload artifacts.
viewer  Read-only access to org resources.
"""

from typing import Final

ROLE_OWNER: Final = "owner"
ROLE_ADMIN: Final = "admin"
ROLE_MEMBER: Final = "member"
ROLE_VIEWER: Final = "viewer"

ALL_ROLES: frozenset[str] = frozenset(
    {ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER, ROLE_VIEWER}
)

# Can create incidents, investigations, and knowledge artifacts.
CAN_WRITE_CONTENT: frozenset[str] = frozenset(
    {ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER}
)

# Can manage integrations, invite members, and approve proposals/actions.
CAN_MANAGE_ORG: frozenset[str] = frozenset({ROLE_OWNER, ROLE_ADMIN})

# Any active member (including read-only viewers).
CAN_READ: frozenset[str] = ALL_ROLES
