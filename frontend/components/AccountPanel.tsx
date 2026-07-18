"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { fetchCurrentUser, type CurrentUser } from "@/lib/api";

export default function AccountPanel() {
  const { session, signOut } = useAuth();
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    fetchCurrentUser()
      .then((data) => {
        if (active) setMe(data);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : "Failed to load account");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [session?.access_token]);

  return (
    <div className="health-card">
      <div className="health-header">
        <span className="health-dot" style={{ backgroundColor: "#22c55e" }} />
        <span className="health-title">Signed in</span>
      </div>

      <p className="health-detail">{session?.user.email}</p>

      {loading && <p className="health-detail">Loading your workspace…</p>}
      {error && <p className="auth-error">Backend: {error}</p>}

      {me && (
        <div className="account-org">
          <p className="health-detail">
            Organization: <strong>{me.organization.name}</strong>
          </p>
          <p className="health-endpoint">
            <code>{me.organization.slug}</code> · onboarding:{" "}
            {me.organization.onboarding_status}
          </p>
        </div>
      )}

      <Link href="/investigations" className="health-button">
        Go to investigations
      </Link>

      <button type="button" className="health-button" onClick={() => signOut()}>
        Log out
      </button>
    </div>
  );
}
