"""Evidence collectors for investigations.

Only real GitHub/Render collectors are registered when backend credentials are
present. There are no hardcoded fake evidence collectors — missing credentials
mean that collector is simply unavailable and the plan step is skipped.
"""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.services.integrations.collector_interface import Collector
from app.services.integrations.github_client import GithubClient
from app.services.integrations.github_collector import GithubCollector
from app.services.integrations.render_client import RenderClient
from app.services.integrations.render_collector import RenderCollector
from app.services.investigation_engine.knowledge_context_builder import InvestigationContext

GITHUB_COLLECTOR = "github_collector"
RENDER_COLLECTOR = "render_collector"


class CollectorRegistry:
    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self._by_name: dict[str, Collector] = {}

        github_client = GithubClient(settings)
        if github_client.enabled:
            self._by_name[GITHUB_COLLECTOR] = GithubCollector(
                github_client, default_repo=settings.github_default_repo
            )

        render_client = RenderClient(settings)
        if render_client.enabled:
            self._by_name[RENDER_COLLECTOR] = RenderCollector(render_client)

    def register(self, name: str, collector: Collector) -> None:
        """Override a collector by logical name (used in tests/wiring)."""
        self._by_name[name] = collector

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
