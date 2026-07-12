"""Ingest knowledge artifacts with secret redaction."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import KnowledgeArtifact, KnowledgeGraphProposal
from app.services.knowledge_builder.architecture_extractor import ArchitectureExtractor
from app.services.knowledge_builder.drift_detector import DriftDetector
from app.services.knowledge_builder.knowledge_validation import validate_extraction
from app.services.knowledge_builder.secret_redactor import redact_secrets


class ArtifactIngestor:
    """Ingest, redact, extract, and propose graph updates from an artifact."""

    def __init__(
        self,
        extractor: ArchitectureExtractor | None = None,
        drift_detector: DriftDetector | None = None,
    ) -> None:
        self._extractor = extractor or ArchitectureExtractor()
        self._drift = drift_detector or DriftDetector()

    def ingest(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        title: str,
        artifact_type: str,
        content: str,
        source: str | None = None,
        proposed_by: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> tuple[KnowledgeArtifact, KnowledgeGraphProposal | None]:
        redaction = redact_secrets(content)

        artifact = KnowledgeArtifact(
            organization_id=organization_id,
            title=title,
            artifact_type=artifact_type,
            source=source,
            content=redaction.redacted_text,
            metadata_={
                **(metadata or {}),
                "redaction_count": redaction.redaction_count,
                "original_length": len(content),
            },
        )
        db.add(artifact)
        db.flush()

        proposal = self._build_proposal(
            db,
            organization_id=organization_id,
            artifact=artifact,
            artifact_type=artifact_type,
            content=redaction.redacted_text,
            proposed_by=proposed_by,
        )

        db.commit()
        db.refresh(artifact)
        if proposal is not None:
            db.refresh(proposal)
        return artifact, proposal

    def build_from_artifact(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        artifact_id: uuid.UUID,
        proposed_by: uuid.UUID | None = None,
    ) -> KnowledgeGraphProposal | None:
        artifact = db.get(KnowledgeArtifact, artifact_id)
        if artifact is None or artifact.organization_id != organization_id:
            raise LookupError("Artifact not found")

        proposal = self._build_proposal(
            db,
            organization_id=organization_id,
            artifact=artifact,
            artifact_type=artifact.artifact_type,
            content=artifact.content or "",
            proposed_by=proposed_by,
        )
        db.commit()
        if proposal is not None:
            db.refresh(proposal)
        return proposal

    def _build_proposal(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        artifact: KnowledgeArtifact,
        artifact_type: str,
        content: str,
        proposed_by: uuid.UUID | None,
    ) -> KnowledgeGraphProposal | None:
        extraction = self._extractor.extract(artifact_type, content)
        if not extraction.services and not extraction.dependencies and not extraction.runbooks:
            return None

        payload = extraction.to_payload()
        drift = self._drift.detect(db, organization_id, payload)
        payload["drift"] = [d.to_dict() for d in drift]

        validation = validate_extraction(payload)
        if not validation.valid:
            payload["validation_errors"] = validation.errors

        proposal = KnowledgeGraphProposal(
            organization_id=organization_id,
            proposal_type="architecture_extraction",
            status="pending",
            payload=payload,
            confidence=extraction.confidence,
            proposed_by=proposed_by,
        )
        db.add(proposal)
        db.flush()

        meta = dict(artifact.metadata_ or {})
        meta["last_proposal_id"] = str(proposal.id)
        artifact.metadata_ = meta
        return proposal
