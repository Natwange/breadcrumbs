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
import { listKnowledgeProposals, type KnowledgeProposal } from "@/lib/api";

export default function KnowledgeProposalsPage() {
  const [proposals, setProposals] = useState<KnowledgeProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const data = await listKnowledgeProposals();
        if (!active) return;
        setProposals(data);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load proposals");
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

  return (
    <div className="workspace-content">
      <PageHeader
        title="Knowledge proposals"
        description="Pending and reviewed graph changes from artifact ingestion."
        actions={
          <Link href="/knowledge" className="btn btn-ghost">
            Back to graph
          </Link>
        }
      />

      {proposals.length === 0 ? (
        <EmptyState
          title="No proposals"
          description="Upload artifacts via the API to generate knowledge graph proposals."
        />
      ) : (
        <ul className="data-list">
          {proposals.map((proposal) => (
            <li key={proposal.id} className="card">
              <div className="card-row">
                <strong>{proposal.proposal_type}</strong>
                <StatusBadge status={proposal.status} />
              </div>
              <p className="muted small">
                {new Date(proposal.created_at).toLocaleString()}
                {proposal.confidence != null
                  ? ` · confidence ${(proposal.confidence * 100).toFixed(0)}%`
                  : ""}
              </p>
              {proposal.payload && (
                <pre className="code-block">
                  {JSON.stringify(proposal.payload, null, 2)}
                </pre>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
