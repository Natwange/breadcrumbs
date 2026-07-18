# breadcrumbs — Backend

FastAPI service for the breadcrumbs **AI Incident Investigation Workspace**.

## Requirements

- Python 3.11+

## Local setup

From the `backend/` directory:

```bash
# 1. Create and activate a virtual environment
python -m venv .venv

# macOS / Linux
source .venv/bin/activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment (required for the database)
cp .env.example .env   # then set BREADCRUMBS_DATABASE_URL (see below)

# 4. Apply database migrations
alembic upgrade head

# 5. Run the development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is then available at http://localhost:8000.

- Health check: http://localhost:8000/health → `{ "status": "ok" }`
- Interactive docs: http://localhost:8000/docs

## Database (Supabase Postgres)

This project uses **Supabase Postgres** with **SQLAlchemy** and **Alembic**.

### Required manual input

You must provide **one secret**: your Supabase database connection string.

1. In the Supabase dashboard, go to **Project Settings → Database → Connection
   string → URI**.
2. Copy the URI and change the scheme from `postgresql://` to
   `postgresql+psycopg2://`, filling in your database password.
3. Put it in **`backend/.env`** as `BREADCRUMBS_DATABASE_URL`
   (see [`.env.example`](.env.example) for the exact format).

> This is the only credential needed for Phase 2. No API keys or other secrets
> are stored anywhere in the codebase. Never commit `.env`.

### Migrations

Run from the `backend/` directory (with `.env` configured):

```bash
alembic upgrade head              # apply all migrations
alembic revision --autogenerate -m "message"   # create a new migration
alembic downgrade -1              # roll back the latest migration
```

### Testing

Model and auth tests run against in-memory SQLite (no database required):

```bash
pip install -r requirements-dev.txt
pytest
```

## Authentication (Supabase Auth)

Authenticated routes require a valid **Supabase JWT** in the
`Authorization: Bearer <access_token>` header. The backend **cryptographically
verifies** each token — signature, expiration (`exp`), issuer (`iss`), and
audience (`aud`) — it never merely decodes it.

### Required manual input

Add to **`backend/.env`** (see [`.env.example`](.env.example)):

1. `BREADCRUMBS_SUPABASE_URL` — your project URL
   (**Project Settings → API → Project URL**).
2. **One** JWT verification strategy:
   - **HS256 (legacy):** set `BREADCRUMBS_SUPABASE_JWT_SECRET` to the value from
     **Project Settings → API → JWT Settings → JWT Secret**, **or**
   - **Asymmetric (RS256/ES256):** leave the secret blank; the backend fetches
     public keys from the project JWKS endpoint automatically.

No API keys or user secrets are stored in the database.

### How auth works

- `get_current_user()` verifies the token and, on a user's first request,
  provisions a `UserProfile` (keyed by the Supabase `sub`), a default
  `Organization`, and an `OrganizationMember` with role **owner**.
- `get_current_organization()` resolves the active organization from the user's
  verified memberships. The client's `organization_id` is **never** trusted; an
  optional `X-Organization-Id` header is validated against membership.

### Routes

| Route                    | Access        |
| ------------------------ | ------------- |
| `GET /health`            | Public        |
| `GET /auth/me`           | Authenticated |
| `/incidents/*`           | Authenticated |
| `/knowledge/*`           | Authenticated |
| `/investigation-runs/*`  | Authenticated |
| `/integrations/*`        | Authenticated |

All authenticated queries are scoped by `organization_id`.

## Organization tenancy & alert correlation (Phase 4)

### Roles

| Role   | Permissions |
| ------ | ----------- |
| owner  | Full org control, soft-delete, all admin capabilities |
| admin  | Manage integrations, invite members, approve proposals |
| member | Create incidents, run investigations, upload artifacts, ingest alerts |
| viewer | Read-only |

Use `require_org_role(...)` on routes to enforce the above. The optional
`X-Organization-Id` header selects among a user's organizations but is always
validated against membership.

### New routes

| Route | Access |
| ----- | ------ |
| `GET/PATCH /organizations/settings` | read / admin |
| `GET /organizations/members` | all members |
| `PATCH /organizations/members/{id}/role` | admin+ |
| `DELETE /organizations/members/{id}` | admin+ |
| `POST/GET /organizations/invitations` | admin+ |
| `DELETE /organizations` | owner (soft-delete) |
| `POST /alerts` | member+ (correlates into incidents) |
| `POST /knowledge/proposals/{id}/approve` | admin+ |

