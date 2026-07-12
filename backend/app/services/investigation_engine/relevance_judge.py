"""Assign simple non-AI relevance labels to evidence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RelevanceLabel:
    score: float
    label: str
    reason: str


_HIGH_TYPES = frozenset({"error_log", "metric_spike", "deploy"})
_MEDIUM_TYPES = frozenset({"provider_status", "trace"})


class RelevanceJudge:
    def judge(self, evidence: dict, *, affected_service: str | None) -> RelevanceLabel:
        evidence_type = (evidence.get("evidence_type") or "").lower()
        title = (evidence.get("title") or "").lower()
        content = (evidence.get("content") or "").lower()
        text = f"{title} {content}"

        if affected_service and affected_service.lower() in text:
            return RelevanceLabel(
                score=0.9,
                label="high",
                reason=f"Mentions affected service {affected_service}",
            )

        if evidence_type in _HIGH_TYPES:
            return RelevanceLabel(
                score=0.75,
                label="high",
                reason=f"Evidence type {evidence_type} is typically incident-critical",
            )

        if evidence_type in _MEDIUM_TYPES:
            return RelevanceLabel(
                score=0.5,
                label="medium",
                reason=f"Evidence type {evidence_type} provides supporting context",
            )

        return RelevanceLabel(
            score=0.25,
            label="low",
            reason="Peripheral evidence with weak incident signal",
        )
