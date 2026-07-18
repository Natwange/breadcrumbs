"""In-process, per-organization sliding-window rate limiting.

Designed for the single-instance demo/staging deployment described in Phase 12.
Limits are keyed by ``(category, organization_id)`` so one org cannot exhaust
the AI budget for another. State is in-memory: it resets on restart and is not
shared across processes/instances (documented as a known limitation — a shared
store like Redis is required for horizontal scaling).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, Request, status
from fastapi.exceptions import HTTPException

from app.core.config import Settings, get_settings
from app.deps import CurrentOrganization


class RateLimiter:
    """Fixed-limit sliding-window counter, safe for threaded servers."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        """Record a hit for ``key``; raise HTTP 429 if over the limit."""
        if limit <= 0:
            return
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(bucket[0] + window_seconds - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please retry shortly.",
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# Module-level singleton shared across requests.
_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _limiter


def _limit_for(settings: Settings, category: str) -> int:
    mapping = {
        "investigation": settings.rate_limit_investigation_per_min,
        "ai": settings.rate_limit_ai_per_min,
        "knowledge_build": settings.rate_limit_knowledge_build_per_min,
        "artifact_upload": settings.rate_limit_artifact_upload_per_min,
        "embedding_backfill": settings.rate_limit_embedding_backfill_per_min,
    }
    return mapping.get(category, 0)


def rate_limit(category: str):
    """Build a dependency enforcing the ``category`` limit for the caller's org.

    The dependency resolves ``CurrentOrganization`` first, so unauthorized
    requests are rejected before any limit is consumed.
    """

    def _dependency(
        request: Request,
        organization: CurrentOrganization,
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> None:
        if not settings.rate_limit_enabled:
            return
        limit = _limit_for(settings, category)
        _limiter.check(
            f"{category}:{organization.id}",
            limit=limit,
            window_seconds=settings.rate_limit_window_seconds,
        )

    return _dependency