### Alert correlation

`POST /alerts` ingests a monitoring signal and runs
`AlertCorrelationService`, which attaches the alert to an **open** incident
when correlation confidence is high enough, or creates a new incident when
uncertain. Resolved incidents are never silently merged.

Audit events: `organization_created`, `member_invited`, `member_role_changed`,
`member_removed`, `alert_correlated`.

## Knowledge builder

Builds a living organizational knowledge graph from untrusted artifacts.

### Flow

1. Ingest artifact (`POST /api/knowledge/artifacts`) — secrets redacted before storage.
2. Extract proposed services/dependencies/runbooks (rule-based by default; Claude optional).
3. Create `KnowledgeGraphProposal` with drift analysis.
4. Admin approves/rejects (`POST /api/knowledge/proposals/{id}/approve|reject`).
5. Approved proposals update `ServiceNode`, `ServiceDependency`, and `Runbook`.
6. Drift is detected but approved knowledge is never auto-deleted.

### API routes

| Route | Access |
| ----- | ------ |
| `POST /api/knowledge/artifacts` | member+ |
| `POST /api/knowledge/build` | member+ |
| `GET /api/knowledge/graph` | all members |
| `GET /api/knowledge/proposals` | all members |
| `POST /api/knowledge/proposals/{id}/approve` | admin+ |
| `POST /api/knowledge/proposals/{id}/reject` | admin+ |
| `POST /api/knowledge/updates` | admin+ |
| `GET /api/knowledge/runbooks` | all members |

### Optional: Claude

Set `BREADCRUMBS_ANTHROPIC_API_KEY` in `backend/.env` to enable Claude-based
architecture extraction. Claude returns structured JSON only and never mutates
the graph directly. Without it, the rule-based extractor handles README,
package.json, Prisma schema, OpenAPI, Render metadata, runbooks, and architecture notes.

## Investigation engine (Phase 6)

Backend-controlled investigations combine incident alerts, the approved
knowledge graph, and fake collectors (no external APIs or Claude).

### Workflow

1. Start `InvestigationRun`
2. Load incident and alerts
3. Build `InvestigationContext` from the knowledge graph
4. Create `InvestigationPlan` (collectors chosen from dependencies)
5. Run fake collectors (`github`, `render`, `metrics`, `errors`, `cloud_status`)
6. Normalize and validate evidence
7. Deduplicate evidence
8. Build `TimelineEvent` rows
9. Assign rule-based relevance labels
10. Generate `rule_based_foundation` hypothesis
11. Generate `SlackDraft`
12. Mark run `completed` or `failed`

### Services (`app/services/investigation_engine/`)

| Module | Role |
| ------ | ---- |
| `investigation_runner.py` | Orchestrates the full workflow |
| `knowledge_context_builder.py` | Builds context from graph + incident |
| `investigation_planner.py` | Plans collector steps from dependencies |
| `collector_registry.py` | Fake collectors + registry |
| `evidence_normalizer.py` | Normalizes raw collector output |
| `evidence_quality_validator.py` | Rejects low-quality evidence |
| `timeline_builder.py` | Chronological timeline from evidence |
| `relevance_judge.py` | Non-AI relevance scores/labels |
| `hypothesis_generator.py` | Rule-based foundation hypothesis |
| `slack_draft_generator.py` | Draft Slack incident update |

### APIs

| Endpoint | Role | Min role |
| -------- | ---- | -------- |
| `POST /api/incidents/{incident_id}/investigation-runs` | Start and run investigation | member+ |
| `GET /api/investigation-runs/{run_id}` | Run detail (plan, counts, hypothesis, draft) | all members |
| `POST /api/alerts/ingest` | Ingest demo alerts (`datadog`, `render`, `new_relic`, `manual_demo`) | member+ |

Legacy routes under `/investigation-runs` and `/alerts` remain for Phase 3/4
compatibility.

The investigation workflow now includes a `finding_similar_incidents` step that
pulls organizational memory (Phase 7) into the hypothesis and Slack draft.

## Vector search & organizational memory (Phase 7)

Durable knowledge is embedded and retrieved via similarity search to surface
past incidents, runbooks, postmortems, and knowledge artifacts during an
investigation.

### What is embedded

