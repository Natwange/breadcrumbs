import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentOrganization, DbSession
from app.models import KnowledgeArtifact
from app.schemas.resources import KnowledgeArtifactCreate, KnowledgeArtifactOut

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("", response_model=list[KnowledgeArtifactOut])
def list_artifacts(
    organization: CurrentOrganization, db: DbSession
) -> list[KnowledgeArtifact]:
    stmt = (
        select(KnowledgeArtifact)
        .where(KnowledgeArtifact.organization_id == organization.id)
        .order_by(KnowledgeArtifact.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("", response_model=KnowledgeArtifactOut, status_code=status.HTTP_201_CREATED)
def create_artifact(
    payload: KnowledgeArtifactCreate, organization: CurrentOrganization, db: DbSession
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
    artifact_id: uuid.UUID, organization: CurrentOrganization, db: DbSession
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
