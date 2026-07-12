"use client";

import AccountPanel from "@/components/AccountPanel";
import AuthForm from "@/components/AuthForm";
import HealthCheck from "@/components/HealthCheck";
import { useAuth } from "@/components/AuthProvider";

export default function Home() {
  const { session, loading } = useAuth();

  return (
    <main className="page">
      <section className="hero">
        <p className="eyebrow">breadcrumbs</p>
        <h1 className="title">AI Incident Investigation Workspace</h1>
        <p className="subtitle">
          Follow a trail of evidence across your engineering systems to find the
          root cause of production outages.
        </p>
      </section>

      {loading ? (
        <div className="health-card">
          <p className="health-detail">Loading…</p>
        </div>
      ) : session ? (
        <AccountPanel />
      ) : (
        <AuthForm />
      )}

      <HealthCheck />
    </main>
  );
}
