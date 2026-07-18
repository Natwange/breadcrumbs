"use client";

import { StatusBadge } from "@/components/ui/Primitives";
import type { SuggestedActionItem } from "@/lib/api";

export default function SuggestedActionsSection({
  actions,
}: {
  actions: SuggestedActionItem[];
}) {
  if (actions.length === 0) {
    return <p className="muted">No suggested actions for this run.</p>;
  }

  return (
    <ul className="data-list">
      {actions.map((item) => (
        <li key={item.id} className="card">
          <div className="card-row">
            <strong>{item.title}</strong>
            <StatusBadge status={item.status} />
          </div>
          {item.action_type && (
            <p className="muted small">{item.action_type}</p>
          )}
          {item.description && <p>{item.description}</p>}
          {item.requires_human_approval && (
            <p className="muted small">Requires human approval</p>
          )}
        </li>
      ))}
    </ul>
  );
}
