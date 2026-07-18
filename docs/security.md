# Security decisions

This document records intentional security choices for the breadcrumbs MVP and
staging deployment.

## Authentication & tenancy

| Decision | Rationale |
| -------- | --------- |
| JWT verified server-side only | Supabase issues tokens; backend validates via HS256 secret or JWKS. |
| `organization_id` never from request body | Prevents cross-tenant ID injection; org comes from `X-Organization-Id` + membership check. |
| Role gates on routes | `CAN_READ`, `CAN_WRITE_CONTENT`, `CAN_MANAGE_ORG` enforced via `require_org_role`. |

## Secrets & credentials

| Decision | Rationale |
| -------- | --------- |
| **No secrets in the database** | `IntegrationConnection.config` is metadata only (repo names, service IDs). |
| **GitHub/Render tokens in env only** | `BREADCRUMBS_GITHUB_TOKEN`, `BREADCRUMBS_RENDER_API_KEY` — never serialized to API responses or frontend. |
| **Single-org integration model (MVP)** | One deployment = one set of integration tokens. Multi-tenant per-org tokens require encrypted vault storage (future). |
| **Secret redaction before persistence** | `redact_secrets()` on artifact content, evidence text, postmortem prompts/output. |
| **Sentry: no PII, no request bodies** | `send_default_pii=False`, `max_request_body_size="never"` on backend. |

## AI safety

| Decision | Rationale |
| -------- | --------- |
| Untrusted-data guardrails in prompts | Alert/evidence blocks wrapped in `<<<UNTRUSTED_DATA>>>`; model instructed not to follow embedded instructions. |
| Strict JSON schema validation | Claude outputs parsed and rejected on invalid shape; fallback templates used instead. |
| Readiness gate before full reasoning | Skips expensive Claude call when evidence quality is insufficient. |
| No invented root cause (postmortem) | Prompt + fallback require evidence-backed or explicitly marked assumptions. |

## Network & abuse

| Decision | Rationale |
| -------- | --------- |
| CORS restricted to configured origins | `BREADCRUMBS_CORS_ORIGINS` comma-separated list; explicit methods/headers. |
| Rate limits on expensive endpoints | Per-org sliding window on investigations, AI/postmortem, knowledge build, artifact upload, embedding backfill. |
| Collector failure isolation | One failed GitHub/Render collector does not fail the whole investigation run. |

## Frontend

| Decision | Rationale |
| -------- | --------- |
| Supabase anon key is public by design | Standard Supabase pattern; RLS and backend auth enforce real authorization. |
| Client-side route guard for `/investigations` | Session in localStorage — server middleware cannot see it until cookie-based auth (@supabase/ssr). Documented limitation. |

## Future hardening

- Per-organization integration credentials via **Supabase Vault** or external secret manager.
- Redis-backed rate limiting for multi-instance backends.
- Cookie-based Supabase sessions for server-side route protection.
- Content Security Policy headers on the frontend.
