"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";

import AlertCards from "@/components/incidents/AlertCards";
import EvidenceByRelevance from "@/components/incidents/EvidenceByRelevance";
import HypothesesSection from "@/components/incidents/HypothesesSection";
import ImpactSection from "@/components/incidents/ImpactSection";
import InvestigationProgress from "@/components/incidents/InvestigationProgress";
import PostmortemSection from "@/components/incidents/PostmortemSection";
import SlackDraftSection from "@/components/incidents/SlackDraftSection";
import SuggestedActionsSection from "@/components/incidents/SuggestedActionsSection";
import TimelineSection from "@/components/incidents/TimelineSection";
import {
  BackLink,
  ErrorBanner,
  LoadingCard,
  PageHeader,
  Section,
  StatusBadge,
} from "@/components/ui/Primitives";
import {
  getIncidentWorkspace,
  isTerminalRunStatus,
  resolveIncident,
  startInvestigation,
  type IncidentWorkspace,
  type PostmortemSummary,
} from "@/lib/api";

const POLL_INTERVAL_MS = 2000;

export default function IncidentDetailPage() {
  const params = useParams<{ id: string }>();
  const incidentId = params.id;

  const [workspace, setWorkspace] = useState<IncidentWorkspace | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [resolving, setResolving] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = useCallback(() => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const loadWorkspace = useCallback(
    async (runId?: string) => {
      const data = await getIncidentWorkspace(incidentId, runId);
      setWorkspace(data);
      setSelectedRunId(data.run?.id ?? data.runs[0]?.id ?? null);
      return data;
    },
    [incidentId]
  );

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        await loadWorkspace();
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load incident");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
      clearTimer();
    };
  }, [incidentId, loadWorkspace, clearTimer]);

  useEffect(() => {
    const run = workspace?.run;
    if (!run || isTerminalRunStatus(run.status)) {
      clearTimer();
      return;
    }

    let active = true;
    const poll = async () => {
      try {
        await loadWorkspace(selectedRunId ?? undefined);
        if (!active) return;
      } catch {
        if (!active) return;
        clearTimer();
        return;
      }
      timer.current = setTimeout(poll, POLL_INTERVAL_MS);
    };
    poll();

    return () => {
      active = false;
      clearTimer();
    };
  }, [workspace?.run, selectedRunId, loadWorkspace, clearTimer]);

  async function handleStart() {
    setStarting(true);
    setError(null);
    try {
      const started = await startInvestigation(incidentId);
      setSelectedRunId(started.id);
      await loadWorkspace(started.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start investigation");
    } finally {
      setStarting(false);
    }
  }

  async function handleResolve() {
    setResolving(true);
    setError(null);
    try {
      await resolveIncident(incidentId);
      await loadWorkspace(selectedRunId ?? undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resolve incident");
    } finally {
      setResolving(false);
    }
  }

  async function handleSelectRun(runId: string) {
    setSelectedRunId(runId);
    setError(null);
    try {
      await loadWorkspace(runId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load run");
    }
  }

  function handlePostmortemGenerated(postmortem: PostmortemSummary) {
    setWorkspace((prev) => (prev ? { ...prev, postmortem } : prev));
  }

  if (loading) return <LoadingCard />;
  if (error && !workspace) return <ErrorBanner message={error} />;
  if (!workspace) return <ErrorBanner message="Incident not found" />;

  const { incident } = workspace;
  const isResolved =
    incident.status === "resolved" || incident.status === "closed";

  return (
    <div className="workspace-content">
      <BackLink href="/incidents" label="Incidents" />
      <PageHeader
        title={incident.title}
        description={incident.description ?? undefined}
        actions={
          <div className="card-row">
            <StatusBadge status={incident.status} />
            {!isResolved && (
              <button
                type="button"
                className="btn btn-ghost"
                onClick={handleResolve}
                disabled={resolving}
              >
                {resolving ? "Resolving…" : "Resolve incident"}
              </button>
            )}
          </div>
        }
      />
      {error && <ErrorBanner message={error} />}

      <Section title="Alerts">
        <AlertCards alerts={workspace.alerts} />
      </Section>

      <Section title="Investigation progress">
        <InvestigationProgress
          runs={workspace.runs}
          run={workspace.run}
          selectedRunId={selectedRunId}
          onSelectRun={handleSelectRun}
          onStart={handleStart}
          starting={starting}
        />
      </Section>

      <Section title="Evidence">
        <EvidenceByRelevance evidence={workspace.evidence} />
      </Section>

      <Section title="Timeline">
        <TimelineSection timeline={workspace.timeline} />
      </Section>

      <Section title="Hypotheses">
        <HypothesesSection hypotheses={workspace.hypotheses} />
      </Section>

      <Section title="Suggested actions">
        <SuggestedActionsSection actions={workspace.suggested_actions} />
      </Section>

      <Section title="Impact">
        <ImpactSection impacts={workspace.impacts} />
      </Section>

      <Section title="Slack draft">
        <SlackDraftSection run={workspace.run} />
      </Section>

      <Section title="Postmortem">
        <PostmortemSection
          incidentId={incidentId}
          postmortem={workspace.postmortem}
          onGenerated={handlePostmortemGenerated}
        />
      </Section>
    </div>
  );
}
