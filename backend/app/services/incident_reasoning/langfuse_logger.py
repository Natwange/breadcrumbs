"""Optional Langfuse observability for Claude reasoning calls.

Logs latency, token usage, cost, and success/failure. Never logs raw prompts
or responses that may contain secrets — only metadata and redacted summaries.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.services.knowledge_builder.secret_redactor import redact_secrets

logger = logging.getLogger(__name__)

_SECRET_PATTERNS = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|bearer\s+\S+|sk-[a-z0-9]{20,})"
)


def _redact_metadata(data: dict[str, Any]) -> dict[str, Any]:
    """Deep-redact string values in metadata before sending to Langfuse."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = redact_secrets(value).redacted_text
        elif isinstance(value, dict):
            result[key] = _redact_metadata(value)
        elif isinstance(value, list):
            result[key] = [
                redact_secrets(v).redacted_text if isinstance(v, str) else v for v in value
            ]
        else:
            result[key] = value
    return result


class LangfuseLogger:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._public_key = self._settings.langfuse_public_key
        self._secret_key = self._settings.langfuse_secret_key
        self._host = self._settings.langfuse_host.rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self._public_key and self._secret_key)

    def log_reasoning_call(
        self,
        *,
        trace_name: str,
        success: bool,
        latency_ms: int,
        metadata: dict[str, Any],
        error: str | None = None,
    ) -> None:
        if not self.enabled:
            return

        safe_meta = _redact_metadata(metadata)
        if error:
            safe_meta["error"] = redact_secrets(error).redacted_text

        # Verify no obvious secrets leaked into metadata.
        payload_str = str(safe_meta)
        if _SECRET_PATTERNS.search(payload_str):
            logger.warning("langfuse metadata still contains secret-like patterns; skipping log")
            return

        body = {
            "batch": [
                {
                    "id": f"reasoning-{trace_name}",
                    "type": "trace-create",
                    "timestamp": None,
                    "body": {
                        "name": trace_name,
                        "metadata": safe_meta,
                        "tags": ["incident-reasoning", "success" if success else "failure"],
                    },
                }
            ]
        }

        auth = base64.b64encode(
            f"{self._public_key}:{self._secret_key}".encode()
        ).decode()

        try:
            with httpx.Client(timeout=10.0) as client:
                client.post(
                    f"{self._host}/api/public/ingestion",
                    headers={
                        "Authorization": f"Basic {auth}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
        except Exception as exc:  # noqa: BLE001 — observability must not break reasoning
            logger.debug("langfuse log failed: %s", exc)
