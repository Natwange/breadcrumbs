"""Investigation engine API routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.rate_limit import rate_limit
from app.core.roles import CAN_READ, CAN_WRITE_CONTENT
from app.deps import CurrentOrganization, DbSession, require_org_role
from app.models import (
    Alert,
    Evidence,
    Hypothesis,
    Incident,
    IncidentImpact,
    InvestigationPlan,
    InvestigationRun,
    Postmortem,
    SlackDraft,
    SuggestedAction,
    TimelineEvent,
)
from app.schemas.investigation_engine import (
    AlertOut,
    EvidenceOut,
    HypothesisOut,
    IncidentImpactOut,
    IncidentWorkspaceIncidentOut,
    IncidentWorkspaceOut,
    InvestigationPlanOut,
    InvestigationRunDetailOut,
    InvestigationRunStartOut,
    PostmortemSummaryOut,
    SlackDraftOut,
    SuggestedActionOut,
    TimelineEventOut,
)
from app.services.investigation_engine.investigation_runner import InvestigationRunner

router = APIRouter(prefix="/api", tags=["investigation-engine"])

_read = require_org_role(*CAN_READ)
_write = require_org_role(*CAN_WRITE_CONTENT)

_runner = InvestigationRunner()


def _run_detail(
    db: DbSession,
    organization_id: uuid.UUID,
    run: InvestigationRun,
) -> InvestigationRunDetailOut:
    plan = db.scalar(
        select(InvestigationPlan).where(
            InvestigationPlan.investigation_run_id == run.id,
            InvestigationPlan.organization_id == organization_id,
        )
    )
    evidence_count = db.scalar(
        select(func.count())
        .select_from(Evidence)
        .where(
            Evidence.investigation_run_id == run.id,
            Evidence.organization_id == organization_id,
        )
    ) or 0
    timeline_count = db.scalar(
        select(func.count())
        .select_from(TimelineEvent)
        .where(
            TimelineEvent.investigation_run_id == run.id,
            TimelineEvent.organization_id == organization_id,
        )
    ) or 0
    hypothesis = db.scalar(
        select(Hypothesis)
        .where(
            Hypothesis.investigation_run_id == run.id,
            Hypothesis.organization_id == organization_id,
        )
        .order_by(Hypothesis.rank.asc())
        .limit(1)
    )
    slack_draft = db.scalar(
        select(SlackDraft).where(
            SlackDraft.investigation_run_id == run.id,
            SlackDraft.organization_id == organization_id,
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
        relevance_tracking=run.relevance_tracking,
        executive_summary=run.executive_summary,
        reasoning_status=run.reasoning_status,
        reasoning_tracking=run.reasoning_tracking,
    )


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
    _rate_limit: Annotated[None, Depends(rate_limit("investigation"))] = None,
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

    return _run_detail(db, organization.id, run)


@router.get(
    "/incidents/{incident_id}/workspace",
    response_model=IncidentWorkspaceOut,
)
def get_incident_workspace(
    incident_id: uuid.UUID,
    organization: CurrentOrganization,
    db: DbSession,
    _membership: Annotated[object, Depends(_read)],
    run_id: uuid.UUID | None = Query(default=None, description="Investigation run to load"),
) -> IncidentWorkspaceOut:
    incident = db.scalar(
        select(Incident).where(
            Incident.id == incident_id,
            Incident.organization_id == organization.id,
        )
    )
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    alerts = list(
        db.scalars(
            select(Alert)
            .where(
                Alert.incident_id == incident.id,
                Alert.organization_id == organization.id,
            )
            .order_by(Alert.fired_at.desc())
        ).all()
    )

    runs = list(
        db.scalars(
            select(InvestigationRun)
            .where(
                InvestigationRun.incident_id == incident.id,
                InvestigationRun.organization_id == organization.id,
            )
            .order_by(InvestigationRun.started_at.desc().nullslast())
        ).all()
    )

    selected: InvestigationRun | None = None
    if run_id is not None:
        selected = db.scalar(
            select(InvestigationRun).where(
                InvestigationRun.id == run_id,
                InvestigationRun.incident_id == incident.id,
                InvestigationRun.organization_id == organization.id,
            )
        )
        if selected is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Investigation run not found for this incident",
            )
    elif runs:
        selected = runs[0]

    run_summaries: list[InvestigationRunStartOut] = []
    for run in runs:
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
        run_summaries.append(
            InvestigationRunStartOut(
                id=run.id,
                organization_id=run.organization_id,
                incident_id=run.incident_id,
                status=run.status,
                trigger=run.trigger,
                summary=run.summary,
                started_at=run.started_at,
                completed_at=run.completed_at,
                evidence_count=evidence_count,
                timeline_count=timeline_count,
            )
        )

    evidence: list[Evidence] = []
    timeline: list[TimelineEvent] = []
    hypotheses: list[Hypothesis] = []
    actions: list[SuggestedAction] = []
    impacts: list[IncidentImpact] = []
    run_detail: InvestigationRunDetailOut | None = None

    if selected is not None:
        run_detail = _run_detail(db, organization.id, selected)
        evidence = list(
            db.scalars(
                select(Evidence)
                .where(
                    Evidence.investigation_run_id == selected.id,
                    Evidence.organization_id == organization.id,
                )
                .order_by(Evidence.relevance_score.desc().nullslast())
            ).all()
        )
        timeline = list(
            db.scalars(
                select(TimelineEvent)
                .where(
                    TimelineEvent.investigation_run_id == selected.id,
                    TimelineEvent.organization_id == organization.id,
                )
                .order_by(TimelineEvent.event_time.asc().nullslast())
            ).all()
        )
        hypotheses = list(
            db.scalars(
                select(Hypothesis)
                .where(
                    Hypothesis.investigation_run_id == selected.id,
                    Hypothesis.organization_id == organization.id,
                )
                .order_by(Hypothesis.rank.asc().nullslast())
            ).all()
        )
        actions = list(
            db.scalars(
                select(SuggestedAction)
                .where(
                    SuggestedAction.investigation_run_id == selected.id,
                    SuggestedAction.organization_id == organization.id,
                )
                .order_by(SuggestedAction.created_at.asc())
            ).all()
        )
        impacts = list(
            db.scalars(
                select(IncidentImpact)
                .where(
                    IncidentImpact.incident_id == incident.id,
                    IncidentImpact.organization_id == organization.id,
                )
                .order_by(IncidentImpact.created_at.asc())
            ).all()
        )

    postmortem = db.scalar(
        select(Postmortem)
        .where(
            Postmortem.incident_id == incident.id,
            Postmortem.organization_id == organization.id,
        )
        .order_by(Postmortem.created_at.desc())
        .limit(1)
    )

    return IncidentWorkspaceOut(
        incident=IncidentWorkspaceIncidentOut.model_validate(incident),
        alerts=[AlertOut.model_validate(a) for a in alerts],
        runs=run_summaries,
        run=run_detail,
        evidence=[EvidenceOut.model_validate(e) for e in evidence],
        timeline=[TimelineEventOut.model_validate(e) for e in timeline],
        hypotheses=[HypothesisOut.model_validate(h) for h in hypotheses],
        suggested_actions=[SuggestedActionOut.model_validate(a) for a in actions],
        impacts=[IncidentImpactOut.model_validate(i) for i in impacts],
        postmortem=PostmortemSummaryOut.model_validate(postmortem) if postmortem else None,
    )
