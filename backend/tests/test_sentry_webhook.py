"""Sentry → Breadcrumbs webhook tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import Alert, Incident, InvestigationRun
from tests.conftest import seed_org_member

SECRET = "test-sentry-webhook-secret"


def _enable_webhook(monkeypatch: pytest.MonkeyPatch, org_id: uuid.UUID) -> None:
    # ``sentry_webhook`` constructs ``Settings()`` directly, so dependency
    # overrides on ``get_settings`` are ignored. Env vars are the supported
    # test seam without changing production code.
    monkeypatch.setenv("BREADCRUMBS_SENTRY_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("BREADCRUMBS_SENTRY_WEBHOOK_ORG_ID", str(org_id))


def test_sentry_webhook_rejects_missing_secret(
    client: TestClient,
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    db = session_factory()
    _, org, _ = seed_org_member(db, role="owner")
    _enable_webhook(monkeypatch, org.id)
    resp = client.post(
        "/api/webhooks/sentry?auto_investigate=false",
        json={"data": {"event": {"title": "boom"}}},
    )
    assert resp.status_code == 401


def test_sentry_webhook_accepts_query_secret_and_creates_incident(
    client: TestClient,
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    db = session_factory()
    _, org, _ = seed_org_member(db, role="owner")
    _enable_webhook(monkeypatch, org.id)
    resp = client.post(
        f"/api/webhooks/sentry?secret={SECRET}&auto_investigate=false",
        json={
            "action": "triggered",
            "data": {
                "event": {
                    "title": "Error: Test error from /debug-sentry",
                    "message": "Test error from /debug-sentry",
                    "level": "error",
                },
                "issue": {
                    "id": "12345",
                    "title": "Error: Test error from /debug-sentry",
                    "culprit": "app.get(/debug-sentry)",
                    "permalink": "https://sentry.io/issues/12345/",
                    "project": {"slug": "focusflow-server"},
                },
            },
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "alert_id" in body
    assert "incident_id" in body

    alert = db.get(Alert, uuid.UUID(body["alert_id"]))
    assert alert is not None
    assert alert.source == "sentry"
    assert "debug-sentry" in (alert.title or "")
    incident = db.get(Incident, uuid.UUID(body["incident_id"]))
    assert incident is not None
    assert incident.organization_id == org.id


def test_sentry_webhook_accepts_header_secret(
    client: TestClient,
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    db = session_factory()
    _, org, _ = seed_org_member(db, role="owner")
    _enable_webhook(monkeypatch, org.id)
    resp = client.post(
        "/api/webhooks/sentry?auto_investigate=false",
        headers={"X-Breadcrumbs-Webhook-Secret": SECRET},
        json={"data": {"issue": {"title": "Header auth test"}}},
    )
    assert resp.status_code == 201


def test_sentry_webhook_auto_investigate(
    client: TestClient,
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
):
    db = session_factory()
    _, org, _ = seed_org_member(db, role="owner")
    _enable_webhook(monkeypatch, org.id)
    resp = client.post(
        f"/api/webhooks/sentry?secret={SECRET}",
        json={"data": {"event": {"title": "Auto investigate me"}}},
    )

    assert resp.status_code == 201
    incident_id = uuid.UUID(resp.json()["incident_id"])
    runs = list(
        db.scalars(
            select(InvestigationRun).where(
                InvestigationRun.incident_id == incident_id
            )
        ).all()
    )
    assert len(runs) == 1
    assert runs[0].trigger == "sentry_webhook"
