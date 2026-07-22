# API reference

breadcrumbs exposes a REST API from the FastAPI backend. The Next.js frontend
is a UI client only — it does not define its own HTTP API routes.

This document describes **what each endpoint does**. Authentication, tenancy,
and secret-handling details live in [security.md](security.md). Deployment
topology is in [architecture.md](architecture.md).

## Conventions

| Topic | Behavior |
| ----- | -------- |
| Auth | Almost all endpoints require a signed-in user and membership in an organization. Exact credential formats are not documented here. |
| Tenancy | Responses and writes are scoped to the caller's organization. Clients cannot choose another org's data via request body fields. |
| Roles | Some writes (settings, members, invitations, knowledge approvals, integrations) require elevated org permissions. |
| Dual surfaces | Older CRUD-style routes sit at root paths (`/incidents`, `/knowledge`, …). Richer product APIs live under `/api/...`. Prefer `/api/...` for new integrations. |

Interactive OpenAPI docs are available from a running backend (`/docs`, `/redoc`)
for local development. Treat those as developer tooling, not a public surface.

---

## Health

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/health` | Liveness check. Unauthenticated; returns a simple status payload. |

---

## Auth

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/auth/me` | Returns the current user and their active organization (provisions the user/org linkage on first successful call). |

---

## Organizations

Manage settings, membership, and invitations for the caller's organization.

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/organizations/settings` | Read org settings (timezone, default severity, preferences, notes). |
| `PATCH` | `/organizations/settings` | Update org settings. |
| `GET` | `/organizations/members` | List org members and roles. |
| `PATCH` | `/organizations/members/{member_id}/role` | Change a member's role. |
| `DELETE` | `/organizations/members/{member_id}` | Remove a member from the org. |
| `POST` | `/organizations/invitations` | Invite a user by email with a role. |
| `GET` | `/organizations/invitations` | List pending/sent invitations. |
| `DELETE` | `/organizations` | Soft-delete the current organization. |

---

## Alerts

Ingest monitoring alerts and correlate them to incidents.

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `POST` | `/alerts` | Ingest an alert and return correlation details (linked or newly created incident, confidence, method). |
| `POST` | `/api/alerts/ingest` | Ingest an alert with a simpler response (`alert_id`, `incident_id`). Suitable for demos and external alert sources. |

Supported alert sources include common monitoring platforms and a manual/demo
source. Payload bodies carry title, optional description/time, and optional
source-specific context — not credentials.

---

## Incidents

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/incidents` | List incidents for the org. |
| `POST` | `/incidents` | Create an incident. |
| `GET` | `/incidents/{incident_id}` | Fetch a single incident. |

---

## Investigation runs

### Record CRUD

Lightweight create/list/get for investigation run records (does not start the
full investigation engine).

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/investigation-runs` | List investigation runs. |
| `POST` | `/investigation-runs` | Create a run record. |
| `GET` | `/investigation-runs/{run_id}` | Fetch a run record. |

### Investigation engine

Starts collectors, evidence gathering, and reasoning for an incident.

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `POST` | `/api/incidents/{incident_id}/investigation-runs` | Start a full investigation for an incident. |
| `GET` | `/api/investigation-runs/{run_id}` | Poll run status and results (plan, hypothesis, Slack draft, evidence/timeline counts). |
| `GET` | `/api/incidents/{incident_id}/workspace` | Aggregated incident workspace: incident, alerts, runs, evidence, timeline, hypotheses, actions, impacts, and postmortem. Optional `run_id` query focuses on one run. |

---

## Knowledge

### Artifact & proposal CRUD

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/knowledge` | List knowledge artifacts (metadata). |
| `POST` | `/knowledge` | Create a knowledge artifact. |
| `GET` | `/knowledge/{artifact_id}` | Fetch one artifact. |
| `POST` | `/knowledge/proposals` | Create a graph change proposal. |
| `POST` | `/knowledge/proposals/{proposal_id}/approve` | Approve and apply a proposal. |

### Knowledge builder (`/api/knowledge`)

Richer graph-building and review flows used by the product UI.

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `POST` | `/api/knowledge/artifacts` | Ingest an artifact; may also create a proposal. |
| `POST` | `/api/knowledge/build` | Extract architecture/services from an artifact into a reviewable proposal. |
| `GET` | `/api/knowledge/graph` | Snapshot of the org service graph (services, dependencies, runbooks). |
| `GET` | `/api/knowledge/proposals` | List proposals; optional status filter. |
| `POST` | `/api/knowledge/proposals/{proposal_id}/approve` | Approve and apply a proposal. |
| `POST` | `/api/knowledge/proposals/{proposal_id}/reject` | Reject a proposal. |
| `POST` | `/api/knowledge/updates` | Submit a manual graph update or drift check; optionally apply. |
| `GET` | `/api/knowledge/runbooks` | List runbooks linked to services. |

---

## Embeddings / memory

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `POST` | `/api/embeddings/backfill` | Backfill vector embeddings for the org so similarity search can use existing artifacts and postmortems. Returns counts of embedded/skipped/rejected items. |

---

## Postmortems

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `POST` | `/api/incidents/{incident_id}/postmortem` | Generate a postmortem draft from investigation evidence (optional resolution notes). |
| `POST` | `/api/postmortems/{postmortem_id}/approve` | Approve a draft and embed it for future incident memory/search. |

---

## Integrations

Connection **metadata** only (provider name, status, non-secret config such as
repo or service identifiers). Provider credentials are never accepted or
returned by these endpoints — see [security.md](security.md).

### Connection records

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/integrations` | List integration connection metadata. |
| `POST` | `/integrations` | Create connection metadata. |
| `GET` | `/integrations/{connection_id}` | Fetch one connection. |

### Provider status

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `GET` | `/api/integrations` | List connections plus whether each provider is configured on this deployment. |
| `POST` | `/api/integrations/github/test` | Connectivity check for GitHub (no secrets in the response). |
| `POST` | `/api/integrations/render/test` | Connectivity check for Render (no secrets in the response). |

---

## Webhooks

Inbound events from external systems. These endpoints are authenticated
differently from user session routes; configuration is deployment-specific and
is not documented here.

| Method | Path | Purpose |
| ------ | ---- | ------- |
| `POST` | `/api/webhooks/sentry` | Accept a Sentry issue/alert payload, create or correlate an alert/incident, and optionally kick off an investigation. |

---

## What is not an API

| Surface | Notes |
| ------- | ----- |
| Next.js pages (`/dashboard`, `/incidents`, `/knowledge`, …) | UI only; they call the FastAPI backend. |
| GraphQL / tRPC / WebSockets | Not used. |
| Third-party LLM / GitHub / Render calls | Made server-side during investigations and knowledge builds; not exposed as separate public routes beyond the test endpoints above. |

---

## Related docs

- [architecture.md](architecture.md) — system design and core workflows
- [security.md](security.md) — auth, tenancy, and secret-handling decisions
- [known-limitations.md](known-limitations.md) — MVP constraints
- [deployment.md](deployment.md) — how to run and deploy
