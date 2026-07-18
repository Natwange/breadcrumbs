"use client";

import { useEffect } from "react";

import { isSentryConfigured } from "@/lib/sentry";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Report to Sentry when configured; always log for local debugging.
    if (isSentryConfigured) {
      void import("@sentry/nextjs").then((Sentry) => Sentry.captureException(error));
    }
    console.error(error);
  }, [error]);

  return (
    <main className="page">
      <section className="hero">
        <h1 className="title">Something went wrong</h1>
        <p className="subtitle">
          An unexpected error occurred. You can try again.
        </p>
      </section>
      <div className="health-card">
        <p className="auth-error">{error.message || "Unknown error"}</p>
        <button type="button" className="health-button" onClick={() => reset()}>
          Try again
        </button>
      </div>
    </main>
  );
}
