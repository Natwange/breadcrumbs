import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.observability import init_sentry
from app.core.request_context import set_request_id
from app.routes import api_router

settings = get_settings()
configure_logging(settings)
init_sentry(settings)
logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"

# Explicit headers the browser client may send. Restricting these (instead of
# "*") keeps the CORS contract tight while still allowing our auth + tenancy
# headers through.
ALLOWED_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-Organization-Id",
    "X-Breadcrumbs-Webhook-Secret",
    REQUEST_ID_HEADER,
]
ALLOWED_METHODS = ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "starting application",
        extra={"app_name": settings.app_name, "environment": settings.environment},
    )
    yield
    logger.info("shutting down application")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="AI Incident Investigation Workspace API",
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming or uuid.uuid4().hex
        set_request_id(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = int((time.perf_counter() - start) * 1000)
            response.headers[REQUEST_ID_HEADER] = request_id
            logger.info(
                "request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response
        finally:
            set_request_id(None)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
        expose_headers=[REQUEST_ID_HEADER],
    )

    app.include_router(api_router)

    return app


app = create_app()
