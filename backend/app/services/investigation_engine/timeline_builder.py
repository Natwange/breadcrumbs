"""Build chronological timeline events from evidence."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.models import Evidence, TimelineEvent


class TimelineBuilder:
    def build_events(
        self,
        *,
        organization_id: uuid.UUID,
        incident_id: uuid.UUID,
        investigation_run_id: uuid.UUID,
        evidence_rows: list[Evidence],
    ) -> list[TimelineEvent]:
        sorted_rows = sorted(
            evidence_rows,
            key=lambda e: e.observed_at or datetime.min.replace(tzinfo=e.created_at.tzinfo),
        )
        events: list[TimelineEvent] = []
        for row in sorted_rows:
            events.append(
                TimelineEvent(
                    organization_id=organization_id,
                    incident_id=incident_id,
                    investigation_run_id=investigation_run_id,
                    event_time=row.observed_at,
                    title=row.title or f"{row.source} {row.evidence_type}",
                    description=row.content,
                    source=row.source,
                    event_type=row.evidence_type,
                )
            )
        return events
