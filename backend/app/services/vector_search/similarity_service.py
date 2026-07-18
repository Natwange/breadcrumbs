"""Retrieve similar organizational memory for an investigation.

Backs the ``finding_similar_incidents`` step of an investigation run: given an
incident, it searches the organization's embedded memory for similar past
incidents, relevant runbooks, related postmortems, and related knowledge
artifacts, returning a ``SimilarityContext``.

All searches are strictly organization-scoped; memory is never shared across
organizations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Incident
from app.services.vector_search.embedding_service import EmbeddingService
from app.services.vector_search.object_types import (
    OBJECT_TYPE_INCIDENT,
    OBJECT_TYPE_KNOWLEDGE_ARTIFACT,
    OBJECT_TYPE_POSTMORTEM,
    OBJECT_TYPE_RUNBOOK,
)
from app.services.vector_search.vector_search import SearchHit, VectorSearch


@dataclass
class SimilarMatch:
    object_type: str
    object_id: uuid.UUID | None
    score: float
    title: str | None
    snippet: str | None


@dataclass
class SimilarityContext:
    similar_incidents: list[SimilarMatch] = field(default_factory=list)
    relevant_runbooks: list[SimilarMatch] = field(default_factory=list)
    related_postmortems: list[SimilarMatch] = field(default_factory=list)
    related_knowledge_artifacts: list[SimilarMatch] = field(default_factory=list)

    def total(self) -> int:
        return (
            len(self.similar_incidents)
            + len(self.relevant_runbooks)
            + len(self.related_postmortems)
            + len(self.related_knowledge_artifacts)
        )


def _to_match(hit: SearchHit) -> SimilarMatch:
    meta = hit.record.metadata_ or {}
    snippet = (hit.record.text_snapshot or "")[:200] or None
    return SimilarMatch(
        object_type=hit.record.source_type,
        object_id=hit.record.source_id,
        score=round(hit.score, 4),
        title=meta.get("title"),
        snippet=snippet,
    )


class SimilarityService:
    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        vector_search: VectorSearch | None = None,
    ) -> None:
        self._embedder = embedding_service or EmbeddingService()
        self._search = vector_search or VectorSearch()

    def find_for_incident(
        self,
        db: Session,
        organization_id: uuid.UUID,
        incident: Incident,
        *,
        limit: int = 5,
        min_score: float = 0.05,
    ) -> SimilarityContext:
        query_text = self._build_query_text(incident)
        query_embedding = self._embedder.embed(query_text)

        similar_incidents = self._search.search(
            db,
            organization_id,
            query_embedding,
            source_types=[OBJECT_TYPE_INCIDENT],
            limit=limit,
            min_score=min_score,
            exclude_source_ids={incident.id},
        )
        runbooks = self._search.search(
            db,
            organization_id,
            query_embedding,
            source_types=[OBJECT_TYPE_RUNBOOK],
            limit=limit,
            min_score=min_score,
        )
        postmortems = self._search.search(
            db,
            organization_id,
            query_embedding,
            source_types=[OBJECT_TYPE_POSTMORTEM],
            limit=limit,
            min_score=min_score,
        )
        artifacts = self._search.search(
            db,
            organization_id,
            query_embedding,
            source_types=[OBJECT_TYPE_KNOWLEDGE_ARTIFACT],
            limit=limit,
            min_score=min_score,
        )

        return SimilarityContext(
            similar_incidents=[_to_match(h) for h in similar_incidents],
            relevant_runbooks=[_to_match(h) for h in runbooks],
            related_postmortems=[_to_match(h) for h in postmortems],
            related_knowledge_artifacts=[_to_match(h) for h in artifacts],
        )

    def _build_query_text(self, incident: Incident) -> str:
        parts = [incident.title or ""]
        if incident.description:
            parts.append(incident.description)
        meta = incident.metadata_ or {}
        if meta.get("affected_service"):
            parts.append(str(meta["affected_service"]))
        return "\n".join(p for p in parts if p)
