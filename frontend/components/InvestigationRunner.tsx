"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  getInvestigationRun,
  isTerminalRunStatus,
  startInvestigation,
  type InvestigationRunDetail,
} from "@/lib/api";

const POLL_INTERVAL_MS = 2000;

interface Props {
  incidentId: string;
  incidentTitle: string;
}

export default function InvestigationRunner({ incidentId, incidentTitle }: Props) {
  const [run, setRun] = useState<InvestigationRunDetail | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = useCallback(() => {
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  // Live polling: fetches run status on an interval and STOPS as soon as the
  // run reaches a terminal state (completed/failed).
  useEffect(() => {
    if (!runId) return;
    let active = true;

    const poll = async () => {
      try {
        const detail = await getInvestigationRun(runId);
        if (!active) return;
        setRun(detail);
        if (isTerminalRunStatus(detail.status)) {
          clearTimer();
          return;
        }
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to poll run");
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
  }, [runId, clearTimer]);

  const onStart = useCallback(async () => {
    setStarting(true);
    setError(null);
    setRun(null);
    setRunId(null);
    try {
      const started = await startInvestigation(incidentId);
      setRunId(started.id);
      setRun(started as InvestigationRunDetail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start investigation");
    } finally {
      setStarting(false);
    }
  }, [incidentId]);

  const isRunning = run != null && !isTerminalRunStatus(run.status);
  const statusColor =
    run?.status === "completed"
      ? "#22c55e"
      : run?.status === "failed"
        ? "#f87171"
        : "#eab308";

  return (
    <div className="health-card">
      <div className="health-header">
        <span className="health-title">{incidentTitle}</span>
      </div>

      <button
        type="button"
        className="health-button"
        onClick={onStart}
        disabled={starting || isRunning}
      >
        {starting ? "Starting…" : isRunning ? "Investigating…" : "Run investigation"}
      </button>

      {error && <p className="auth-error">{error}</p>}

      {run && (
        <div className="account-org">
          <p className="health-detail">
            <span
              className="health-dot"
              style={{ backgroundColor: statusColor, marginRight: 8 }}
            />
            Status: <strong>{run.status}</strong>
            {isRunning && " (live)"}
          </p>
          <p className="health-endpoint">
            Evidence: {run.evidence_count} · Timeline: {run.timeline_count}
            {run.reasoning_status ? ` · Reasoning: ${run.reasoning_status}` : ""}
          </p>
          {run.executive_summary && (
            <p className="health-detail">{run.executive_summary}</p>
          )}
          {run.hypothesis && (
            <p className="health-detail">
              Top hypothesis: <strong>{run.hypothesis.title}</strong>
            </p>
          )}
          {isTerminalRunStatus(run.status) && (
            <p className="health-endpoint">Polling stopped — run {run.status}.</p>
          )}
        </div>
      )}
    </div>
  );
}
