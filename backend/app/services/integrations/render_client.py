"""Thin Render API client.

The API key is read from ``Settings.render_api_key`` (backend env only) and is
never returned by any method. A custom ``httpx`` transport can be injected for
tests so no real network calls are made.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings, get_settings


class RenderClient:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings = settings or get_settings()
        self._api_key = settings.render_api_key
        self._base_url = settings.render_api_base.rstrip("/")
        self._owner_id = settings.render_owner_id
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    @property
    def owner_id(self) -> str:
        return self._owner_id

    def _client(self) -> httpx.Client:
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=30.0,
            transport=self._transport,
        )

    def test_connection(self) -> dict[str, Any]:
        """Lightweight authenticated probe. Never returns the API key."""
        if not self._api_key:
            return {"ok": False, "detail": "Render API key not configured"}
        try:
            with self._client() as client:
                resp = client.get("/services", params={"limit": 1})
                resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return {"ok": False, "detail": f"Render returned {exc.response.status_code}"}
        except httpx.HTTPError as exc:
            return {"ok": False, "detail": f"Render request failed: {exc.__class__.__name__}"}
        return {"ok": True, "detail": "Authenticated"}

    def get_services(self, *, limit: int = 50) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if self._owner_id:
            params["ownerId"] = self._owner_id
        with self._client() as client:
            resp = client.get("/services", params=params)
            resp.raise_for_status()
            data = resp.json()
        return _unwrap_list(data)

    def get_deploys(self, service_id: str, *, limit: int = 20) -> list[dict]:
        with self._client() as client:
            resp = client.get(f"/services/{service_id}/deploys", params={"limit": limit})
            resp.raise_for_status()
            data = resp.json()
        return _unwrap_list(data)


def _unwrap_list(data: Any) -> list[dict]:
    """Render list endpoints return ``[{"<entity>": {...}, "cursor": "..."}]``."""
    if not isinstance(data, list):
        return []
    items: list[dict] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        # Prefer the nested entity payload; fall back to the entry itself.
        nested = entry.get("service") or entry.get("deploy")
        items.append(nested if isinstance(nested, dict) else entry)
    return items
