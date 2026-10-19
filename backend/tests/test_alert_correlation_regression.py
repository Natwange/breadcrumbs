"""Regression tests for alert correlation algorithm behavior.

These tests exercise ``AlertCorrelationService`` and the authenticated
``POST /alerts`` path (raw ``AlertSignal`` ingestion without webhook
normalization). They document intended correlation *policy* and will fail
where the current implementation does not yet match that policy.

Policy notes (uncertain cases are left unconstrained unless stated):
* Strong identity (same provider issue id / fingerprint) → should correlate.
* Distinct error identities on the same service → should stay separate.
* Title similarity alone across different services → should not merge.
* Sparse metadata → must not attach with unjustifiably high confidence.
* Cross-provider alerts may correlate when service + type + message align.
* Organizations are hard isolation boundaries.
* Resolved incidents are never reused for silent attachment.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Alert, AlertCorrelation, AuditLog, Incident
from app.services.alert_correlation import AlertCorrelationService, AlertSignal
from app.services.audit import AUDIT_ALERT_CORRELATED
from tests.conftest import auth_headers, make_token, seed_org_member


def _ingest(
    db: Session,
    org_id: uuid.UUID,
    *,
    source: str,
    title: str,
    description: str | None = None,
    fired_at: datetime | None = None,
    raw_payload: dict | None = None,
):
    return AlertCorrelationService().ingest(
        db,
        AlertSignal.from_payload(
            organization_id=org_id,
            source=source,
            title=title,
            description=description,
            fired_at=fired_at or datetime.now(tz=timezone.utc),
            raw_payload=raw_payload,
        ),
    )


# ---------------------------------------------------------------------------
# 1. Unrelated errors on the same service must stay separate
# ---------------------------------------------------------------------------


def test_unrelated_errors_same_service_remain_separate(session: Session):
    """Two distinct exception identities on one service → two incidents.

    Intended policy: same service is necessary but not sufficient. Without a
    shared strong identifier (issue id / fingerprint) or clear causal link,
    different error types/culprits must not merge.
    """
    _, org, _ = seed_org_member(session, role="member")
    now = datetime.now(tz=timezone.utc)

    first = _ingest(
        session,
        org.id,
        source="sentry",
        title="TypeError: Cannot read property 'id' of undefined",
        description="app.api.users.get_user",
        fired_at=now,
        raw_payload={
            "service": "focusflow-server",
            "alert_type": "error",
            "error_type": "TypeError",
            "culprit": "app.api.users.get_user",
            "sentry_issue_id": "111",
            "fingerprint": ["typeerror-users-get"],
        },
    )
    second = _ingest(
        session,
        org.id,
        source="sentry",
        title="ConnectionRefusedError: Redis connection refused",
        description="app.cache.redis.connect",
        fired_at=now + timedelta(minutes=2),
        raw_payload={
            "service": "focusflow-server",
            "alert_type": "error",
            "error_type": "ConnectionRefusedError",
            "culprit": "app.cache.redis.connect",
            "sentry_issue_id": "222",
            "fingerprint": ["redis-connection-refused"],
        },
    )

    assert second.created_incident is True, (
        "Distinct Sentry issues on the same service were merged; correlation "
        f"confidence={second.confidence}, factors={second.factors}"
    )
    assert second.incident.id != first.incident.id


# ---------------------------------------------------------------------------
# 2. Repeated notifications for the same Sentry issue should correlate
# ---------------------------------------------------------------------------


def test_repeated_same_sentry_issue_correlates(session: Session):
    """Same issue id / fingerprint / title → attach to the open incident."""
    _, org, _ = seed_org_member(session, role="member")
    now = datetime.now(tz=timezone.utc)
    payload = {
        "service": "focusflow-server",
        "alert_type": "error",
        "error_type": "ValueError",
        "culprit": "app.billing.charge",
        "sentry_issue_id": "99901",
        "fingerprint": ["valueerror-billing-charge"],
    }

    first = _ingest(
        session,
        org.id,
        source="sentry",
        title="ValueError: invalid card token",
        description="app.billing.charge",
        fired_at=now,
        raw_payload=payload,
    )
    second = _ingest(
        session,
        org.id,
        source="sentry",
        title="ValueError: invalid card token",
        description="app.billing.charge",
        fired_at=now + timedelta(minutes=3),
        raw_payload=payload,
    )

    assert second.created_incident is False
    assert second.incident.id == first.incident.id
    assert second.method == "attached_to_open_incident"


# ---------------------------------------------------------------------------
# 3. Different exception types / culprits must not auto-merge
# ---------------------------------------------------------------------------


def test_different_exception_types_same_service_do_not_auto_merge(session: Session):
    _, org, _ = seed_org_member(session, role="member")
    now = datetime.now(tz=timezone.utc)

    first = _ingest(
        session,
        org.id,
        source="sentry",
        title="KeyError: 'user_id'",
        fired_at=now,
        raw_payload={
            "service": "api",
            "alert_type": "error",
            "error_type": "KeyError",
            "culprit": "app.auth.session",
            "sentry_issue_id": "a1",
        },
    )
    second = _ingest(
        session,
        org.id,
        source="sentry",
        title="TimeoutError: upstream deadline exceeded",
        fired_at=now + timedelta(minutes=1),
        raw_payload={
            "service": "api",
            "alert_type": "error",
            "error_type": "TimeoutError",
            "culprit": "app.payments.gateway",
            "sentry_issue_id": "a2",
        },
    )

    assert second.incident.id != first.incident.id, (
        f"Different exception types merged (confidence={second.confidence}, "
        f"factors={second.factors})"
    )


# ---------------------------------------------------------------------------
# 4. Similar titles from unrelated services must not auto-merge
# ---------------------------------------------------------------------------


def test_similar_titles_different_services_do_not_merge(session: Session):
    _, org, _ = seed_org_member(session, role="member")
    now = datetime.now(tz=timezone.utc)

    first = _ingest(
        session,
        org.id,
        source="datadog",
        title="Elevated error rate on checkout",
        fired_at=now,
        raw_payload={
            "service": "checkout-api",
            "alert_type": "error_rate",
            "environment": "production",
        },
    )
    second = _ingest(
        session,
        org.id,
        source="datadog",
        title="Elevated error rate on checkout",
        fired_at=now + timedelta(minutes=2),
        raw_payload={
            "service": "inventory-api",
            "alert_type": "error_rate",
            "environment": "production",
        },
    )

    assert second.incident.id != first.incident.id, (
        "Similar titles across different services merged; "
        f"confidence={second.confidence}, factors={second.factors}"
    )


# ---------------------------------------------------------------------------
# 5. Sparse metadata must not produce unjustifiably high confidence
# ---------------------------------------------------------------------------


def test_sparse_metadata_does_not_inflate_attach_confidence(session: Session):
    """Title-only overlap must not attach with near-certainty.

    Intended policy: if the only soft signal is textual similarity, either
    create a new incident or attach with low/moderate confidence — never
    score as if rich identity evidence were present.
    """
    _, org, _ = seed_org_member(session, role="member")
    now = datetime.now(tz=timezone.utc)

    _first = _ingest(
        session,
        org.id,
        source="manual_demo",
        title="Something went wrong in production",
        fired_at=now,
        raw_payload={},  # intentionally sparse
    )
    second = _ingest(
        session,
        org.id,
        source="manual_demo",
        title="Something went wrong in production systems",
        fired_at=now + timedelta(minutes=1),
        raw_payload={},  # still sparse — no service / type / fingerprint
    )

    if not second.created_incident:
        assert second.confidence < 0.75, (
            "Sparse title-only match attached with inflated confidence "
            f"{second.confidence}; factors={second.factors}"
        )


# ---------------------------------------------------------------------------
# 6. Cross-provider alerts describing the same incident can correlate
# ---------------------------------------------------------------------------


def test_cross_provider_same_incident_correlates_with_sufficient_evidence(
    session: Session,
):
    """Preserve intended multi-tool grouping when evidence is rich and aligned."""
    _, org, _ = seed_org_member(session, role="member")
    now = datetime.now(tz=timezone.utc)

    first = _ingest(
        session,
        org.id,
        source="datadog",
        title="checkout latency spike",
        fired_at=now,
        raw_payload={
            "service": "checkout-api",
            "alert_type": "latency",
            "environment": "production",
            "region": "us-east-1",
        },
    )
    second = _ingest(
        session,
        org.id,
        source="pagerduty",
        title="checkout latency spike",
        fired_at=now + timedelta(minutes=4),
        raw_payload={
            "service": "checkout-api",
            "alert_type": "latency",
            "environment": "production",
            "region": "us-east-1",
        },
    )

    assert second.incident.id == first.incident.id
    assert second.created_incident is False


# ---------------------------------------------------------------------------
# 7. Different organizations must never correlate
# ---------------------------------------------------------------------------


def test_alerts_from_different_orgs_never_correlate(session: Session):
    _, org_a, _ = seed_org_member(session, role="member", email="a@example.com")
    _, org_b, _ = seed_org_member(session, role="member", email="b@example.com")
    now = datetime.now(tz=timezone.utc)
    payload = {
        "service": "checkout-api",
        "alert_type": "latency",
        "environment": "production",
    }

    first = _ingest(
        session,
        org_a.id,
        source="datadog",
        title="checkout latency spike",
        fired_at=now,
        raw_payload=payload,
    )
    second = _ingest(
        session,
        org_b.id,
        source="datadog",
        title="checkout latency spike",
        fired_at=now + timedelta(minutes=1),
        raw_payload=payload,
    )

    assert second.incident.id != first.incident.id
    assert second.incident.organization_id == org_b.id
    assert first.incident.organization_id == org_a.id


# ---------------------------------------------------------------------------
# 8. Resolved incidents must not be silently reused
# ---------------------------------------------------------------------------


def test_resolved_incident_not_silently_reused(session: Session):
    _, org, _ = seed_org_member(session, role="member")
    now = datetime.now(tz=timezone.utc)

    resolved = Incident(
        organization_id=org.id,
        title="checkout latency spike",
        status="resolved",
        detected_at=now - timedelta(hours=2),
        metadata_={
            "service": "checkout-api",
            "environment": "production",
            "region": "us-east-1",
        },
    )
    session.add(resolved)
    session.commit()

    result = _ingest(
        session,
        org.id,
        source="datadog",
        title="checkout latency spike",
        fired_at=now,
        raw_payload={
            "service": "checkout-api",
            "alert_type": "latency",
            "environment": "production",
            "region": "us-east-1",
        },
    )

    assert result.created_incident is True
    assert result.incident.id != resolved.id


# ---------------------------------------------------------------------------
# 9 / 10. Explainability via service result + audit (API surface is limited)
# ---------------------------------------------------------------------------


def test_correlation_result_exposes_factors_on_service_object(session: Session):
    """Service-layer CorrelationResult must carry the factor breakdown."""
    _, org, _ = seed_org_member(session, role="member")
    result = _ingest(
        session,
        org.id,
        source="datadog",
        title="api errors",
        raw_payload={"service": "api", "alert_type": "errors"},
    )

    assert isinstance(result.factors, dict)
    assert result.factors, "Expected non-empty factors explaining the decision"
    assert result.method in {"created_new_incident", "attached_to_open_incident"}


def test_alerts_api_returns_confidence_and_method_but_not_factors(
    client: TestClient, session_factory: sessionmaker
):
    """Document current API explainability: confidence/method yes, factors no.

    ``POST /alerts`` returns confidence/method/created_incident. Factor detail
    is only persisted on the audit log today — redesign should surface it.
    """
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
    body = resp.json()
    assert "confidence" in body
    assert "method" in body
    assert "created_incident" in body
    assert "factors" not in body

    audits = list(
        db.scalars(
            select(AuditLog).where(
                AuditLog.organization_id == org.id,
                AuditLog.action == AUDIT_ALERT_CORRELATED,
            )
        ).all()
    )
    assert len(audits) == 1
    assert isinstance((audits[0].metadata_ or {}).get("factors"), dict)


def test_correlation_key_is_stored_but_not_used_to_find_existing_alerts(
    session: Session,
):
    """Document that correlation_key is computed/stored, not queried for grouping.

    Intended redesign: strong keys (issue id / fingerprint) should drive
    attachment. Today the key is written then ignored during candidate search.
    """
    _, org, _ = seed_org_member(session, role="member")
    now = datetime.now(tz=timezone.utc)
    payload = {
        "service": "billing",
        "alert_type": "error",
        "sentry_issue_id": "shared-issue-42",
        "fingerprint": ["billing-shared"],
    }

    first = _ingest(
        session,
        org.id,
        source="sentry",
        title="Billing failure A",
        fired_at=now,
        raw_payload=payload,
    )
    # Deliberately different title so message similarity is weak; same issue id
    # in payload — a key-aware correlator would still attach.
    second = _ingest(
        session,
        org.id,
        source="sentry",
        title="Completely different wording for the same billing outage",
        fired_at=now + timedelta(minutes=2),
        raw_payload=payload,
    )

    assert first.alert.correlation_key
    assert second.alert.correlation_key
    # Today's key hashes title, so wording drift yields different keys even for
    # the same provider issue — evidence the key is not a stable issue identity.
    assert first.alert.correlation_key != second.alert.correlation_key

    correlations = list(
        session.scalars(
            select(AlertCorrelation).where(AlertCorrelation.organization_id == org.id)
        ).all()
    )
    assert len(correlations) == 2

    # Policy: same provider issue id should correlate even when titles diverge.
    assert second.incident.id == first.incident.id, (
        "Same sentry_issue_id did not correlate when titles differed — "
        "correlation_key/issue id is not driving grouping. "
        f"keys=({first.alert.correlation_key}, {second.alert.correlation_key}), "
        f"factors={second.factors}"
    )


def test_alerts_from_multiple_tools_still_share_one_incident_via_http(
    client: TestClient, session_factory: sessionmaker
):
    """Preserve existing Phase-4 multi-tool behavior through POST /alerts."""
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
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["incident_id"] == first.json()["incident_id"]

    alerts = list(db.scalars(select(Alert).where(Alert.organization_id == org.id)).all())
    assert len(alerts) == 2
