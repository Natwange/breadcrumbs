"""Produce embedding vectors for organizational memory.

The default embedder is a deterministic, dependency-free hashing model. It maps
token counts into a fixed-dimension vector and L2-normalizes the result, so that
texts sharing vocabulary land close together under cosine similarity. This keeps
the whole pipeline reproducible and offline; a real embedding provider can be
swapped in behind the same interface.
"""

from __future__ import annotations

import hashlib
import math
import re

from app.core.config import get_settings

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _stable_hash(*parts: str) -> int:
    """Process-stable hash (built-in ``hash`` is salted per run)."""
    digest = hashlib.blake2b("\x1f".join(parts).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


class EmbeddingService:
    def __init__(
        self,
        *,
        model: str | None = None,
        version: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        settings = get_settings()
        self.model = model or settings.embedding_model
        self.version = version or settings.embedding_version
        self.dimensions = dimensions or settings.embedding_dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = _tokenize(text or "")
        if not tokens:
            return vector

        for token in tokens:
            # Two independent stable hashes: one for the bucket, one for sign.
            bucket = _stable_hash(self.version, token) % self.dimensions
            sign = 1.0 if _stable_hash(self.version, "sign", token) % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0.0:
            return vector
        return [v / norm for v in vector]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]
