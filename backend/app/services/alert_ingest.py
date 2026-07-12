"""Normalize demo alert payloads for ingestion."""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.investigation_engine import AlertIngestRequest


_ALLOWED_SOURCES = frozenset({"datadog", "render", "new_relic", "manual_demo"})


def validate_alert_ingest(payload: AlertIngestRequest) -> None:
    if payload.source not in _ALLOWED_SOURCES:
        raise ValueError(f"Unsupported alert source: {payload.source}")
    if not payload.title.strip():
        raise ValueError("Alert title is required")


def normalize_demo_payload(payload: AlertIngestRequest) -> dict:
    """Map MVP demo payloads to a common correlation shape."""
    raw = dict(payload.raw_payload or {})

    if payload.source == "datadog":
        raw.setdefault("alert_type", raw.get("type") or "monitor")
        raw.setdefault("service", raw.get("service") or raw.get("tags", {}).get("service"))
    elif payload.source == "render":
        raw.setdefault("service_name", raw.get("service_name") or raw.get("service"))
        raw.setdefault("alert_type", raw.get("event") or "deploy")
    elif payload.source == "new_relic":
        raw.setdefault("entity", raw.get("entity") or raw.get("condition_name"))
        raw.setdefault("alert_type", raw.get("policy_name") or "condition")
    elif payload.source == "manual_demo":
        raw.setdefault("service", raw.get("service") or raw.get("service_name"))

    if payload.description and not raw.get("description"):
        raw["description"] = payload.description

    return raw


def build_alert_signal_fields(payload: AlertIngestRequest) -> dict:
    raw = normalize_demo_payload(payload)
    return {
        "source": payload.source,
        "title": payload.title.strip(),
        "description": payload.description,
        "fired_at": payload.fired_at or datetime.now(tz=timezone.utc),
        "raw_payload": raw,
    }
