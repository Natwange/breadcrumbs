"""Fake evidence collectors for MVP investigations (no external APIs)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from app.services.investigation_engine.knowledge_context_builder import InvestigationContext


class Collector(Protocol):
    name: str

    def collect(
        self,
        service_name: str,
        start_time: datetime,
        end_time: datetime,
        alert_context: dict,
    ) -> list[dict]:
        ...


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


class FakeGithubCollector:
    name = "fake_github_collector"

    def collect(
        self,
        service_name: str,
        start_time: datetime,
        end_time: datetime,
        alert_context: dict,
    ) -> list[dict]:
        return [
            {
                "source": "github",
                "evidence_type": "deploy",
                "title": f"Recent commit on {service_name}",
                "content": f"Commit abc1234 touched {service_name} configuration",
                "observed_at": _iso(end_time),
                "metadata": {"repo": "acme/focusflow", "sha": "abc1234"},
            }
        ]


class FakeRenderCollector:
    name = "fake_render_collector"

    def collect(
        self,
        service_name: str,
        start_time: datetime,
        end_time: datetime,
        alert_context: dict,
    ) -> list[dict]:
        return [
            {
                "source": "render",
                "evidence_type": "deploy",
                "title": f"Render deploy for {service_name}",
                "content": "Deploy succeeded 12 minutes before alert fired",
                "observed_at": _iso(start_time),
                "metadata": {"provider": "render", "status": "live"},
            }
        ]


class FakeMetricsCollector:
    name = "fake_metrics_collector"

    def collect(
        self,
        service_name: str,
        start_time: datetime,
        end_time: datetime,
        alert_context: dict,
    ) -> list[dict]:
        return [
            {
                "source": "metrics",
                "evidence_type": "metric_spike",
                "title": f"Elevated p95 latency on {service_name}",
                "content": f"p95 latency rose from 120ms to 890ms on {service_name}",
                "observed_at": _iso(end_time),
                "metadata": {"metric": "http.latency.p95", "value": 890},
            },
            {
                "source": "metrics",
                "evidence_type": "metric_spike",
                "title": f"Elevated p95 latency on {service_name}",
                "content": f"p95 latency rose from 120ms to 890ms on {service_name}",
                "observed_at": _iso(end_time),
                "metadata": {"metric": "http.latency.p95", "value": 890},
            },
        ]


class FakeErrorsCollector:
    name = "fake_errors_collector"

    def collect(
        self,
        service_name: str,
        start_time: datetime,
        end_time: datetime,
        alert_context: dict,
    ) -> list[dict]:
        return [
            {
                "source": "errors",
                "evidence_type": "error_log",
                "title": f"Connection timeout errors on {service_name}",
                "content": "Timeout connecting to downstream database pool",
                "observed_at": _iso(end_time),
                "metadata": {"error_class": "TimeoutError", "count": 42},
            }
        ]


class FakeCloudStatusCollector:
    name = "fake_cloud_status_collector"

    def collect(
        self,
        service_name: str,
        start_time: datetime,
        end_time: datetime,
        alert_context: dict,
    ) -> list[dict]:
        return [
            {
                "source": "cloud_status",
                "evidence_type": "provider_status",
                "title": f"{service_name} status page",
                "content": f"No active incidents reported for {service_name}",
                "observed_at": _iso(end_time),
                "metadata": {"provider": service_name, "status": "operational"},
            }
        ]


class CollectorRegistry:
    def __init__(self) -> None:
        collectors: list[Collector] = [
            FakeGithubCollector(),
            FakeRenderCollector(),
            FakeMetricsCollector(),
            FakeErrorsCollector(),
            FakeCloudStatusCollector(),
        ]
        self._by_name = {c.name: c for c in collectors}

    def get(self, name: str) -> Collector | None:
        return self._by_name.get(name)

    def names(self) -> list[str]:
        return list(self._by_name.keys())

    def build_alert_context(
        self, context: InvestigationContext, alerts: list
    ) -> dict:
        return {
            "affected_service": context.affected_service,
            "direct_dependencies": context.direct_dependencies,
            "alert_titles": [a.title for a in alerts],
            "external_providers": context.external_providers,
        }
