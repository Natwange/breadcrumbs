"""Real external integrations (Phase 11).

GitHub and Render evidence collectors that plug into the same investigation
engine collector interface as the fake collectors. Provider credentials are
read from the backend environment only and are never persisted or exposed.
"""

from app.services.integrations.collector_interface import Collector, CollectorError
from app.services.integrations.github_client import GithubClient
from app.services.integrations.github_collector import GithubCollector
from app.services.integrations.integration_service import IntegrationService
from app.services.integrations.render_client import RenderClient
from app.services.integrations.render_collector import RenderCollector

__all__ = [
    "Collector",
    "CollectorError",
    "GithubClient",
    "GithubCollector",
    "IntegrationService",
    "RenderClient",
    "RenderCollector",
]
