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
