"""Phase 6 investigation engine tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Alert,
    Evidence,
    Incident,
    InvestigationPlan,
    InvestigationRun,
    Runbook,
    ServiceDependency,
    ServiceNode,
    SlackDraft,
    TimelineEvent,
)
from app.services.investigation_engine.evidence_normalizer import EvidenceNormalizer
from app.services.investigation_engine.evidence_quality_validator import EvidenceQualityValidator
from app.services.investigation_engine.investigation_planner import InvestigationPlanner
from app.services.investigation_engine.investigation_runner import InvestigationRunner
from app.services.investigation_engine.knowledge_context_builder import KnowledgeContextBuilder
from tests.conftest import auth_headers, make_token, seed_org_member


def _seed_knowledge_graph(db: Session, org_id: uuid.UUID) -> dict[str, ServiceNode]:
    frontend = ServiceNode(
        organization_id=org_id, name="frontend", service_type="web"
    )
    backend = ServiceNode(organization_id=org_id, name="backend", service_type="api")
    supabase = ServiceNode(
        organization_id=org_id, name="supabase", service_type="database"
    )
    render = ServiceNode(organization_id=org_id, name="render", service_type="hosting")
    db.add_all([frontend, backend, supabase, render])
    db.flush()

    db.add_all(
        [
            ServiceDependency(
                organization_id=org_id,
                upstream_service_id=frontend.id,
                downstream_service_id=backend.id,
                dependency_type="http",
            ),
            ServiceDependency(
                organization_id=org_id,
                upstream_service_id=backend.id,
                downstream_service_id=supabase.id,
                dependency_type="database",
            ),
            ServiceDependency(
                organization_id=org_id,
                upstream_service_id=backend.id,
                downstream_service_id=render.id,
                dependency_type="hosting",
            ),
        ]
    )
    db.add(
        Runbook(
            organization_id=org_id,
            title="Backend outage runbook",
            content="Steps when backend is degraded",
        )
    )
    db.commit()
    return {
        "frontend": frontend,
        "backend": backend,
        "supabase": supabase,
        "render": render,
    }


def _seed_incident_with_alert(db: Session, org_id: uuid.UUID) -> Incident:
    incident = Incident(
        organization_id=org_id,
        title="Backend latency spike",
        status="open",
        metadata_={"affected_service": "backend"},
    )
    db.add(incident)
    db.flush()
    db.add(
        Alert(
            organization_id=org_id,
            incident_id=incident.id,
            source="datadog",
            title="High p95 latency",
            raw_payload={"service": "backend", "alert_type": "latency"},
            fired_at=datetime.now(tz=timezone.utc),
        )
    )
    db.commit()
    return incident


def test_investigation_run_progresses_to_completed(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    _seed_knowledge_graph(db, org.id)
    incident = _seed_incident_with_alert(db, org.id)
    token = make_token(str(user.id), user.email)
    headers = auth_headers(token, org.id)

    resp = client.post(
        f"/api/incidents/{incident.id}/investigation-runs",
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "completed"
    assert body["evidence_count"] > 0
    assert body["timeline_count"] > 0

    run = db.get(InvestigationRun, uuid.UUID(body["id"]))
    assert run is not None
    assert run.status == "completed"
    assert run.completed_at is not None


def test_planner_uses_dependencies(session: Session):
    db = session
    user, org, _ = seed_org_member(db, role="member")
    services = _seed_knowledge_graph(db, org.id)
    incident = _seed_incident_with_alert(db, org.id)
    alerts = list(
        db.scalars(select(Alert).where(Alert.incident_id == incident.id)).all()
    )

    context = KnowledgeContextBuilder().build(db, org.id, incident, alerts)
    assert context.affected_service == "backend"
    assert "supabase" in context.direct_dependencies
    assert "render" in context.direct_dependencies
    assert "frontend" in context.possible_blast_radius

    plan = InvestigationPlanner().create_plan(context)
    collectors = {s["collector"] for s in plan["steps"] if s.get("collector")}
    targets = {s["target_service"] for s in plan["steps"] if s.get("target_service")}

    assert "github_collector" in collectors
    assert "render_collector" in collectors
    assert "supabase" not in targets  # no fake dependency-metrics collectors
    assert services["backend"].name in targets
    assert "fake_metrics_collector" not in collectors
    assert "fake_errors_collector" not in collectors
    assert "fake_cloud_status_collector" not in collectors


def test_evidence_normalizes_and_deduplicates(session: Session):
    normalizer = EvidenceNormalizer()
    validator = EvidenceQualityValidator()
    runner = InvestigationRunner()

    raw = [
        {
            "source": "metrics",
            "evidence_type": "metric_spike",
            "title": "Latency",
            "content": "p95 latency elevated on backend",
        },
        {
            "source": "metrics",
            "evidence_type": "metric_spike",
            "title": "Latency",
            "content": "p95 latency elevated on backend",
        },
    ]
    normalized = normalizer.normalize_many(raw)
    assert len(normalized) == 2
    valid = [n for n in normalized if validator.validate(n).valid]
    assert len(valid) == 2
    deduped = runner._deduplicate(valid)
    assert len(deduped) == 1


def test_timeline_and_slack_draft_created(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    _seed_knowledge_graph(db, org.id)
    incident = _seed_incident_with_alert(db, org.id)
    token = make_token(str(user.id), user.email)
    headers = auth_headers(token, org.id)

    start = client.post(
        f"/api/incidents/{incident.id}/investigation-runs",
        headers=headers,
    )
    run_id = start.json()["id"]

    detail = client.get(f"/api/investigation-runs/{run_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["timeline_count"] > 0
    assert body["slack_draft"] is not None
    assert body["hypothesis"] is not None
    assert body["hypothesis"]["title"]  # reasoning engine sets title
    assert body.get("reasoning_status")

    timeline = list(
        db.scalars(
            select(TimelineEvent).where(TimelineEvent.investigation_run_id == uuid.UUID(run_id))
        ).all()
    )
    assert len(timeline) == body["timeline_count"]

    draft = db.scalar(
        select(SlackDraft).where(SlackDraft.investigation_run_id == uuid.UUID(run_id))
    )
    assert draft is not None
    assert draft.content


def test_alert_ingest_creates_incident(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    token = make_token(str(user.id), user.email)
    headers = auth_headers(token, org.id)

    resp = client.post(
        "/api/alerts/ingest",
        headers=headers,
        json={
            "source": "datadog",
            "title": "Error rate high",
            "description": "Backend errors above threshold",
            "raw_payload": {"service": "backend", "alert_type": "error_rate"},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "alert_id" in body
    assert "incident_id" in body

    alert = db.get(Alert, uuid.UUID(body["alert_id"]))
    assert alert is not None
    assert alert.incident_id == uuid.UUID(body["incident_id"])


def test_investigation_plan_persisted(session: Session):
    db = session
    user, org, _ = seed_org_member(db, role="member")
    _seed_knowledge_graph(db, org.id)
    incident = _seed_incident_with_alert(db, org.id)

    result = InvestigationRunner().run(db, org.id, incident.id)
    plan = db.scalar(
        select(InvestigationPlan).where(
            InvestigationPlan.investigation_run_id == result.run.id
        )
    )
    assert plan is not None
    assert plan.steps is not None
    assert plan.steps.get("direct_dependencies")

    evidence = list(
        db.scalars(
            select(Evidence).where(Evidence.investigation_run_id == result.run.id)
        ).all()
    )
    assert len(evidence) == result.evidence_count


def test_incident_workspace_returns_nested_data(
    client: TestClient, session: Session
):
    db = session
    user, org, _ = seed_org_member(db, role="member")
    _seed_knowledge_graph(db, org.id)
    incident = _seed_incident_with_alert(db, org.id)
    result = InvestigationRunner().run(db, org.id, incident.id)

    headers = auth_headers(make_token(str(user.id), user.email))
    resp = client.get(
        f"/api/incidents/{incident.id}/workspace",
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["incident"]["id"] == str(incident.id)
    assert len(body["alerts"]) >= 1
    assert len(body["runs"]) == 1
    assert body["run"]["id"] == str(result.run.id)
    assert len(body["evidence"]) == result.evidence_count
    assert len(body["timeline"]) == result.timeline_count