Embedded: `Runbook`, `Postmortem`, `KnowledgeArtifact`, and **resolved**
`Incident`. Never embedded: live logs, live metrics, live evidence, timeline
events. Text is always redacted before it is embedded or stored.

### `EmbeddingRecord`

`organization_id`, `source_type` (object type), `source_id` (object id),
`embedding` (JSON float array; pgvector-backed in production), `text_snapshot`
(redacted), `embedding_model`, `embedding_version`, `dimensions`,
`content_hash`, `metadata`.

### Services (`app/services/vector_search/`)

| Module | Role |
| ------ | ---- |
| `embedding_service.py` | Deterministic local hashing embedder (offline, no API) |
| `embedding_validator.py` | Redacts + rejects unredacted secrets before embedding |
| `embedding_queue.py` | Idempotent per-object embedding + org backfill |
| `vector_search.py` | Cosine similarity search, strictly org-scoped |
| `similarity_service.py` | Builds `SimilarityContext` for an incident |

### Security

- Searches are always filtered by `organization_id`; memory is never shared
  across organizations.
- Only redacted text is embedded or stored in `text_snapshot`.

### APIs

| Endpoint | Role | Min role |
| -------- | ---- | -------- |
| `POST /api/embeddings/backfill` | Embed all org memory (idempotent) | admin+ |

The default embedder is a deterministic hashing model requiring no external
API. Swap in a real embedding provider behind `EmbeddingService` and store
vectors in a pgvector column for production-scale search.

## Evidence relevance judge (Phase 8)

Ranks how relevant each piece of evidence is to an incident using Claude plus
deterministic incident context. Judging is **categorical only** — no numeric
scores, no hardcoded weights.

### Claude output (per evidence item)

```json
{ "evidence_id": "...", "relevance": "high|medium|low|uncertain",
  "confidence": "high|medium|low", "reason": "..." }
```

### Rules & safety

- One batched Claude call judges all evidence — never one call per item.
- Evidence, logs, timelines, and docs are wrapped as UNTRUSTED DATA; the model
  is instructed to treat them as data, never as instructions (prompt-injection
  defense).
- Claude must not invent facts and returns JSON only. Output is strictly
  validated against `relevance_schema`.
- If Claude is unconfigured, errors, or returns malformed JSON, a deterministic
  `rule_based_fallback` assigns categorical labels.
- Each evidence row stores `relevance_source` = `claude` or `rule_based_fallback`,
  plus `relevance_label`, `relevance_confidence`, and `relevance_reason`.

### Observability

Per judging batch, `InvestigationRun.relevance_tracking` records:
`prompt_version`, `model_version`, `schema_version`, `latency_ms`,
`token_usage`, `estimated_cost`, and `relevance_source`.

### Services (`app/services/investigation_engine/`)

| Module | Role |
| ------ | ---- |
| `relevance_schema.py` | Judgment schema, allowed values, strict validation |
| `relevance_prompt_builder.py` | Builds batched prompt with untrusted-data guardrails |
| `relevance_judge.py` | Batched Claude call + deterministic fallback + tracking |

Enable Claude by setting `BREADCRUMBS_ANTHROPIC_API_KEY`; otherwise the
deterministic fallback is used (the default in dev/tests).

## Claude incident reasoning (Phase 9)

Generates evidence-backed incident analysis: executive summary, hypotheses,
estimated impact, suggested actions, missing evidence, and Slack draft.

### Readiness gate

Before full Claude reasoning, `ReasoningReadinessGate` checks evidence quality.
If there is no high-relevance evidence and most items are low/uncertain,
reasoning is skipped with `reasoning_status = "insufficient_evidence"` and
missing-evidence suggestions are generated instead.

### Services (`app/services/incident_reasoning/`)

| Module | Role |
| ------ | ---- |
| `evidence_pack_builder.py` | Budgeted, redacted evidence pack from run data |
| `reasoning_engine.py` | Orchestrates gate, Claude call, fallback, persistence |
| `reasoning_prompt_builder.py` | Batched prompt with untrusted-data guardrails |
| `reasoning_schema.py` | Output schema and strict validation |
| `action_generator.py` | Creates `SuggestedAction` rows (approval for risky actions) |
| `impact_estimator.py` | Creates `IncidentImpact` rows |
| `confidence_validator.py` | Rejects hypotheses citing unknown evidence IDs |
| `langfuse_logger.py` | Optional Langfuse observability (redacted metadata only) |

