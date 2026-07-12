# FocusFlow

FocusFlow is a full-stack productivity application.

## Architecture

- **Frontend**: Next.js app deployed on Render
- **Backend**: FastAPI API (uvicorn) deployed on Render
- **Database**: Supabase Postgres (managed)

The frontend calls the backend over HTTP. The backend connects to Supabase Postgres.

## Environment

```
API_KEY=sk-test-secret-key-should-be-redacted-12345678
DATABASE_URL=postgresql+psycopg2://postgres:supersecret@db.example.supabase.co:5432/postgres
```
