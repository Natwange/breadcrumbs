"""Detect architecture drift without deleting approved knowledge.

Compares a new extraction against the live graph and reports differences.
Drift is informational — approved nodes are never removed automatically.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ServiceDependency, ServiceNode


@dataclass
class DriftItem:
    drift_type: str
    message: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "drift_type": self.drift_type,
            "message": self.message,
            "details": self.details,
        }


class DriftDetector:
    def detect(
        self, db: Session, organization_id: uuid.UUID, proposed: dict
    ) -> list[DriftItem]:
        items: list[DriftItem] = []

        existing_services = {
            s.name.lower(): s
            for s in db.scalars(
                select(ServiceNode).where(ServiceNode.organization_id == organization_id)
            ).all()
        }
        proposed_services = {
            str(s["name"]).lower()
            for s in proposed.get("services", [])
            if isinstance(s, dict) and s.get("name")
        }

        for name in proposed_services - set(existing_services.keys()):
            items.append(
                DriftItem(
                    drift_type="new_service",
                    message=f"Proposed new service '{name}' not in graph",
                    details={"service": name},
                )
            )

        for name, node in existing_services.items():
            if name not in proposed_services:
                items.append(
                    DriftItem(
                        drift_type="missing_in_proposal",
                        message=f"Approved service '{node.name}' not mentioned in artifact",
                        details={"service": node.name, "service_id": str(node.id)},
                    )
                )

        existing_deps: set[tuple[str, str]] = set()
        dep_rows = db.scalars(
            select(ServiceDependency).where(
                ServiceDependency.organization_id == organization_id
            )
        ).all()
        id_to_name = {s.id: s.name.lower() for s in existing_services.values()}
        for dep in dep_rows:
            up = id_to_name.get(dep.upstream_service_id)
            down = id_to_name.get(dep.downstream_service_id)
            if up and down:
                existing_deps.add((up, down))

        proposed_deps: set[tuple[str, str]] = set()
        for dep in proposed.get("dependencies", []):
            if not isinstance(dep, dict):
                continue
            up = str(dep.get("upstream", "")).lower()
            down = str(dep.get("downstream", "")).lower()
            if up and down:
                proposed_deps.add((up, down))

        for up, down in proposed_deps - existing_deps:
            items.append(
                DriftItem(
                    drift_type="new_dependency",
                    message=f"Proposed new dependency {up} -> {down}",
                    details={"upstream": up, "downstream": down},
                )
            )

        for up, down in existing_deps - proposed_deps:
            items.append(
                DriftItem(
                    drift_type="dependency_not_in_artifact",
                    message=f"Approved dependency {up} -> {down} not in artifact",
                    details={"upstream": up, "downstream": down},
                )
            )

        return items
