"""Schema and validation for Claude evidence-relevance judgments.

Claude returns categorical judgments only — no numeric scores. Each judgment is
strictly validated against this schema; any deviation raises ``RelevanceSchemaError``
so the caller can fall back to deterministic rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

# Bump when the judgment shape or allowed values change.
SCHEMA_VERSION = "1.0"

RELEVANCE_VALUES = frozenset({"high", "medium", "low", "uncertain"})
CONFIDENCE_VALUES = frozenset({"high", "medium", "low"})

RELEVANCE_SOURCE_CLAUDE = "claude"
RELEVANCE_SOURCE_FALLBACK = "rule_based_fallback"


class RelevanceSchemaError(ValueError):
    """Raised when Claude output does not conform to the expected schema."""


@dataclass
class RelevanceJudgment:
    evidence_id: str
    relevance: str
    confidence: str
    reason: str
    source: str = RELEVANCE_SOURCE_CLAUDE

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "relevance": self.relevance,
            "confidence": self.confidence,
            "reason": self.reason,
            "source": self.source,
        }


def _validate_item(item: object, valid_ids: set[str]) -> RelevanceJudgment:
    if not isinstance(item, dict):
        raise RelevanceSchemaError("judgment item is not an object")

    evidence_id = item.get("evidence_id")
    relevance = item.get("relevance")
    confidence = item.get("confidence")
    reason = item.get("reason")

    if not isinstance(evidence_id, str) or evidence_id not in valid_ids:
        raise RelevanceSchemaError(f"unknown or missing evidence_id: {evidence_id!r}")
    if not isinstance(relevance, str) or relevance.lower() not in RELEVANCE_VALUES:
        raise RelevanceSchemaError(f"invalid relevance: {relevance!r}")
    if not isinstance(confidence, str) or confidence.lower() not in CONFIDENCE_VALUES:
        raise RelevanceSchemaError(f"invalid confidence: {confidence!r}")
    if reason is not None and not isinstance(reason, str):
        raise RelevanceSchemaError("reason must be a string")

    return RelevanceJudgment(
        evidence_id=evidence_id,
        relevance=relevance.lower(),
        confidence=confidence.lower(),
        reason=(reason or "").strip()[:2000],
        source=RELEVANCE_SOURCE_CLAUDE,
    )


def parse_judgments(raw: str, valid_ids: set[str]) -> list[RelevanceJudgment]:
    """Parse and validate a raw Claude response into judgments.

    Accepts either a bare JSON list or an object with a ``judgments`` key.
    Raises ``RelevanceSchemaError`` on any malformed or unexpected content.
    """
    if not raw or not raw.strip():
        raise RelevanceSchemaError("empty response")

    text = raw.strip()
    if text.startswith("```"):
        # Strip markdown code fences.
        text = text.lstrip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip().rstrip("`").strip()

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RelevanceSchemaError(f"response is not valid JSON: {exc}") from exc

    if isinstance(parsed, dict) and "judgments" in parsed:
        parsed = parsed["judgments"]
    if not isinstance(parsed, list):
        raise RelevanceSchemaError("expected a JSON list of judgments")

    judgments = [_validate_item(item, valid_ids) for item in parsed]
    if not judgments:
        raise RelevanceSchemaError("no judgments returned")
    return judgments
