# breadcrumbs

A full-stack AI-powered incident investigation platform that follows a trail of
evidence across engineering systems to identify the root cause of production
outages.

It ingests alerts, builds a knowledge graph of your services, collects evidence
from real integrations (GitHub, Render) or fake collectors, judges evidence
relevance, reasons with Claude to produce hypotheses and suggested actions, and
generates structured postmortems — all scoped per organization.

## Repository layout

```
breadcrumbs/
  backend/           # FastAPI service (API, AI engine, integrations, migrations)
  frontend/          # Next.js + TypeScript app (auth, investigations UI)
  docs/              # Architecture, security decisions, demo script, limitations
  render.yaml        # Render deployment blueprint (backend + frontend)
  .github/workflows/ # CI: lint + test (backend) and lint + build (frontend)
```

## Architecture at a glance

| Layer | Technology |
| ----- | ---------- |
| Frontend | Next.js (App Router) + TypeScript, deployed to Vercel or Render |
| Backend | FastAPI (Python 3.12), deployed to Render (Docker) |
| Database | Supabase Postgres (SQLAlchemy + Alembic) |
| Auth | Supabase Auth (JWT verified by the backend) |
| AI | Claude (optional) with deterministic fallbacks |
| Observability | Sentry (errors), Langfuse (LLM), structured logs w/ request IDs |

See [`docs/architecture.md`](docs/architecture.md) for the full picture.

## Quick start

Run the backend and frontend in two terminals.

### 1. Backend (http://localhost:8000)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env             # set BREADCRUMBS_DATABASE_URL + Supabase vars
alembic upgrade head
uvicorn app.main:app --reload
```

Verify: http://localhost:8000/health returns `{ "status": "ok" }`.

### 2. Frontend (http://localhost:3000)

```bash
cd frontend
npm install
cp .env.example .env.local       # set NEXT_PUBLIC_* vars
npm run dev
```

Open http://localhost:3000, sign in, then go to **Investigations** to trigger an
AI investigation and watch evidence stream in live.

## Deployment

- **Backend → Render** using [`backend/Dockerfile`](backend/Dockerfile) or the
  [`render.yaml`](render.yaml) blueprint.
- **Frontend → Vercel or Render.**
- **Database → Supabase Postgres.**
- **Auth → Supabase Auth.**

Set secrets as environment variables in the platform dashboard — never commit
them. See [`docs/deployment.md`](docs/deployment.md).

## Documentation

- [`backend/README.md`](backend/README.md) — backend features (Phases 1–12)
- [`docs/architecture.md`](docs/architecture.md) — system architecture
- [`docs/security.md`](docs/security.md) — security decisions
- [`docs/deployment.md`](docs/deployment.md) — deploying to Render/Vercel/Supabase
- [`docs/demo-script.md`](docs/demo-script.md) — step-by-step demo walkthrough
- [`docs/known-limitations.md`](docs/known-limitations.md) — known limitations

## Testing

```bash
cd backend && pytest        # backend unit/API/tenancy/workflow tests
cd frontend && npm run lint && npm run build
```
