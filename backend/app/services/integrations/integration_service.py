"""Application service for listing and testing external integrations.

Never returns credentials. Provider availability is reported as a boolean
("configured") derived from the presence of a backend env token — the token
value itself is never exposed.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import IntegrationConnection
from app.services.integrations.github_client import GithubClient
from app.services.integrations.render_client import RenderClient

PROVIDER_GITHUB = "github"
PROVIDER_RENDER = "render"


class IntegrationService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        github_client: GithubClient | None = None,
        render_client: RenderClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._github = github_client or GithubClient(self._settings)
        self._render = render_client or RenderClient(self._settings)

    def provider_status(self) -> list[dict[str, Any]]:
        """Non-secret availability summary for each supported provider."""
        return [
            {"provider": PROVIDER_GITHUB, "configured": self._github.enabled},
            {"provider": PROVIDER_RENDER, "configured": self._render.enabled},
        ]

    def list_connections(
        self, db: Session, organization_id: uuid.UUID
    ) -> list[IntegrationConnection]:
        stmt = (
            select(IntegrationConnection)
            .where(IntegrationConnection.organization_id == organization_id)
            .order_by(IntegrationConnection.created_at.desc())
        )
        return list(db.scalars(stmt).all())

    def test_github(self) -> dict[str, Any]:
        result = self._github.test_connection()
        return {
            "provider": PROVIDER_GITHUB,
            "configured": self._github.enabled,
            "ok": bool(result.get("ok")),
            "detail": str(result.get("detail") or ""),
        }

    def test_render(self) -> dict[str, Any]:
        result = self._render.test_connection()
        return {
            "provider": PROVIDER_RENDER,
            "configured": self._render.enabled,
            "ok": bool(result.get("ok")),
            "detail": str(result.get("detail") or ""),
        }
