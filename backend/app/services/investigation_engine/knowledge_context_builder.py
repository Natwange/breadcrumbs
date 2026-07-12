"""Build investigation context from the approved knowledge graph."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Alert, Incident
from app.services.knowledge_builder.knowledge_graph_service import KnowledgeGraphService


@dataclass
class InvestigationContext:
    affected_service: str | None
    direct_dependencies: list[str] = field(default_factory=list)
    indirect_dependencies: list[str] = field(default_factory=list)
    related_services: list[str] = field(default_factory=list)
    relevant_runbooks: list[dict] = field(default_factory=list)
    external_providers: list[str] = field(default_factory=list)
    architecture_summary: str = ""
    possible_blast_radius: list[str] = field(default_factory=list)


_EXTERNAL_TYPES = frozenset({"database", "hosting", "external", "saas", "cloud"})


class KnowledgeContextBuilder:
    def __init__(self, graph_service: KnowledgeGraphService | None = None) -> None:
        self._graph = graph_service or KnowledgeGraphService()

    def build(
        self,
        db: Session,
        organization_id: uuid.UUID,
        incident: Incident,
        alerts: list[Alert],
    ) -> InvestigationContext:
        snapshot = self._graph.get_graph(db, organization_id)
        service_by_name = {s.name.lower(): s for s in snapshot.services}
        affected = self._resolve_affected_service(incident, alerts)

        direct: set[str] = set()
        indirect: set[str] = set()
        blast: set[str] = set()
        related: set[str] = set()

        if affected:
            affected_key = affected.lower()
            related.add(affected)

            for dep in snapshot.dependencies:
                up = dep.upstream_name.lower()
                down = dep.downstream_name.lower()
                if up == affected_key:
                    direct.add(dep.downstream_name)
                    related.add(dep.downstream_name)
                if down == affected_key:
                    blast.add(dep.upstream_name)
                    related.add(dep.upstream_name)

            for dep in snapshot.dependencies:
                up = dep.upstream_name.lower()
                down = dep.downstream_name.lower()
                if up in {d.lower() for d in direct}:
                    indirect.add(dep.downstream_name)
                    related.add(dep.downstream_name)

        indirect -= direct
        indirect.discard(affected or "")

        external: list[str] = []
        for name in related:
            node = service_by_name.get(name.lower())
            if node is None:
                continue
            st = (node.service_type or "").lower()
            if st in _EXTERNAL_TYPES or name.lower() in {"render", "supabase", "aws", "datadog"}:
                external.append(node.name)

        runbooks: list[dict] = []
        for rb in snapshot.runbooks:
            text = f"{rb.title} {rb.content or ''}".lower()
            if affected and affected.lower() in text:
                runbooks.append({"id": str(rb.id), "title": rb.title})
            elif not affected:
                runbooks.append({"id": str(rb.id), "title": rb.title})

        summary_parts = [f"{len(snapshot.services)} services", f"{len(snapshot.dependencies)} dependencies"]
        if affected:
            summary_parts.insert(0, f"affected={affected}")
        architecture_summary = "; ".join(summary_parts)

        return InvestigationContext(
            affected_service=affected,
            direct_dependencies=sorted(direct),
            indirect_dependencies=sorted(indirect),
            related_services=sorted(related),
            relevant_runbooks=runbooks,
            external_providers=sorted(set(external)),
            architecture_summary=architecture_summary,
            possible_blast_radius=sorted(blast),
        )

    def _resolve_affected_service(
        self, incident: Incident, alerts: list[Alert]
    ) -> str | None:
        meta = incident.metadata_ or {}
        if meta.get("affected_service"):
            return str(meta["affected_service"])

        for alert in alerts:
            payload = alert.raw_payload or {}
            for key in ("service", "service_name", "entity", "host"):
                if payload.get(key):
                    return str(payload[key])

        return None
