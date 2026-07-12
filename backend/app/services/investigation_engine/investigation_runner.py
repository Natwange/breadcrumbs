"""Orchestrate the full investigation workflow."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    CollectorRun,
    Evidence,
    Hypothesis,
    Incident,
    InvestigationPlan,
    InvestigationRun,
    SlackDraft,
    TimelineEvent,
)
from app.services.investigation_engine.collector_registry import CollectorRegistry
from app.services.investigation_engine.evidence_normalizer import EvidenceNormalizer
from app.services.investigation_engine.evidence_quality_validator import EvidenceQualityValidator
from app.services.investigation_engine.investigation_planner import InvestigationPlanner
from app.services.investigation_engine.knowledge_context_builder import KnowledgeContextBuilder
from app.services.investigation_engine.relevance_judge import RelevanceJudge
from app.services.investigation_engine.timeline_builder import TimelineBuilder
from app.services.incident_reasoning.reasoning_engine import ReasoningEngine
from app.services.vector_search.similarity_service import SimilarityContext, SimilarityService


@dataclass
class InvestigationResult:
    run: InvestigationRun
    plan: InvestigationPlan | None
    evidence_count: int
    timeline_count: int
    hypothesis: Hypothesis | None
    slack_draft: SlackDraft | None
    similarity: SimilarityContext | None = None


class InvestigationRunner:
    def __init__(self) -> None:
        self._context_builder = KnowledgeContextBuilder()
        self._planner = InvestigationPlanner()
        self._collectors = CollectorRegistry()
        self._normalizer = EvidenceNormalizer()
        self._validator = EvidenceQualityValidator()
        self._timeline = TimelineBuilder()
        self._relevance = RelevanceJudge()
        self._reasoning = ReasoningEngine()
        self._similarity = SimilarityService()

    def run(
        self,
        db: Session,
        organization_id: uuid.UUID,
        incident_id: uuid.UUID,
        *,
        trigger: str | None = "manual",
    ) -> InvestigationResult:
        incident = db.scalar(
            select(Incident).where(
                Incident.id == incident_id,
                Incident.organization_id == organization_id,
            )
        )
        if incident is None:
            raise ValueError("Incident not found")

        now = datetime.now(tz=timezone.utc)
        run = InvestigationRun(
            organization_id=organization_id,
            incident_id=incident_id,
            status="running",
            trigger=trigger,
            started_at=now,
        )
        db.add(run)
        db.flush()

        plan_row: InvestigationPlan | None = None
        evidence_rows: list[Evidence] = []
        timeline_events: list[TimelineEvent] = []
        hypothesis_row: Hypothesis | None = None
        slack_row: SlackDraft | None = None
        similarity: SimilarityContext | None = None

        try:
            alerts = list(
                db.scalars(
                    select(Alert)
                    .where(
                        Alert.organization_id == organization_id,
                        Alert.incident_id == incident_id,
                    )
                    .order_by(Alert.fired_at.desc())
                ).all()
            )

            context = self._context_builder.build(db, organization_id, incident, alerts)
            plan_payload = self._planner.create_plan(context)
            plan_row = InvestigationPlan(
                organization_id=organization_id,
                investigation_run_id=run.id,
                status="active",
                steps=plan_payload,
            )
            db.add(plan_row)
            db.flush()

            end_time = now
            start_time = end_time - timedelta(hours=1)
            alert_context = self._collectors.build_alert_context(context, alerts)

            raw_items: list[dict] = []
            for step in plan_payload.get("steps", []):
                collector_name = step.get("collector")
                if not collector_name:
                    continue
                collector = self._collectors.get(collector_name)
                if collector is None:
                    continue

                target = step.get("target_service") or context.affected_service or "unknown"
                collector_run = CollectorRun(
                    organization_id=organization_id,
                    investigation_run_id=run.id,
                    collector_type=collector_name,
                    status="running",
                    started_at=now,
                )
                db.add(collector_run)
                db.flush()

                try:
                    items = collector.collect(target, start_time, end_time, alert_context)
                    raw_items.extend(items)
                    collector_run.status = "completed"
                    collector_run.completed_at = datetime.now(tz=timezone.utc)
                    collector_run.result_summary = f"Collected {len(items)} item(s)"
                except Exception as exc:  # noqa: BLE001
                    collector_run.status = "failed"
                    collector_run.completed_at = datetime.now(tz=timezone.utc)
                    collector_run.error = str(exc)

            normalized = self._normalizer.normalize_many(raw_items)
            validated = [e for e in normalized if self._validator.validate(e).valid]
            deduped = self._deduplicate(validated)

            # Persist evidence first so each row has a stable id to judge.
            item_by_evidence: dict[str, Evidence] = {}
            for item in deduped:
                dedup_key = self._deduplication_key(item)
                row = Evidence(
                    organization_id=organization_id,
                    investigation_run_id=run.id,
                    incident_id=incident_id,
                    source=item["source"],
                    evidence_type=item["evidence_type"],
                    title=item["title"],
                    content=item["content"],
                    deduplication_key=dedup_key,
                    metadata_=item.get("metadata"),
                    observed_at=item.get("observed_at"),
                )
                evidence_rows.append(row)
            db.add_all(evidence_rows)
            db.flush()

            # Step: finding_similar_incidents — retrieve organizational memory.
            # Best-effort: an empty memory store must not fail the run.
            try:
                similarity = self._similarity.find_for_incident(
                    db, organization_id, incident
                )
            except Exception:  # noqa: BLE001
                similarity = None

            timeline_events = self._timeline.build_events(
                organization_id=organization_id,
                incident_id=incident_id,
                investigation_run_id=run.id,
                evidence_rows=evidence_rows,
            )
            db.add_all(timeline_events)
            db.flush()

            # Step: batched evidence relevance judging (Claude + fallback).
            evidence_payload: list[dict] = []
            for row, item in zip(evidence_rows, deduped):
                eid = str(row.id)
                item_by_evidence[eid] = row
                evidence_payload.append(
                    {
                        "evidence_id": eid,
                        "source": item["source"],
                        "evidence_type": item["evidence_type"],
                        "title": item["title"],
                        "content": item["content"],
                    }
                )

            relevance_outcome = self._relevance.judge_batch(
                evidence_payload,
                incident=incident,
                alerts=alerts,
                plan=plan_payload,
                context=context,
                timeline_events=timeline_events,
                runbooks=context.relevant_runbooks,
            )
            for eid, judgment in relevance_outcome.judgments.items():
                row = item_by_evidence.get(eid)
                if row is None:
                    continue
                row.relevance_label = judgment.relevance
                row.relevance_confidence = judgment.confidence
                row.relevance_source = judgment.source
                row.relevance_reason = judgment.reason
            if relevance_outcome.tracking is not None:
                run.relevance_tracking = relevance_outcome.tracking.to_dict()
            db.flush()

            reasoning_result = self._reasoning.run(
                db,
                organization_id,
                run,
                incident,
                similarity=similarity,
            )
            hypothesis_row = (
                reasoning_result.hypotheses[0] if reasoning_result.hypotheses else None
            )
            slack_row = reasoning_result.slack_draft

            run.status = "completed"
            run.completed_at = datetime.now(tz=timezone.utc)
            similar_count = similarity.total() if similarity else 0
            run.summary = (
                f"Collected {len(evidence_rows)} evidence item(s), "
                f"{len(timeline_events)} timeline event(s), "
                f"{similar_count} similar memory match(es), "
                f"reasoning={run.reasoning_status}"
            )
            db.commit()
            db.refresh(run)

        except Exception as exc:
            run.status = "failed"
            run.completed_at = datetime.now(tz=timezone.utc)
            run.summary = f"Investigation failed: {exc}"
            db.commit()
            db.refresh(run)
            raise

        return InvestigationResult(
            run=run,
            plan=plan_row,
            evidence_count=len(evidence_rows),
            timeline_count=len(timeline_events),
            hypothesis=hypothesis_row,
            slack_draft=slack_row,
            similarity=similarity,
        )

    def _deduplication_key(self, item: dict) -> str:
        parts = [
            item.get("source", ""),
            item.get("evidence_type", ""),
            (item.get("title") or "").strip().lower(),
            (item.get("content") or "")[:200].strip().lower(),
        ]
        digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
        return digest[:32]

    def _deduplicate(self, items: list[dict]) -> list[dict]:
        seen: set[str] = set()
        result: list[dict] = []
        for item in items:
            key = self._deduplication_key(item)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result
