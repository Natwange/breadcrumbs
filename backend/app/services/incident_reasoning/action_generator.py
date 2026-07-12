"""Create SuggestedAction rows from reasoning output."""

from __future__ import annotations

import uuid

from app.models import SuggestedAction
from app.services.incident_reasoning.reasoning_schema import ReasoningAction, REASONING_SOURCE_CLAUDE


class ActionGenerator:
    def generate(
        self,
        actions: list[ReasoningAction],
        *,
        organization_id: uuid.UUID,
        investigation_run_id: uuid.UUID,
        incident_id: uuid.UUID,
        hypothesis_ids: dict[str, uuid.UUID] | None = None,
        reasoning_source: str = REASONING_SOURCE_CLAUDE,
    ) -> list[SuggestedAction]:
        rows: list[SuggestedAction] = []
        hypothesis_ids = hypothesis_ids or {}
        for action in actions:
            status = "pending_approval" if action.requires_human_approval else "pending"
            rows.append(
                SuggestedAction(
                    organization_id=organization_id,
                    investigation_run_id=investigation_run_id,
                    incident_id=incident_id,
                    title=action.title,
                    description=action.description,
                    action_type=action.action_type,
                    status=status,
                    requires_human_approval=action.requires_human_approval,
                    reasoning_source=reasoning_source,
                    supporting_evidence_ids=action.supporting_evidence_ids or None,
                )
            )
        return rows
