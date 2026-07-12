# breadcrumbs

A full-stack AI-powered incident investigation platform that follows a trail of
evidence across engineering systems to identify the root cause of production
outages.

> **Phase 1 — Project Foundation.** This repository currently contains the
> monorepo scaffolding: a FastAPI backend with a health endpoint and a Next.js
> frontend homepage. No database, auth, AI, or integrations yet.

## Repository layout

```
breadcrumbs/
  backend/     # FastAPI service (GET /health, config, structured logging)
  frontend/    # Next.js + TypeScript app (homepage + backend health check)
```

## Quick start

Run the backend and frontend in two terminals.

### 1. Backend (http://localhost:8000)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Verify: http://localhost:8000/health returns `{ "status": "ok" }`.

### 2. Frontend (http://localhost:3000)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 — the homepage shows the **AI Incident
Investigation Workspace** landing page and a live backend health check.

See [`backend/README.md`](backend/README.md) and
[`frontend/README.md`](frontend/README.md) for details.
