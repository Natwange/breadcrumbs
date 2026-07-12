"""Knowledge builder API routes (/api/knowledge)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.roles import CAN_MANAGE_ORG, CAN_READ, CAN_WRITE_CONTENT
from app.deps import CurrentOrganization, CurrentUser, DbSession, require_org_role
from app.models import KnowledgeGraphProposal
from app.schemas.knowledge_builder import (
    ApplyResultOut,
    ArtifactIngestRequest,
    ArtifactIngestResponse,
    ArtifactOut,
    BuildRequest,
    GraphDependencyOut,
    KnowledgeGraphOut,
    ManualUpdateRequest,
    ManualUpdateResponse,
    ProposalOut,
    RunbookOut,
    ServiceNodeOut,
)
from app.services.knowledge_builder.artifact_ingestor import ArtifactIngestor
from app.services.knowledge_builder.drift_detector import DriftDetector
from app.services.knowledge_builder.knowledge_graph_service import KnowledgeGraphService
from app.services.knowledge_builder.knowledge_update_service import KnowledgeUpdateService
from app.services.knowledge_builder.knowledge_validation import validate_extraction

router = APIRouter(prefix="/api/knowledge", tags=["knowledge-builder"])

_read = require_org_role(*CAN_READ)
_write = require_org_role(*CAN_WRITE_CONTENT)
_manage = require_org_role(*CAN_MANAGE_ORG)

_ingestor = ArtifactIngestor()
_graph = KnowledgeGraphService()
_updates = KnowledgeUpdateService()
_drift = DriftDetector()


@router.post("/artifacts", response_model=ArtifactIngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_artifact(
    payload: ArtifactIngestRequest,
    organization: CurrentOrganization,
    user: CurrentUser,
    db: DbSession,
    _membership: Annotated[object, Depends(_write)],
) -> ArtifactIngestResponse:
    artifact, proposal = _ingestor.ingest(
        db,
        organization_id=organization.id,
        title=payload.title,
        artifact_type=payload.artifact_type,
        content=payload.content,
        source=payload.source,
        proposed_by=user.id,
        metadata=payload.metadata,
    )
    return ArtifactIngestResponse(
        artifact=ArtifactOut.model_validate(artifact),
        proposal_id=proposal.id if proposal else None,
    )


@router.post("/build", response_model=ProposalOut, status_code=status.HTTP_201_CREATED)
def build_from_artifact(
    payload: BuildRequest,
    organization: CurrentOrganization,
    user: CurrentUser,
    db: DbSession,
    _membership: Annotated[object, Depends(_write)],
) -> KnowledgeGraphProposal:
    try:
        proposal = _ingestor.build_from_artifact(
            db,
            organization_id=organization.id,
            artifact_id=payload.artifact_id,
            proposed_by=user.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No architecture could be extracted from artifact",
        )
    return proposal


@router.get("/graph", response_model=KnowledgeGraphOut)
def get_graph(
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_read)],
) -> KnowledgeGraphOut:
    snapshot = _graph.get_graph(db, organization.id)
    return KnowledgeGraphOut(
        services=[ServiceNodeOut.model_validate(s) for s in snapshot.services],
        dependencies=[
            GraphDependencyOut(
                id=d.id,
                upstream_service_id=d.upstream_service_id,
                downstream_service_id=d.downstream_service_id,
                upstream_name=d.upstream_name,
                downstream_name=d.downstream_name,
                dependency_type=d.dependency_type,
            )
            for d in snapshot.dependencies
        ],
        runbooks=[RunbookOut.model_validate(r) for r in snapshot.runbooks],
    )


@router.get("/proposals", response_model=list[ProposalOut])
def list_proposals(
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_read)],
    status_filter: str | None = None,
) -> list[KnowledgeGraphProposal]:
    stmt = select(KnowledgeGraphProposal).where(
        KnowledgeGraphProposal.organization_id == organization.id
    )
    if status_filter:
        stmt = stmt.where(KnowledgeGraphProposal.status == status_filter)
    stmt = stmt.order_by(KnowledgeGraphProposal.created_at.desc())
    return list(db.scalars(stmt).all())


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

    apply_result = _updates.apply_proposal(db, proposal)
    if apply_result.errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Failed to apply proposal", "errors": apply_result.errors},
        )

    proposal.status = "approved"
    proposal.reviewed_by = user.id
    db.commit()
    db.refresh(proposal)
    return proposal


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalOut)
def reject_proposal(
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

    proposal.status = "rejected"
    proposal.reviewed_by = user.id
    db.commit()
    db.refresh(proposal)
    return proposal


@router.post("/updates", response_model=ManualUpdateResponse)
def knowledge_updates(
    payload: ManualUpdateRequest,
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_manage)],
) -> ManualUpdateResponse:
    validation = validate_extraction(payload.payload)
    if not validation.valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=validation.errors
        )

    drift_items = _drift.detect(db, organization.id, payload.payload)
    drift_payload = [d.to_dict() for d in drift_items]

    result_out: dict | None = None
    if payload.apply:
        apply_result = _updates.apply_payload(db, organization.id, payload.payload)
        if apply_result.errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=apply_result.errors
            )
        db.commit()
        result_out = ApplyResultOut(
            services_created=apply_result.services_created,
            services_updated=apply_result.services_updated,
            dependencies_created=apply_result.dependencies_created,
            runbooks_created=apply_result.runbooks_created,
            errors=apply_result.errors,
        ).model_dump()

    return ManualUpdateResponse(
        drift=drift_payload,
        applied=payload.apply,
        result=result_out,
    )


@router.get("/runbooks", response_model=list[RunbookOut])
def list_runbooks(
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_read)],
) -> list[RunbookOut]:
    snapshot = _graph.get_graph(db, organization.id)
    return [RunbookOut.model_validate(r) for r in snapshot.runbooks]
