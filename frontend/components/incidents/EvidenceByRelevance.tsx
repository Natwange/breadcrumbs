"use client";

import type { EvidenceItem } from "@/lib/api";

const GROUP_ORDER = ["high", "medium", "low", "unknown"] as const;

function groupKey(item: EvidenceItem): string {
  const label = item.relevance_label?.toLowerCase();
  if (label === "high" || label === "medium" || label === "low") return label;
  return "unknown";
}

function groupTitle(key: string): string {
  switch (key) {
    case "high":
      return "High relevance";
    case "medium":
      return "Medium relevance";
    case "low":
      return "Low relevance";
    default:
      return "Unjudged";
  }
}

export default function EvidenceByRelevance({ evidence }: { evidence: EvidenceItem[] }) {
  if (evidence.length === 0) {
    return <p className="muted">No evidence collected for this run.</p>;
  }

  const groups = new Map<string, EvidenceItem[]>();
  for (const item of evidence) {
    const key = groupKey(item);
    const list = groups.get(key) ?? [];
    list.push(item);
    groups.set(key, list);
  }

  return (
    <div className="stack">
      {GROUP_ORDER.filter((key) => groups.has(key)).map((key) => (
        <div key={key} className="stack">
          <h3 className="subsection-title">{groupTitle(key)}</h3>
          <ul className="data-list">
            {(groups.get(key) ?? []).map((item) => (
              <li key={item.id} className="card">
                <div className="card-row">
                  <strong>{item.title ?? item.evidence_type}</strong>
                  <span className="muted small">{item.source}</span>
                </div>
                {item.relevance_reason && (
                  <p className="muted small">{item.relevance_reason}</p>
                )}
                {item.content && <p className="pre-wrap">{item.content}</p>}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
