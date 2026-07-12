"""Embedding / organizational memory API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.roles import CAN_MANAGE_ORG
from app.deps import CurrentOrganization, DbSession, require_org_role
from app.schemas.vector_search import EmbeddingBackfillResponse
from app.services.vector_search.embedding_queue import EmbeddingQueue

router = APIRouter(prefix="/api/embeddings", tags=["vector-search"])

_manage = require_org_role(*CAN_MANAGE_ORG)

_queue = EmbeddingQueue()


@router.post(
    "/backfill",
    response_model=EmbeddingBackfillResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def backfill_embeddings(
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_manage)],
) -> EmbeddingBackfillResponse:
    """Embed all embeddable organizational memory (runbooks, postmortems,
    knowledge artifacts, resolved incidents). Idempotent per object."""
    summary = _queue.backfill_organization(db, organization.id)
    return EmbeddingBackfillResponse(
        embedded=summary.embedded,
        skipped=summary.skipped,
        rejected=summary.rejected,
        by_type=summary.by_type,
    )
