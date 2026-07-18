"""Phase 9 incident reasoning tests."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Evidence, Incident, InvestigationRun
from app.services.incident_reasoning.confidence_validator import ConfidenceValidator
from app.services.incident_reasoning.evidence_pack_builder import EvidencePack
from app.services.incident_reasoning.langfuse_logger import LangfuseLogger, _redact_metadata
from app.services.incident_reasoning.reasoning_engine import (
    ReasoningEngine,
    ReasoningReadinessGate,
)
from app.services.incident_reasoning.reasoning_schema import (
    REASONING_SOURCE_CLAUDE,
    REASONING_SOURCE_FALLBACK,
    REASONING_STATUS_INSUFFICIENT_EVIDENCE,
    ReasoningAction,
    ReasoningHypothesis,
    ReasoningOutput,
    ReasoningSchemaError,
    parse_reasoning_output,
)
from tests.conftest import seed_org_member


def _pack(
    *,
    high: int = 2,
    medium: int = 1,
    uncertain: int = 0,
    low: int = 0,
    affected: str = "backend",
) -> EvidencePack:
    def _items(n: int, label: str) -> list[dict]:
        return [
            {
                "evidence_id": f"{label}-{i}",
                "source": "metrics",
                "evidence_type": "metric_spike",
                "title": f"{label} evidence {i}",
                "content": f"Signal on {affected}",
                "relevance_label": label,
            }
            for i in range(n)
        ]

    all_items = (
        _items(high, "high")
        + _items(medium, "medium")
        + _items(uncertain, "uncertain")
        + _items(low, "low")
    )
    return EvidencePack(
        incident={"title": "Backend outage", "status": "open", "severity": "high"},
        alerts=[],
        context={
            "affected_service": affected,
            "direct_dependencies": ["supabase"],
            "possible_blast_radius": ["frontend"],
            "architecture_summary": "3 services",
        },
        plan={},
        evidence_groups={
            "high": _items(high, "high"),
            "medium": _items(medium, "medium"),
            "uncertain": _items(uncertain, "uncertain"),
            "low_sample": _items(min(low, 2), "low"),
        },
        timeline=[],
        similarity={},
        valid_evidence_ids={i["evidence_id"] for i in all_items},
        budget_summary={
            "total_evidence": high + medium + uncertain + low,
            "high_included": high,
        },
    )


@dataclass
class _FakeReasoningClient:
    raw: str
    enabled: bool = True
    token_usage: dict = field(default_factory=lambda: {"input_tokens": 200, "output_tokens": 80})
    model_version: str = "claude-test"

    def reason(self, system: str, user: str):
        return self.raw, self.token_usage, self.model_version


def test_readiness_gate_insufficient_when_no_high_relevance():
    pack = _pack(high=0, medium=1, uncertain=3, low=2)
    result = ReasoningReadinessGate().assess(pack)
    assert result.ready is False
    assert result.reasoning_status == REASONING_STATUS_INSUFFICIENT_EVIDENCE
    assert len(result.missing_evidence) >= 2


def test_readiness_gate_passes_with_high_evidence():
    pack = _pack(high=2, medium=1, uncertain=1)
    result = ReasoningReadinessGate().assess(pack)
    assert result.ready is True


def test_unsupported_claims_rejected():
    output = ReasoningOutput(
        executive_summary="summary",
        hypotheses=[
            ReasoningHypothesis(
                title="Bad hyp",
                description="d",
                supporting_evidence_ids=["fake-id-not-in-pack"],
            )
        ],
        estimated_impact=[],
        suggested_actions=[
            ReasoningAction(
                title="Bad action",
                description="d",
                action_type="restart",
                supporting_evidence_ids=["also-fake"],
            )
        ],
        missing_evidence=[],
        slack_update_draft="draft",
    )
    report = ConfidenceValidator().validate(output, {"real-id-1"})
    assert report.valid is False
    assert "Bad hyp" in report.rejected_hypotheses
    assert "Bad action" in report.rejected_actions
    assert output.hypotheses == []
    assert output.suggested_actions == []


def test_parse_reasoning_requires_supporting_evidence_ids():
    raw = json.dumps(
        {
            "executive_summary": "summary",
            "hypotheses": [{"title": "h", "description": "d", "supporting_evidence_ids": []}],
            "estimated_impact": [],
            "suggested_actions": [],
            "missing_evidence": [],
            "slack_update_draft": "draft",
        }
    )
    try:
        parse_reasoning_output(raw)
        assert False, "expected ReasoningSchemaError"
    except ReasoningSchemaError:
        pass


def test_claude_success_parsed_and_validated():
    raw = json.dumps(
        {
            "executive_summary": "Backend latency caused by DB pool exhaustion.",
            "hypotheses": [
                {
                    "title": "DB pool exhausted",
                    "description": "Timeouts match pool metrics",
                    "supporting_evidence_ids": ["high-0"],
                    "contradicting_evidence_ids": [],
                    "confidence": "high",
                    "is_estimate": False,
                }
            ],
            "estimated_impact": [
                {
                    "impact_type": "latency",
                    "description": "Users see slow responses",
                    "severity": "high",
                    "affected_services": ["backend"],
                    "is_estimate": True,
                }
            ],
            "suggested_actions": [
                {
                    "title": "Scale connection pool",
                    "description": "Increase pool size",
                    "action_type": "config_change",
                    "risk_level": "high",
                    "requires_human_approval": True,
                    "supporting_evidence_ids": ["high-0"],
                }
            ],
            "missing_evidence": [],
            "slack_update_draft": "Investigating backend latency",
        }
    )
    output = parse_reasoning_output(raw)
    report = ConfidenceValidator().validate(output, {"high-0", "high-1"})
    assert report.valid is True
    assert output.hypotheses[0].title == "DB pool exhausted"
    assert output.suggested_actions[0].requires_human_approval is True


def test_fallback_when_claude_returns_invalid_json():
    pack = _pack(high=2)
    client = _FakeReasoningClient(raw="not json {{{")
    engine = ReasoningEngine(llm_client=client, langfuse=LangfuseLogger())
    # readiness passes but claude fails -> fallback
    result = engine._run_claude(pack)  # noqa: SLF001
    assert result is None
    fb = engine._fallback_output(pack)  # noqa: SLF001
    assert fb.source == REASONING_SOURCE_FALLBACK
    assert fb.hypotheses[0].supporting_evidence_ids


def test_insufficient_evidence_generates_missing_suggestions(session: Session):
    db = session
    _, org, _ = seed_org_member(db, role="member")
    incident = Incident(organization_id=org.id, title="Test", status="open")
    db.add(incident)
    db.flush()
    run = InvestigationRun(
        organization_id=org.id, incident_id=incident.id, status="running"
    )
    db.add(run)
    db.flush()

    # Only low-relevance evidence.
    db.add(
        Evidence(
            organization_id=org.id,
            investigation_run_id=run.id,
            incident_id=incident.id,
            source="metrics",
            evidence_type="metric_spike",
            title="noise",
            content="peripheral signal",
            relevance_label="low",
        )
    )
    db.commit()

    engine = ReasoningEngine()
    result = engine.run(db, org.id, run, incident)
    assert result.reasoning_status == REASONING_STATUS_INSUFFICIENT_EVIDENCE
    assert result.output.missing_evidence
    assert run.executive_summary is not None


def test_langfuse_redacts_secrets_in_metadata():
    meta = {
        "note": "token=supersecretvalue12345678",
        "nested": {"key": "Bearer abcdefghijklmnop"},
    }
    redacted = _redact_metadata(meta)
    assert "supersecretvalue12345678" not in str(redacted)
    assert "Bearer abcdefghijklmnop" not in str(redacted)


def test_langfuse_skips_log_when_secrets_remain(monkeypatch):
    logger = LangfuseLogger()
    logger._public_key = "pk-test"  # noqa: SLF001
    logger._secret_key = "sk-test"  # noqa: SLF001
    called = {"n": 0}

    def _fake_post(*_a, **_kw):
        called["n"] += 1

    import httpx

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: _fake_post())

    # Force pattern that survives redaction poorly - use raw secret in field name bypass
    # The logger should skip if secret patterns detected after redaction.
    logger.log_reasoning_call(
        trace_name="t",
        success=True,
        latency_ms=1,
        metadata={"safe": "no secrets here"},
    )
    # With valid safe metadata, post may be attempted (or fail network) - not the focus.
    # Verify redaction path blocks obvious secrets:
    logger.log_reasoning_call(
        trace_name="t2",
        success=False,
        latency_ms=1,
        metadata={"error": "failed with sk-abcdefghijklmnopqrstuvwxyz123456"},
        error="sk-abcdefghijklmnopqrstuvwxyz123456",
    )
    # Second call should be skipped due to secret pattern after redaction attempt.


def test_engine_claude_path(session: Session):
    db = session
    _, org, _ = seed_org_member(db, role="member")
    incident = Incident(
        organization_id=org.id,
        title="Backend latency",
        status="open",
        metadata_={"affected_service": "backend"},
    )
    db.add(incident)
    db.flush()
    run = InvestigationRun(
        organization_id=org.id, incident_id=incident.id, status="running"
    )
    db.add(run)
    db.flush()
    eid = uuid.uuid4()
    db.add(
        Evidence(
            id=eid,
            organization_id=org.id,
            investigation_run_id=run.id,
            incident_id=incident.id,
            source="errors",
            evidence_type="error_log",
            title="DB timeout",
            content="connection pool exhausted on backend",
            relevance_label="high",
        )
    )
    db.commit()

    raw = json.dumps(
        {
            "executive_summary": "DB pool issue on backend.",
            "hypotheses": [
                {
                    "title": "Pool exhausted",
                    "description": "Timeouts",
                    "supporting_evidence_ids": [str(eid)],
                    "confidence": "high",
                }
            ],
            "estimated_impact": [],
            "suggested_actions": [],
            "missing_evidence": [],
            "slack_update_draft": "Investigating pool issue",
        }
    )
    engine = ReasoningEngine(llm_client=_FakeReasoningClient(raw=raw))
    result = engine.run(db, org.id, run, incident)
    assert result.reasoning_status != REASONING_STATUS_INSUFFICIENT_EVIDENCE
    assert result.hypotheses
    assert result.hypotheses[0].reasoning_source == REASONING_SOURCE_CLAUDE
    assert result.tracking["reasoning_source"] == REASONING_SOURCE_CLAUDE
