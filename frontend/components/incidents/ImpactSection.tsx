"use client";

import { StatusBadge } from "@/components/ui/Primitives";
import type { ImpactItem } from "@/lib/api";

export default function ImpactSection({ impacts }: { impacts: ImpactItem[] }) {
  if (impacts.length === 0) {
    return <p className="muted">No impact assessment recorded.</p>;
  }

  return (
    <ul className="data-list">
      {impacts.map((item) => (
        <li key={item.id} className="card">
          <div className="card-row">
            <strong>{item.impact_type}</strong>
            {item.severity && <StatusBadge status={item.severity} />}
          </div>
          {item.description && <p>{item.description}</p>}
          {item.affected_services && (
            <pre className="code-block">
              {JSON.stringify(item.affected_services, null, 2)}
            </pre>
          )}
        </li>
      ))}
    </ul>
  );
}
