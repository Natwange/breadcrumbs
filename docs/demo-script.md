# Demo script

End-to-end walkthrough for staging or local demo. Adjust URLs and credentials
for your environment.

**Duration:** ~15–20 minutes  
**Audience:** Engineering leads, investors, or internal stakeholders

---

## Before you start

- [ ] Backend running (`/health` → `ok`)
- [ ] Frontend running; Supabase auth configured
- [ ] At least one user signed up and in an organization
- [ ] Knowledge graph seeded (optional but improves investigation plan)
- [ ] For live evidence: `BREADCRUMBS_GITHUB_TOKEN` + `BREADCRUMBS_RENDER_API_KEY` set

---

## 1. Sign in (2 min)

1. Open the frontend home page.
2. Sign up or sign in with email/password.
3. Confirm **Signed in** panel shows organization name.
4. Click **Go to investigations**.

---

## 2. Trigger an incident (3 min)

**Option A — API (recommended for demo control)**

```bash
curl -X POST "$API/api/alerts/ingest" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-Id: $ORG_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "manual_demo",
    "title": "Elevated error rate on backend",
    "description": "5xx errors spiking on API service",
    "raw_payload": {"service": "backend", "alert_type": "error_rate"}
  }'
```

Note the `incident_id` from the response.

**Option B — Pre-seeded incident**

If you already have incidents, they appear on `/investigations`.

---

## 3. Run investigation (5 min)

1. On **Investigations**, find the incident card.
2. Click **Run investigation**.
3. Watch live status: `running` → evidence/timeline counts update.
4. When status is **completed**, polling stops automatically.
5. Point out:
   - Evidence count (collectors + fake/real GitHub/Render if configured)
   - Executive summary / reasoning status
   - Top hypothesis title

**Talking points:**

- Collectors are pluggable; same engine for fake and real data.
- Relevance judge filters noise before Claude reasoning.
- If Claude is off, fallbacks still produce a coherent draft.

---

## 4. Inspect results via API (3 min)

```bash
curl "$API/api/investigation-runs/$RUN_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-Id: $ORG_ID"
```

Highlight: `evidence_count`, `hypothesis`, `executive_summary`, `reasoning_status`,
`relevance_tracking`.

---

## 5. Resolve incident + postmortem (4 min)

1. Mark incident resolved (API or DB for demo).
2. Generate postmortem:

```bash
curl -X POST "$API/api/incidents/$INCIDENT_ID/postmortem" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-Id: $ORG_ID" \
  -H "Content-Type: application/json" \
  -d '{"resolution_notes": "Scaled connection pool; deployed hotfix abc123"}'
```

3. Show structured `sections` (summary, timeline, root_cause, prevention).
4. Approve postmortem → embedded for organizational memory.

---

## 6. Integrations health (2 min)

```bash
curl -X POST "$API/api/integrations/github/test" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Organization-Id: $ORG_ID"
```

Confirm `configured` / `ok` without any token in the response body.

---

## 7. Wrap-up talking points

- **Tenancy:** every query scoped by `organization_id`; tests enforce isolation.
- **Security:** secrets in env only; redaction on ingest and evidence.
- **Production readiness:** request IDs, rate limits, Sentry, CI, Docker, Render blueprint.
- **Limitations:** single-org integration tokens; in-memory rate limits — see
  [known-limitations.md](known-limitations.md).

---

## Troubleshooting

| Issue | Check |
| ----- | ----- |
| 401 on API | JWT expired; re-login; `Authorization` header |
| 403 on org | `X-Organization-Id` matches membership |
| 429 | Rate limit; wait 60s or disable in dev |
| No GitHub evidence | Token set? `github_default_repo`? `related_services` in plan? |
| `insufficient_evidence` | Seed knowledge graph; ensure collectors return content ≥ 8 chars |
