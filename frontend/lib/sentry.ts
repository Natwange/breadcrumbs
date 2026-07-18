import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
const environment = process.env.NEXT_PUBLIC_ENVIRONMENT ?? "development";

let clientInitialized = false;

/**
 * Initialize Sentry in the browser. No-op when the DSN is not configured, so
 * local development and CI runs without Sentry keep working. PII is not sent.
 */
export function initSentryClient(): void {
  if (clientInitialized || !dsn) return;
  clientInitialized = true;
  Sentry.init({
    dsn,
    environment,
    tracesSampleRate: 0,
    sendDefaultPii: false,
  });
}

export const isSentryConfigured = Boolean(dsn);
