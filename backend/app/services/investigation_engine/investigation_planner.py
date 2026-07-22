"""Create an investigation plan from context and incident signals."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.investigation_engine.collector_registry import (
    GITHUB_COLLECTOR,
    RENDER_COLLECTOR,
)
from app.services.investigation_engine.knowledge_context_builder import InvestigationContext


@dataclass
class PlannedStep:
    order: int
    action: str
    collector: str | None
    target_service: str | None
    rationale: str


class InvestigationPlanner:
    def create_plan(self, context: InvestigationContext) -> dict:
        steps: list[PlannedStep] = []
        order = 1
        affected = context.affected_service or "unknown"

        steps.append(
            PlannedStep(
                order=order,
                action="finding_similar_incidents",
                collector=None,
                target_service=affected,
                rationale="Search organizational memory for similar incidents, "
                "runbooks, postmortems, and knowledge artifacts",
            )
        )
        order += 1

        # Real collectors only. The runner skips a step when the named collector
        # is not registered (e.g. no GitHub/Render credentials configured).
        steps.append(
            PlannedStep(
                order=order,
                action="collect_recent_commits",
                collector=GITHUB_COLLECTOR,
                target_service=affected,
                rationale="Correlate recent commits/PRs with incident onset",
            )
        )
        order += 1

        if any(p.lower() == "render" for p in context.external_providers) or (
            context.affected_service
            and context.affected_service.lower() in {"render", "focusflow-server"}
        ):
            steps.append(
                PlannedStep(
                    order=order,
                    action="collect_deploy_events",
                    collector=RENDER_COLLECTOR,
                    target_service="render",
                    rationale="Collect Render deploy and health evidence",
                )
            )
            order += 1
        else:
            # Still attempt Render when it appears as a dependency/hosting edge.
            if any(d.lower() == "render" for d in context.direct_dependencies):
                steps.append(
                    PlannedStep(
                        order=order,
                        action="collect_deploy_events",
                        collector=RENDER_COLLECTOR,
                        target_service="render",
                        rationale="Render is a direct dependency of the affected service",
                    )
                )
                order += 1

        steps.append(
            PlannedStep(
                order=order,
                action="synthesize_timeline",
                collector=None,
                target_service=None,
                rationale="Merge evidence into a chronological timeline",
            )
        )

        return {
            "affected_service": context.affected_service,
            "direct_dependencies": context.direct_dependencies,
            "steps": [
                {
                    "order": s.order,
                    "action": s.action,
                    "collector": s.collector,
                    "target_service": s.target_service,
                    "rationale": s.rationale,
                }
                for s in steps
            ],
        }
