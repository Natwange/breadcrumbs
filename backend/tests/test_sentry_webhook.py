"""Sentry → Breadcrumbs webhook tests."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.main import app
from app.models import Alert, Incident, InvestigationRun
from tests.conftest import seed_org_member

SECRET = "test-sentry-webhook-secret"


def _webhook_settings(org_id: str, *, secret: str = SECRET) -> Settings:
    return Settings(
        supabase_url="https://test.supabase.co",
        sentry_webhook_secret=secret,
        sentry_webhook_org_id=org_id,
    )


def test_sentry_webhook_rejects_missing_secret(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    _, org, _ = seed_org_member(db, role="owner")
    app.dependency_overrides[get_settings] = lambda: _webhook_settings(str(org.id))
    try:
        resp = client.post(
            "/api/webhooks/sentry?auto_investigate=false",
            json={"data": {"event": {"title": "boom"}}},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert resp.status_code == 401


def test_sentry_webhook_accepts_query_secret_and_creates_incident(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    _, org, _ = seed_org_member(db, role="owner")
    app.dependency_overrides[get_settings] = lambda: _webhook_settings(str(org.id))
    try:
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
    finally:
        app.dependency_overrides.pop(get_settings, None)

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
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    _, org, _ = seed_org_member(db, role="owner")
    app.dependency_overrides[get_settings] = lambda: _webhook_settings(str(org.id))
    try:
        resp = client.post(
            "/api/webhooks/sentry?auto_investigate=false",
            headers={"X-Breadcrumbs-Webhook-Secret": SECRET},
            json={"data": {"issue": {"title": "Header auth test"}}},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert resp.status_code == 201


def test_sentry_webhook_auto_investigate(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    _, org, _ = seed_org_member(db, role="owner")
    app.dependency_overrides[get_settings] = lambda: _webhook_settings(str(org.id))
    try:
        resp = client.post(
            f"/api/webhooks/sentry?secret={SECRET}",
            json={"data": {"event": {"title": "Auto investigate me"}}},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

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
