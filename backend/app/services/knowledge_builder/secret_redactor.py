"""Redact secrets from artifact text before persistence.

Only redacted text may be stored. Patterns cover common credential formats
found in READMEs, env examples, package configs, and infrastructure metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (pattern, replacement label)
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\"]{8,})"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-._~+/]+=*"), "Bearer [REDACTED]"),
    (re.compile(r"postgresql(?:\+psycopg2)?://[^\s]+"), "postgresql://[REDACTED]"),
    (re.compile(r"mongodb(?:\+srv)?://[^\s]+"), "mongodb://[REDACTED]"),
    (re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"(?i)ANTHROPIC_API_KEY\s*=\s*[^\s]+"), "ANTHROPIC_API_KEY=[REDACTED]"),
    (re.compile(r"(?i)SUPABASE_(?:ANON|SERVICE_ROLE)_KEY\s*=\s*[^\s]+"), r"SUPABASE_KEY=[REDACTED]"),
    (re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC )?PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
]


@dataclass
class RedactionResult:
    redacted_text: str
    redaction_count: int


def redact_secrets(text: str) -> RedactionResult:
    """Return text with secrets replaced by placeholders."""
    if not text:
        return RedactionResult(redacted_text=text, redaction_count=0)

    redacted = text
    count = 0
    for pattern, replacement in _PATTERNS:
        redacted, n = pattern.subn(replacement, redacted)
        count += n
    return RedactionResult(redacted_text=redacted, redaction_count=count)


def contains_likely_secret(text: str) -> bool:
    """Heuristic check that redaction removed obvious secrets."""
    if not text:
        return False
    for pattern, _ in _PATTERNS:
        if pattern.search(text):
            return True
    return False
