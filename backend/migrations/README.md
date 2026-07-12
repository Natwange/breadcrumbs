# Database migrations (Alembic)

Migrations are driven by application settings. Set
`BREADCRUMBS_DATABASE_URL` (in `backend/.env`) to your Supabase Postgres
connection string, then run from the `backend/` directory:

```bash
# Apply all migrations
alembic upgrade head

# Create a new migration after changing models
alembic revision --autogenerate -m "describe change"

# Roll back the most recent migration
alembic downgrade -1
```