### Evidence pack budget

Context budget (~24k chars): high 60%, medium 30%, uncertain 10%, low sampled.
Over-budget groups are summarized; evidence IDs are always preserved.

### Observability

`InvestigationRun.reasoning_tracking` records `prompt_version`, `model_version`,
`schema_version`, `latency_ms`, `token_usage`, `estimated_cost`, and
`reasoning_source`. Optional Langfuse via `BREADCRUMBS_LANGFUSE_PUBLIC_KEY` and
`BREADCRUMBS_LANGFUSE_SECRET_KEY`.

## Postmortem generator (Phase 10)

Generates a structured postmortem after an incident is **resolved**. Claude
returns JSON internally; the API stores structured sections and a rendered
markdown `content` field for the UI.

### API

| Method | Path | Role |
| ------ | ---- | ---- |
| `POST` | `/api/incidents/{incident_id}/postmortem` | member+ — generate draft postmortem |
| `POST` | `/api/postmortems/{postmortem_id}/approve` | member+ — approve and embed for memory |

Generation requires `incident.status = "resolved"`. Active or investigating
incidents return HTTP 400.

### Services (`app/services/postmortem/`)

| Module | Role |
| ------ | ---- |
| `postmortem_generator.py` | Gathers incident context, calls Claude/fallback, persists |
| `postmortem_prompt_builder.py` | Prompt with untrusted-data guardrails |
| `postmortem_schema.py` | Section schema, validation, paragraph rendering |
| `postmortem_fallback.py` | Deterministic template when Claude is unavailable |

### Output sections

Stored in `Postmortem.sections` (JSON): `summary`, `impact`, `timeline`,
`root_cause`, `resolution`, `prevention_items`, `incident_duration_minutes`,
`postmortem_source`, and `assumptions` (facts vs assumptions separated).

`incident_duration_minutes` is computed from `started_at`/`detected_at` to
`resolved_at`. All gathered text is redacted before prompts or storage.

### Approval & memory

Approving a draft sets `status = "approved"` and enqueues an embedding via
`EmbeddingQueue.embed_postmortem()` for future similarity search.

### Audit

`postmortem_generated` is recorded when a postmortem is created.

## Real integrations: GitHub + Render (Phase 11)

Connects live GitHub and Render evidence while preserving the fake collectors,
so the app still runs fully offline in dev/tests.

### Connector framework

Every collector — fake or real — implements the same
`collect(service_name, start_time, end_time, alert_context) -> list[dict]`
interface (`app/services/integrations/collector_interface.py`). Real API
responses are normalized into the exact same raw-evidence shape as the fakes,
so the investigation engine never needs to know which is in use.

The `CollectorRegistry` transparently swaps a real collector in under the same
logical name the planner uses, but **only when the corresponding backend
credential is configured**. No token ⇒ fake collector.

### Services (`app/services/integrations/`)

| Module | Role |
| ------ | ---- |
| `collector_interface.py` | Shared `Collector` protocol + `CollectorError` |
| `github_client.py` | Thin GitHub REST client (injectable httpx transport) |
| `render_client.py` | Thin Render API client (injectable httpx transport) |
| `github_collector.py` | Normalizes commits, PRs, merges, deploy-related commits |
| `render_collector.py` | Normalizes deploy events, status, health, failed deploys |
| `integration_service.py` | Lists connections + tests providers (no secrets) |

**GitHub collects:** commits, pull requests, merges, deploy-related commits,
commit messages, author, timestamp, repo, branch.

**Render collects:** deploy events, deploy status, service health, failed
deploys, log/commit summaries, service name, timestamp.

### API

| Method | Path | Role |
| ------ | ---- | ---- |
| `GET` | `/api/integrations` | any member — connections + provider availability |
| `POST` | `/api/integrations/github/test` | admin/owner — probe GitHub connectivity |
| `POST` | `/api/integrations/render/test` | admin/owner — probe Render connectivity |

Provider availability is a boolean (`configured`); token values are never
serialized.

### Security

- Tokens are read from backend env vars only
  (`BREADCRUMBS_GITHUB_TOKEN`, `BREADCRUMBS_RENDER_API_KEY`).
