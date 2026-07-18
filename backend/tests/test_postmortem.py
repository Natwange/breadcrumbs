"""Phase 10 postmortem generator tests."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import AuditLog, EmbeddingRecord, Incident
from app.services.audit import AUDIT_POSTMORTEM_GENERATED
from app.services.postmortem.postmortem_generator import (
    PostmortemGenerator,
    calculate_duration_minutes,
)
from app.services.postmortem.postmortem_schema import SOURCE_FALLBACK
from tests.conftest import auth_headers, make_token, seed_org_member


@dataclass
class _FakePostmortemClient:
    raw: str
    enabled: bool = True
    token_usage: dict = field(default_factory=lambda: {"input_tokens": 50, "output_tokens": 30})
    model_version: str = "claude-test"

    def generate(self, system: str, user: str):
        return self.raw, self.token_usage, self.model_version


def _resolved_incident(db, org_id, *, with_times: bool = True) -> Incident:
    now = datetime.now(tz=timezone.utc)
    incident = Incident(
        organization_id=org_id,
        title="Backend outage",
        description="Database pool exhausted",
        status="resolved",
        started_at=now - timedelta(hours=2) if with_times else None,
        resolved_at=now if with_times else None,
    )
    db.add(incident)
    db.flush()
    return incident


def test_cannot_generate_for_unresolved_incident(session: Session):
    db = session
    _, org, _ = seed_org_member(db, role="member")
    incident = Incident(organization_id=org.id, title="Open", status="open")
    db.add(incident)
    db.commit()

    try:
        PostmortemGenerator().generate(db, org.id, incident.id)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "resolved" in str(exc).lower()


def test_cannot_generate_via_api_for_open_incident(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    incident = Incident(organization_id=org.id, title="Open", status="investigating")
    db.add(incident)
    db.commit()

    token = make_token(str(user.id), user.email)
    resp = client.post(
        f"/api/incidents/{incident.id}/postmortem",
        headers=auth_headers(token, org.id),
        json={},
    )
    assert resp.status_code == 400


def test_duration_calculated(session: Session):
    db = session
    _, org, _ = seed_org_member(db, role="member")
    incident = _resolved_incident(db, org.id)
    minutes = calculate_duration_minutes(incident)
    assert minutes == 120


def test_fallback_generates_structured_postmortem(session: Session):
    db = session
    _, org, _ = seed_org_member(db, role="member")
    incident = _resolved_incident(db, org.id)

    gen = PostmortemGenerator(llm_client=_FakePostmortemClient(raw="not json", enabled=True))
    result = gen.generate(db, org.id, incident.id, resolution_notes="Restarted pool")

    assert result.postmortem.postmortem_source == SOURCE_FALLBACK
    assert result.sections.summary
    assert result.postmortem.sections_ is not None
    assert result.postmortem.sections_["summary"]
    assert result.postmortem.incident_duration_minutes == 120
    assert "## Summary" in (result.postmortem.content or "")


def test_no_secrets_in_postmortem_content(session: Session):
    db = session
    _, org, _ = seed_org_member(db, role="member")
    incident = _resolved_incident(db, org.id)
    incident.description = "Failure with API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456"
    db.commit()

    result = PostmortemGenerator(llm_client=_FakePostmortemClient(raw="bad", enabled=True)).generate(
        db, org.id, incident.id
    )
    content = (result.postmortem.content or "") + str(result.postmortem.sections_)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in content
    assert "[REDACTED" in content or "sk-" not in content


def test_claude_success_generates_postmortem(session: Session):
    db = session
    _, org, _ = seed_org_member(db, role="member")
    incident = _resolved_incident(db, org.id)

    raw = json.dumps(
        {
            "summary": "DB pool exhaustion caused backend errors.",
            "impact": "Users experienced elevated latency.",
            "timeline": [{"time": "2026-01-01T10:00:00Z", "description": "Alert fired", "is_fact": True}],
            "root_cause": {
                "description": "Connection pool too small",
                "is_assumption": False,
                "supporting_evidence_ids": [],
            },
            "resolution": "Increased pool size",
            "prevention_items": [{"title": "Add pool alert", "description": "Monitor saturation"}],
            "assumptions": [],
            "incident_duration_minutes": 120,
        }
    )
    gen = PostmortemGenerator(llm_client=_FakePostmortemClient(raw=raw))
    result = gen.generate(db, org.id, incident.id)
    assert result.postmortem.postmortem_source == "claude"
    assert result.sections.root_cause.description == "Connection pool too small"


def test_audit_logged_on_generate(session: Session):
    db = session
    user, org, _ = seed_org_member(db, role="member")
    incident = _resolved_incident(db, org.id)

    PostmortemGenerator(llm_client=_FakePostmortemClient(raw="x", enabled=False)).generate(
        db, org.id, incident.id, actor_id=user.id
    )

    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.organization_id == org.id,
            AuditLog.action == AUDIT_POSTMORTEM_GENERATED,
        )
    )
    assert audit is not None


def test_approve_embeds_postmortem(session: Session):
    db = session
    _, org, _ = seed_org_member(db, role="member")
    incident = _resolved_incident(db, org.id)

    gen = PostmortemGenerator(llm_client=_FakePostmortemClient(raw="x", enabled=False))
    result = gen.generate(db, org.id, incident.id)
    approved = gen.approve_and_embed(db, org.id, result.postmortem.id)

    assert approved.status == "approved"
    record = db.scalar(
        select(EmbeddingRecord).where(
            EmbeddingRecord.source_id == approved.id,
            EmbeddingRecord.source_type == "postmortem",
        )
    )
    assert record is not None


def test_api_generate_postmortem(client: TestClient, session_factory: sessionmaker):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    incident = _resolved_incident(db, org.id)
    db.commit()

    token = make_token(str(user.id), user.email)
    resp = client.post(
        f"/api/incidents/{incident.id}/postmortem",
        headers=auth_headers(token, org.id),
        json={"resolution_notes": "Scaled pool"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["postmortem"]["status"] == "draft"
    assert body["postmortem"]["sections"]["summary"]
