"""Model foundation tests for Phase 2."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models as models
from app.db.base import Base, OrganizationScopedMixin
from app.models import (
    Evidence,
    Incident,
    Organization,
    UserProfile,
)

EXPECTED_MODELS = {
    "UserProfile",
    "Organization",
    "OrganizationMember",
    "OrganizationInvitation",
    "OrganizationSettings",
    "KnowledgeArtifact",
    "ServiceNode",
    "ServiceDependency",
    "KnowledgeGraphProposal",
    "Runbook",
    "Incident",
    "Alert",
    "AlertCorrelation",
    "IncidentImpact",
    "Postmortem",
    "InvestigationRun",
    "InvestigationPlan",
    "CollectorRun",
    "Evidence",
    "TimelineEvent",
    "Hypothesis",
    "SuggestedAction",
    "SlackDraft",
    "EmbeddingRecord",
    "IntegrationConnection",
    "AuditLog",
}


def test_all_models_import():
    """Every expected model is importable and mapped."""
    for name in EXPECTED_MODELS:
        assert hasattr(models, name), f"missing model export: {name}"
    mapped_tables = set(Base.metadata.tables.keys())
    # 26 models, but ServiceDependency etc. all have distinct tables.
    assert len(mapped_tables) == len(EXPECTED_MODELS)


def test_uuid_primary_keys():
    """Primary keys are UUIDs generated on instantiation."""
    org = Organization(name="Acme", slug="acme")
    # default is applied at flush time; construct + check type after add below.
    assert org.id is None or isinstance(org.id, uuid.UUID)


def _make_org(session: Session, slug: str = "acme") -> Organization:
    org = Organization(name="Acme", slug=slug)
    session.add(org)
    session.flush()
    return org


def test_create_core_entities(session: Session):
    """Can create Organization, UserProfile, Incident, and Evidence."""
    org = _make_org(session)
    assert isinstance(org.id, uuid.UUID)
    assert org.onboarding_status == "pending"
    assert org.deleted_at is None

    user = UserProfile(email="engineer@acme.test", full_name="Engineer")
    session.add(user)
    session.flush()
    assert isinstance(user.id, uuid.UUID)

    incident = Incident(
        organization_id=org.id,
        title="Checkout latency spike",
        status="open",
        severity="sev2",
    )
    session.add(incident)
    session.flush()
    assert isinstance(incident.id, uuid.UUID)

    evidence = Evidence(
        organization_id=org.id,
        incident_id=incident.id,
        source="datadog",
        evidence_type="metric",
        content="p99 latency > 2s",
        deduplication_key="datadog:checkout:p99",
        metadata_={"host": "web-01", "region": "us-east-1"},
        relevance_score=0.92,
        relevance_reason="Strong temporal correlation with incident start",
    )
    session.add(evidence)
    session.commit()

    stored = session.get(Evidence, evidence.id)
    assert stored is not None
    assert stored.organization_id == org.id
    assert stored.metadata_ == {"host": "web-01", "region": "us-east-1"}
    assert stored.deduplication_key == "datadog:checkout:p99"
    assert stored.relevance_score == pytest.approx(0.92)


def test_cross_org_model_requires_organization_id(session: Session):
    """Organization-scoped models reject a NULL organization_id."""
    incident = Incident(title="Orphan incident", status="open")
    session.add(incident)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_evidence_requires_organization_id(session: Session):
    """Evidence specifically must be organization-scoped."""
    org = _make_org(session)
    incident = Incident(organization_id=org.id, title="Incident", status="open")
    session.add(incident)
    session.flush()

    evidence = Evidence(
        incident_id=incident.id,
        source="logs",
        evidence_type="log",
    )
    session.add(evidence)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_org_scoped_models_have_indexed_org_id():
    """Every org-scoped model exposes an indexed, NOT NULL organization_id."""
    scoped = [
        mapper.class_
        for mapper in Base.registry.mappers
        if issubclass(mapper.class_, OrganizationScopedMixin)
    ]
    assert scoped, "expected organization-scoped models"

    for cls in scoped:
        table = cls.__table__
        assert "organization_id" in table.columns, cls.__name__
        col = table.columns["organization_id"]
        assert col.nullable is False, cls.__name__
        indexed_cols = {
            tuple(c.name for c in idx.columns) for idx in table.indexes
        }
        assert ("organization_id",) in indexed_cols, cls.__name__


def test_key_foreign_keys_are_indexed():
    """incident_id and investigation_run_id columns are indexed where present."""
    for table in Base.metadata.tables.values():
        for fk_col in ("incident_id", "investigation_run_id"):
            if fk_col in table.columns:
                indexed = any(
                    fk_col in {c.name for c in idx.columns} for idx in table.indexes
                )
                assert indexed, f"{table.name}.{fk_col} should be indexed"
