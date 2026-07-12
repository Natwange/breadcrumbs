"""Phase 4 organization tenancy and role permission tests."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.models import KnowledgeGraphProposal, UserProfile
from tests.conftest import auth_headers, make_token, seed_org_member


def test_viewer_cannot_create_incident(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="viewer")
    token = make_token(str(user.id), user.email)

    resp = client.post(
        "/incidents",
        headers=auth_headers(token, org.id),
        json={"title": "Should fail"},
    )
    assert resp.status_code == 403


def test_member_cannot_approve_proposal(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    proposal = KnowledgeGraphProposal(
        organization_id=org.id,
        proposal_type="add_service",
        status="pending",
        proposed_by=user.id,
    )
    db.add(proposal)
    db.commit()

    token = make_token(str(user.id), user.email)
    resp = client.post(
        f"/knowledge/proposals/{proposal.id}/approve",
        headers=auth_headers(token, org.id),
    )
    assert resp.status_code == 403


def test_admin_can_approve_proposal(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    admin, org, _ = seed_org_member(db, role="admin", email="admin@example.com")
    member = UserProfile(id=uuid.uuid4(), email="member@example.com")
    db.add(member)
    db.flush()
    proposal = KnowledgeGraphProposal(
        organization_id=org.id,
        proposal_type="add_dependency",
        status="pending",
        proposed_by=member.id,
    )
    db.add(proposal)
    db.commit()

    token = make_token(str(admin.id), admin.email)
    resp = client.post(
        f"/knowledge/proposals/{proposal.id}/approve",
        headers=auth_headers(token, org.id),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_viewer_can_list_incidents(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="viewer")
    token = make_token(str(user.id), user.email)

    resp = client.get("/incidents", headers=auth_headers(token, org.id))
    assert resp.status_code == 200


def test_member_cannot_create_integration(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    token = make_token(str(user.id), user.email)

    resp = client.post(
        "/integrations",
        headers=auth_headers(token, org.id),
        json={"provider": "datadog", "name": "Primary"},
    )
    assert resp.status_code == 403


def test_admin_can_invite_member(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    admin, org, _ = seed_org_member(db, role="admin")
    token = make_token(str(admin.id), admin.email)

    resp = client.post(
        "/organizations/invitations",
        headers=auth_headers(token, org.id),
        json={"email": "newhire@example.com", "role": "member"},
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "newhire@example.com"
    assert resp.json()["status"] == "pending"
