"""Validate that reasoning output is supported by the evidence pack."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.incident_reasoning.reasoning_schema import (
    ReasoningAction,
    ReasoningHypothesis,
    ReasoningOutput,
    ReasoningSchemaError,
)


@dataclass
class ValidationReport:
    valid: bool
    rejected_hypotheses: list[str] = field(default_factory=list)
    rejected_actions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ConfidenceValidator:
    """Reject hypotheses/actions that cite evidence not in the pack."""

    def validate(
        self,
        output: ReasoningOutput,
        valid_evidence_ids: set[str],
    ) -> ValidationReport:
        report = ValidationReport(valid=True)
        kept_hypotheses: list[ReasoningHypothesis] = []
        kept_actions: list[ReasoningAction] = []

        for hyp in output.hypotheses:
            unsupported = [
                eid for eid in hyp.supporting_evidence_ids if eid not in valid_evidence_ids
            ]
            if unsupported:
                report.rejected_hypotheses.append(hyp.title)
                report.errors.append(
                    f"hypothesis '{hyp.title}' cites unknown evidence: {unsupported}"
                )
                continue
            # Filter contradicting ids to valid set only.
            hyp.contradicting_evidence_ids = [
                eid for eid in hyp.contradicting_evidence_ids if eid in valid_evidence_ids
            ]
            kept_hypotheses.append(hyp)

        for action in output.suggested_actions:
            unsupported = [
                eid for eid in action.supporting_evidence_ids if eid not in valid_evidence_ids
            ]
            if unsupported:
                report.rejected_actions.append(action.title)
                report.errors.append(
                    f"action '{action.title}' cites unknown evidence: {unsupported}"
                )
                continue
            if action.risk_level == "high":
                action.requires_human_approval = True
            kept_actions.append(action)

        output.hypotheses = kept_hypotheses
        output.suggested_actions = kept_actions
        report.valid = not report.rejected_hypotheses and not report.rejected_actions
        return report

    def require_hypotheses(self, output: ReasoningOutput) -> None:
        if not output.hypotheses:
            raise ReasoningSchemaError("no valid hypotheses after validation")
