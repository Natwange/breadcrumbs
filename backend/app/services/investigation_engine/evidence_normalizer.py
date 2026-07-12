"""Normalize raw collector output into a consistent evidence shape."""

from __future__ import annotations

from datetime import datetime, timezone


def _parse_observed_at(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


class EvidenceNormalizer:
    def normalize(self, raw: dict) -> dict | None:
        source = str(raw.get("source") or "").strip()
        evidence_type = str(raw.get("evidence_type") or raw.get("type") or "").strip()
        title = str(raw.get("title") or "").strip()
        content = str(raw.get("content") or raw.get("body") or "").strip()

        if not source or not evidence_type:
            return None

        metadata = raw.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            metadata = {"raw": metadata}

        return {
            "source": source,
            "evidence_type": evidence_type,
            "title": title or f"{source} {evidence_type}",
            "content": content,
            "observed_at": _parse_observed_at(raw.get("observed_at") or raw.get("timestamp")),
            "metadata": metadata or {},
        }

    def normalize_many(self, items: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for item in items:
            row = self.normalize(item)
            if row is not None:
                normalized.append(row)
        return normalized
