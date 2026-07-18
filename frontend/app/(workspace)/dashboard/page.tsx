"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  ErrorBanner,
  LoadingCard,
  PageHeader,
  StatusBadge,
} from "@/components/ui/Primitives";
import { fetchCurrentUser, listIncidents, type CurrentUser, type Incident } from "@/lib/api";

export default function DashboardPage() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [me, list] = await Promise.all([
          fetchCurrentUser(),
          listIncidents(),
        ]);
        if (!active) return;
        setUser(me);
        setIncidents(list.slice(0, 5));
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load dashboard");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  if (loading) return <LoadingCard />;
  if (error) return <ErrorBanner message={error} />;

  const openCount = incidents.filter((i) => i.status === "open").length;

  return (
    <div className="workspace-content">
      <PageHeader
        title="Dashboard"
        description={
          user
            ? `${user.organization.name} · ${user.email}`
            : undefined
        }
      />

      <div className="card-grid">
        <div className="card">
          <p className="muted small">Open incidents (recent sample)</p>
          <p className="stat">{openCount}</p>
        </div>
        <div className="card">
          <p className="muted small">Recent incidents loaded</p>
          <p className="stat">{incidents.length}</p>
        </div>
      </div>

      <section className="section">
        <div className="section-header">
          <h2 className="section-title">Recent incidents</h2>
          <Link href="/incidents" className="text-link">
            View all
          </Link>
        </div>
        {incidents.length === 0 ? (
          <p className="muted">No incidents yet. Create one from the incidents page.</p>
        ) : (
          <ul className="data-list">
            {incidents.map((incident) => (
              <li key={incident.id} className="card">
                <div className="card-row">
                  <Link href={`/incidents/${incident.id}`} className="text-link">
                    {incident.title}
                  </Link>
                  <StatusBadge status={incident.status} />
                </div>
                <p className="muted small">
                  {new Date(incident.created_at).toLocaleString()}
                  {incident.severity ? ` · ${incident.severity}` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
