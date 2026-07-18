"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/AuthProvider";
import { LoadingCard } from "@/components/ui/Primitives";

export default function WelcomePage() {
  const { session, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && session) {
      router.replace("/dashboard");
    }
  }, [loading, session, router]);

  if (loading) {
    return (
      <main className="public-page">
        <LoadingCard />
      </main>
    );
  }

  return (
    <main className="public-page">
      <section className="hero">
        <p className="eyebrow">breadcrumbs</p>
        <h1 className="title">AI Incident Investigation Workspace</h1>
        <p className="subtitle">
          Follow evidence across your engineering systems to find root cause faster.
        </p>
      </section>
      <div className="card">
        <p className="muted">
          Sign in to access investigations, knowledge graph, integrations, and settings.
        </p>
        <div className="card-row">
          <Link href="/login" className="btn">
            Sign in
          </Link>
          <Link href="/login" className="btn btn-ghost">
            Create account
          </Link>
        </div>
      </div>
    </main>
  );
}
