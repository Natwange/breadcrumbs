"""Phase 4 alert correlation tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import Alert, AuditLog, Incident
from app.services.audit import AUDIT_ALERT_CORRELATED
from tests.conftest import auth_headers, make_token, seed_org_member


def test_alerts_from_multiple_tools_share_one_incident(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    token = make_token(str(user.id), user.email)
    headers = auth_headers(token, org.id)
    now = datetime.now(tz=timezone.utc)

    first = client.post(
        "/alerts",
        headers=headers,
        json={
            "source": "datadog",
            "title": "checkout latency spike",
            "fired_at": now.isoformat(),
            "raw_payload": {
                "service": "checkout-api",
                "alert_type": "latency",
                "environment": "production",
                "region": "us-east-1",
            },
        },
    )
    assert first.status_code == 201
    first_body = first.json()
    assert first_body["created_incident"] is True
    incident_id = first_body["incident_id"]

    second = client.post(
        "/alerts",
        headers=headers,
        json={
            "source": "pagerduty",
            "title": "checkout latency spike",
            "fired_at": (now + timedelta(minutes=5)).isoformat(),
            "raw_payload": {
                "service": "checkout-api",
                "alert_type": "latency",
                "environment": "production",
                "region": "us-east-1",
            },
        },
    )
    assert second.status_code == 201
    second_body = second.json()
    assert second_body["incident_id"] == incident_id
    assert second_body["created_incident"] is False
    assert second_body["method"] == "attached_to_open_incident"

    alerts = list(
        db.scalars(select(Alert).where(Alert.organization_id == org.id)).all()
    )
    assert len(alerts) == 2
    assert {a.source for a in alerts} == {"datadog", "pagerduty"}
    assert all(str(a.incident_id) == incident_id for a in alerts)


def test_resolved_incident_not_used_for_correlation(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    token = make_token(str(user.id), user.email)
    headers = auth_headers(token, org.id)
    now = datetime.now(tz=timezone.utc)

    resolved = Incident(
        organization_id=org.id,
        title="old checkout latency spike",
        status="resolved",
        detected_at=now - timedelta(hours=1),
        metadata_={
            "service": "checkout-api",
            "environment": "production",
            "region": "us-east-1",
        },
    )
    db.add(resolved)
    db.commit()

    resp = client.post(
        "/alerts",
        headers=headers,
        json={
            "source": "datadog",
            "title": "checkout latency spike",
            "fired_at": now.isoformat(),
            "raw_payload": {
                "service": "checkout-api",
                "alert_type": "latency",
                "environment": "production",
                "region": "us-east-1",
            },
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["created_incident"] is True
    assert body["incident_id"] != str(resolved.id)


def test_uncertain_alert_creates_new_incident(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    token = make_token(str(user.id), user.email)
    headers = auth_headers(token, org.id)
    now = datetime.now(tz=timezone.utc)

    existing = client.post(
        "/incidents",
        headers=headers,
        json={"title": "Unrelated database issue", "status": "open"},
    )
    assert existing.status_code == 201

    resp = client.post(
        "/alerts",
        headers=headers,
        json={
            "source": "sentry",
            "title": "completely different payment failure",
            "fired_at": now.isoformat(),
            "raw_payload": {
                "service": "payments",
                "alert_type": "error_rate",
                "environment": "staging",
            },
        },
    )
    assert resp.status_code == 201
    assert resp.json()["created_incident"] is True


def test_alert_correlation_writes_audit_log(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    token = make_token(str(user.id), user.email)

    resp = client.post(
        "/alerts",
        headers=auth_headers(token, org.id),
        json={
            "source": "datadog",
            "title": "api errors",
            "raw_payload": {"service": "api", "alert_type": "errors"},
        },
    )
    assert resp.status_code == 201

    audits = list(
        db.scalars(
            select(AuditLog).where(
                AuditLog.organization_id == org.id,
                AuditLog.action == AUDIT_ALERT_CORRELATED,
            )
        ).all()
    )
    assert len(audits) == 1
