"""Audit log helper."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import AuditLog

# Well-known audit actions (Phase 4).
AUDIT_ORGANIZATION_CREATED = "organization_created"
AUDIT_MEMBER_INVITED = "member_invited"
AUDIT_MEMBER_ROLE_CHANGED = "member_role_changed"
AUDIT_MEMBER_REMOVED = "member_removed"
AUDIT_ALERT_CORRELATED = "alert_correlated"


def record_audit(
    db: Session,
    *,
    organization_id: uuid.UUID,
    action: str,
    actor_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_=metadata,
    )
    db.add(entry)
    return entry
