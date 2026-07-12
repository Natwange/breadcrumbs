"""Schema for structured postmortem output."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

SCHEMA_VERSION = "1.0"

SOURCE_CLAUDE = "claude"
SOURCE_FALLBACK = "rule_based_fallback"
SOURCE_MANUAL = "manual"


class PostmortemSchemaError(ValueError):
    pass


@dataclass
class TimelineEntry:
    time: str
    description: str
    is_fact: bool = True


@dataclass
class RootCauseSection:
    description: str
    is_assumption: bool = False
    supporting_evidence_ids: list[str] = field(default_factory=list)


@dataclass
class PreventionItem:
    title: str
    description: str


@dataclass
class PostmortemSections:
    summary: str
    impact: str
    timeline: list[TimelineEntry]
    root_cause: RootCauseSection
    resolution: str
    prevention_items: list[PreventionItem]
    incident_duration_minutes: int | None = None
    postmortem_source: str = SOURCE_CLAUDE
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "impact": self.impact,
            "timeline": [
                {"time": t.time, "description": t.description, "is_fact": t.is_fact}
                for t in self.timeline
            ],
            "root_cause": {
                "description": self.root_cause.description,
                "is_assumption": self.root_cause.is_assumption,
                "supporting_evidence_ids": self.root_cause.supporting_evidence_ids,
            },
            "resolution": self.resolution,
            "prevention_items": [
                {"title": p.title, "description": p.description} for p in self.prevention_items
            ],
            "incident_duration_minutes": self.incident_duration_minutes,
            "postmortem_source": self.postmortem_source,
            "assumptions": self.assumptions,
        }

    def render_paragraphs(self) -> str:
        """Readable text for UI display from structured sections."""
        lines = [
            "## Summary",
            self.summary,
            "",
            "## Impact",
            self.impact,
            "",
            "## Timeline",
        ]
        for entry in self.timeline:
            prefix = "" if entry.is_fact else "(assumption) "
            lines.append(f"- {entry.time}: {prefix}{entry.description}")
        lines.extend(["", "## Root Cause"])
        if self.root_cause.is_assumption:
            lines.append("(assumption — not fully confirmed by evidence)")
        lines.append(self.root_cause.description)
        lines.extend(["", "## Resolution", self.resolution])
        if self.prevention_items:
            lines.extend(["", "## Prevention"])
            for item in self.prevention_items:
                lines.append(f"- **{item.title}**: {item.description}")
        if self.assumptions:
            lines.extend(["", "## Assumptions"])
            for a in self.assumptions:
                lines.append(f"- {a}")
        if self.incident_duration_minutes is not None:
            lines.extend(["", f"Duration: {self.incident_duration_minutes} minutes"])
        return "\n".join(lines)


def parse_postmortem_response(raw: str) -> PostmortemSections:
    if not raw or not raw.strip():
        raise PostmortemSchemaError("empty response")

    text = raw.strip()
    if text.startswith("```"):
        text = text.lstrip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip().rstrip("`").strip()

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise PostmortemSchemaError(f"invalid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise PostmortemSchemaError("expected JSON object")

    summary = parsed.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise PostmortemSchemaError("missing summary")

    impact = str(parsed.get("impact") or "").strip()
    resolution = str(parsed.get("resolution") or "").strip()

    timeline_raw = parsed.get("timeline", [])
    timeline: list[TimelineEntry] = []
    if isinstance(timeline_raw, list):
        for item in timeline_raw:
            if isinstance(item, dict):
                timeline.append(
                    TimelineEntry(
                        time=str(item.get("time") or ""),
                        description=str(item.get("description") or ""),
                        is_fact=bool(item.get("is_fact", True)),
                    )
                )
            elif isinstance(item, str):
                timeline.append(TimelineEntry(time="", description=item))

    rc_raw = parsed.get("root_cause") or {}
    if isinstance(rc_raw, str):
        root_cause = RootCauseSection(description=rc_raw, is_assumption=True)
    elif isinstance(rc_raw, dict):
        root_cause = RootCauseSection(
            description=str(rc_raw.get("description") or "Unknown"),
            is_assumption=bool(rc_raw.get("is_assumption", False)),
            supporting_evidence_ids=[
                str(x) for x in (rc_raw.get("supporting_evidence_ids") or [])
            ],
        )
    else:
        raise PostmortemSchemaError("invalid root_cause")

    prevention: list[PreventionItem] = []
    for item in parsed.get("prevention_items", []) or []:
        if isinstance(item, dict) and item.get("title"):
            prevention.append(
                PreventionItem(
                    title=str(item["title"]),
                    description=str(item.get("description") or ""),
                )
            )

    assumptions = [str(a) for a in (parsed.get("assumptions") or []) if a]

    duration = parsed.get("incident_duration_minutes")
    if duration is not None and not isinstance(duration, int):
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            duration = None

    return PostmortemSections(
        summary=summary.strip(),
        impact=impact or "Impact not fully documented.",
        timeline=timeline,
        root_cause=root_cause,
        resolution=resolution or "Resolution details not provided.",
        prevention_items=prevention,
        incident_duration_minutes=duration,
        postmortem_source=SOURCE_CLAUDE,
        assumptions=assumptions,
    )
