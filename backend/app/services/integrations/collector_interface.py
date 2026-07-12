"""Shared collector interface for fake and real evidence collectors.

Every collector — fake or real — implements the same ``collect(...)`` method
and returns a list of raw evidence dicts. The investigation engine treats all
collectors identically; it never needs to know whether the evidence came from a
canned fixture or a live GitHub/Render API call.

Raw evidence dict shape (before normalization/validation):

    {
        "source": str,          # e.g. "github", "render"
        "evidence_type": str,   # e.g. "commit", "pull_request", "deploy"
        "title": str,
        "content": str,         # secret-redacted human-readable body
        "observed_at": str,     # ISO-8601 timestamp (optional)
        "metadata": dict,       # structured, non-secret details
    }
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Collector(Protocol):
    """Uniform collector contract used across the investigation engine."""

    name: str

    def collect(
        self,
        service_name: str,
        start_time: datetime,
        end_time: datetime,
        alert_context: dict,
    ) -> list[dict]:
        ...


class CollectorError(RuntimeError):
    """Raised when a real collector cannot gather evidence.

    The investigation runner catches this per-collector so one provider outage
    never fails the whole run.
    """
