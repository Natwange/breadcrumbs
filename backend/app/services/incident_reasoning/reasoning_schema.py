"""Schema and validation for Claude incident-reasoning output."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

SCHEMA_VERSION = "1.0"

REASONING_SOURCE_CLAUDE = "claude"
REASONING_SOURCE_FALLBACK = "rule_based_fallback"

REASONING_STATUS_COMPLETE = "complete"
REASONING_STATUS_INSUFFICIENT_EVIDENCE = "insufficient_evidence"
REASONING_STATUS_FALLBACK = "fallback"

IMPACT_LEVELS = frozenset({"critical", "high", "medium", "low", "unknown"})
ACTION_RISK_LEVELS = frozenset({"low", "medium", "high"})


class ReasoningSchemaError(ValueError):
    """Raised when Claude output does not conform to the expected schema."""


@dataclass
class ReasoningHypothesis:
    title: str
    description: str
    supporting_evidence_ids: list[str]
    contradicting_evidence_ids: list[str] = field(default_factory=list)
    confidence: str = "medium"
    is_estimate: bool = False


@dataclass
class ReasoningAction:
    title: str
    description: str
    action_type: str
    risk_level: str = "low"
    requires_human_approval: bool = False
    supporting_evidence_ids: list[str] = field(default_factory=list)


@dataclass
class ReasoningImpact:
    impact_type: str
    description: str
    severity: str
    affected_services: list[str] = field(default_factory=list)
    is_estimate: bool = True


@dataclass
class MissingEvidence:
    category: str
    description: str
    rationale: str


@dataclass
class ReasoningOutput:
    executive_summary: str
    hypotheses: list[ReasoningHypothesis]
    estimated_impact: list[ReasoningImpact]
    suggested_actions: list[ReasoningAction]
    missing_evidence: list[MissingEvidence]
    slack_update_draft: str
    source: str = REASONING_SOURCE_CLAUDE


def _as_str_list(value: object, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ReasoningSchemaError(f"{field_name} must be a list")
    return [str(v) for v in value]


def _parse_hypothesis(item: object) -> ReasoningHypothesis:
    if not isinstance(item, dict):
        raise ReasoningSchemaError("hypothesis item is not an object")
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ReasoningSchemaError("hypothesis missing title")
    supporting = _as_str_list(item.get("supporting_evidence_ids"), "supporting_evidence_ids")
    if not supporting:
        raise ReasoningSchemaError(f"hypothesis '{title}' has no supporting_evidence_ids")
    return ReasoningHypothesis(
        title=title.strip(),
        description=str(item.get("description") or "").strip(),
        supporting_evidence_ids=supporting,
        contradicting_evidence_ids=_as_str_list(
            item.get("contradicting_evidence_ids"), "contradicting_evidence_ids"
        ),
        confidence=str(item.get("confidence") or "medium").lower(),
        is_estimate=bool(item.get("is_estimate", False)),
    )


def _parse_action(item: object) -> ReasoningAction:
    if not isinstance(item, dict):
        raise ReasoningSchemaError("action item is not an object")
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ReasoningSchemaError("action missing title")
    risk = str(item.get("risk_level") or "low").lower()
    if risk not in ACTION_RISK_LEVELS:
        risk = "low"
    requires = bool(item.get("requires_human_approval", risk == "high"))
    return ReasoningAction(
        title=title.strip(),
        description=str(item.get("description") or "").strip(),
        action_type=str(item.get("action_type") or "investigate"),
        risk_level=risk,
        requires_human_approval=requires,
        supporting_evidence_ids=_as_str_list(
            item.get("supporting_evidence_ids"), "supporting_evidence_ids"
        ),
    )


def _parse_impact(item: object) -> ReasoningImpact:
    if not isinstance(item, dict):
        raise ReasoningSchemaError("impact item is not an object")
    severity = str(item.get("severity") or "unknown").lower()
    if severity not in IMPACT_LEVELS:
        severity = "unknown"
    return ReasoningImpact(
        impact_type=str(item.get("impact_type") or "service_degradation"),
        description=str(item.get("description") or "").strip(),
        severity=severity,
        affected_services=_as_str_list(item.get("affected_services"), "affected_services"),
        is_estimate=bool(item.get("is_estimate", True)),
    )


def _parse_missing(item: object) -> MissingEvidence:
    if not isinstance(item, dict):
        raise ReasoningSchemaError("missing_evidence item is not an object")
    category = item.get("category")
    description = item.get("description")
    if not isinstance(category, str) or not category.strip():
        raise ReasoningSchemaError("missing_evidence missing category")
    if not isinstance(description, str) or not description.strip():
        raise ReasoningSchemaError("missing_evidence missing description")
    return MissingEvidence(
        category=category.strip(),
        description=description.strip(),
        rationale=str(item.get("rationale") or "").strip(),
    )


def parse_reasoning_output(raw: str) -> ReasoningOutput:
    if not raw or not raw.strip():
        raise ReasoningSchemaError("empty response")

    text = raw.strip()
    if text.startswith("```"):
        text = text.lstrip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip().rstrip("`").strip()

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ReasoningSchemaError(f"response is not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ReasoningSchemaError("expected a JSON object")

    summary = parsed.get("executive_summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ReasoningSchemaError("missing executive_summary")

    slack = parsed.get("slack_update_draft")
    if not isinstance(slack, str):
        slack = summary

    hypotheses = [_parse_hypothesis(h) for h in parsed.get("hypotheses", [])]
    actions = [_parse_action(a) for a in parsed.get("suggested_actions", [])]
    impacts = [_parse_impact(i) for i in parsed.get("estimated_impact", [])]
    missing = [_parse_missing(m) for m in parsed.get("missing_evidence", [])]

    return ReasoningOutput(
        executive_summary=summary.strip(),
        hypotheses=hypotheses,
        estimated_impact=impacts,
        suggested_actions=actions,
        missing_evidence=missing,
        slack_update_draft=slack.strip(),
        source=REASONING_SOURCE_CLAUDE,
    )
