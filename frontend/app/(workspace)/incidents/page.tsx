"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  EmptyState,
  ErrorBanner,
  LoadingCard,
  PageHeader,
  StatusBadge,
} from "@/components/ui/Primitives";
import { createIncident, listIncidents, type Incident } from "@/lib/api";

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [creating, setCreating] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setIncidents(await listIncidents());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load incidents");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await createIncident({ title: title.trim(), severity: "medium" });
      setTitle("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create incident");
    } finally {
      setCreating(false);
    }
  }

  if (loading) return <LoadingCard />;

  return (
    <div className="workspace-content">
      <PageHeader
        title="Incidents"
        description="Open incidents and investigation workspaces."
      />
      {error && <ErrorBanner message={error} />}

      <form className="card stack" onSubmit={handleCreate}>
        <label className="field">
          <span className="field-label">New incident title</span>
          <input
            className="input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Checkout API elevated error rate"
            required
          />
        </label>
        <button type="submit" className="btn" disabled={creating}>
          {creating ? "Creating…" : "Create incident"}
        </button>
      </form>

      <section className="section">
        <h2 className="section-title">All incidents</h2>
        {incidents.length === 0 ? (
          <EmptyState
            title="No incidents"
            description="Create an incident or ingest an alert via the API."
          />
        ) : (
          <ul className="data-list">
            {incidents.map((incident) => (
              <li key={incident.id} className="card">
                <div className="card-row">
                  <Link href={`/incidents/${incident.id}`} className="text-link">
                    <strong>{incident.title}</strong>
                  </Link>
                  <StatusBadge status={incident.status} />
                </div>
                <p className="muted small">
                  {new Date(incident.created_at).toLocaleString()}
                  {incident.severity ? ` · ${incident.severity}` : ""}
                </p>
                {incident.description && <p>{incident.description}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
