"""Build and persist embeddings for embeddable organizational memory.

Only durable knowledge is embedded: runbooks, postmortems, knowledge artifacts,
and resolved incidents. Live telemetry (logs, metrics, evidence, timeline
events) is never embedded. Text is always redacted before it is embedded or
stored.

Embedding is idempotent per object via a content hash: unchanged content is
skipped, changed content updates the existing record in place.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    EmbeddingRecord,
    Incident,
    KnowledgeArtifact,
    Postmortem,
    Runbook,
)
from app.services.vector_search.embedding_service import EmbeddingService
from app.services.vector_search.embedding_validator import EmbeddingValidator
from app.services.vector_search.object_types import (
    EMBEDDABLE_OBJECT_TYPES,
    OBJECT_TYPE_INCIDENT,
    OBJECT_TYPE_KNOWLEDGE_ARTIFACT,
    OBJECT_TYPE_POSTMORTEM,
    OBJECT_TYPE_RUNBOOK,
)

_RESOLVED_INCIDENT_STATUSES = frozenset({"resolved", "closed"})


@dataclass
class BackfillSummary:
    embedded: int = 0
    skipped: int = 0
    rejected: int = 0
    by_type: dict[str, int] = field(default_factory=dict)


def _content_hash(text: str, model: str, version: str) -> str:
    payload = f"{model}\x1f{version}\x1f{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class EmbeddingQueue:
    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        validator: EmbeddingValidator | None = None,
    ) -> None:
        self._embedder = embedding_service or EmbeddingService()
        self._validator = validator or EmbeddingValidator()

    def embed_object(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        object_type: str,
        object_id: uuid.UUID,
        text: str,
        incident_id: uuid.UUID | None = None,
        metadata: dict | None = None,
    ) -> EmbeddingRecord | None:
        if object_type not in EMBEDDABLE_OBJECT_TYPES:
            raise ValueError(f"Object type '{object_type}' is not embeddable")

        validation = self._validator.validate(text)
        if not validation.is_valid:
            return None

        redacted = validation.redacted_text
        content_hash = _content_hash(redacted, self._embedder.model, self._embedder.version)

        existing = db.scalar(
            select(EmbeddingRecord).where(
                EmbeddingRecord.organization_id == organization_id,
                EmbeddingRecord.source_type == object_type,
                EmbeddingRecord.source_id == object_id,
            )
        )
        if existing is not None and existing.content_hash == content_hash:
            return existing

        vector = self._embedder.embed(redacted)

        if existing is not None:
            existing.embedding = vector
            existing.text_snapshot = redacted
            existing.content_hash = content_hash
            existing.embedding_model = self._embedder.model
            existing.embedding_version = self._embedder.version
            existing.dimensions = self._embedder.dimensions
            existing.incident_id = incident_id
            existing.metadata_ = metadata
            db.flush()
            return existing

        record = EmbeddingRecord(
            organization_id=organization_id,
            source_type=object_type,
            source_id=object_id,
            incident_id=incident_id,
            embedding=vector,
            text_snapshot=redacted,
            content_hash=content_hash,
            embedding_model=self._embedder.model,
            embedding_version=self._embedder.version,
            dimensions=self._embedder.dimensions,
            metadata_=metadata,
        )
        db.add(record)
        db.flush()
        return record

    # -- Typed helpers -------------------------------------------------

    def embed_runbook(self, db: Session, runbook: Runbook) -> EmbeddingRecord | None:
        text = f"{runbook.title}\n{runbook.content or ''}"
        return self.embed_object(
            db,
            organization_id=runbook.organization_id,
            object_type=OBJECT_TYPE_RUNBOOK,
            object_id=runbook.id,
            text=text,
            metadata={"title": runbook.title},
        )

    def embed_postmortem(self, db: Session, postmortem: Postmortem) -> EmbeddingRecord | None:
        text = f"{postmortem.title}\n{postmortem.content or ''}"
        return self.embed_object(
            db,
            organization_id=postmortem.organization_id,
            object_type=OBJECT_TYPE_POSTMORTEM,
            object_id=postmortem.id,
            text=text,
            incident_id=postmortem.incident_id,
            metadata={"title": postmortem.title},
        )

    def embed_knowledge_artifact(
        self, db: Session, artifact: KnowledgeArtifact
    ) -> EmbeddingRecord | None:
        text = f"{artifact.title}\n{artifact.content or ''}"
        return self.embed_object(
            db,
            organization_id=artifact.organization_id,
            object_type=OBJECT_TYPE_KNOWLEDGE_ARTIFACT,
            object_id=artifact.id,
            text=text,
            metadata={"title": artifact.title, "artifact_type": artifact.artifact_type},
        )

    def embed_resolved_incident(
        self, db: Session, incident: Incident
    ) -> EmbeddingRecord | None:
        if incident.status not in _RESOLVED_INCIDENT_STATUSES:
            return None
        text = f"{incident.title}\n{incident.description or ''}"
        return self.embed_object(
            db,
            organization_id=incident.organization_id,
            object_type=OBJECT_TYPE_INCIDENT,
            object_id=incident.id,
            text=text,
            incident_id=incident.id,
            metadata={"title": incident.title, "severity": incident.severity},
        )

    # -- Bulk backfill -------------------------------------------------

    def backfill_organization(
        self, db: Session, organization_id: uuid.UUID
    ) -> BackfillSummary:
        summary = BackfillSummary()

        def _apply(object_type: str, record: EmbeddingRecord | None, eligible: bool = True) -> None:
            if not eligible:
                return
            if record is None:
                summary.rejected += 1
                return
            summary.embedded += 1
            summary.by_type[object_type] = summary.by_type.get(object_type, 0) + 1

        runbooks = db.scalars(
            select(Runbook).where(Runbook.organization_id == organization_id)
        ).all()
        for rb in runbooks:
            _apply(OBJECT_TYPE_RUNBOOK, self.embed_runbook(db, rb))

        postmortems = db.scalars(
            select(Postmortem).where(Postmortem.organization_id == organization_id)
        ).all()
        for pm in postmortems:
            _apply(OBJECT_TYPE_POSTMORTEM, self.embed_postmortem(db, pm))

        artifacts = db.scalars(
            select(KnowledgeArtifact).where(
                KnowledgeArtifact.organization_id == organization_id
            )
        ).all()
        for art in artifacts:
            _apply(OBJECT_TYPE_KNOWLEDGE_ARTIFACT, self.embed_knowledge_artifact(db, art))

        incidents = db.scalars(
            select(Incident).where(
                Incident.organization_id == organization_id,
                Incident.status.in_(tuple(_RESOLVED_INCIDENT_STATUSES)),
            )
        ).all()
        for inc in incidents:
            _apply(OBJECT_TYPE_INCIDENT, self.embed_resolved_incident(db, inc))

        db.commit()
        return summary
