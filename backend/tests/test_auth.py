"""Phase 3 auth tests.

Tokens are signed with HS256 using a test secret, exercising the *real*
signature/exp/iss/aud verification path in ``app.core.security`` (not a decode
stub). The database is an in-memory SQLite instance.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.security import JWTVerifier
from app.db.session import get_db
from app.deps import get_verifier_dep
from app.main import app
from app.models import Base

TEST_SECRET = "unit-test-secret-value"
TEST_SUPABASE_URL = "https://test.supabase.co"
TEST_AUDIENCE = "authenticated"
TEST_ISSUER = f"{TEST_SUPABASE_URL}/auth/v1"


def _make_token(
    subject: str,
    email: str,
    *,
    secret: str = TEST_SECRET,
    audience: str = TEST_AUDIENCE,
    issuer: str = TEST_ISSUER,
    expires_in: int = 3600,
) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": subject,
        "email": email,
        "aud": audience,
        "iss": issuer,
        "role": "authenticated",
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture()
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_get_db() -> Iterator:
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    test_settings = Settings(
        supabase_url=TEST_SUPABASE_URL,
        supabase_jwt_secret=TEST_SECRET,
        supabase_jwt_audience=TEST_AUDIENCE,
    )
    verifier = JWTVerifier(test_settings)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_verifier_dep] = lambda: verifier

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_is_public(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_missing_token_returns_401(client: TestClient):
    for path in ("/incidents", "/knowledge", "/investigation-runs", "/integrations", "/auth/me"):
        resp = client.get(path)
        assert resp.status_code == 401, path


def test_invalid_signature_returns_401(client: TestClient):
    token = _make_token(str(uuid.uuid4()), "a@example.com", secret="wrong-secret")
    resp = client.get("/auth/me", headers=_auth(token))
    assert resp.status_code == 401


def test_malformed_token_returns_401(client: TestClient):
    resp = client.get("/auth/me", headers=_auth("not-a-jwt"))
    assert resp.status_code == 401


def test_expired_token_returns_401(client: TestClient):
    token = _make_token(str(uuid.uuid4()), "a@example.com", expires_in=-10)
    resp = client.get("/auth/me", headers=_auth(token))
    assert resp.status_code == 401


def test_wrong_audience_returns_401(client: TestClient):
    token = _make_token(str(uuid.uuid4()), "a@example.com", audience="anon")
    resp = client.get("/auth/me", headers=_auth(token))
    assert resp.status_code == 401


def test_wrong_issuer_returns_401(client: TestClient):
    token = _make_token(
        str(uuid.uuid4()), "a@example.com", issuer="https://evil.supabase.co/auth/v1"
    )
    resp = client.get("/auth/me", headers=_auth(token))
    assert resp.status_code == 401


def test_valid_token_provisions_user_and_org(client: TestClient):
    sub = str(uuid.uuid4())
    token = _make_token(sub, "owner@example.com")

    resp = client.get("/auth/me", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == sub
    assert body["email"] == "owner@example.com"
    assert body["organization"]["slug"]
    assert body["organization"]["onboarding_status"] == "pending"

    # Calling again returns the same user/org (idempotent provisioning).
    resp2 = client.get("/auth/me", headers=_auth(token))
    assert resp2.status_code == 200
    assert resp2.json()["organization"]["id"] == body["organization"]["id"]


def test_user_cannot_access_another_organizations_data(client: TestClient):
    token_a = _make_token(str(uuid.uuid4()), "a@example.com")
    token_b = _make_token(str(uuid.uuid4()), "b@example.com")

    # User A creates an incident in their own org.
    created = client.post(
        "/incidents", headers=_auth(token_a), json={"title": "A's incident"}
    )
    assert created.status_code == 201
    incident = created.json()
    org_a_id = incident["organization_id"]

    # User B provisions their own org.
    me_b = client.get("/auth/me", headers=_auth(token_b))
    assert me_b.status_code == 200
    org_b_id = me_b.json()["organization"]["id"]
    assert org_b_id != org_a_id

    # B cannot read A's incident by id (scoped -> 404).
    resp = client.get(f"/incidents/{incident['id']}", headers=_auth(token_b))
    assert resp.status_code == 404

    # B's incident list does not include A's incident.
    list_b = client.get("/incidents", headers=_auth(token_b))
    assert list_b.status_code == 200
    assert all(i["id"] != incident["id"] for i in list_b.json())

    # B cannot spoof A's org via the X-Organization-Id header.
    spoof = client.get(
        "/incidents",
        headers={**_auth(token_b), "X-Organization-Id": org_a_id},
    )
    assert spoof.status_code == 403


def test_org_id_from_body_is_ignored(client: TestClient):
    """Even if a client sends organization_id, it must be overridden."""
    token = _make_token(str(uuid.uuid4()), "c@example.com")
    foreign_org = str(uuid.uuid4())
    created = client.post(
        "/incidents",
        headers=_auth(token),
        json={"title": "scoped", "organization_id": foreign_org},
    )
    assert created.status_code == 201
    assert created.json()["organization_id"] != foreign_org
