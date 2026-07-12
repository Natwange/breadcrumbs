"""Phase 7 vector search + organizational memory tests."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    EmbeddingRecord,
    Incident,
    KnowledgeArtifact,
    Postmortem,
    Runbook,
)
from app.services.vector_search.embedding_queue import EmbeddingQueue
from app.services.vector_search.embedding_service import EmbeddingService
from app.services.vector_search.embedding_validator import EmbeddingValidator
from app.services.vector_search.object_types import (
    OBJECT_TYPE_INCIDENT,
    OBJECT_TYPE_KNOWLEDGE_ARTIFACT,
    OBJECT_TYPE_RUNBOOK,
)
from app.services.vector_search.similarity_service import SimilarityService
from app.services.vector_search.vector_search import VectorSearch, cosine_similarity
from tests.conftest import auth_headers, make_token, seed_org_member


def test_embedding_is_deterministic_and_similar_texts_close():
    svc = EmbeddingService()
    a = svc.embed("database connection pool timeout on backend service")
    b = svc.embed("backend service database connection pool timeouts")
    c = svc.embed("frontend css styling button color change")

    # Determinism across calls.
    assert svc.embed("database connection pool timeout on backend service") == a
    # Similar texts are closer than unrelated ones.
    assert cosine_similarity(a, b) > cosine_similarity(a, c)


def test_vector_search_returns_similar_objects(session: Session):
    db = session
    _, org, _ = seed_org_member(db, role="member")
    queue = EmbeddingQueue()

    rb_db = Runbook(
        organization_id=org.id,
        title="Database pool exhaustion runbook",
        content="Steps to resolve database connection pool exhaustion and timeouts",
    )
    rb_ui = Runbook(
        organization_id=org.id,
        title="Frontend styling guide",
        content="How to change button colors and CSS themes in the UI",
    )
    db.add_all([rb_db, rb_ui])
    db.flush()
    queue.embed_runbook(db, rb_db)
    queue.embed_runbook(db, rb_ui)
    db.commit()

    query = EmbeddingService().embed("database connection pool timeout")
    hits = VectorSearch().search(
        db, org.id, query, source_types=[OBJECT_TYPE_RUNBOOK], limit=5
    )
    assert hits
    assert hits[0].record.source_id == rb_db.id


def test_cross_org_vectors_are_isolated(session: Session):
    db = session
    _, org_a, _ = seed_org_member(db, role="member", email="a@example.com")
    _, org_b, _ = seed_org_member(db, role="member", email="b@example.com")
    queue = EmbeddingQueue()

    rb_a = Runbook(
        organization_id=org_a.id,
        title="Org A database runbook",
        content="database connection pool timeout resolution for org a",
    )
    rb_b = Runbook(
        organization_id=org_b.id,
        title="Org B database runbook",
        content="database connection pool timeout resolution for org b",
    )
    db.add_all([rb_a, rb_b])
    db.flush()
    queue.embed_runbook(db, rb_a)
    queue.embed_runbook(db, rb_b)
    db.commit()

    query = EmbeddingService().embed("database connection pool timeout")
    hits = VectorSearch().search(db, org_a.id, query, limit=10)
    returned_orgs = {h.record.organization_id for h in hits}
    returned_ids = {h.record.source_id for h in hits}

    assert returned_orgs == {org_a.id}
    assert rb_a.id in returned_ids
    assert rb_b.id not in returned_ids


def test_redacted_artifacts_are_embedded(session: Session):
    db = session
    _, org, _ = seed_org_member(db, role="member")
    queue = EmbeddingQueue()

    artifact = KnowledgeArtifact(
        organization_id=org.id,
        title="Service README",
        artifact_type="readme",
        content=(
            "Backend service configuration. "
            "API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456 "
            "Connect via postgresql://user:supersecret@host/db"
        ),
    )
    db.add(artifact)
    db.flush()
    record = queue.embed_knowledge_artifact(db, artifact)
    db.commit()

    assert record is not None
    assert record.embedding is not None and len(record.embedding) > 0
    # The stored snapshot must be redacted — no raw secrets embedded.
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in (record.text_snapshot or "")
    assert "supersecret" not in (record.text_snapshot or "")
    assert "[REDACTED" in (record.text_snapshot or "")


def test_validator_rejects_empty_and_embeds_redacted():
    validator = EmbeddingValidator()
    empty = validator.validate("   ")
    assert empty.is_valid is False

    secret = validator.validate("token=abcdefgh12345678 hello world context here")
    assert secret.is_valid is True
    assert "abcdefgh12345678" not in secret.redacted_text


def test_only_resolved_incidents_embedded(session: Session):
    db = session
    _, org, _ = seed_org_member(db, role="member")
    queue = EmbeddingQueue()

    open_inc = Incident(organization_id=org.id, title="Open incident", status="open")
    resolved_inc = Incident(
        organization_id=org.id,
        title="Resolved database outage",
        description="database pool exhausted, resolved by scaling",
        status="resolved",
    )
    db.add_all([open_inc, resolved_inc])
    db.flush()

    assert queue.embed_resolved_incident(db, open_inc) is None
    rec = queue.embed_resolved_incident(db, resolved_inc)
    assert rec is not None
    assert rec.source_type == OBJECT_TYPE_INCIDENT


def test_embed_object_rejects_non_embeddable_type(session: Session):
    db = session
    _, org, _ = seed_org_member(db, role="member")
    queue = EmbeddingQueue()
    try:
        queue.embed_object(
            db,
            organization_id=org.id,
            object_type="live_metric",
            object_id=uuid.uuid4(),
            text="cpu 90 percent",
        )
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_embedding_is_idempotent(session: Session):
    db = session
    _, org, _ = seed_org_member(db, role="member")
    queue = EmbeddingQueue()

    rb = Runbook(organization_id=org.id, title="Runbook", content="some content here")
    db.add(rb)
    db.flush()
    first = queue.embed_runbook(db, rb)
    second = queue.embed_runbook(db, rb)
    db.commit()

    assert first.id == second.id
    count = db.scalar(
        select(EmbeddingRecord).where(
            EmbeddingRecord.source_id == rb.id,
        )
    )
    assert count is not None


def test_similarity_service_finds_memory_for_incident(session: Session):
    db = session
    _, org, _ = seed_org_member(db, role="member")
    queue = EmbeddingQueue()

    rb = Runbook(
        organization_id=org.id,
        title="Backend latency runbook",
        content="resolve backend latency spikes and database timeouts",
    )
    past = Incident(
        organization_id=org.id,
        title="Previous backend latency incident",
        description="backend latency spike caused by database timeouts",
        status="resolved",
    )
    db.add_all([rb, past])
    db.flush()
    queue.embed_runbook(db, rb)
    queue.embed_resolved_incident(db, past)
    db.commit()

    current = Incident(
        organization_id=org.id,
        title="Backend latency spike",
        description="high latency on backend, suspect database timeouts",
        status="open",
        metadata_={"affected_service": "backend"},
    )
    db.add(current)
    db.flush()

    ctx = SimilarityService().find_for_incident(db, org.id, current)
    assert ctx.total() > 0
    assert any(m.object_id == rb.id for m in ctx.relevant_runbooks)
    assert any(m.object_id == past.id for m in ctx.similar_incidents)


def test_backfill_endpoint_embeds_memory(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    admin, org, _ = seed_org_member(db, role="admin")
    db.add_all(
        [
            Runbook(organization_id=org.id, title="RB", content="database timeout runbook"),
            KnowledgeArtifact(
                organization_id=org.id,
                title="Arch",
                artifact_type="architecture",
                content="frontend calls backend which calls supabase",
            ),
        ]
    )
    db.commit()

    token = make_token(str(admin.id), admin.email)
    resp = client.post("/api/embeddings/backfill", headers=auth_headers(token, org.id))
    assert resp.status_code == 202
    body = resp.json()
    assert body["embedded"] >= 2

    records = list(
        db.scalars(
            select(EmbeddingRecord).where(EmbeddingRecord.organization_id == org.id)
        ).all()
    )
    assert len(records) >= 2


def test_backfill_endpoint_requires_admin(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    member, org, _ = seed_org_member(db, role="member")
    token = make_token(str(member.id), member.email)
    resp = client.post("/api/embeddings/backfill", headers=auth_headers(token, org.id))
    assert resp.status_code == 403
