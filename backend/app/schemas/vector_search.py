"""Schemas for the vector search / organizational memory API."""

from __future__ import annotations

from pydantic import BaseModel


class EmbeddingBackfillResponse(BaseModel):
    embedded: int
    skipped: int
    rejected: int
    by_type: dict[str, int]
