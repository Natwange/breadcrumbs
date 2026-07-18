"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/components/AuthProvider";

/**
 * Client-side route guard. Redirects unauthenticated users to the home page.
 *
 * NOTE: Supabase sessions are stored in localStorage on this frontend, so a
 * server-side `middleware.ts` cannot see them. Protection is therefore
 * enforced in the browser. Migrating to cookie-based sessions (@supabase/ssr)
 * would enable true server-side guards — see docs/known-limitations.md.
 */
export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !session) {
      router.replace("/login");
    }
  }, [loading, session, router]);

  if (loading) {
    return (
      <main className="page">
        <div className="health-card">
          <p className="health-detail">Loading…</p>
        </div>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="page">
        <div className="health-card">
          <p className="health-detail">Redirecting to sign in…</p>
        </div>
      </main>
    );
  }

  return <>{children}</>;
}
