"""Resolve incident endpoint tests."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.models import Alert, Incident
from tests.conftest import auth_headers, make_token, seed_org_member


def test_resolve_incident_marks_incident_and_alerts(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    token = make_token(str(user.id), user.email)

    incident = Incident(
        organization_id=org.id,
        title="Login outage",
        status="open",
    )
    db.add(incident)
    db.flush()
    alert = Alert(
        organization_id=org.id,
        incident_id=incident.id,
        source="sentry",
        title="Error: debug-sentry",
        status="firing",
    )
    db.add(alert)
    db.commit()
    incident_id = incident.id
    alert_id = alert.id

    resp = client.post(
        f"/incidents/{incident_id}/resolve",
        headers=auth_headers(token, org.id),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"

    db.expire_all()
    updated = db.get(Incident, incident_id)
    assert updated is not None
    assert updated.status == "resolved"
    assert updated.resolved_at is not None

    updated_alert = db.get(Alert, alert_id)
    assert updated_alert is not None
    assert updated_alert.status == "resolved"


def test_resolve_incident_is_idempotent(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="owner")
    token = make_token(str(user.id), user.email)

    created = client.post(
        "/incidents",
        headers=auth_headers(token, org.id),
        json={"title": "Already done"},
    )
    assert created.status_code == 201
    incident_id = created.json()["id"]

    first = client.post(
        f"/incidents/{incident_id}/resolve",
        headers=auth_headers(token, org.id),
    )
    second = client.post(
        f"/incidents/{incident_id}/resolve",
        headers=auth_headers(token, org.id),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "resolved"


def test_viewer_cannot_resolve_incident(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="viewer")
    token = make_token(str(user.id), user.email)
    incident = Incident(organization_id=org.id, title="Locked", status="open")
    db.add(incident)
    db.commit()

    resp = client.post(
        f"/incidents/{incident.id}/resolve",
        headers=auth_headers(token, org.id),
    )
    assert resp.status_code == 403
