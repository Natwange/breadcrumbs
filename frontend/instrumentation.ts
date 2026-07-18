import * as Sentry from "@sentry/nextjs";

/**
 * Server/edge Sentry initialization. Next.js calls `register()` once at
 * startup. No-op when SENTRY_DSN is not set, so dev/CI runs unaffected.
 */
export async function register() {
  const dsn = process.env.SENTRY_DSN ?? process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;

  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_ENVIRONMENT ?? "production",
    tracesSampleRate: 0,
    sendDefaultPii: false,
  });
}
