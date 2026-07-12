"""Object types eligible for embedding.

Live telemetry (logs, metrics, evidence, timeline events) is intentionally
excluded and has no constant here.
"""

from __future__ import annotations

OBJECT_TYPE_RUNBOOK = "runbook"
OBJECT_TYPE_POSTMORTEM = "postmortem"
OBJECT_TYPE_KNOWLEDGE_ARTIFACT = "knowledge_artifact"
OBJECT_TYPE_INCIDENT = "incident"

EMBEDDABLE_OBJECT_TYPES = frozenset(
    {
        OBJECT_TYPE_RUNBOOK,
        OBJECT_TYPE_POSTMORTEM,
        OBJECT_TYPE_KNOWLEDGE_ARTIFACT,
        OBJECT_TYPE_INCIDENT,
    }
)
