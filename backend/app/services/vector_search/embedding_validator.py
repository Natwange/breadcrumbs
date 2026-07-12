"""Validate and redact text before it is embedded.

Guarantees that no unredacted secret is ever turned into a vector or stored in
``text_snapshot``. Callers must embed the returned ``redacted_text`` only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.knowledge_builder.secret_redactor import (
    contains_likely_secret,
    redact_secrets,
)

_MIN_LEN = 3

# Redaction placeholders like ``[REDACTED]`` can themselves look like a
# key=value secret to the detector, so they are stripped before re-checking.
_PLACEHOLDER_RE = re.compile(r"\[REDACTED[^\]]*\]")


@dataclass
class EmbeddingValidationResult:
    is_valid: bool
    redacted_text: str
    redaction_count: int = 0
    reason: str | None = None


class EmbeddingValidator:
    def validate(self, text: str | None) -> EmbeddingValidationResult:
        if not text or not text.strip():
            return EmbeddingValidationResult(
                is_valid=False, redacted_text="", reason="empty text"
            )

        result = redact_secrets(text)
        redacted = result.redacted_text

        if contains_likely_secret(_PLACEHOLDER_RE.sub("", redacted)):
            # Redaction failed to remove an obvious secret — refuse to embed.
            return EmbeddingValidationResult(
                is_valid=False,
                redacted_text=redacted,
                redaction_count=result.redaction_count,
                reason="unredacted secret detected",
            )

        if len(redacted.strip()) < _MIN_LEN:
            return EmbeddingValidationResult(
                is_valid=False,
                redacted_text=redacted,
                redaction_count=result.redaction_count,
                reason="text too short after redaction",
            )

        return EmbeddingValidationResult(
            is_valid=True,
            redacted_text=redacted,
            redaction_count=result.redaction_count,
        )
