"""SQLAlchemy models.

Importing this package registers every model with ``Base.metadata`` so that
Alembic autogeneration and ``create_all`` see the full schema.
"""

from app.db.base import Base
from app.models.audit import AuditLog
from app.models.embeddings import EmbeddingRecord
from app.models.incidents import (
    Alert,
    AlertCorrelation,
    Incident,
    IncidentImpact,
    Postmortem,
)
from app.models.integrations import IntegrationConnection
from app.models.investigations import (
    CollectorRun,
    Evidence,
    Hypothesis,
    InvestigationPlan,
    InvestigationRun,
    SlackDraft,
    SuggestedAction,
    TimelineEvent,
)
from app.models.knowledge import (
    KnowledgeArtifact,
    KnowledgeGraphProposal,
    Runbook,
    ServiceDependency,
    ServiceNode,
)
from app.models.organizations import (
    Organization,
    OrganizationInvitation,
    OrganizationMember,
    OrganizationSettings,
)
from app.models.users import UserProfile

__all__ = [
    "Base",
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
]
