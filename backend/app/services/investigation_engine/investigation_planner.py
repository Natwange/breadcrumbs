"""Create an investigation plan from context and incident signals."""

from __future__ import annotations

from dataclasses import dataclass

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
                action="collect_metrics",
                collector="fake_metrics_collector",
                target_service=affected,
                rationale=f"Gather latency and error metrics for {affected}",
            )
        )
        order += 1

        steps.append(
            PlannedStep(
                order=order,
                action="collect_errors",
                collector="fake_errors_collector",
                target_service=affected,
                rationale=f"Pull recent error logs for {affected}",
            )
        )
        order += 1

        for dep in context.direct_dependencies:
            steps.append(
                PlannedStep(
                    order=order,
                    action="collect_dependency_metrics",
                    collector="fake_metrics_collector",
                    target_service=dep,
                    rationale=f"Check direct dependency {dep} (upstream of {affected})",
                )
            )
            order += 1

        if any(p.lower() == "render" for p in context.external_providers):
            steps.append(
                PlannedStep(
                    order=order,
                    action="collect_deploy_events",
                    collector="fake_render_collector",
                    target_service="render",
                    rationale="Render is an external provider in the blast radius",
                )
            )
            order += 1

        if context.related_services:
            steps.append(
                PlannedStep(
                    order=order,
                    action="collect_recent_commits",
                    collector="fake_github_collector",
                    target_service=affected,
                    rationale="Correlate recent deploys with incident onset",
                )
            )
            order += 1

        if context.external_providers:
            steps.append(
                PlannedStep(
                    order=order,
                    action="check_provider_status",
                    collector="fake_cloud_status_collector",
                    target_service=context.external_providers[0],
                    rationale="Verify third-party provider status pages",
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
