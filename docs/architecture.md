# Architecture

breadcrumbs is a monorepo with a FastAPI backend and a Next.js frontend. All
organization-owned data is scoped by `organization_id`; the backend never trusts
client-supplied org identifiers.

## High-level diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Browser (Next.js)                                                      │
│  Supabase Auth (localStorage session) → JWT on every API call           │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTPS + Bearer JWT
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  FastAPI backend (Render / Docker)                                      │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  │
│  │ Auth deps   │  │ Rate limits  │  │ Request-ID + structured logs │  │
│  │ (JWT/JWKS)  │  │ (per-org)    │  │ + Sentry (optional)          │  │
│  └─────────────┘  └──────────────┘  └──────────────────────────────┘  │
│                                                                         │
│  Routes → Services → Models (SQLAlchemy)                                │
│                                                                         │
│  Investigation engine                                                   │
│    Planner → Collectors (fake or real) → Normalize → Relevance judge    │
│    → Reasoning engine (Claude/fallback) → Timeline → Slack draft        │
│                                                                         │
│  Knowledge builder → Vector search → Postmortem generator               │
│  Integrations (GitHub, Render) — env tokens only                        │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
  Supabase Postgres      Anthropic API (opt)     GitHub / Render APIs (opt)
  Supabase Auth          Langfuse (opt)          Sentry (opt)
```

## Core workflows

### Alert → incident → investigation

1. **Alert ingest** (`POST /api/alerts/ingest`) correlates or creates an incident.
2. **Investigation run** (`POST /api/incidents/{id}/investigation-runs`):
   - Builds context from the knowledge graph (affected service, dependencies).
   - Plans collector steps (metrics, errors, GitHub, Render, similarity search).
   - Runs collectors (fake when no token; real when `BREADCRUMBS_GITHUB_TOKEN` /
     `BREADCRUMBS_RENDER_API_KEY` are set).
   - Normalizes and deduplicates evidence; judges relevance (Claude batch).
   - Runs reasoning engine (readiness gate → hypotheses, impact, actions, Slack).
3. **Frontend** polls `GET /api/investigation-runs/{id}` until `completed` or
   `failed`, then stops.

### Knowledge & memory

- Artifacts ingested → optional Claude extraction → graph proposals → approval.
- Embeddings (local-hash by default) power similarity search during investigations.
- Approved postmortems are embedded for future incident matching.

## Deployment topology (MVP)

| Component | Target |
| --------- | ------ |
| Frontend | Vercel or Render (static/Node) |
| Backend | Render (Docker, `backend/Dockerfile`) |
| Database | Supabase Postgres |
| Auth | Supabase Auth |

**Integration model (MVP):** one organization per deployment. GitHub and Render
tokens live in **backend environment variables** only — not per-tenant in the DB.
See [known-limitations.md](known-limitations.md).

## Observability

| Signal | Mechanism |
| ------ | --------- |
| HTTP logs | Structured JSON (`BREADCRUMBS_LOG_JSON=true`) with `request_id` |
| Errors | Sentry (`BREADCRUMBS_SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_DSN`) |
| LLM calls | Langfuse (`BREADCRUMBS_LANGFUSE_*`) + run tracking JSON on rows |
| Audit | `AuditLog` for sensitive actions (e.g. `postmortem_generated`) |

## Data model (summary)

26 SQLAlchemy models grouped by: users, organizations, knowledge, incidents,
investigations, embeddings, integrations, audit. UUID PKs; org-scoped rows carry
indexed `organization_id`. No secrets in `IntegrationConnection.config`.