- Raw tokens are never stored in the database and never returned to the frontend.
- `IntegrationConnection.config` holds non-secret metadata only.
- All collected free-text is secret-redacted before it becomes `Evidence`.

### Resilience

A single collector failure raises `CollectorError`, which the investigation
runner isolates per-collector: the collector's `CollectorRun` is marked
`failed` and the run continues with evidence from the other collectors.

## Production hardening & deployment (Phase 12)

Prepares the MVP for demo and staging: Docker, CI, observability, rate limits,
and deployment docs.

### MVP integration model

- **One organization per deployment** for real GitHub/Render tokens.
- Tokens live in **backend environment variables only** (not per-tenant in DB).
- **Multi-tenant per-org integration credentials are not supported** until
  encrypted vault storage (Supabase Vault or external secret manager) is added.

### Hardening

| Feature | Implementation |
| ------- | -------------- |
| Request IDs | `X-Request-ID` on every response; included in structured logs |
| Structured logging | JSON via `BREADCRUMBS_LOG_JSON=true`; `request_id` on every line |
| Sentry (backend) | Optional `BREADCRUMBS_SENTRY_DSN`; PII off, no request bodies |
| Rate limits | Per-org sliding window on expensive endpoints (see below) |
| CORS | Restricted to `BREADCRUMBS_CORS_ORIGINS`; explicit methods/headers |

### Rate-limited endpoints

| Endpoint | Category | Default limit/min |
| -------- | -------- | ----------------- |
| `POST /api/incidents/{id}/investigation-runs` | investigation | 5 |
| `POST /api/incidents/{id}/postmortem` | ai | 5 |
| `POST /api/knowledge/build` | knowledge_build | 10 |
| `POST /api/knowledge/artifacts` | artifact_upload | 20 |
| `POST /api/embeddings/backfill` | embedding_backfill | 2 |

Disable with `BREADCRUMBS_RATE_LIMIT_ENABLED=false` (dev only).

### Deployment artifacts

- `backend/Dockerfile` — production image (migrations + uvicorn)
- `render.yaml` — Render blueprint (backend + frontend)
- `.github/workflows/ci.yml` — ruff + pytest + frontend lint/build

### Documentation

See repo root `docs/`: architecture, security, deployment, demo script, known
limitations.

## Configuration

Settings are loaded from environment variables (prefixed with `BREADCRUMBS_`)
or a local `.env` file. See [`.env.example`](.env.example) for all options.

