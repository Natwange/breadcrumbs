"""Orchestrate Claude incident reasoning with readiness gating and fallback."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import (
    Hypothesis,
    Incident,
    InvestigationRun,
    SlackDraft,
)
from app.services.incident_reasoning.action_generator import ActionGenerator
from app.services.incident_reasoning.confidence_validator import ConfidenceValidator
from app.services.incident_reasoning.evidence_pack_builder import EvidencePack, EvidencePackBuilder
from app.services.incident_reasoning.impact_estimator import ImpactEstimator
from app.services.incident_reasoning.langfuse_logger import LangfuseLogger
from app.services.incident_reasoning.reasoning_prompt_builder import PROMPT_VERSION, build_prompt
from app.services.incident_reasoning.reasoning_schema import (
    REASONING_SOURCE_CLAUDE,
    REASONING_SOURCE_FALLBACK,
    REASONING_STATUS_COMPLETE,
    REASONING_STATUS_FALLBACK,
    REASONING_STATUS_INSUFFICIENT_EVIDENCE,
    SCHEMA_VERSION,
    MissingEvidence,
    ReasoningHypothesis,
    ReasoningImpact,
    ReasoningOutput,
    ReasoningSchemaError,
    parse_reasoning_output,
)
from app.services.vector_search.similarity_service import SimilarityContext

_COST_PER_INPUT = 3.0 / 1_000_000
_COST_PER_OUTPUT = 15.0 / 1_000_000


@dataclass
class ReadinessResult:
    ready: bool
    reasoning_status: str
    high_count: int = 0
    low_uncertain_count: int = 0
    total_count: int = 0
    missing_evidence: list[MissingEvidence] = field(default_factory=list)


class ReasoningReadinessGate:
    """Decide whether there is enough evidence for full Claude reasoning."""

    def assess(self, pack: EvidencePack) -> ReadinessResult:
        groups = pack.evidence_groups
        high = len(groups.get("high", []))
        medium = len(groups.get("medium", []))
        uncertain = len(groups.get("uncertain", []))
        low = len(groups.get("low_sample", [])) + max(
            0, pack.budget_summary.get("total_evidence", 0)
            - high
            - len(groups.get("medium", []))
            - len(groups.get("uncertain", []))
        )
        total = pack.budget_summary.get("total_evidence", high + medium + uncertain + low)
        low_uncertain = uncertain + low

        if total == 0:
            return ReadinessResult(
                ready=False,
                reasoning_status=REASONING_STATUS_INSUFFICIENT_EVIDENCE,
                total_count=0,
                missing_evidence=self._suggest_missing(pack, reason="no evidence collected"),
            )

        # No high relevance and majority low/uncertain -> insufficient.
        non_high = medium + uncertain + low
        if high == 0 and non_high > 0 and low_uncertain >= non_high * 0.5:
            return ReadinessResult(
                ready=False,
                reasoning_status=REASONING_STATUS_INSUFFICIENT_EVIDENCE,
                high_count=high,
                low_uncertain_count=low_uncertain,
                total_count=total,
                missing_evidence=self._suggest_missing(
                    pack, reason="no high-relevance evidence; majority low/uncertain"
                ),
            )

        return ReadinessResult(
            ready=True,
            reasoning_status=REASONING_STATUS_COMPLETE,
            high_count=high,
            low_uncertain_count=low_uncertain,
            total_count=total,
        )

    def _suggest_missing(self, pack: EvidencePack, *, reason: str) -> list[MissingEvidence]:
        affected = pack.context.get("affected_service") or "affected service"
        suggestions = [
            MissingEvidence(
                category="metrics",
                description=f"Error rate and latency metrics for {affected}",
                rationale=f"Need quantitative signals: {reason}",
            ),
            MissingEvidence(
                category="logs",
                description=f"Recent error logs from {affected}",
                rationale="Log evidence would clarify root cause",
            ),
        ]
        for dep in pack.context.get("direct_dependencies", [])[:2]:
            suggestions.append(
                MissingEvidence(
                    category="dependency_health",
                    description=f"Health checks for dependency {dep}",
                    rationale="Rule out downstream failure",
                )
            )
        return suggestions


@dataclass
class ReasoningResult:
    output: ReasoningOutput
    reasoning_status: str
    tracking: dict[str, Any]
    hypotheses: list[Hypothesis] = field(default_factory=list)
    slack_draft: SlackDraft | None = None


class ReasoningLLMClient(Protocol):
    @property
    def enabled(self) -> bool: ...

    def reason(self, system: str, user: str) -> tuple[str, dict[str, int], str]: ...


class ClaudeReasoningClient:
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.anthropic_api_key
        self._model = settings.anthropic_model

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def reason(self, system: str, user: str) -> tuple[str, dict[str, int], str]:
        if not self._api_key:
            raise RuntimeError("Anthropic API key is not configured")
        with httpx.Client(timeout=90.0) as client:
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": 8192,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            response.raise_for_status()
            data = response.json()
        text_blocks = [
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        ]
        raw = "\n".join(text_blocks).strip()
        usage = data.get("usage", {}) or {}
        token_usage = {
            "input_tokens": int(usage.get("input_tokens", 0)),
            "output_tokens": int(usage.get("output_tokens", 0)),
        }
        return raw, token_usage, data.get("model", self._model)


class ReasoningEngine:
    def __init__(
        self,
        settings: Settings | None = None,
        pack_builder: EvidencePackBuilder | None = None,
        readiness_gate: ReasoningReadinessGate | None = None,
        validator: ConfidenceValidator | None = None,
        action_gen: ActionGenerator | None = None,
        impact_est: ImpactEstimator | None = None,
        llm_client: ReasoningLLMClient | None = None,
        langfuse: LangfuseLogger | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._pack_builder = pack_builder or EvidencePackBuilder()
        self._gate = readiness_gate or ReasoningReadinessGate()
        self._validator = validator or ConfidenceValidator()
        self._actions = action_gen or ActionGenerator()
        self._impacts = impact_est or ImpactEstimator()
        self._llm = llm_client or ClaudeReasoningClient(self._settings)
        self._langfuse = langfuse or LangfuseLogger(self._settings)

    def run(
        self,
        db: Session,
        organization_id: uuid.UUID,
        investigation_run: InvestigationRun,
        incident: Incident,
        *,
        similarity: SimilarityContext | None = None,
    ) -> ReasoningResult:
        pack = self._pack_builder.build(
            db, organization_id, investigation_run.id, similarity=similarity
        )
        readiness = self._gate.assess(pack)

        if not readiness.ready:
            output = self._insufficient_output(readiness, pack)
            tracking = self._tracking(
                source=REASONING_SOURCE_FALLBACK,
                model_version="readiness_gate",
                latency_ms=0,
                token_usage={},
                success=True,
            )
            return self._persist(
                db,
                organization_id=organization_id,
                run=investigation_run,
                incident=incident,
                output=output,
                reasoning_status=REASONING_STATUS_INSUFFICIENT_EVIDENCE,
                tracking=tracking,
            )

        if getattr(self._llm, "enabled", False):
            result = self._run_claude(pack)
            if result is not None:
                return self._persist(
                    db,
                    organization_id=organization_id,
                    run=investigation_run,
                    incident=incident,
                    output=result.output,
                    reasoning_status=result.reasoning_status,
                    tracking=result.tracking,
                )

        output = self._fallback_output(pack)
        tracking = self._tracking(
            source=REASONING_SOURCE_FALLBACK,
            model_version="rule_based_fallback",
            latency_ms=0,
            token_usage={},
            success=True,
        )
        return self._persist(
            db,
            organization_id=organization_id,
            run=investigation_run,
            incident=incident,
            output=output,
            reasoning_status=REASONING_STATUS_FALLBACK,
            tracking=tracking,
        )

    def _run_claude(self, pack: EvidencePack) -> ReasoningResult | None:
        prompt = build_prompt(pack)
        start = time.perf_counter()
        success = False
        error_msg: str | None = None
        token_usage: dict[str, int] = {}
        model_version = self._settings.anthropic_model

        try:
            raw, token_usage, model_version = self._llm.reason(prompt.system, prompt.user)
            output = parse_reasoning_output(raw)
            self._validator.validate(output, pack.valid_evidence_ids)
            success = True
        except (ReasoningSchemaError, httpx.HTTPError, RuntimeError, ValueError) as exc:
            error_msg = str(exc)
            self._langfuse.log_reasoning_call(
                trace_name="incident-reasoning",
                success=False,
                latency_ms=int((time.perf_counter() - start) * 1000),
                metadata=self._langfuse_meta(prompt, token_usage, model_version, success=False),
                error=error_msg,
            )
            return None
        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            self._langfuse.log_reasoning_call(
                trace_name="incident-reasoning",
                success=False,
                latency_ms=int((time.perf_counter() - start) * 1000),
                metadata=self._langfuse_meta(prompt, token_usage, model_version, success=False),
                error=error_msg,
            )
            return None

        latency_ms = int((time.perf_counter() - start) * 1000)
        tracking = self._tracking(
            source=REASONING_SOURCE_CLAUDE,
            model_version=model_version,
            latency_ms=latency_ms,
            token_usage=token_usage,
            success=success,
            prompt_version=prompt.prompt_version,
        )
        self._langfuse.log_reasoning_call(
            trace_name="incident-reasoning",
            success=True,
            latency_ms=latency_ms,
            metadata=self._langfuse_meta(prompt, token_usage, model_version, success=True),
        )
        return ReasoningResult(
            output=output,
            reasoning_status=REASONING_STATUS_COMPLETE,
            tracking=tracking,
        )

    def _langfuse_meta(
        self, prompt: Any, token_usage: dict, model_version: str, *, success: bool
    ) -> dict[str, Any]:
        return {
            "prompt_version": prompt.prompt_version,
            "schema_version": prompt.schema_version,
            "model_version": model_version,
            "token_usage": token_usage,
            "success": success,
            # Deliberately omit raw prompt/response text.
            "user_prompt_chars": len(prompt.user),
        }

    def _tracking(
        self,
        *,
        source: str,
        model_version: str,
        latency_ms: int,
        token_usage: dict[str, int],
        success: bool,
        prompt_version: str = PROMPT_VERSION,
    ) -> dict[str, Any]:
        cost = (
            token_usage.get("input_tokens", 0) * _COST_PER_INPUT
            + token_usage.get("output_tokens", 0) * _COST_PER_OUTPUT
        )
        return {
            "prompt_version": prompt_version,
            "model_version": model_version,
            "schema_version": SCHEMA_VERSION,
            "latency_ms": latency_ms,
            "token_usage": token_usage,
            "estimated_cost": round(cost, 6),
            "reasoning_source": source,
            "success": success,
        }

    def _insufficient_output(
        self, readiness: ReadinessResult, pack: EvidencePack
    ) -> ReasoningOutput:
        affected = pack.context.get("affected_service") or "the affected service"
        missing = readiness.missing_evidence
        summary = (
            f"Insufficient evidence to run full incident analysis for {affected}. "
            f"Collected {readiness.total_count} item(s) with {readiness.high_count} high-relevance. "
            "Gather additional telemetry before drawing conclusions."
        )
        return ReasoningOutput(
            executive_summary=summary,
            hypotheses=[],
            estimated_impact=[],
            suggested_actions=[],
            missing_evidence=missing,
            slack_update_draft=summary,
            source=REASONING_SOURCE_FALLBACK,
        )

    def _fallback_output(self, pack: EvidencePack) -> ReasoningOutput:
        affected = pack.context.get("affected_service") or "affected service"
        high_items = pack.evidence_groups.get("high", []) or pack.evidence_groups.get("medium", [])
        evidence_ids = [e["evidence_id"] for e in high_items[:3]]
        if not evidence_ids and pack.valid_evidence_ids:
            evidence_ids = [next(iter(pack.valid_evidence_ids))]

        hyp = ReasoningHypothesis(
            title=f"rule_based_fallback: {affected} degradation",
            description=(
                f"Limited automated analysis for '{pack.incident.get('title')}'. "
                f"Top signals from {len(pack.valid_evidence_ids)} evidence item(s)."
            ),
            supporting_evidence_ids=evidence_ids,
            confidence="low",
            is_estimate=True,
        )
        impact = ReasoningImpact(
            impact_type="service_degradation",
            description=f"Potential impact on {affected} and dependencies",
            severity="unknown",
            affected_services=pack.context.get("possible_blast_radius", []),
            is_estimate=True,
        )
        summary = (
            f"Automated fallback analysis for {pack.incident.get('title')}. "
            "Claude reasoning was unavailable; conclusions are preliminary."
        )
        return ReasoningOutput(
            executive_summary=summary,
            hypotheses=[hyp] if evidence_ids else [],
            estimated_impact=[impact],
            suggested_actions=[],
            missing_evidence=[
                MissingEvidence(
                    category="reasoning",
                    description="Re-run analysis when Claude is available",
                    rationale="Full reasoning engine fallback was used",
                )
            ],
            slack_update_draft=summary,
            source=REASONING_SOURCE_FALLBACK,
        )

    def _persist(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        run: InvestigationRun,
        incident: Incident,
        output: ReasoningOutput,
        reasoning_status: str,
        tracking: dict[str, Any],
    ) -> ReasoningResult:
        run.executive_summary = output.executive_summary
        run.reasoning_status = reasoning_status
        run.reasoning_tracking = tracking

        hypotheses: list[Hypothesis] = []
        for rank, hyp in enumerate(output.hypotheses, start=1):
            conf_map = {"high": 0.85, "medium": 0.6, "low": 0.35}
            row = Hypothesis(
                organization_id=organization_id,
                investigation_run_id=run.id,
                incident_id=incident.id,
                title=hyp.title,
                description=hyp.description,
                status="proposed",
                confidence=conf_map.get(hyp.confidence, 0.5),
                rank=rank,
                supporting_evidence_ids=hyp.supporting_evidence_ids,
                contradicting_evidence_ids=hyp.contradicting_evidence_ids or None,
                reasoning_source=output.source,
            )
            hypotheses.append(row)
        db.add_all(hypotheses)

        impacts = self._impacts.generate(
            output.estimated_impact,
            organization_id=organization_id,
            incident_id=incident.id,
            investigation_run_id=run.id,
        )
        db.add_all(impacts)

        actions = self._actions.generate(
            output.suggested_actions,
            organization_id=organization_id,
            investigation_run_id=run.id,
            incident_id=incident.id,
            reasoning_source=output.source,
        )
        db.add_all(actions)

        slack = SlackDraft(
            organization_id=organization_id,
            incident_id=incident.id,
            investigation_run_id=run.id,
            channel="#incidents",
            content=output.slack_update_draft,
            status="draft",
            reasoning_source=output.source,
        )
        db.add(slack)
        db.flush()

        return ReasoningResult(
            output=output,
            reasoning_status=reasoning_status,
            tracking=tracking,
            hypotheses=hypotheses,
            slack_draft=slack,
        )
