"""Phase 5 knowledge builder tests."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import (
    KnowledgeGraphProposal,
    OrganizationMember,
    ServiceDependency,
    ServiceNode,
    UserProfile,
)
from app.services.knowledge_builder.secret_redactor import redact_secrets
from tests.conftest import auth_headers, make_token, seed_org_member

FIXTURES = Path(__file__).parent / "fixtures"


def _focusflow_readme() -> str:
    return (FIXTURES / "focusflow_readme.md").read_text(encoding="utf-8")


def test_secrets_redacted_before_storage(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    token = make_token(str(user.id), user.email)
    headers = auth_headers(token, org.id)

    raw = _focusflow_readme()
    resp = client.post(
        "/api/knowledge/artifacts",
        headers=headers,
        json={
            "title": "FocusFlow README",
            "artifact_type": "readme",
            "content": raw,
            "source": "repo",
        },
    )
    assert resp.status_code == 201
    stored = resp.json()["artifact"]["content"]
    assert "sk-test-secret-key" not in stored
    assert "supersecret" not in stored
    assert "[REDACTED]" in stored


def test_redact_secrets_unit():
    text = "API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456"
    result = redact_secrets(text)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in result.redacted_text
    assert result.redaction_count >= 1


def test_focusflow_fixture_proposes_frontend_backend_supabase_render(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    token = make_token(str(user.id), user.email)
    headers = auth_headers(token, org.id)

    resp = client.post(
        "/api/knowledge/artifacts",
        headers=headers,
        json={
            "title": "FocusFlow README",
            "artifact_type": "readme",
            "content": _focusflow_readme(),
        },
    )
    assert resp.status_code == 201
    proposal_id = resp.json()["proposal_id"]
    assert proposal_id is not None

    proposal = db.get(KnowledgeGraphProposal, uuid.UUID(proposal_id))
    assert proposal is not None
    payload = proposal.payload or {}
    service_names = {s["name"].lower() for s in payload.get("services", [])}
    assert {"frontend", "backend", "supabase", "render"}.issubset(service_names)

    dep_pairs = {
        (d["upstream"].lower(), d["downstream"].lower())
        for d in payload.get("dependencies", [])
    }
    assert ("frontend", "backend") in dep_pairs
    assert ("backend", "supabase") in dep_pairs
    assert ("backend", "render") in dep_pairs or ("frontend", "render") in dep_pairs


def test_member_cannot_approve_knowledge_proposal(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    proposal = KnowledgeGraphProposal(
        organization_id=org.id,
        proposal_type="architecture_extraction",
        status="pending",
        payload={"services": [{"name": "api", "service_type": "api"}]},
        proposed_by=user.id,
    )
    db.add(proposal)
    db.commit()

    token = make_token(str(user.id), user.email)
    resp = client.post(
        f"/api/knowledge/proposals/{proposal.id}/approve",
        headers=auth_headers(token, org.id),
    )
    assert resp.status_code == 403


def _add_member_to_org(db, org, email: str, role: str = "member") -> UserProfile:
    user = UserProfile(id=uuid.uuid4(), email=email)
    db.add(user)
    db.flush()
    membership = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role=role,
        status="active",
    )
    db.add(membership)
    db.commit()
    return user


def test_admin_can_approve_proposal_and_apply_graph(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    admin, org, _ = seed_org_member(db, role="admin", email="admin@example.com")
    member = _add_member_to_org(db, org, "member@example.com", role="member")

    resp_ingest = client.post(
        "/api/knowledge/artifacts",
        headers=auth_headers(make_token(str(member.id), member.email), org.id),
        json={
            "title": "FocusFlow README",
            "artifact_type": "readme",
            "content": _focusflow_readme(),
        },
    )
    assert resp_ingest.status_code == 201
    proposal_id = resp_ingest.json()["proposal_id"]
    assert proposal_id is not None

    token = make_token(str(admin.id), admin.email)
    approve = client.post(
        f"/api/knowledge/proposals/{proposal_id}/approve",
        headers=auth_headers(token, org.id),
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    services = list(
        db.scalars(
            select(ServiceNode).where(ServiceNode.organization_id == org.id)
        ).all()
    )
    names = {s.name.lower() for s in services}
    assert "frontend" in names
    assert "backend" in names
    assert "supabase" in names

    deps = list(
        db.scalars(
            select(ServiceDependency).where(
                ServiceDependency.organization_id == org.id
            )
        ).all()
    )
    assert len(deps) >= 2


def test_drift_does_not_delete_approved_services(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    admin, org, _ = seed_org_member(db, role="admin")
    existing = ServiceNode(
        organization_id=org.id,
        name="legacy-billing",
        service_type="api",
        description="Approved legacy service",
    )
    db.add(existing)
    db.commit()

    token = make_token(str(admin.id), admin.email)
    headers = auth_headers(token, org.id)

    # Ingest unrelated artifact — drift should note missing service, not delete it.
    client.post(
        "/api/knowledge/artifacts",
        headers=headers,
        json={
            "title": "Tiny README",
            "artifact_type": "readme",
            "content": "# Other\nFrontend Next.js only.",
        },
    )

    still_there = db.scalar(
        select(ServiceNode).where(
            ServiceNode.organization_id == org.id,
            ServiceNode.name == "legacy-billing",
        )
    )
    assert still_there is not None
