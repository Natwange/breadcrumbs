"""Apply approved proposals and manual graph updates."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeGraphProposal, Runbook, ServiceDependency, ServiceNode
from app.services.knowledge_builder.knowledge_validation import validate_extraction


@dataclass
class ApplyResult:
    services_created: int = 0
    services_updated: int = 0
    dependencies_created: int = 0
    runbooks_created: int = 0
    errors: list[str] = field(default_factory=list)


class KnowledgeUpdateService:
    """Mutate ServiceNode / ServiceDependency / Runbook from approved proposals."""

    def apply_proposal(
        self, db: Session, proposal: KnowledgeGraphProposal
    ) -> ApplyResult:
        if proposal.payload is None:
            return ApplyResult(errors=["Proposal has no payload"])

        validation = validate_extraction(proposal.payload)
        if not validation.valid:
            return ApplyResult(errors=validation.errors)

        return self.apply_payload(db, proposal.organization_id, proposal.payload)

    def apply_payload(
        self, db: Session, organization_id: uuid.UUID, payload: dict
    ) -> ApplyResult:
        result = ApplyResult()
        services_by_name = {
            s.name.lower(): s
            for s in db.scalars(
                select(ServiceNode).where(ServiceNode.organization_id == organization_id)
            ).all()
        }

        for svc in payload.get("services", []):
            if not isinstance(svc, dict) or not svc.get("name"):
                continue
            key = str(svc["name"]).lower()
            existing = services_by_name.get(key)
            if existing is None:
                node = ServiceNode(
                    organization_id=organization_id,
                    name=str(svc["name"]),
                    service_type=svc.get("service_type"),
                    description=svc.get("description"),
                    metadata_={"source": "knowledge_builder"},
                )
                db.add(node)
                db.flush()
                services_by_name[key] = node
                result.services_created += 1
            else:
                if svc.get("description") and not existing.description:
                    existing.description = svc.get("description")
                if svc.get("service_type") and not existing.service_type:
                    existing.service_type = svc.get("service_type")
                result.services_updated += 1

        for dep in payload.get("dependencies", []):
            if not isinstance(dep, dict):
                continue
            up_name = str(dep.get("upstream", "")).lower()
            down_name = str(dep.get("downstream", "")).lower()
            upstream = services_by_name.get(up_name)
            downstream = services_by_name.get(down_name)
            if upstream is None or downstream is None:
                result.errors.append(f"Missing service for dependency {up_name}->{down_name}")
                continue

            exists = db.scalar(
                select(ServiceDependency).where(
                    ServiceDependency.organization_id == organization_id,
                    ServiceDependency.upstream_service_id == upstream.id,
                    ServiceDependency.downstream_service_id == downstream.id,
                )
            )
            if exists is None:
                db.add(
                    ServiceDependency(
                        organization_id=organization_id,
                        upstream_service_id=upstream.id,
                        downstream_service_id=downstream.id,
                        dependency_type=dep.get("dependency_type"),
                    )
                )
                result.dependencies_created += 1

        for rb in payload.get("runbooks", []):
            if not isinstance(rb, dict) or not rb.get("title"):
                continue
            service_id = None
            svc_name = rb.get("service")
            if svc_name:
                svc = services_by_name.get(str(svc_name).lower())
                service_id = svc.id if svc else None

            db.add(
                Runbook(
                    organization_id=organization_id,
                    title=str(rb["title"]),
                    content=rb.get("content"),
                    service_id=service_id,
                    tags={"source": "knowledge_builder"},
                )
            )
            result.runbooks_created += 1

        db.flush()
        return result
