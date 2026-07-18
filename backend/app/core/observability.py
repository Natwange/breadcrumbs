"""Sentry error tracking initialization (optional).

Sentry is only enabled when ``BREADCRUMBS_SENTRY_DSN`` is set. The import is
guarded so the app runs even if ``sentry-sdk`` is not installed. PII sending is
disabled and request bodies are not captured, keeping tokens/secrets out of
error reports.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def init_sentry(settings: Settings) -> bool:
    """Initialize Sentry if configured. Returns True when enabled."""
    if not settings.sentry_dsn:
        return False

    try:
        import sentry_sdk
    except ImportError:
        logger.warning("sentry_dsn set but sentry-sdk is not installed; skipping")
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=settings.release or None,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # Never attach PII or request bodies (may contain tokens/secrets).
        send_default_pii=False,
        max_request_body_size="never",
    )
    logger.info("sentry initialized", extra={"environment": settings.environment})
    return True
