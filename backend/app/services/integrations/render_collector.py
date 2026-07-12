"""Collect Render evidence (deploy events, status, health) for an incident.

Normalizes Render API responses into the same raw-evidence shape produced by
the fake collectors. All free-text content is secret-redacted before storage.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from app.services.integrations.collector_interface import CollectorError
from app.services.integrations.render_client import RenderClient
from app.services.knowledge_builder.secret_redactor import redact_secrets

_SOURCE = "render"
_FAILED_STATUSES = {"build_failed", "update_failed", "canceled", "deactivated", "failed"}
_LIVE_STATUSES = {"live", "update_in_progress", "created"}


class RenderCollector:
    name = "render_collector"

    def __init__(self, client: RenderClient) -> None:
        self._client = client

    def collect(
        self,
        service_name: str,
        start_time: datetime,
        end_time: datetime,
        alert_context: dict,
    ) -> list[dict]:
        try:
            services = self._client.get_services()
        except httpx.HTTPError as exc:
            raise CollectorError(f"Render service lookup failed: {exc}") from exc

        target = self._match_service(service_name, services, alert_context)
        if target is None:
            return []

        service_id = str(target.get("id") or "")
        resolved_name = str(target.get("name") or service_name)
        evidence: list[dict] = [self._service_health(resolved_name, target)]

        if not service_id:
            return evidence

        try:
            deploys = self._client.get_deploys(service_id)
        except httpx.HTTPError as exc:
            raise CollectorError(f"Render deploy lookup failed for {resolved_name}: {exc}") from exc

        for deploy in deploys:
            normalized = self._normalize_deploy(resolved_name, deploy)
            if normalized:
                evidence.append(normalized)
        return evidence

    def _match_service(
        self, service_name: str, services: list[dict], alert_context: dict
    ) -> dict | None:
        wanted_id = (alert_context or {}).get("render_service_id")
        if wanted_id:
            for svc in services:
                if str(svc.get("id")) == str(wanted_id):
                    return svc
        name_lower = (service_name or "").lower()
        for svc in services:
            if str(svc.get("name") or "").lower() == name_lower:
                return svc
        for svc in services:
            if name_lower and name_lower in str(svc.get("name") or "").lower():
                return svc
        # Fall back to the first service when only one is configured.
        return services[0] if len(services) == 1 else None

    def _service_health(self, name: str, service: dict) -> dict:
        suspended = service.get("suspended")
        status = "suspended" if suspended in (True, "suspended") else "operational"
        return {
            "source": _SOURCE,
            "evidence_type": "provider_status",
            "title": f"Render service health: {name}",
            "content": redact_secrets(
                f"Service '{name}' is {status}. Type: {service.get('type') or 'unknown'}."
            ).redacted_text,
            "observed_at": service.get("updatedAt") or service.get("createdAt"),
            "metadata": {
                "service": name,
                "service_id": service.get("id"),
                "status": status,
                "type": service.get("type"),
            },
        }

    def _normalize_deploy(self, service_name: str, deploy: dict) -> dict | None:
        if not isinstance(deploy, dict):
            return None
        status = str(deploy.get("status") or "unknown")
        failed = status in _FAILED_STATUSES
        commit = deploy.get("commit") if isinstance(deploy.get("commit"), dict) else {}
        commit_message = str(commit.get("message") or "")
        commit_id = str(commit.get("id") or "")[:7]

        title_prefix = "Failed deploy" if failed else "Deploy"
        summary = f"{title_prefix} for {service_name} ({status})"
        if commit_message:
            summary = f"{summary}: {commit_message.splitlines()[0]}"

        return {
            "source": _SOURCE,
            "evidence_type": "deploy",
            "title": redact_secrets(summary).redacted_text,
            "content": redact_secrets(
                f"Deploy {deploy.get('id') or ''} status={status}. "
                f"Commit {commit_id}: {commit_message or '(none)'}"
            ).redacted_text,
            "observed_at": deploy.get("finishedAt")
            or deploy.get("updatedAt")
            or deploy.get("createdAt"),
            "metadata": {
                "service": service_name,
                "deploy_id": deploy.get("id"),
                "status": status,
                "failed": failed,
                "commit": commit_id,
            },
        }
