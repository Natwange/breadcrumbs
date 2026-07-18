"""Phase 11 real integrations tests (GitHub + Render).

External APIs are mocked via httpx.MockTransport so no network calls happen.
Verifies: normalized evidence, per-collector failure isolation, and that
tokens are never returned by the API.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.main import app
from app.models import CollectorRun, Evidence
from app.routes.integrations_api import get_integration_service
from app.services.integrations.collector_interface import CollectorError
from app.services.integrations.github_client import GithubClient
from app.services.integrations.github_collector import GithubCollector
from app.services.integrations.integration_service import IntegrationService
from app.services.integrations.render_client import RenderClient
from app.services.integrations.render_collector import RenderCollector
from app.services.investigation_engine.collector_registry import CollectorRegistry
from app.services.investigation_engine.investigation_runner import InvestigationRunner
from tests.conftest import auth_headers, make_token, seed_org_member
from tests.test_investigation_engine import (
    _seed_incident_with_alert,
    _seed_knowledge_graph,
)

FAKE_GITHUB_TOKEN = "ghp_fake_secret_token_value_1234567890"
FAKE_RENDER_KEY = "rnd_fake_secret_key_value_1234567890"


def _github_settings() -> Settings:
    return Settings(
        github_token=FAKE_GITHUB_TOKEN,
        github_api_base="https://api.github.com",
        github_default_repo="acme/backend",
    )


def _render_settings() -> Settings:
    return Settings(
        render_api_key=FAKE_RENDER_KEY,
        render_api_base="https://api.render.com/v1",
    )


def _github_transport(*, fail: bool = False) -> httpx.MockTransport:
    now = datetime.now(tz=timezone.utc)

    def handler(request: httpx.Request) -> httpx.Response:
        if fail:
            return httpx.Response(500, json={"message": "server error"})
        path = request.url.path
        if path == "/rate_limit":
            return httpx.Response(200, json={"resources": {"core": {"remaining": 4999}}})
        if path.endswith("/commits"):
            return httpx.Response(
                200,
                json=[
                    {
                        "sha": "abc1234deadbeef",
                        "html_url": "https://github.com/acme/backend/commit/abc1234",
                        "commit": {
                            "message": "Deploy release v1.2.3 to production",
                            "author": {"name": "Alice", "date": now.isoformat()},
                        },
                        "author": {"login": "alice"},
                    },
                    {
                        "sha": "def5678cafebabe",
                        "html_url": "https://github.com/acme/backend/commit/def5678",
                        "commit": {
                            "message": "Refactor connection pool",
                            "author": {"name": "Bob", "date": now.isoformat()},
                        },
                        "author": {"login": "bob"},
                    },
                ],
            )
        if path.endswith("/pulls"):
            return httpx.Response(
                200,
                json=[
                    {
                        "number": 42,
                        "title": "Increase DB pool size",
                        "body": "Bumps pool from 5 to 20",
                        "merged_at": (now - timedelta(minutes=30)).isoformat(),
                        "updated_at": (now - timedelta(minutes=30)).isoformat(),
                        "state": "closed",
                        "head": {"ref": "fix/pool"},
                        "base": {"ref": "main"},
                        "user": {"login": "carol"},
                        "html_url": "https://github.com/acme/backend/pull/42",
                    }
                ],
            )
        return httpx.Response(404, json={"message": "not found"})

    return httpx.MockTransport(handler)


def _render_transport(*, fail: bool = False) -> httpx.MockTransport:
    now = datetime.now(tz=timezone.utc)

    def handler(request: httpx.Request) -> httpx.Response:
        if fail:
            return httpx.Response(500, json={"message": "server error"})
        path = request.url.path
        if path == "/v1/services":
            return httpx.Response(
                200,
                json=[
                    {
                        "service": {
                            "id": "srv-123",
                            "name": "backend",
                            "type": "web_service",
                            "suspended": "not_suspended",
                            "updatedAt": now.isoformat(),
                        },
                        "cursor": "c1",
                    }
                ],
            )
        if path == "/v1/services/srv-123/deploys":
            return httpx.Response(
                200,
                json=[
                    {
                        "deploy": {
                            "id": "dep-1",
                            "status": "live",
                            "finishedAt": now.isoformat(),
                            "commit": {"id": "abc1234", "message": "ok deploy"},
                        },
                        "cursor": "d1",
                    },
                    {
                        "deploy": {
                            "id": "dep-2",
                            "status": "build_failed",
                            "finishedAt": now.isoformat(),
                            "commit": {"id": "def5678", "message": "broke the build"},
                        }
                    },
                ],
            )
        return httpx.Response(404, json={"message": "not found"})

    return httpx.MockTransport(handler)


# --------------------------------------------------------------------------
# Collectors normalize mocked provider responses
# --------------------------------------------------------------------------


def test_github_collector_normalizes_commits_and_pulls():
    client = GithubClient(_github_settings(), transport=_github_transport())
    collector = GithubCollector(client, default_repo="acme/backend")
    now = datetime.now(tz=timezone.utc)

    evidence = collector.collect("acme/backend", now - timedelta(hours=1), now, {})

    types = {e["evidence_type"] for e in evidence}
    assert "deploy" in types  # deploy-keyword commit
    assert "commit" in types  # ordinary commit
    assert "merge" in types  # merged PR
    for item in evidence:
        assert item["source"] == "github"
        assert item["title"]
        assert item["content"]
    deploy = next(e for e in evidence if e["evidence_type"] == "deploy")
    assert deploy["metadata"]["repo"] == "acme/backend"
    assert deploy["metadata"]["sha"]
    assert deploy["metadata"]["author"]


def test_render_collector_normalizes_deploys_and_health():
    client = RenderClient(_render_settings(), transport=_render_transport())
    collector = RenderCollector(client)
    now = datetime.now(tz=timezone.utc)

    evidence = collector.collect("backend", now - timedelta(hours=1), now, {})

    assert any(e["evidence_type"] == "provider_status" for e in evidence)
    deploys = [e for e in evidence if e["evidence_type"] == "deploy"]
    assert len(deploys) == 2
    assert any(d["metadata"]["failed"] for d in deploys)
    for item in evidence:
        assert item["source"] == "render"


def test_github_collector_without_repo_returns_empty():
    client = GithubClient(_github_settings(), transport=_github_transport())
    collector = GithubCollector(client, default_repo="")
    now = datetime.now(tz=timezone.utc)
    # service_name is not "owner/repo" and no default repo -> nothing to do
    assert collector.collect("backend", now - timedelta(hours=1), now, {}) == []


# --------------------------------------------------------------------------
# Collector failure isolation
# --------------------------------------------------------------------------


def test_github_collector_raises_collector_error_on_http_failure():
    client = GithubClient(_github_settings(), transport=_github_transport(fail=True))
    collector = GithubCollector(client, default_repo="acme/backend")
    now = datetime.now(tz=timezone.utc)
    with pytest.raises(CollectorError):
        collector.collect("acme/backend", now - timedelta(hours=1), now, {})


def test_collector_failure_does_not_fail_investigation_run(session_factory: sessionmaker):
    db = session_factory()
    _, org, _ = seed_org_member(db, role="member")
    _seed_knowledge_graph(db, org.id)
    incident = _seed_incident_with_alert(db, org.id)

    registry = CollectorRegistry()
    failing_client = GithubClient(_github_settings(), transport=_github_transport(fail=True))
    registry.register(
        "fake_github_collector",
        GithubCollector(failing_client, default_repo="acme/backend"),
    )
    runner = InvestigationRunner(collectors=registry)

    result = runner.run(db, org.id, incident.id)

    assert result.run.status == "completed"
    # Other collectors still produced evidence.
    assert result.evidence_count > 0

    github_run = db.scalar(
        select(CollectorRun).where(
            CollectorRun.investigation_run_id == result.run.id,
            CollectorRun.collector_type == "github_collector",
        )
    )
    assert github_run is not None
    assert github_run.status == "failed"


def test_real_github_collector_evidence_persisted_in_run(session_factory: sessionmaker):
    db = session_factory()
    _, org, _ = seed_org_member(db, role="member")
    _seed_knowledge_graph(db, org.id)
    incident = _seed_incident_with_alert(db, org.id)

    registry = CollectorRegistry()
    client = GithubClient(_github_settings(), transport=_github_transport())
    registry.register(
        "fake_github_collector",
        GithubCollector(client, default_repo="acme/backend"),
    )
    runner = InvestigationRunner(collectors=registry)

    result = runner.run(db, org.id, incident.id)
    assert result.run.status == "completed"

    github_evidence = list(
        db.scalars(
            select(Evidence).where(
                Evidence.investigation_run_id == result.run.id,
                Evidence.source == "github",
            )
        ).all()
    )
    assert github_evidence
    assert any(e.metadata_ and e.metadata_.get("repo") == "acme/backend" for e in github_evidence)


# --------------------------------------------------------------------------
# API: list + test endpoints never expose tokens
# --------------------------------------------------------------------------


def _override_service(service: IntegrationService):
    app.dependency_overrides[get_integration_service] = lambda: service


def _clear_override():
    app.dependency_overrides.pop(get_integration_service, None)


def test_list_integrations_reports_configured_without_token(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="admin")
    token = make_token(str(user.id), user.email)

    service = IntegrationService(
        github_client=GithubClient(_github_settings(), transport=_github_transport()),
        render_client=RenderClient(_render_settings(), transport=_render_transport()),
    )
    _override_service(service)
    try:
        resp = client.get("/api/integrations", headers=auth_headers(token, org.id))
    finally:
        _clear_override()

    assert resp.status_code == 200
    body = resp.json()
    providers = {p["provider"]: p["configured"] for p in body["providers"]}
    assert providers == {"github": True, "render": True}
    assert FAKE_GITHUB_TOKEN not in resp.text
    assert FAKE_RENDER_KEY not in resp.text


def test_github_test_endpoint_success_without_token(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="admin")
    token = make_token(str(user.id), user.email)

    service = IntegrationService(
        github_client=GithubClient(_github_settings(), transport=_github_transport()),
        render_client=RenderClient(_render_settings(), transport=_render_transport()),
    )
    _override_service(service)
    try:
        resp = client.post("/api/integrations/github/test", headers=auth_headers(token, org.id))
    finally:
        _clear_override()

    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "github"
    assert body["configured"] is True
    assert body["ok"] is True
    assert FAKE_GITHUB_TOKEN not in resp.text


def test_render_test_endpoint_reports_failure_without_token(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="admin")
    token = make_token(str(user.id), user.email)

    service = IntegrationService(
        github_client=GithubClient(_github_settings(), transport=_github_transport()),
        render_client=RenderClient(_render_settings(), transport=_render_transport(fail=True)),
    )
    _override_service(service)
    try:
        resp = client.post("/api/integrations/render/test", headers=auth_headers(token, org.id))
    finally:
        _clear_override()

    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "render"
    assert body["ok"] is False
    assert FAKE_RENDER_KEY not in resp.text


def test_test_endpoint_requires_manage_role(
    client: TestClient, session_factory: sessionmaker
):
    db = session_factory()
    user, org, _ = seed_org_member(db, role="member")
    token = make_token(str(user.id), user.email)

    resp = client.post("/api/integrations/github/test", headers=auth_headers(token, org.id))
    assert resp.status_code == 403


def test_provider_status_defaults_to_unconfigured():
    service = IntegrationService(settings=Settings(github_token="", render_api_key=""))
    status = {p["provider"]: p["configured"] for p in service.provider_status()}
    assert status == {"github": False, "render": False}
