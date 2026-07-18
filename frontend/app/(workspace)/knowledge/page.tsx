"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  EmptyState,
  ErrorBanner,
  LoadingCard,
  PageHeader,
} from "@/components/ui/Primitives";
import { getKnowledgeGraph, type KnowledgeGraph } from "@/lib/api";

export default function KnowledgePage() {
  const [graph, setGraph] = useState<KnowledgeGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const data = await getKnowledgeGraph();
        if (!active) return;
        setGraph(data);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load knowledge graph");
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
  if (!graph) return <ErrorBanner message="No knowledge graph data" />;

  const isEmpty =
    graph.services.length === 0 &&
    graph.dependencies.length === 0 &&
    graph.runbooks.length === 0;

  return (
    <div className="workspace-content">
      <PageHeader
        title="Knowledge"
        description="Service graph and runbooks from approved proposals."
        actions={
          <Link href="/knowledge/proposals" className="btn btn-ghost">
            View proposals
          </Link>
        }
      />

      {isEmpty ? (
        <EmptyState
          title="Knowledge graph is empty"
          description="Ingest artifacts and approve proposals to populate services and runbooks."
        />
      ) : (
        <>
          <section className="section">
            <h2 className="section-title">Services ({graph.services.length})</h2>
            <ul className="data-list">
              {graph.services.map((service) => (
                <li key={service.id} className="card">
                  <strong>{service.name}</strong>
                  <p className="muted small">
                    {service.service_type ?? "unknown type"}
                    {service.description ? ` · ${service.description}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          </section>

          <section className="section">
            <h2 className="section-title">Dependencies ({graph.dependencies.length})</h2>
            {graph.dependencies.length === 0 ? (
              <p className="muted">No dependencies recorded.</p>
            ) : (
              <ul className="data-list">
                {graph.dependencies.map((dep) => (
                  <li key={dep.id} className="card">
                    <span>
                      {dep.upstream_name} → {dep.downstream_name}
                    </span>
                    {dep.dependency_type && (
                      <span className="muted small"> · {dep.dependency_type}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="section">
            <h2 className="section-title">Runbooks ({graph.runbooks.length})</h2>
            {graph.runbooks.length === 0 ? (
              <p className="muted">No runbooks yet.</p>
            ) : (
              <ul className="data-list">
                {graph.runbooks.map((runbook) => (
                  <li key={runbook.id} className="card">
                    <strong>{runbook.title}</strong>
                    {runbook.content && <p className="pre-wrap">{runbook.content}</p>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
