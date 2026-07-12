"""Investigation engine API routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.core.roles import CAN_READ, CAN_WRITE_CONTENT
from app.deps import CurrentOrganization, DbSession, require_org_role
from app.models import (
    Evidence,
    Hypothesis,
    Incident,
    InvestigationPlan,
    InvestigationRun,
    SlackDraft,
    TimelineEvent,
)
from app.schemas.investigation_engine import (
    HypothesisOut,
    InvestigationPlanOut,
    InvestigationRunDetailOut,
    InvestigationRunStartOut,
    SlackDraftOut,
)
from app.services.investigation_engine.investigation_runner import InvestigationRunner

router = APIRouter(prefix="/api", tags=["investigation-engine"])

_read = require_org_role(*CAN_READ)
_write = require_org_role(*CAN_WRITE_CONTENT)

_runner = InvestigationRunner()


@router.post(
    "/incidents/{incident_id}/investigation-runs",
    response_model=InvestigationRunStartOut,
    status_code=status.HTTP_201_CREATED,
)
def start_investigation(
    incident_id: uuid.UUID,
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_write)],
) -> InvestigationRunStartOut:
    incident = db.scalar(
        select(Incident).where(
            Incident.id == incident_id,
            Incident.organization_id == organization.id,
        )
    )
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    try:
        result = _runner.run(
            db,
            organization.id,
            incident_id,
            trigger="api",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Investigation failed: {exc}",
        ) from exc

    return InvestigationRunStartOut(
        id=result.run.id,
        organization_id=result.run.organization_id,
        incident_id=result.run.incident_id,
        status=result.run.status,
        trigger=result.run.trigger,
        summary=result.run.summary,
        started_at=result.run.started_at,
        completed_at=result.run.completed_at,
        evidence_count=result.evidence_count,
        timeline_count=result.timeline_count,
    )


@router.get(
    "/investigation-runs/{run_id}",
    response_model=InvestigationRunDetailOut,
)
def get_investigation_run(
    run_id: uuid.UUID,
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_read)],
) -> InvestigationRunDetailOut:
    run = db.scalar(
        select(InvestigationRun).where(
            InvestigationRun.id == run_id,
            InvestigationRun.organization_id == organization.id,
        )
    )
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    plan = db.scalar(
        select(InvestigationPlan).where(
            InvestigationPlan.investigation_run_id == run.id,
            InvestigationPlan.organization_id == organization.id,
        )
    )
    evidence_count = db.scalar(
        select(func.count())
        .select_from(Evidence)
        .where(
            Evidence.investigation_run_id == run.id,
            Evidence.organization_id == organization.id,
        )
    ) or 0
    timeline_count = db.scalar(
        select(func.count())
        .select_from(TimelineEvent)
        .where(
            TimelineEvent.investigation_run_id == run.id,
            TimelineEvent.organization_id == organization.id,
        )
    ) or 0
    hypothesis = db.scalar(
        select(Hypothesis)
        .where(
            Hypothesis.investigation_run_id == run.id,
            Hypothesis.organization_id == organization.id,
        )
        .order_by(Hypothesis.rank.asc())
        .limit(1)
    )
    slack_draft = db.scalar(
        select(SlackDraft).where(
            SlackDraft.investigation_run_id == run.id,
            SlackDraft.organization_id == organization.id,
        )
    )

    return InvestigationRunDetailOut(
        id=run.id,
        organization_id=run.organization_id,
        incident_id=run.incident_id,
        status=run.status,
        trigger=run.trigger,
        summary=run.summary,
        started_at=run.started_at,
        completed_at=run.completed_at,
        plan=InvestigationPlanOut.model_validate(plan) if plan else None,
        evidence_count=evidence_count,
        timeline_count=timeline_count,
        hypothesis=HypothesisOut.model_validate(hypothesis) if hypothesis else None,
        slack_draft=SlackDraftOut.model_validate(slack_draft) if slack_draft else None,
    )
