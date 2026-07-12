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
    anthropic_model: str = "claude-sonnet-4-20250514"

    # ------------------------------------------------------------------
    # Vector search / organizational memory (Phase 7)
    # ------------------------------------------------------------------
    # Default embedder is a deterministic local hashing model requiring no
    # external API. It keeps tests reproducible and never leaves the process.
    embedding_model: str = "local-hash"
    embedding_version: str = "v1"
    embedding_dimensions: int = 256

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
