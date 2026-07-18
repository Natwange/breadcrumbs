"use client";

import { useEffect, useState } from "react";

import {
  EmptyState,
  ErrorBanner,
  LoadingCard,
  PageHeader,
  StatusBadge,
} from "@/components/ui/Primitives";
import {
  getIntegrations,
  testGithubIntegration,
  testRenderIntegration,
  type IntegrationsStatus,
} from "@/lib/api";

export default function IntegrationsPage() {
  const [data, setData] = useState<IntegrationsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const result = await getIntegrations();
        if (!active) return;
        setData(result);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load integrations");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  async function runTest(provider: "github" | "render") {
    setTesting(provider);
    setTestResult(null);
    setError(null);
    try {
      const result =
        provider === "github"
          ? await testGithubIntegration()
          : await testRenderIntegration();
      setTestResult(`${provider}: ${result.ok ? "OK" : "Failed"} — ${result.detail}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setTesting(null);
    }
  }

  if (loading) return <LoadingCard />;
  if (error && !data) return <ErrorBanner message={error} />;
  if (!data) return <ErrorBanner message="No integration data" />;

  return (
    <div className="workspace-content">
      <PageHeader
        title="Integrations"
        description="Provider status from backend environment configuration."
      />
      {error && <ErrorBanner message={error} />}
      {testResult && <div className="card"><p>{testResult}</p></div>}

      <section className="section">
        <h2 className="section-title">Providers</h2>
        <ul className="data-list">
          {data.providers.map((provider) => (
            <li key={provider.provider} className="card">
              <div className="card-row">
                <strong>{provider.provider}</strong>
                <StatusBadge status={provider.configured ? "configured" : "not_configured"} />
              </div>
              {(provider.provider === "github" || provider.provider === "render") && (
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={!provider.configured || testing === provider.provider}
                  onClick={() =>
                    runTest(provider.provider as "github" | "render")
                  }
                >
                  {testing === provider.provider ? "Testing…" : "Test connection"}
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section className="section">
        <h2 className="section-title">Saved connections</h2>
        {data.connections.length === 0 ? (
          <EmptyState
            title="No saved connections"
            description="MVP uses backend env tokens; per-org vault storage is not enabled yet."
          />
        ) : (
          <ul className="data-list">
            {data.connections.map((conn) => (
              <li key={conn.id} className="card">
                <div className="card-row">
                  <strong>{conn.name ?? conn.provider}</strong>
                  <StatusBadge status={conn.status} />
                </div>
                <p className="muted small">{conn.provider}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
