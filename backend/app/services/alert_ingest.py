"""Normalize demo alert payloads for ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.investigation_engine import AlertIngestRequest

_ALLOWED_SOURCES = frozenset(
    {"datadog", "render", "new_relic", "manual_demo", "sentry"}
)


def validate_alert_ingest(payload: AlertIngestRequest) -> None:
    if payload.source not in _ALLOWED_SOURCES:
        raise ValueError(f"Unsupported alert source: {payload.source}")
    if not payload.title.strip():
        raise ValueError("Alert title is required")


def normalize_demo_payload(payload: AlertIngestRequest) -> dict:
    """Map MVP demo payloads to a common correlation shape.

    Caller-supplied ``raw_payload`` keys are kept. Sentry service and alert
    type are filled only from fields the payload actually contains.
    """
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
    elif payload.source == "sentry":
        _fill_missing_sentry_metadata(raw)

    if payload.description and not raw.get("description"):
        raw["description"] = payload.description

    return raw


def extract_sentry_correlation_metadata(body: dict[str, Any]) -> dict[str, Any]:
    """Map a Sentry issue or issue-alert payload onto correlation metadata.

    ``provider`` is the monitor (``sentry``), not the affected service.
    ``service`` is the Sentry project slug/name, or an explicit service field
    or tag when the payload has one. ``alert_type`` is the exception/error
    type when Sentry sent one. It is never the placeholder ``"error"``.

    Missing facts are ``None``. Nothing here is guessed to help a later
    correlation score. Caller-supplied identity fields on ``body`` win over
    nested event/issue copies of the same fact.
    """
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    event = data.get("event") if isinstance(data.get("event"), dict) else {}
    issue = data.get("issue") if isinstance(data.get("issue"), dict) else {}
    issue_alert = data.get("issue_alert") if isinstance(data.get("issue_alert"), dict) else {}
    metric_alert = data.get("metric_alert") if isinstance(data.get("metric_alert"), dict) else {}

    event_meta = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    issue_meta = issue.get("metadata") if isinstance(issue.get("metadata"), dict) else {}
    body_meta = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}

    project_name, project_id = _coalesce_projects(
        issue.get("project"),
        event.get("project"),
        data.get("project"),
        body.get("project"),
        _metric_alert_project(metric_alert),
    )
    service = _first_str(
        body.get("service"),
        body.get("service_name"),
        project_name,
        _tag_value(event, "service"),
        _tag_value(issue, "service"),
        _tag_value(body, "service"),
    )

    event_exc_type, event_exc_value = _exception_parts(event)
    issue_exc_type, issue_exc_value = _exception_parts(issue)
    error_type = _first_str(
        body.get("error_type"),
        body.get("exception_type"),
        event_meta.get("type"),
        issue_meta.get("type"),
        body_meta.get("type"),
        event_exc_type,
        issue_exc_type,
    )
    exception_type = _first_str(
        body.get("exception_type"),
        event_exc_type,
        issue_exc_type,
        error_type,
    )
    # A caller-supplied alert_type is preserved, including a literal "error".
    # We only refuse to invent that word when the payload has no type at all.
    # Sentry's event ``type`` ("error", "default", …) is the event category,
    # not an exception class, so it is intentionally not read here.
    alert_type = _first_str(body.get("alert_type"), error_type)

    metadata: dict[str, Any] = {
        "provider": "sentry",
        "service": service,
        "project": project_name,
        "project_id": project_id,
        "alert_type": alert_type,
        "error_type": error_type,
        "exception_type": exception_type,
        "sentry_issue_id": _first_id(
            body.get("sentry_issue_id"),
            issue.get("id"),
            event.get("issue_id"),
            body.get("issue_id"),
        ),
        "sentry_event_id": _first_id(
            body.get("sentry_event_id"),
            event.get("event_id"),
            event.get("eventID"),
        ),
        "fingerprint": _fingerprint(
            body.get("fingerprint"),
            event.get("fingerprint"),
            issue.get("fingerprint"),
        ),
        "culprit": _first_str(
            body.get("culprit"),
            issue.get("culprit"),
            event.get("culprit"),
            event.get("location"),
            issue.get("location"),
        ),
        "environment": _first_str(
            body.get("environment"),
            body.get("env"),
            event.get("environment"),
            issue.get("environment"),
            _tag_value(event, "environment"),
            _tag_value(issue, "environment"),
            _tag_value(body, "environment"),
        ),
        "region": _first_str(
            body.get("region"),
            event.get("region"),
            _tag_value(event, "region"),
            _tag_value(issue, "region"),
            _tag_value(body, "region"),
        ),
        "level": _first_str(body.get("level"), event.get("level"), issue.get("level")),
        "sentry_url": _first_str(
            body.get("sentry_url"),
            issue.get("web_url"),
            issue.get("permalink"),
            event.get("web_url"),
            event.get("issue_url"),
        ),
        "triggered_rule": _first_str(
            body.get("triggered_rule"),
            data.get("triggered_rule"),
            issue_alert.get("title"),
        ),
        "action": _first_str(body.get("action")),
    }

    optional = {
        "exception_value": _first_str(
            body.get("exception_value"),
            event_meta.get("value"),
            issue_meta.get("value"),
            body_meta.get("value"),
            event_exc_value,
            issue_exc_value,
        ),
        "sentry_short_id": _first_str(
            body.get("sentry_short_id"),
            issue.get("shortId"),
            issue.get("short_id"),
        ),
        "release": _first_str(body.get("release"), event.get("release"), issue.get("release")),
    }
    for key, value in optional.items():
        if value is not None:
            metadata[key] = value
    return metadata


def _fill_missing_sentry_metadata(raw: dict[str, Any]) -> None:
    """Add extracted Sentry fields without replacing values the caller sent."""
    extracted = extract_sentry_correlation_metadata(raw)
    for key, value in extracted.items():
        if value is None:
            continue
        current = raw.get(key)
        if current is None or (isinstance(current, str) and not current.strip()):
            raw[key] = value


def _metric_alert_project(metric_alert: dict[str, Any]) -> Any:
    projects = metric_alert.get("projects")
    if isinstance(projects, list) and projects:
        return projects[0]
    return metric_alert.get("project")


def _coalesce_projects(*projects: Any) -> tuple[str | None, str | None]:
    name: str | None = None
    project_id: str | None = None
    for project in projects:
        found_name, found_id = _project_parts(project)
        if name is None and found_name:
            name = found_name
        if project_id is None and found_id:
            project_id = found_id
    return name, project_id


def _project_parts(project: Any) -> tuple[str | None, str | None]:
    """Return ``(slug_or_name, numeric_id)``.

    A numeric Sentry project id is not a service name. It is stored separately
    so a missing slug does not become a fake service such as ``"1"``.
    """
    if isinstance(project, dict):
        name = _nonempty_str(project.get("slug")) or _nonempty_str(project.get("name"))
        return name, _id_str(project.get("id"))
    if isinstance(project, str):
        text = project.strip()
        if not text:
            return None, None
        if text.isdigit():
            return None, text
        return text, None
    if isinstance(project, int) and not isinstance(project, bool):
        return None, str(project)
    return None, None


def _exception_parts(container: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return ``(type, value)`` from a Sentry exception interface.

    ``exception.values`` lists causes first and the raised exception last.
    """
    exc = container.get("exception")
    if not isinstance(exc, dict):
        return None, None
    values = exc.get("values")
    items = values if isinstance(values, list) else []
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        exc_type = _nonempty_str(item.get("type"))
        exc_value = _nonempty_str(item.get("value"))
        if exc_type or exc_value:
            return exc_type, exc_value
    return _nonempty_str(exc.get("type")), _nonempty_str(exc.get("value"))


