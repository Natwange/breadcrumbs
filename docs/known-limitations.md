# Known limitations

Explicit constraints of the breadcrumbs MVP and Phase 12 staging deployment.
These are intentional tradeoffs for demo velocity, not oversights.

## Integrations & multi-tenancy

| Limitation | Impact | Future |
| ---------- | ------ | ------ |
| **One org per deployment for real GitHub/Render tokens** | All tenants in a shared deployment would share the same PAT/API key if you pointed multiple orgs at one backend with env-only tokens. | Per-organization credentials in **Supabase Vault** or an external secret manager; `IntegrationConnection` stores only non-secret metadata + vault reference. |
| **Tokens not in database** | Cannot configure GitHub/Render per customer in the UI today. | Vault-backed `config.integration_secret_ref` resolved at collector runtime. |
| **Fake collectors when token missing** | Dev/tests work offline; production without tokens never sees live evidence. | Expected; set env vars in staging/prod. |

## Rate limiting

| Limitation | Impact | Future |
| ---------- | ------ | ------ |
| **In-memory per-process counters** | Limits reset on restart; not shared across multiple backend instances. | Redis or similar shared store for horizontal scaling. |
| **Per-organization only** | No per-user sub-limits within an org. | Optional user-level keys for abuse cases. |

## Frontend auth

| Limitation | Impact | Future |
| ---------- | ------ | ------ |
| **Supabase session in localStorage** | `middleware.ts` cannot enforce auth server-side; `/investigations` uses client-side `RequireAuth`. | Migrate to `@supabase/ssr` with HTTP-only cookies for true server guards. |
| **Minimal UI surface** | Home + investigations list/run; no full incident CRUD UI yet. | Expand pages as product matures. |

## AI & evidence

| Limitation | Impact | Future |
| ---------- | ------ | ------ |
| **Claude optional** | Without `BREADCRUMBS_ANTHROPIC_API_KEY`, relevance/reasoning/postmortem/knowledge build use rule-based fallbacks. | Expected for cost and offline dev. |
| **Local-hash embeddings** | Similarity is deterministic but not semantic vs. production embedding APIs. | Swap `BREADCRUMBS_EMBEDDING_MODEL` when ready. |
| **Investigation time window** | Collectors default to ~1 hour lookback. | Configurable per incident or alert time. |
| **GitHub repo resolution** | Needs `owner/repo` hint, `github_default_repo`, or `github_repo` in alert context. | Auto-map from knowledge graph service → repo metadata. |

## Observability

| Limitation | Impact | Future |
| ---------- | ------ | ------ |
| **Langfuse optional** | No centralized LLM traces without keys. | Set `BREADCRUMBS_LANGFUSE_*` in staging. |
| **Sentry traces disabled by default** | `traces_sample_rate=0` to reduce noise/cost. | Tune per environment. |

## Operations

| Limitation | Impact | Future |
| ---------- | ------ | ------ |
| **Migrations run on container start** | Simple for single-instance Render; risky for multi-instance concurrent deploys. | Separate release job or migration-only init container. |
| **No automated staging E2E in CI** | FocusFlow GitHub/Render staging test is manual (see demo script). | Scheduled workflow with mocked or dedicated staging creds. |
| **httpx not connection-pooled globally** | Each Claude/integration call opens a short-lived client. | Shared client pool if latency becomes an issue. |

## Testing coverage (what CI runs)

CI runs **backend pytest** (unit, API, tenancy, workflow, secret redaction, vector
search, mock integrations, hardening) and **frontend lint + build**. It does
**not** call live GitHub, Render, Anthropic, or Supabase in the pipeline.

For manual staging verification, follow
[deployment.md](deployment.md) § FocusFlow staging and [demo-script.md](demo-script.md).
