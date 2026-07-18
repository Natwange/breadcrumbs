from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    Values can be provided via a local ``.env`` file (see ``.env.example``)
    or through the process environment. Environment variables take
    precedence over ``.env`` entries.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="BREADCRUMBS_",
        extra="ignore",
    )

    app_name: str = "breadcrumbs"
    environment: str = "development"
    debug: bool = True

    # Database. For Supabase, use the connection string from
    # Project Settings -> Database (see backend/README.md). Example:
    #   postgresql+psycopg2://postgres.<ref>:<password>@<host>:6543/postgres
    # Left empty by default; required for running the app and migrations.
    database_url: str = ""

    # Log SQL statements emitted by SQLAlchemy (verbose; dev only).
    database_echo: bool = False

    # ------------------------------------------------------------------
    # Supabase auth
    # ------------------------------------------------------------------
    # Base project URL, e.g. https://<project-ref>.supabase.co
    # Used to derive the JWT issuer and JWKS endpoint. Required for auth.
    supabase_url: str = ""

    # Legacy HS256 shared secret (Project Settings -> API -> JWT Secret).
    # If set, tokens are verified with HS256 using this secret. If empty,
    # the verifier fetches asymmetric public keys from the project JWKS
    # endpoint (RS256/ES256). Provide whichever matches your project.
    supabase_jwt_secret: str = ""

    # Expected audience claim. Supabase user tokens use "authenticated".
    supabase_jwt_audience: str = "authenticated"

    @property
    def supabase_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    # ------------------------------------------------------------------
    # Claude (optional — knowledge builder architecture extraction)
    # ------------------------------------------------------------------
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    # ------------------------------------------------------------------
    # Vector search / organizational memory (Phase 7)
    # ------------------------------------------------------------------
    # Default embedder is a deterministic local hashing model requiring no
    # external API. It keeps tests reproducible and never leaves the process.
    embedding_model: str = "local-hash"
    embedding_version: str = "v1"
    embedding_dimensions: int = 256

    # ------------------------------------------------------------------
    # Real integrations (optional — Phase 11 GitHub + Render)
    # ------------------------------------------------------------------
    # Tokens are read from the backend environment ONLY. They are never stored
    # in the database and never returned to the frontend. When a token is
    # empty, the investigation engine transparently falls back to the fake
    # collector for that provider.
    github_token: str = ""
    github_api_base: str = "https://api.github.com"
    # Optional default "owner/repo" used when an incident has no repo hint.
    github_default_repo: str = ""

    render_api_key: str = ""
    render_api_base: str = "https://api.render.com/v1"
    # Optional owner id used to scope Render service lookups.
    render_owner_id: str = ""

    # ------------------------------------------------------------------
    # Langfuse observability (optional — Phase 9 incident reasoning)
    # ------------------------------------------------------------------
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # ------------------------------------------------------------------
    # Sentry error tracking (optional — Phase 12 production hardening)
    # ------------------------------------------------------------------
    # When a DSN is set, unhandled errors are reported to Sentry. Leave blank
    # to disable (the default in dev/tests). PII sending is disabled.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0
    # Optional release identifier (e.g. git SHA) attached to Sentry events.
    release: str = ""

    # Incoming Sentry webhooks (alerts FROM an instrumented app → Breadcrumbs).
    # Shared secret + org id; empty secret disables the webhook endpoint.
    sentry_webhook_secret: str = ""
    sentry_webhook_org_id: str = ""

    # ------------------------------------------------------------------
    # Rate limiting (Phase 12) — protects expensive/AI endpoints.
    # Limits are per-organization, per-category, over a sliding window.
    # ------------------------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    # Full AI investigation runs (collectors + Claude reasoning).
    rate_limit_investigation_per_min: int = 5
    # Postmortem generation (Claude).
    rate_limit_ai_per_min: int = 5
    # Knowledge graph build (Claude architecture extraction).
    rate_limit_knowledge_build_per_min: int = 10
    # Artifact uploads / ingestion.
    rate_limit_artifact_upload_per_min: int = 20
    # Embedding backfill (bulk).
    rate_limit_embedding_backfill_per_min: int = 2

    # Logging
    log_level: str = "INFO"
    log_json: bool = False

    # HTTP server
    host: str = "0.0.0.0"
    port: int = 8000

    # Comma-separated list of allowed CORS origins for the frontend.
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
