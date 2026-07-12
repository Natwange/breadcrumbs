"""Generate rule-based foundation hypotheses (no LLM)."""

from __future__ import annotations

import uuid

from app.models import Evidence, Hypothesis, Incident
from app.services.investigation_engine.knowledge_context_builder import InvestigationContext


class HypothesisGenerator:
    def generate_foundation(
        self,
        *,
        organization_id: uuid.UUID,
        incident: Incident,
        investigation_run_id: uuid.UUID,
        context: InvestigationContext,
        evidence_rows: list[Evidence],
    ) -> Hypothesis:
        affected = context.affected_service or "the affected service"
        deps = ", ".join(context.direct_dependencies) or "no known dependencies"

        top_types: list[str] = []
        for row in evidence_rows[:3]:
            if row.evidence_type and row.evidence_type not in top_types:
                top_types.append(row.evidence_type)

        signal = ", ".join(top_types) if top_types else "limited telemetry"
        title = f"rule_based_foundation: {affected} degradation"
        description = (
            f"Incident '{incident.title}' on {affected} may stem from dependency or deploy "
            f"issues. Direct dependencies: {deps}. Top evidence signals: {signal}. "
            f"Blast radius may include: {', '.join(context.possible_blast_radius) or 'unknown'}."
        )

        confidence = 0.55
        if context.direct_dependencies and any(r.evidence_type == "error_log" for r in evidence_rows):
            confidence = 0.7

        return Hypothesis(
            organization_id=organization_id,
            investigation_run_id=investigation_run_id,
            incident_id=incident.id,
            title=title,
            description=description,
            status="proposed",
            confidence=confidence,
            rank=1,
        )
