import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.roles import CAN_MANAGE_ORG, CAN_READ, CAN_WRITE_CONTENT
from app.deps import CurrentOrganization, CurrentUser, DbSession, require_org_role
from app.models import KnowledgeArtifact, KnowledgeGraphProposal
from app.schemas.proposals import ProposalCreate, ProposalOut
from app.schemas.resources import KnowledgeArtifactCreate, KnowledgeArtifactOut

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

_read = require_org_role(*CAN_READ)
_write = require_org_role(*CAN_WRITE_CONTENT)
_manage = require_org_role(*CAN_MANAGE_ORG)


@router.get("", response_model=list[KnowledgeArtifactOut])
def list_artifacts(
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_read)],
) -> list[KnowledgeArtifact]:
    stmt = (
        select(KnowledgeArtifact)
        .where(KnowledgeArtifact.organization_id == organization.id)
        .order_by(KnowledgeArtifact.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("", response_model=KnowledgeArtifactOut, status_code=status.HTTP_201_CREATED)
def create_artifact(
    payload: KnowledgeArtifactCreate,
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_write)],
) -> KnowledgeArtifact:
    artifact = KnowledgeArtifact(
        organization_id=organization.id,
        title=payload.title,
        artifact_type=payload.artifact_type,
        source=payload.source,
        content=payload.content,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


@router.get("/{artifact_id}", response_model=KnowledgeArtifactOut)
def get_artifact(
    artifact_id: uuid.UUID,
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_read)],
) -> KnowledgeArtifact:
    artifact = db.scalar(
        select(KnowledgeArtifact).where(
            KnowledgeArtifact.id == artifact_id,
            KnowledgeArtifact.organization_id == organization.id,
        )
    )
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return artifact


@router.post("/proposals", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
def create_proposal(
    payload: ProposalCreate,
    organization: CurrentOrganization,
    user: CurrentUser,
    db: DbSession,
    _membership: Annotated[object, Depends(_write)],
) -> KnowledgeGraphProposal:
    proposal = KnowledgeGraphProposal(
        organization_id=organization.id,
        proposal_type=payload.proposal_type,
        status="pending",
        payload=payload.payload,
        confidence=payload.confidence,
        proposed_by=user.id,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


@router.post("/proposals/{proposal_id}/approve", response_model=ProposalOut)
def approve_proposal(
    proposal_id: uuid.UUID,
    organization: CurrentOrganization,
    user: CurrentUser,
    db: DbSession,
    _membership: Annotated[object, Depends(_manage)],
) -> KnowledgeGraphProposal:
    proposal = db.scalar(
        select(KnowledgeGraphProposal).where(
            KnowledgeGraphProposal.id == proposal_id,
            KnowledgeGraphProposal.organization_id == organization.id,
        )
    )
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if proposal.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Proposal is not pending"
        )
    proposal.status = "approved"
    proposal.reviewed_by = user.id
    db.commit()
    db.refresh(proposal)
    return proposal
