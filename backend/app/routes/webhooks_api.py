"""Public webhooks from external monitors (e.g. Sentry)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from sqlalchemy import select

from app.core.config import Settings
from app.core.logging import get_logger
from app.deps import DbSession
from app.models import Organization
from app.schemas.investigation_engine import AlertIngestResponse
from app.services.alert_correlation import AlertCorrelationService, AlertSignal
from app.services.investigation_engine.investigation_runner import InvestigationRunner

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
logger = get_logger(__name__)
_runner = InvestigationRunner()


def _require_secret(provided: str | None, settings: Settings) -> None:
    expected = (settings.sentry_webhook_secret or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sentry webhook is not configured",
        )
    if not provided or provided.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )


def _parse_sentry_alert(body: dict[str, Any]) -> tuple[str, str | None, dict[str, Any]]:
    """Turn a Sentry issue-alert / issue webhook payload into title/description/raw."""
    data = body.get("data") or {}
    event = data.get("event") or {}
    issue = data.get("issue") or {}
    issue_alert = data.get("issue_alert") or {}

    title = (
        event.get("title")
        or (issue.get("metadata") or {}).get("title")
        or issue.get("title")
        or body.get("action")
        or "Sentry alert"
    )
    if isinstance(title, str):
        title = title.strip() or "Sentry alert"
    else:
        title = "Sentry alert"

    description = (
        event.get("message")
        or issue.get("culprit")
        or issue_alert.get("title")
        or data.get("triggered_rule")
        or "Incoming Sentry alert"
    )
    if description is not None and not isinstance(description, str):
        description = str(description)

    project = event.get("project") or issue.get("project")
    if isinstance(project, dict):
        project = project.get("slug") or project.get("name")

    raw: dict[str, Any] = {
        "service": "focusflow-server",
        "alert_type": "error",
        "sentry_issue_id": str(issue.get("id") or event.get("issue_id") or ""),
        "sentry_url": (
            issue.get("web_url")
            or issue.get("permalink")
            or event.get("web_url")
        ),
        "level": event.get("level") or issue.get("level"),
        "culprit": issue.get("culprit") or event.get("culprit"),
        "project": project,
        "triggered_rule": data.get("triggered_rule") or issue_alert.get("title"),
        "provider": "sentry",
        "action": body.get("action"),
    }
    return title, description, raw


@router.post(
    "/sentry",
    response_model=AlertIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def sentry_webhook(
    request: Request,
    db: DbSession,
    x_breadcrumbs_webhook_secret: Annotated[str | None, Header()] = None,
    secret: Annotated[str | None, Query(description="Shared secret (for Sentry URLs)")] = None,
    auto_investigate: Annotated[bool, Query()] = True,
) -> AlertIngestResponse:
    """Public endpoint for Sentry issue alerts.

    Auth: ``X-Breadcrumbs-Webhook-Secret`` header **or** ``?secret=`` query param
    must match ``BREADCRUMBS_SENTRY_WEBHOOK_SECRET``.
    Org: ``BREADCRUMBS_SENTRY_WEBHOOK_ORG_ID``.
    """
    # Prefer a fresh Settings() so .env edits are visible without relying on
    # the process-wide lru_cache (which can stay stale across --reload races).
    settings = Settings()
    _require_secret(x_breadcrumbs_webhook_secret or secret, settings)

    raw_org = (settings.sentry_webhook_org_id or "").strip()
    if not raw_org:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sentry webhook org id is not configured",
        )
    try:
        org_id = uuid.UUID(raw_org)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sentry webhook org id is invalid",
        ) from exc

    org = db.scalar(select(Organization).where(Organization.id == org_id))
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sentry webhook org id does not exist",
        )

    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body",
        ) from exc

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook body must be a JSON object",
        )

    title, description, raw = _parse_sentry_alert(body)
    signal = AlertSignal.from_payload(
        organization_id=org_id,
        source="sentry",
        title=title,
        description=description,
        fired_at=datetime.now(tz=timezone.utc),
        raw_payload=raw,
    )
    result = AlertCorrelationService().ingest(db, signal)

    if auto_investigate:
        try:
            _runner.run(
                db,
                org_id,
                result.incident.id,
                trigger="sentry_webhook",
            )
        except Exception:
            logger.exception(
                "auto investigation failed for incident %s",
                result.incident.id,
            )

    return AlertIngestResponse(
        alert_id=result.alert.id,
        incident_id=result.incident.id,
    )
