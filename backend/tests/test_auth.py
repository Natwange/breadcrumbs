"""Phase 3 auth tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_headers, make_token


def test_health_is_public(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_missing_token_returns_401(client: TestClient):
    for path in (
        "/incidents",
        "/knowledge",
        "/investigation-runs",
        "/integrations",
        "/auth/me",
    ):
        resp = client.get(path)
        assert resp.status_code == 401, path


def test_invalid_signature_returns_401(client: TestClient):
    token = make_token(str(uuid.uuid4()), "a@example.com", secret="wrong-secret")
    resp = client.get("/auth/me", headers=auth_headers(token))
    assert resp.status_code == 401


def test_malformed_token_returns_401(client: TestClient):
    resp = client.get("/auth/me", headers=auth_headers("not-a-jwt"))
    assert resp.status_code == 401


def test_expired_token_returns_401(client: TestClient):
    token = make_token(str(uuid.uuid4()), "a@example.com", expires_in=-10)
    resp = client.get("/auth/me", headers=auth_headers(token))
    assert resp.status_code == 401


def test_wrong_audience_returns_401(client: TestClient):
    token = make_token(str(uuid.uuid4()), "a@example.com", audience="anon")
    resp = client.get("/auth/me", headers=auth_headers(token))
    assert resp.status_code == 401


def test_wrong_issuer_returns_401(client: TestClient):
    token = make_token(
        str(uuid.uuid4()), "a@example.com", issuer="https://evil.supabase.co/auth/v1"
    )
    resp = client.get("/auth/me", headers=auth_headers(token))
    assert resp.status_code == 401


def test_valid_token_provisions_user_and_org(client: TestClient):
    sub = str(uuid.uuid4())
    token = make_token(sub, "owner@example.com")

    resp = client.get("/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == sub
    assert body["email"] == "owner@example.com"
    assert body["organization"]["slug"]
    assert body["organization"]["onboarding_status"] == "pending"

    resp2 = client.get("/auth/me", headers=auth_headers(token))
    assert resp2.status_code == 200
    assert resp2.json()["organization"]["id"] == body["organization"]["id"]


def test_user_cannot_access_another_organizations_data(client: TestClient):
    token_a = make_token(str(uuid.uuid4()), "a@example.com")
    token_b = make_token(str(uuid.uuid4()), "b@example.com")

    created = client.post(
        "/incidents", headers=auth_headers(token_a), json={"title": "A's incident"}
    )
    assert created.status_code == 201
    incident = created.json()
    org_a_id = incident["organization_id"]

    me_b = client.get("/auth/me", headers=auth_headers(token_b))
    assert me_b.status_code == 200
    org_b_id = me_b.json()["organization"]["id"]
    assert org_b_id != org_a_id

    resp = client.get(f"/incidents/{incident['id']}", headers=auth_headers(token_b))
    assert resp.status_code == 404

    list_b = client.get("/incidents", headers=auth_headers(token_b))
    assert list_b.status_code == 200
    assert all(i["id"] != incident["id"] for i in list_b.json())

    spoof = client.get(
        "/incidents",
        headers=auth_headers(token_b, uuid.UUID(org_a_id)),
    )
    assert spoof.status_code == 403


def test_org_id_from_body_is_ignored(client: TestClient):
    token = make_token(str(uuid.uuid4()), "c@example.com")
    foreign_org = str(uuid.uuid4())
    created = client.post(
        "/incidents",
        headers=auth_headers(token),
        json={"title": "scoped", "organization_id": foreign_org},
    )
    assert created.status_code == 201
    assert created.json()["organization_id"] != foreign_org
