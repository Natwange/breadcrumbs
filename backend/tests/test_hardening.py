"""Phase 12 production hardening tests: request IDs, rate limiting, Sentry."""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.core.observability import init_sentry
from app.core.rate_limit import RateLimiter, get_rate_limiter
from app.core.request_context import RequestIdFilter, request_id_var
from app.main import REQUEST_ID_HEADER, app
from tests.conftest import auth_headers, make_token, seed_org_member

# --------------------------------------------------------------------------
# Request IDs
# --------------------------------------------------------------------------


def test_response_includes_generated_request_id(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get(REQUEST_ID_HEADER)


def test_incoming_request_id_is_echoed(client: TestClient):
    resp = client.get("/health", headers={REQUEST_ID_HEADER: "trace-abc-123"})
    assert resp.headers.get(REQUEST_ID_HEADER) == "trace-abc-123"


def test_request_id_filter_sets_default_when_missing():
    record = logging.LogRecord("t", logging.INFO, "f", 1, "msg", (), None)
    request_id_var.set(None)
    assert RequestIdFilter().filter(record) is True
    assert record.request_id == "-"

    request_id_var.set("req-42")
    RequestIdFilter().filter(record)
    assert record.request_id == "req-42"
    request_id_var.set(None)


# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------


def test_rate_limiter_unit_blocks_over_limit():
    limiter = RateLimiter()
    for _ in range(3):
        limiter.check("k", limit=3, window_seconds=60)
    try:
        limiter.check("k", limit=3, window_seconds=60)
        assert False, "expected HTTP 429"
    except Exception as exc:  # HTTPException
        assert getattr(exc, "status_code", None) == 429


def test_rate_limiter_zero_limit_is_noop():
    limiter = RateLimiter()
    for _ in range(100):
        limiter.check("k", limit=0, window_seconds=60)  # never raises


def test_rate_limiter_separate_keys_isolated():
    limiter = RateLimiter()
    limiter.check("org-a", limit=1, window_seconds=60)
    # Different key still allowed.
    limiter.check("org-b", limit=1, window_seconds=60)


def test_artifact_upload_endpoint_rate_limited(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    token = make_token(str(user.id), user.email)

    low_limit = Settings(
        supabase_url="https://test.supabase.co",
        rate_limit_artifact_upload_per_min=2,
    )
    get_rate_limiter().reset()
    app.dependency_overrides[get_settings] = lambda: low_limit
    try:
        payload = {
            "title": "Readme",
            "artifact_type": "readme",
            "content": "The backend service talks to the database.",
        }
        statuses = [
            client.post(
                "/api/knowledge/artifacts",
                headers=auth_headers(token, org.id),
                json=payload,
            ).status_code
            for _ in range(3)
        ]
    finally:
        app.dependency_overrides.pop(get_settings, None)
        get_rate_limiter().reset()

    assert statuses[0] == 201
    assert statuses[1] == 201
    assert statuses[2] == 429


def test_rate_limit_disabled_allows_all(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    token = make_token(str(user.id), user.email)

    disabled = Settings(
        supabase_url="https://test.supabase.co",
        rate_limit_enabled=False,
        rate_limit_artifact_upload_per_min=1,
    )
    get_rate_limiter().reset()
    app.dependency_overrides[get_settings] = lambda: disabled
    try:
        payload = {
            "title": "Readme",
            "artifact_type": "readme",
            "content": "The backend service talks to the database.",
        }
        statuses = [
            client.post(
                "/api/knowledge/artifacts",
                headers=auth_headers(token, org.id),
                json=payload,
            ).status_code
            for _ in range(3)
        ]
    finally:
        app.dependency_overrides.pop(get_settings, None)
        get_rate_limiter().reset()

    assert statuses == [201, 201, 201]


# --------------------------------------------------------------------------
# Sentry init guard
# --------------------------------------------------------------------------


def test_init_sentry_disabled_without_dsn():
    assert init_sentry(Settings(sentry_dsn="")) is False
