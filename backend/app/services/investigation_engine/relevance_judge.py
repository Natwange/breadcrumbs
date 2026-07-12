"""Rank evidence relevance using Claude, with a deterministic fallback.

Claude judges the whole batch of evidence in a single call and returns
categorical judgments only (no numeric scores, no weights). If Claude is not
configured, fails, or returns malformed output, a deterministic rule-based
fallback assigns categorical labels instead. Every judgment records whether it
came from ``claude`` or ``rule_based_fallback``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import Settings, get_settings
from app.services.investigation_engine.relevance_prompt_builder import (
    PROMPT_VERSION,
    build_prompt,
)
from app.services.investigation_engine.relevance_schema import (
    RELEVANCE_SOURCE_CLAUDE,
    RELEVANCE_SOURCE_FALLBACK,
    SCHEMA_VERSION,
    RelevanceJudgment,
    RelevanceSchemaError,
    parse_judgments,
)

# Rough Claude pricing (USD per token) for cost estimation only. Values are
# order-of-magnitude and configurable; they are not used for any logic.
_COST_PER_INPUT_TOKEN = 3.0 / 1_000_000
_COST_PER_OUTPUT_TOKEN = 15.0 / 1_000_000

# Evidence types that are, on their own, typically incident-relevant. Used only
# by the deterministic fallback (no weights, no scoring — just categories).
_FALLBACK_HIGH_TYPES = frozenset({"error_log", "metric_spike", "deploy"})
_FALLBACK_MEDIUM_TYPES = frozenset({"provider_status", "trace"})


@dataclass
class RelevanceTracking:
    prompt_version: str
    model_version: str
    schema_version: str
    latency_ms: int
    token_usage: dict[str, int]
    estimated_cost: float
    relevance_source: str

    def to_dict(self) -> dict:
        return {
            "prompt_version": self.prompt_version,
            "model_version": self.model_version,
            "schema_version": self.schema_version,
            "latency_ms": self.latency_ms,
            "token_usage": self.token_usage,
            "estimated_cost": self.estimated_cost,
            "relevance_source": self.relevance_source,
        }


@dataclass
class RelevanceOutcome:
    judgments: dict[str, RelevanceJudgment] = field(default_factory=dict)
    tracking: RelevanceTracking | None = None


class RelevanceLLMClient(Protocol):
    @property
    def enabled(self) -> bool: ...

    def judge(self, system: str, user: str) -> tuple[str, dict[str, int], str]:
        """Return (raw_text, token_usage, model_version)."""
        ...


class ClaudeRelevanceClient:
    """Calls Claude for a batched relevance judgment. Returns raw text only."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.anthropic_api_key
        self._model = settings.anthropic_model

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def judge(self, system: str, user: str) -> tuple[str, dict[str, int], str]:
        if not self._api_key:
            raise RuntimeError("Anthropic API key is not configured")

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": 4096,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            response.raise_for_status()
            data = response.json()

        text_blocks = [
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ]
        raw = "\n".join(text_blocks).strip()

        usage_raw = data.get("usage", {}) or {}
        token_usage = {
            "input_tokens": int(usage_raw.get("input_tokens", 0)),
            "output_tokens": int(usage_raw.get("output_tokens", 0)),
        }
        model_version = data.get("model", self._model)
        return raw, token_usage, model_version


