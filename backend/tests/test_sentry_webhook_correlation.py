"""Sentry webhook normalization + correlation regression tests.

These tests hit the real ``POST /api/webhooks/sentry`` route with realistic
Sentry issue-alert payloads. They distinguish:

* **Normalization** — how the webhook maps provider fields into ``raw_payload``
* **Correlation** — whether resulting alerts are grouped correctly

Because ``sentry_webhook`` constructs ``Settings()`` directly (not via
``get_settings``), secrets/org id are injected with ``monkeypatch`` env vars.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import Alert, Incident
from app.services.alert_ingest import normalize_demo_payload
from app.schemas.investigation_engine import AlertIngestRequest
from tests.conftest import seed_org_member

SECRET = "test-sentry-webhook-secret"


def _enable_webhook(monkeypatch: pytest.MonkeyPatch, org_id: uuid.UUID) -> None:
    monkeypatch.setenv("BREADCRUMBS_SENTRY_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("BREADCRUMBS_SENTRY_WEBHOOK_ORG_ID", str(org_id))


def _sentry_issue_payload(
    *,
    issue_id: str,
    title: str,
    culprit: str,
    error_type: str,
    project_slug: str = "focusflow-server",
    fingerprint: list[str] | None = None,
    level: str = "error",
) -> dict[str, Any]:
    """Realistic Sentry issue-alert style body (subset used in production)."""
    return {
        "action": "triggered",
        "data": {
            "event": {
                "title": title,
                "message": title,
                "level": level,
                "culprit": culprit,
                "fingerprint": fingerprint or [error_type.lower(), culprit],
                "issue_id": issue_id,
                "project": project_slug,
                "metadata": {"type": error_type, "value": title},
            },
            "issue": {
                "id": issue_id,
                "title": title,
                "culprit": culprit,
                "level": level,
                "permalink": f"https://sentry.io/issues/{issue_id}/",
                "project": {"slug": project_slug, "name": project_slug},
                "metadata": {"type": error_type, "title": title},
            },
            "triggered_rule": "Send a notification for high priority issues",
        },
    }


def _post_sentry(
    client: TestClient,
    payload: dict[str, Any],
    *,
    auto_investigate: bool = False,
):
    return client.post(
        f"/api/webhooks/sentry?secret={SECRET}&auto_investigate={str(auto_investigate).lower()}",
        json=payload,
    )


# ===========================================================================
# Normalization tests (webhook mapping + demo ingest defaults)
# ===========================================================================


def test_webhook_does_not_hardcode_service_when_project_slug_present(
    client: TestClient,
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    """Normalization policy: prefer Sentry project slug as service name."""
    db = session_factory()
    _, org, _ = seed_org_member(db, role="owner")
    _enable_webhook(monkeypatch, org.id)

    resp = _post_sentry(
        client,
        _sentry_issue_payload(
            issue_id="501",
            title="TypeError: boom",
            culprit="app.handlers.checkout",
            error_type="TypeError",
            project_slug="payments-api",
        ),
    )
    assert resp.status_code == 201, resp.text
    alert = db.get(Alert, uuid.UUID(resp.json()["alert_id"]))
    assert alert is not None
    service = (alert.raw_payload or {}).get("service")
    assert service == "payments-api", (
        f"Expected service from project slug 'payments-api', got {service!r}. "
        "Hardcoded focusflow-server (or other default) is misleading."
    )


def test_webhook_does_not_hardcode_generic_alert_type(
    client: TestClient,
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    """Normalization policy: alert_type should reflect error identity, not 'error'."""
    db = session_factory()
    _, org, _ = seed_org_member(db, role="owner")
    _enable_webhook(monkeypatch, org.id)

    resp = _post_sentry(
        client,
        _sentry_issue_payload(
            issue_id="502",
            title="ConnectionRefusedError: redis down",
            culprit="app.cache.redis",
            error_type="ConnectionRefusedError",
        ),
    )
    assert resp.status_code == 201, resp.text
    alert = db.get(Alert, uuid.UUID(resp.json()["alert_id"]))
    assert alert is not None
    raw = alert.raw_payload or {}
    assert raw.get("alert_type") != "error" or raw.get("error_type") == "ConnectionRefusedError", (
        "Generic alert_type='error' without a more specific error identity "
        f"creates artificial similarity. raw={raw}"
    )
    # Stronger expectation for the redesign: expose typed error metadata.
    assert raw.get("error_type") == "ConnectionRefusedError" or raw.get("alert_type") == (
        "ConnectionRefusedError"
    ), f"Error type from Sentry metadata was not preserved for correlation: {raw}"


def test_webhook_preserves_issue_id_culprit_and_fingerprint_fields(
    client: TestClient,
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    db = session_factory()
    _, org, _ = seed_org_member(db, role="owner")
    _enable_webhook(monkeypatch, org.id)

    fp = ["connectionrefusederror", "app.cache.redis"]
    resp = _post_sentry(
        client,
        _sentry_issue_payload(
            issue_id="777",
            title="ConnectionRefusedError: redis down",
            culprit="app.cache.redis",
            error_type="ConnectionRefusedError",
            fingerprint=fp,
        ),
    )
    assert resp.status_code == 201, resp.text
    raw = (db.get(Alert, uuid.UUID(resp.json()["alert_id"])).raw_payload) or {}
    assert str(raw.get("sentry_issue_id") or "") == "777"
    assert raw.get("culprit") == "app.cache.redis"
    # Fingerprint is present on the provider payload; normalization should keep it.
    assert raw.get("fingerprint") == fp or raw.get("fingerprint") == fp[0], (
        f"Fingerprint from Sentry event was dropped during normalization: {raw}"
    )


def test_demo_ingest_normalization_does_not_invent_sentry_service():
    """``normalize_demo_payload`` must not invent focusflow-server for Sentry."""
    # AlertIngestRequest currently rejects source=sentry at the schema layer;
    # construct a minimal stand-in using model_construct to unit-test the
    # normalizer itself without going through the restricted Literal.
    payload = AlertIngestRequest.model_construct(
        source="sentry",
        title="Error: something",
        description=None,
        fired_at=None,
        raw_payload={},
    )
    raw = normalize_demo_payload(payload)
    assert raw.get("service") != "focusflow-server", (
        "Demo Sentry normalization invents service=focusflow-server when missing"
    )
    assert raw.get("alert_type") != "error" or "alert_type" not in raw, (
        "Demo Sentry normalization invents alert_type=error when missing"
    )


def test_api_alerts_ingest_rejects_sentry_and_pagerduty_sources(
    client: TestClient, session_factory: sessionmaker
):
    """Document DemoAlertSource restriction on ``POST /api/alerts/ingest``."""
    from tests.conftest import auth_headers, make_token

    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    headers = auth_headers(make_token(str(user.id), user.email), org.id)

    for source in ("sentry", "pagerduty"):
        resp = client.post(
            "/api/alerts/ingest",
            headers=headers,
            json={"source": source, "title": "x", "raw_payload": {}},
        )
        assert resp.status_code == 422, (
            f"Expected schema rejection for source={source}, got {resp.status_code}"
        )


# ===========================================================================
# Correlation via the real webhook route
# ===========================================================================


def test_webhook_unrelated_sentry_errors_same_project_remain_separate(
    client: TestClient,
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    """FocusFlow failure mode: unrelated issues must not share one incident."""
    db = session_factory()
    _, org, _ = seed_org_member(db, role="owner")
    _enable_webhook(monkeypatch, org.id)

    first = _post_sentry(
        client,
        _sentry_issue_payload(
            issue_id="1001",
            title="TypeError: Cannot read property 'id' of undefined",
            culprit="app.api.users.get_user",
            error_type="TypeError",
            project_slug="focusflow-server",
        ),
    )
    second = _post_sentry(
        client,
        _sentry_issue_payload(
            issue_id="1002",
            title="ConnectionRefusedError: Redis connection refused",
            culprit="app.cache.redis.connect",
            error_type="ConnectionRefusedError",
            project_slug="focusflow-server",
        ),
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text

    assert first.json()["incident_id"] != second.json()["incident_id"], (
        "Unrelated Sentry issues from the same project were merged into one "
        f"incident ({first.json()['incident_id']})."
    )


def test_webhook_repeated_same_issue_correlates(
    client: TestClient,
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    db = session_factory()
    _, org, _ = seed_org_member(db, role="owner")
    _enable_webhook(monkeypatch, org.id)

    payload = _sentry_issue_payload(
        issue_id="2002",
        title="ValueError: invalid card token",
        culprit="app.billing.charge",
        error_type="ValueError",
    )
    first = _post_sentry(client, payload)
    second = _post_sentry(client, payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["incident_id"] == second.json()["incident_id"]


def test_webhook_similar_titles_different_projects_do_not_merge(
    client: TestClient,
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    db = session_factory()
    _, org, _ = seed_org_member(db, role="owner")
    _enable_webhook(monkeypatch, org.id)

    first = _post_sentry(
        client,
        _sentry_issue_payload(
            issue_id="3001",
            title="Elevated error rate on checkout",
            culprit="checkout",
            error_type="Error",
            project_slug="checkout-api",
        ),
    )
    second = _post_sentry(
        client,
        _sentry_issue_payload(
            issue_id="3002",
            title="Elevated error rate on checkout",
            culprit="inventory",
            error_type="Error",
            project_slug="inventory-api",
        ),
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["incident_id"] != second.json()["incident_id"], (
        "Similar titles across different Sentry projects merged incorrectly"
    )


def test_webhook_missing_project_does_not_invent_focusflow_server(
    client: TestClient,
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    db = session_factory()
    _, org, _ = seed_org_member(db, role="owner")
    _enable_webhook(monkeypatch, org.id)

    resp = _post_sentry(
        client,
        {
            "action": "triggered",
            "data": {
                "event": {"title": "Bare error without project", "level": "error"},
                "issue": {"id": "4001", "title": "Bare error without project"},
            },
        },
    )
    assert resp.status_code == 201, resp.text
    raw = (db.get(Alert, uuid.UUID(resp.json()["alert_id"])).raw_payload) or {}
    assert raw.get("service") != "focusflow-server", (
        f"Missing project invented service=focusflow-server; raw={raw}"
    )


def test_webhook_org_isolation(
    client: TestClient,
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    """Webhook is pinned to configured org; alerts must land only there."""
    db = session_factory()
    _, org_a, _ = seed_org_member(db, role="owner", email="wa@example.com")
    _, org_b, _ = seed_org_member(db, role="owner", email="wb@example.com")
    _enable_webhook(monkeypatch, org_a.id)

    resp = _post_sentry(
        client,
        _sentry_issue_payload(
            issue_id="5001",
            title="Org isolation check",
            culprit="app.main",
            error_type="RuntimeError",
        ),
    )
    assert resp.status_code == 201
    incident = db.get(Incident, uuid.UUID(resp.json()["incident_id"]))
    assert incident is not None
    assert incident.organization_id == org_a.id

    foreign = list(
        db.scalars(select(Alert).where(Alert.organization_id == org_b.id)).all()
    )
    assert foreign == []
