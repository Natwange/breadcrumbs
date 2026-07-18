"""Low-level vector similarity search over stored embeddings.

Similarity is computed with cosine distance in Python over embeddings stored as
JSON arrays, which keeps the implementation portable across Supabase Postgres
(where a pgvector column can back this later) and the SQLite test database.

Cross-organization isolation is enforced unconditionally: every query filters
``EmbeddingRecord.organization_id`` and a caller can never search another org's
memory.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EmbeddingRecord


@dataclass
class SearchHit:
    record: EmbeddingRecord
    score: float


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b, strict=False):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


class VectorSearch:
    def search(
        self,
        db: Session,
        organization_id: uuid.UUID,
        query_embedding: list[float],
        *,
        source_types: list[str] | None = None,
        limit: int = 5,
        min_score: float = 0.0,
        exclude_source_ids: set[uuid.UUID] | None = None,
    ) -> list[SearchHit]:
        if organization_id is None:
            raise ValueError("organization_id is required for vector search")
        if not query_embedding:
            return []

        stmt = select(EmbeddingRecord).where(
            EmbeddingRecord.organization_id == organization_id,
            EmbeddingRecord.embedding.is_not(None),
        )
        if source_types:
            stmt = stmt.where(EmbeddingRecord.source_type.in_(source_types))

        excluded = exclude_source_ids or set()
        hits: list[SearchHit] = []
        for record in db.scalars(stmt).all():
            if record.source_id is not None and record.source_id in excluded:
                continue
            score = cosine_similarity(query_embedding, record.embedding or [])
            if score < min_score:
                continue
            hits.append(SearchHit(record=record, score=score))

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]
