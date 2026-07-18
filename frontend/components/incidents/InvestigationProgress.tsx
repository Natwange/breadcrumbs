"use client";

import { StatusBadge } from "@/components/ui/Primitives";
import type { InvestigationRun, InvestigationRunDetail } from "@/lib/api";
import { isTerminalRunStatus } from "@/lib/api";

interface Props {
  runs: InvestigationRun[];
  run: InvestigationRunDetail | null;
  selectedRunId: string | null;
  onSelectRun: (runId: string) => void;
  onStart: () => void;
  starting: boolean;
}

export default function InvestigationProgress({
  runs,
  run,
  selectedRunId,
  onSelectRun,
  onStart,
  starting,
}: Props) {
  const isRunning = run != null && !isTerminalRunStatus(run.status);

  return (
    <div className="stack">
      <div className="card-row">
        <button
          type="button"
          className="btn"
          onClick={onStart}
          disabled={starting || isRunning}
        >
          {starting ? "Starting…" : isRunning ? "Investigation running…" : "Run investigation"}
        </button>
        {run && (
          <span className="muted small">
            {isRunning ? "Live updates enabled" : `Run ${run.status}`}
          </span>
        )}
      </div>

      {runs.length > 1 && (
        <label className="field">
          <span className="field-label">Investigation run</span>
          <select
            className="input"
            value={selectedRunId ?? ""}
            onChange={(e) => onSelectRun(e.target.value)}
          >
            {runs.map((item) => (
              <option key={item.id} value={item.id}>
                {item.started_at
                  ? new Date(item.started_at).toLocaleString()
                  : item.id.slice(0, 8)}{" "}
                — {item.status}
              </option>
            ))}
          </select>
        </label>
      )}

      {run ? (
        <div className="card">
          <div className="card-row">
            <strong>Run status</strong>
            <StatusBadge status={run.status} />
          </div>
          <p className="muted small">
            Evidence: {run.evidence_count} · Timeline: {run.timeline_count}
            {run.reasoning_status ? ` · Reasoning: ${run.reasoning_status}` : ""}
          </p>
          {run.executive_summary && <p>{run.executive_summary}</p>}
        </div>
      ) : (
        <p className="muted">No investigation runs yet. Start one to collect evidence.</p>
      )}
    </div>
  );
}
