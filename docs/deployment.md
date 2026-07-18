# Deployment guide

Deploy breadcrumbs for demo or staging using **Render** (backend + optional
frontend), **Vercel** (frontend alternative), and **Supabase** (database +
auth).

## Prerequisites

- Supabase project (Postgres + Auth enabled)
- Optional: Anthropic API key, GitHub PAT, Render API key, Sentry DSN, Langfuse keys

## 1. Supabase

1. Create a project at [supabase.com](https://supabase.com).
2. **Database:** Project Settings → Database → Connection string (URI). Use
   `postgresql+psycopg2://...` for SQLAlchemy.
3. **Auth:** Project Settings → API → Project URL + anon key (frontend) + JWT
   secret or JWKS (backend).
4. Run migrations from your machine or CI:
   ```bash
   cd backend
   export BREADCRUMBS_DATABASE_URL="postgresql+psycopg2://..."
   alembic upgrade head
   ```

## 2. Backend (Render)

### Option A: Blueprint

1. Connect the GitHub repo to Render.
2. Use [`render.yaml`](../render.yaml) at the repo root.
3. Set **sync: false** env vars in the Render dashboard (see below).

### Option B: Manual Docker service

1. New **Web Service** → Docker.
2. Dockerfile path: `backend/Dockerfile`, context: `backend`.
3. Health check path: `/health`.
4. The container runs `alembic upgrade head` then `uvicorn` on `$PORT`.

### Required backend env vars

| Variable | Notes |
| -------- | ----- |
| `BREADCRUMBS_DATABASE_URL` | Supabase Postgres URI |
| `BREADCRUMBS_SUPABASE_URL` | `https://<ref>.supabase.co` |
| `BREADCRUMBS_SUPABASE_JWT_SECRET` | Or leave blank for JWKS |
| `BREADCRUMBS_CORS_ORIGINS` | Your frontend URL(s), comma-separated |
| `BREADCRUMBS_ENVIRONMENT` | `production` |
| `BREADCRUMBS_DEBUG` | `false` |
| `BREADCRUMBS_LOG_JSON` | `true` |

### Optional backend env vars

| Variable | Purpose |
| -------- | ------- |
| `BREADCRUMBS_ANTHROPIC_API_KEY` | Claude reasoning, relevance, postmortem, knowledge build |
| `BREADCRUMBS_GITHUB_TOKEN` | Real GitHub collector |
| `BREADCRUMBS_GITHUB_DEFAULT_REPO` | e.g. `your-org/focusflow` |
| `BREADCRUMBS_RENDER_API_KEY` | Real Render collector |
| `BREADCRUMBS_SENTRY_DSN` | Error tracking |
| `BREADCRUMBS_LANGFUSE_*` | LLM observability |

## 3. Frontend (Vercel or Render)

### Vercel

1. Import the repo; root directory: `frontend`.
2. Set environment variables:

| Variable | Example |
| -------- | ------- |
| `NEXT_PUBLIC_API_BASE_URL` | `https://breadcrumbs-backend.onrender.com` |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<ref>.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key |
| `NEXT_PUBLIC_ENVIRONMENT` | `production` |
| `NEXT_PUBLIC_SENTRY_DSN` | Optional |

### Render (from blueprint)

The second service in `render.yaml` builds and runs `npm run start` in
`frontend/`.

## 4. FocusFlow staging integration (single-org model)

For the MVP demo, use **one organization** in the deployment:

1. Set `BREADCRUMBS_GITHUB_TOKEN` with read access to the FocusFlow staging repo.
2. Set `BREADCRUMBS_GITHUB_DEFAULT_REPO=your-org/focusflow` (adjust to your repo).
3. Set `BREADCRUMBS_RENDER_API_KEY` for the staging Render account.
4. Seed the knowledge graph (ingest README / runbook) so the planner knows
   `backend`, `render`, and dependencies.
5. Trigger **safe staging failures only** (e.g. synthetic alert via
   `POST /api/alerts/ingest` with `manual_demo` source) — never production.

Verify:

- Investigation collects GitHub commits/PRs and Render deploy/health evidence.
- Hypothesis cites evidence (check `supporting_evidence_ids` on hypotheses).
- With `BREADCRUMBS_ANTHROPIC_API_KEY` unset, reasoning and postmortem use
  fallbacks (`reasoning_status`, `postmortem_source` = rule-based).

## 5. CI

GitHub Actions (`.github/workflows/ci.yml`) runs on push/PR to `main`:

- Backend: `ruff check` + `pytest`
- Frontend: `npm run lint` + `npm run build`

## 6. Local Docker smoke test

```bash
cd backend
docker build -t breadcrumbs-api .
docker run --rm -p 8000:8000 \
  -e BREADCRUMBS_DATABASE_URL=... \
  -e BREADCRUMBS_SUPABASE_URL=... \
  breadcrumbs-api
```