class RelevanceJudge:
    def __init__(
        self,
        settings: Settings | None = None,
        llm_client: RelevanceLLMClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._llm = llm_client or ClaudeRelevanceClient(self._settings)

    def judge_batch(
        self,
        evidence_items: list[dict[str, Any]],
        *,
        incident: Any,
        alerts: list[Any],
        plan: dict | None,
        context: Any,
        timeline_events: list[Any],
        runbooks: list[dict] | None,
    ) -> RelevanceOutcome:
        if not evidence_items:
            return RelevanceOutcome(
                judgments={},
                tracking=RelevanceTracking(
                    prompt_version=PROMPT_VERSION,
                    model_version="none",
                    schema_version=SCHEMA_VERSION,
                    latency_ms=0,
                    token_usage={},
                    estimated_cost=0.0,
                    relevance_source=RELEVANCE_SOURCE_FALLBACK,
                ),
            )

        valid_ids = {str(item["evidence_id"]) for item in evidence_items}

        if getattr(self._llm, "enabled", False):
            outcome = self._judge_with_claude(
                evidence_items,
                valid_ids,
                incident=incident,
                alerts=alerts,
                plan=plan,
                context=context,
                timeline_events=timeline_events,
                runbooks=runbooks,
            )
            if outcome is not None:
                return outcome

        return self._fallback(evidence_items, context=context)

    def _judge_with_claude(
        self,
        evidence_items: list[dict[str, Any]],
        valid_ids: set[str],
        *,
        incident: Any,
        alerts: list[Any],
        plan: dict | None,
        context: Any,
        timeline_events: list[Any],
        runbooks: list[dict] | None,
    ) -> RelevanceOutcome | None:
        prompt = build_prompt(
            incident=incident,
            alerts=alerts,
            plan=plan,
            context=context,
            evidence_items=evidence_items,
            timeline_events=timeline_events,
            runbooks=runbooks,
        )
        start = time.perf_counter()
        try:
            raw, token_usage, model_version = self._llm.judge(prompt.system, prompt.user)
            judgments = parse_judgments(raw, valid_ids)
        except (RelevanceSchemaError, httpx.HTTPError, RuntimeError, ValueError):
            return None
        except Exception:  # noqa: BLE001 — any client error triggers fallback
            return None

        latency_ms = int((time.perf_counter() - start) * 1000)
        estimated_cost = (
            token_usage.get("input_tokens", 0) * _COST_PER_INPUT_TOKEN
            + token_usage.get("output_tokens", 0) * _COST_PER_OUTPUT_TOKEN
        )
        judged = {j.evidence_id: j for j in judgments}

        # Any evidence Claude omitted is completed via deterministic fallback so
        # every item always has a judgment.
        missing = [i for i in evidence_items if str(i["evidence_id"]) not in judged]
        if missing:
            fb = self._fallback(missing, context=context).judgments
            judged.update(fb)

        return RelevanceOutcome(
            judgments=judged,
            tracking=RelevanceTracking(
                prompt_version=prompt.prompt_version,
                model_version=model_version,
                schema_version=prompt.schema_version,
                latency_ms=latency_ms,
                token_usage=token_usage,
                estimated_cost=round(estimated_cost, 6),
                relevance_source=RELEVANCE_SOURCE_CLAUDE,
            ),
        )

    def _fallback(
        self, evidence_items: list[dict[str, Any]], *, context: Any
    ) -> RelevanceOutcome:
        affected = getattr(context, "affected_service", None)
        affected_l = affected.lower() if isinstance(affected, str) else None

        judgments: dict[str, RelevanceJudgment] = {}
        for item in evidence_items:
            eid = str(item["evidence_id"])
            etype = (item.get("evidence_type") or "").lower()
            text = f"{item.get('title', '')} {item.get('content', '')}".lower()

            if affected_l and affected_l in text:
                relevance, confidence = "high", "medium"
                reason = f"Mentions affected service {affected}"
            elif etype in _FALLBACK_HIGH_TYPES:
                relevance, confidence = "high", "low"
                reason = f"Evidence type {etype} is typically incident-critical"
            elif etype in _FALLBACK_MEDIUM_TYPES:
                relevance, confidence = "medium", "low"
                reason = f"Evidence type {etype} provides supporting context"
            else:
                relevance, confidence = "low", "low"
                reason = "Peripheral evidence with weak incident signal"

            judgments[eid] = RelevanceJudgment(
                evidence_id=eid,
                relevance=relevance,
                confidence=confidence,
                reason=reason,
                source=RELEVANCE_SOURCE_FALLBACK,
            )

        return RelevanceOutcome(
            judgments=judgments,
            tracking=RelevanceTracking(
                prompt_version=PROMPT_VERSION,
                model_version="rule_based_fallback",
                schema_version=SCHEMA_VERSION,
                latency_ms=0,
                token_usage={},
                estimated_cost=0.0,
                relevance_source=RELEVANCE_SOURCE_FALLBACK,
            ),
        )
