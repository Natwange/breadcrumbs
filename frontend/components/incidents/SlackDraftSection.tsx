"use client";

import { StatusBadge } from "@/components/ui/Primitives";
import type { InvestigationRunDetail } from "@/lib/api";

export default function SlackDraftSection({
  run,
}: {
  run: InvestigationRunDetail | null;
}) {
  const draft = run?.slack_draft;
  if (!draft) {
    return <p className="muted">No Slack draft generated for this run.</p>;
  }

  return (
    <div className="card">
      <div className="card-row">
        <strong>{draft.channel ? `#${draft.channel}` : "Slack draft"}</strong>
        <StatusBadge status={draft.status} />
      </div>
      {draft.content ? (
        <pre className="pre-wrap">{draft.content}</pre>
      ) : (
        <p className="muted">Draft is empty.</p>
      )}
    </div>
  );
}
