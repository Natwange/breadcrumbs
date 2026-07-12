"""Thin GitHub REST API client.

The token is read from ``Settings.github_token`` (backend env only) and is
never returned by any method. A custom ``httpx`` transport can be injected for
tests so no real network calls are made.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings

_API_VERSION = "2022-11-28"


class GithubClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings = settings or get_settings()
        self._token = settings.github_token
        self._base_url = settings.github_api_base.rstrip("/")
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return bool(self._token)

    def _client(self) -> httpx.Client:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _API_VERSION,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=30.0,
            transport=self._transport,
        )

    def test_connection(self) -> dict[str, Any]:
        """Lightweight authenticated probe. Never returns the token."""
        if not self._token:
            return {"ok": False, "detail": "GitHub token not configured"}
        try:
            with self._client() as client:
                resp = client.get("/rate_limit")
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            return {"ok": False, "detail": f"GitHub returned {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            return {"ok": False, "detail": f"GitHub request failed: {exc.__class__.__name__}"}
        remaining = (
            data.get("resources", {}).get("core", {}).get("remaining")
            if isinstance(data, dict)
            else None
        )
        detail = "Authenticated"
        if remaining is not None:
            detail = f"Authenticated ({remaining} core requests remaining)"
        return {"ok": True, "detail": detail}

    def get_commits(
        self,
        repo: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        branch: str | None = None,
        per_page: int = 30,
    ) -> list[dict]:
        params: dict[str, Any] = {"per_page": per_page}
        if since is not None:
            params["since"] = _iso(since)
        if until is not None:
            params["until"] = _iso(until)
        if branch:
            params["sha"] = branch
        with self._client() as client:
            resp = client.get(f"/repos/{repo}/commits", params=params)
            resp.raise_for_status()
            data = resp.json()
        return data if isinstance(data, list) else []

    def get_pull_requests(
        self,
        repo: str,
        *,
        state: str = "all",
        per_page: int = 30,
    ) -> list[dict]:
        params = {"state": state, "sort": "updated", "direction": "desc", "per_page": per_page}
        with self._client() as client:
            resp = client.get(f"/repos/{repo}/pulls", params=params)
            resp.raise_for_status()
            data = resp.json()
        return data if isinstance(data, list) else []


def _iso(dt: datetime) -> str:
    return dt.astimezone().isoformat()
