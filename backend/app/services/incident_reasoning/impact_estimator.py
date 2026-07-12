"""Create IncidentImpact rows from reasoning output."""

from __future__ import annotations

import uuid

from app.models import IncidentImpact
from app.services.incident_reasoning.reasoning_schema import ReasoningImpact


class ImpactEstimator:
    def generate(
        self,
        impacts: list[ReasoningImpact],
        *,
        organization_id: uuid.UUID,
        incident_id: uuid.UUID,
        investigation_run_id: uuid.UUID | None = None,
    ) -> list[IncidentImpact]:
        rows: list[IncidentImpact] = []
        for impact in impacts:
            rows.append(
                IncidentImpact(
                    organization_id=organization_id,
                    incident_id=incident_id,
                    investigation_run_id=investigation_run_id,
                    impact_type=impact.impact_type,
                    description=impact.description,
                    severity=impact.severity,
                    affected_services={"services": impact.affected_services}
                    if impact.affected_services
                    else None,
                    metrics={"is_estimate": impact.is_estimate},
                )
            )
        return rows
