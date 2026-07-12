"""Read the organization's knowledge graph."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Runbook, ServiceDependency, ServiceNode


@dataclass
class GraphDependency:
    id: uuid.UUID
    upstream_service_id: uuid.UUID
    downstream_service_id: uuid.UUID
    upstream_name: str
    downstream_name: str
    dependency_type: str | None


@dataclass
class KnowledgeGraphSnapshot:
    services: list[ServiceNode]
    dependencies: list[GraphDependency]
    runbooks: list[Runbook]


class KnowledgeGraphService:
    def get_graph(self, db: Session, organization_id: uuid.UUID) -> KnowledgeGraphSnapshot:
        services = list(
            db.scalars(
                select(ServiceNode)
                .where(ServiceNode.organization_id == organization_id)
                .order_by(ServiceNode.name.asc())
            ).all()
        )
        service_by_id = {s.id: s for s in services}

        deps_raw = list(
            db.scalars(
                select(ServiceDependency).where(
                    ServiceDependency.organization_id == organization_id
                )
            ).all()
        )
        dependencies: list[GraphDependency] = []
        for dep in deps_raw:
            up = service_by_id.get(dep.upstream_service_id)
            down = service_by_id.get(dep.downstream_service_id)
            if up is None or down is None:
                continue
            dependencies.append(
                GraphDependency(
                    id=dep.id,
                    upstream_service_id=dep.upstream_service_id,
                    downstream_service_id=dep.downstream_service_id,
                    upstream_name=up.name,
                    downstream_name=down.name,
                    dependency_type=dep.dependency_type,
                )
            )

        runbooks = list(
            db.scalars(
                select(Runbook)
                .where(Runbook.organization_id == organization_id)
                .order_by(Runbook.title.asc())
            ).all()
        )

        return KnowledgeGraphSnapshot(
            services=services,
            dependencies=dependencies,
            runbooks=runbooks,
        )
