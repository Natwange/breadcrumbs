"use client";

import { StatusBadge } from "@/components/ui/Primitives";
import type { AlertItem } from "@/lib/api";

export default function AlertCards({ alerts }: { alerts: AlertItem[] }) {
  if (alerts.length === 0) {
    return (
      <p className="muted">No alerts linked to this incident yet.</p>
    );
  }

  return (
    <div className="card-grid">
      {alerts.map((alert) => (
        <article key={alert.id} className="card">
          <div className="card-row">
            <strong>{alert.title}</strong>
            <StatusBadge status={alert.status} />
          </div>
          <p className="muted small">
            {alert.source}
            {alert.severity ? ` · ${alert.severity}` : ""}
            {alert.fired_at ? ` · ${new Date(alert.fired_at).toLocaleString()}` : ""}
          </p>
          {alert.description && <p>{alert.description}</p>}
        </article>
      ))}
    </div>
  );
}
