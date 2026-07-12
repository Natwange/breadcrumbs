"""Postmortem generation API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.roles import CAN_WRITE_CONTENT
from app.deps import CurrentOrganization, CurrentUser, DbSession, require_org_role
from app.schemas.postmortem import (
    PostmortemGenerateRequest,
    PostmortemGenerateResponse,
    PostmortemOut,
)
from app.services.postmortem.postmortem_generator import PostmortemGenerator

router = APIRouter(prefix="/api", tags=["postmortem"])

_write = require_org_role(*CAN_WRITE_CONTENT)

_generator = PostmortemGenerator()


@router.post(
    "/incidents/{incident_id}/postmortem",
    response_model=PostmortemGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_postmortem(
    incident_id: uuid.UUID,
    payload: PostmortemGenerateRequest,
    organization: CurrentOrganization,
    user: CurrentUser,
    db: DbSession,
    _membership: Annotated[object, Depends(_write)],
) -> PostmortemGenerateResponse:
    try:
        result = _generator.generate(
            db,
            organization.id,
            incident_id,
            actor_id=user.id,
            resolution_notes=payload.resolution_notes,
        )
    except ValueError as exc:
        msg = str(exc)
        code = (
            status.HTTP_400_BAD_REQUEST
            if "resolved" in msg.lower()
            else status.HTTP_404_NOT_FOUND
        )
        raise HTTPException(status_code=code, detail=msg) from exc

    return PostmortemGenerateResponse(
        postmortem=PostmortemOut.model_validate(result.postmortem),
        tracking=result.tracking,
    )


@router.post(
    "/postmortems/{postmortem_id}/approve",
    response_model=PostmortemOut,
)
def approve_postmortem(
    postmortem_id: uuid.UUID,
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_write)],
) -> PostmortemOut:
    """Approve a draft postmortem and embed it for organizational memory."""
    try:
        postmortem = _generator.approve_and_embed(db, organization.id, postmortem_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PostmortemOut.model_validate(postmortem)
