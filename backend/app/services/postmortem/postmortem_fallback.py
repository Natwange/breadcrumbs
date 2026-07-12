"""Deterministic postmortem template when Claude is unavailable."""

from __future__ import annotations

from typing import Any

from app.services.postmortem.postmortem_schema import (
    SOURCE_FALLBACK,
    PostmortemSections,
    PreventionItem,
    RootCauseSection,
    TimelineEntry,
)


def build_fallback(context: dict[str, Any], duration_minutes: int | None) -> PostmortemSections:
    incident = context["incident"]
    title = incident.get("title") or "Incident"
    affected = context.get("investigation_context", {}).get("affected_service") or "unknown"

    timeline: list[TimelineEntry] = []
    for t in context.get("timeline", [])[:10]:
        timeline.append(
            TimelineEntry(
                time=str(t.get("event_time") or ""),
                description=str(t.get("title") or ""),
                is_fact=True,
            )
        )

    hypotheses = context.get("hypotheses", [])
    root_desc = "Root cause not confirmed — review investigation hypotheses."
    is_assumption = True
    evidence_ids: list[str] = []
    if hypotheses:
        top = hypotheses[0]
        root_desc = top.get("description") or top.get("title") or root_desc
        evidence_ids = list(top.get("supporting_evidence_ids") or [])

    impacts = context.get("impacts", [])
    impact_text = (
        impacts[0].get("description") if impacts else f"Service degradation on {affected}."
    )

    resolution = context.get("resolution_notes") or incident.get("description") or (
        "Incident marked resolved. Add resolution notes for a complete postmortem."
    )

    prevention = [
        PreventionItem(
            title="Improve monitoring",
            description=f"Add alerts for {affected} health indicators",
        ),
        PreventionItem(
            title="Document runbook",
            description="Update runbook with lessons learned from this incident",
        ),
    ]

    return PostmortemSections(
        summary=(
            f"Postmortem for '{title}' (automated fallback). "
            f"Affected service: {affected}. "
            "This draft was generated without Claude — review and edit before approval."
        ),
        impact=str(impact_text),
        timeline=timeline,
        root_cause=RootCauseSection(
            description=root_desc,
            is_assumption=is_assumption,
            supporting_evidence_ids=evidence_ids,
        ),
        resolution=str(resolution),
        prevention_items=prevention,
        incident_duration_minutes=duration_minutes,
        postmortem_source=SOURCE_FALLBACK,
        assumptions=["Root cause is preliminary pending human review"],
    )
