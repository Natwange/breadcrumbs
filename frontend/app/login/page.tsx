"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import AuthForm from "@/components/AuthForm";
import { useAuth } from "@/components/AuthProvider";
import { LoadingCard } from "@/components/ui/Primitives";

export default function LoginPage() {
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

  if (session) {
    return (
      <main className="public-page">
        <LoadingCard message="Redirecting…" />
      </main>
    );
  }

  return (
    <main className="public-page">
      <section className="hero">
        <p className="eyebrow">breadcrumbs</p>
        <h1 className="title">Sign in</h1>
        <p className="subtitle">
          Use your Supabase account to access the workspace.
        </p>
      </section>
      <AuthForm />
      <p className="muted">
        <Link href="/welcome" className="text-link">
          Back to welcome
        </Link>
      </p>
    </main>
  );
}
