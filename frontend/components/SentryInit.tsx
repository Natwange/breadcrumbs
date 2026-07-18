"use client";

import { useEffect } from "react";

import { initSentryClient } from "@/lib/sentry";

/**
 * Initializes browser-side Sentry once on mount. Renders nothing.
 * Safe to include unconditionally — it no-ops without a configured DSN.
 */
export default function SentryInit() {
  useEffect(() => {
    initSentryClient();
  }, []);
  return null;
}