def _tag_value(container: dict[str, Any], key: str) -> str | None:
    tags = container.get("tags")
    if isinstance(tags, dict):
        return _nonempty_str(tags.get(key))
    if not isinstance(tags, list):
        return None
    for item in tags:
        if isinstance(item, (list, tuple)) and len(item) >= 2 and str(item[0]) == key:
            return _nonempty_str(item[1])
        if isinstance(item, dict) and item.get("key") == key:
            return _nonempty_str(item.get("value"))
    return None


def _fingerprint(*candidates: Any) -> Any:
    for candidate in candidates:
        if isinstance(candidate, list) and any(
            _fingerprint_item_present(item) for item in candidate
        ):
            return list(candidate)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _fingerprint_item_present(item: Any) -> bool:
    if item is None:
        return False
    if isinstance(item, str):
        return bool(item.strip())
    return True


def _first_str(*values: Any) -> str | None:
    for value in values:
        text = _nonempty_str(value)
        if text:
            return text
    return None


def _first_id(*values: Any) -> str | None:
    for value in values:
        text = _id_str(value)
        if text:
            return text
    return None


def _nonempty_str(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _id_str(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def build_alert_signal_fields(payload: AlertIngestRequest) -> dict:
    raw = normalize_demo_payload(payload)
    return {
        "source": payload.source,
        "title": payload.title.strip(),
        "description": payload.description,
        "fired_at": payload.fired_at or datetime.now(tz=timezone.utc),
        "raw_payload": raw,
    }
