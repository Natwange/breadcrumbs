"use client";

import { StatusBadge } from "@/components/ui/Primitives";
import type { HypothesisItem } from "@/lib/api";

export default function HypothesesSection({
  hypotheses,
}: {
  hypotheses: HypothesisItem[];
}) {
  if (hypotheses.length === 0) {
    return <p className="muted">No hypotheses generated yet.</p>;
  }

  return (
    <ul className="data-list">
      {hypotheses.map((item) => (
        <li key={item.id} className="card">
          <div className="card-row">
            <strong>{item.title}</strong>
            <StatusBadge status={item.status} />
          </div>
          {item.confidence != null && (
            <p className="muted small">Confidence: {(item.confidence * 100).toFixed(0)}%</p>
          )}
          {item.description && <p>{item.description}</p>}
        </li>
      ))}
    </ul>
  );
}
