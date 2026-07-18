"use client";

import { useState } from "react";

import { StatusBadge } from "@/components/ui/Primitives";
import { generatePostmortem, type PostmortemSummary } from "@/lib/api";

interface Props {
  incidentId: string;
  postmortem: PostmortemSummary | null;
  onGenerated: (postmortem: PostmortemSummary) => void;
}

export default function PostmortemSection({
  incidentId,
  postmortem,
  onGenerated,
}: Props) {
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const result = await generatePostmortem(incidentId);
      onGenerated(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate postmortem");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="stack">
      <button
        type="button"
        className="btn"
        onClick={handleGenerate}
        disabled={generating}
      >
        {generating ? "Generating…" : postmortem ? "Regenerate postmortem" : "Generate postmortem"}
      </button>
      {error && <p className="error-text">{error}</p>}
      {postmortem ? (
        <div className="card">
          <div className="card-row">
            <strong>{postmortem.title}</strong>
            <StatusBadge status={postmortem.status} />
          </div>
          <p className="muted small">Source: {postmortem.postmortem_source}</p>
          {postmortem.sections ? (
            <pre className="code-block">
              {JSON.stringify(postmortem.sections, null, 2)}
            </pre>
          ) : (
            <p className="muted">No structured sections available.</p>
          )}
        </div>
      ) : (
        <p className="muted">No postmortem yet for this incident.</p>
      )}
    </div>
  );
}