| Variable                    | Default                 | Description                                  |
| --------------------------- | ----------------------- | -------------------------------------------- |
| `BREADCRUMBS_ENVIRONMENT`   | `development`           | Deployment environment name.                 |
| `BREADCRUMBS_DEBUG`         | `true`                  | Enable FastAPI debug mode.                    |
| `BREADCRUMBS_LOG_LEVEL`     | `INFO`                  | Root log level.                              |
| `BREADCRUMBS_LOG_JSON`      | `false`                 | Emit structured JSON logs when `true`.       |
| `BREADCRUMBS_HOST`          | `0.0.0.0`               | Bind host.                                   |
| `BREADCRUMBS_PORT`          | `8000`                  | Bind port.                                   |
| `BREADCRUMBS_CORS_ORIGINS`  | `http://localhost:3000` | Comma-separated allowed CORS origins.        |
| `BREADCRUMBS_DATABASE_URL`  | _(empty)_               | Supabase Postgres connection string.         |
| `BREADCRUMBS_DATABASE_ECHO` | `false`                 | Log SQL statements (dev only).               |
| `BREADCRUMBS_SUPABASE_URL`  | _(empty)_               | Supabase project URL (auth issuer/JWKS).     |
| `BREADCRUMBS_SUPABASE_JWT_SECRET` | _(empty)_         | HS256 JWT secret; blank uses JWKS.           |
| `BREADCRUMBS_SUPABASE_JWT_AUDIENCE` | `authenticated`  | Expected JWT audience.                        |
| `BREADCRUMBS_EMBEDDING_MODEL`      | `local-hash`     | Embedding model identifier.                    |
| `BREADCRUMBS_EMBEDDING_VERSION`    | `v1`             | Embedding version (changes force re-embed).    |
| `BREADCRUMBS_EMBEDDING_DIMENSIONS` | `256`            | Embedding vector dimensionality.               |
| `BREADCRUMBS_LANGFUSE_PUBLIC_KEY`    | _(empty)_        | Langfuse public key (optional observability).  |
| `BREADCRUMBS_LANGFUSE_SECRET_KEY`    | _(empty)_        | Langfuse secret key.                           |
| `BREADCRUMBS_LANGFUSE_HOST`          | `https://cloud.langfuse.com` | Langfuse API host.              |
| `BREADCRUMBS_GITHUB_TOKEN`           | _(empty)_        | GitHub PAT; blank uses fake collector.         |
| `BREADCRUMBS_GITHUB_API_BASE`        | `https://api.github.com` | GitHub API base URL.               |
| `BREADCRUMBS_GITHUB_DEFAULT_REPO`    | _(empty)_        | Default `owner/repo` when no incident hint.    |
| `BREADCRUMBS_RENDER_API_KEY`         | _(empty)_        | Render API key; blank uses fake collector.     |
| `BREADCRUMBS_RENDER_API_BASE`        | `https://api.render.com/v1` | Render API base URL.            |
| `BREADCRUMBS_RENDER_OWNER_ID`        | _(empty)_        | Optional owner id to scope Render services.     |
| `BREADCRUMBS_SENTRY_DSN`             | _(empty)_        | Sentry DSN; blank disables error reporting.       |
| `BREADCRUMBS_SENTRY_TRACES_SAMPLE_RATE` | `0.0`         | Sentry performance sampling (0 = off).            |
| `BREADCRUMBS_RELEASE`                | _(empty)_        | Optional release tag for Sentry events.          |
| `BREADCRUMBS_RATE_LIMIT_ENABLED`     | `true`           | Enable per-org rate limits on expensive routes.   |
| `BREADCRUMBS_RATE_LIMIT_WINDOW_SECONDS` | `60`          | Sliding window length in seconds.                 |
| `BREADCRUMBS_RATE_LIMIT_INVESTIGATION_PER_MIN` | `5`    | Investigation runs per org per window.            |
| `BREADCRUMBS_RATE_LIMIT_AI_PER_MIN`  | `5`              | Postmortem / AI endpoints per org per window.     |
| `BREADCRUMBS_RATE_LIMIT_KNOWLEDGE_BUILD_PER_MIN` | `10` | Knowledge build per org per window.               |
| `BREADCRUMBS_RATE_LIMIT_ARTIFACT_UPLOAD_PER_MIN` | `20` | Artifact ingest per org per window.               |
| `BREADCRUMBS_RATE_LIMIT_EMBEDDING_BACKFILL_PER_MIN` | `2` | Embedding backfill per org per window.         |

## Project structure

```
app/
  main.py        # FastAPI app factory & startup
  routes/        # API route handlers (health)
  services/      # Business logic (empty for now)
  models/        # SQLAlchemy ORM models (26 models)
  schemas/       # Pydantic request/response schemas
  db/            # Base, mixins, portable types, session/engine
  core/          # Config & logging
migrations/      # Alembic environment + versioned migrations
tests/           # Pytest model tests
```

## Data model overview

All models use UUID primary keys and created/updated timestamps. Every
**organization-owned** model carries an indexed, NOT NULL `organization_id`
(enforced via `OrganizationScopedMixin`). Frequently-queried foreign keys
(`organization_id`, `incident_id`, `investigation_run_id`) are indexed.

Model groups (`app/models/`):

- **users** — `UserProfile` (global identity)
- **organizations** — `Organization`, `OrganizationMember`,
  `OrganizationInvitation`, `OrganizationSettings`
- **knowledge** — `KnowledgeArtifact`, `ServiceNode`, `ServiceDependency`,
  `KnowledgeGraphProposal`, `Runbook`
- **incidents** — `Incident`, `Alert`, `AlertCorrelation`, `IncidentImpact`,
  `Postmortem`
- **investigations** — `InvestigationRun`, `InvestigationPlan`, `CollectorRun`,
  `Evidence`, `TimelineEvent`, `Hypothesis`, `SuggestedAction`, `SlackDraft`
- **embeddings** — `EmbeddingRecord`
- **integrations** — `IntegrationConnection` (non-secret metadata only)
- **audit** — `AuditLog`

### Security notes

- **No secrets are stored in the database.** `IntegrationConnection.config`
  holds non-secret metadata only; API keys/tokens belong in a secret manager.
- The only credential the app needs is `BREADCRUMBS_DATABASE_URL` in `.env`.
