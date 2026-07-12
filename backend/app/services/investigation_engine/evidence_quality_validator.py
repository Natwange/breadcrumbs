"""Validate normalized evidence before persistence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationResult:
    valid: bool
    reason: str | None = None


class EvidenceQualityValidator:
    _MIN_CONTENT_LEN = 8

    def validate(self, evidence: dict) -> ValidationResult:
        title = (evidence.get("title") or "").strip()
        content = (evidence.get("content") or "").strip()
        source = (evidence.get("source") or "").strip()
        evidence_type = (evidence.get("evidence_type") or "").strip()

        if not source:
            return ValidationResult(False, "missing source")
        if not evidence_type:
            return ValidationResult(False, "missing evidence_type")
        if not title:
            return ValidationResult(False, "missing title")
        if len(content) < self._MIN_CONTENT_LEN:
            return ValidationResult(False, "content too short")

        return ValidationResult(True)
