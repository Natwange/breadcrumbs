from fastapi import APIRouter

from app.routes import (
    alerts,
    auth,
    health,
    incidents,
    integrations,
    investigation_runs,
    knowledge,
    organizations,
)

api_router = APIRouter()

# Public
api_router.include_router(health.router)

# Authenticated
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(alerts.router)
api_router.include_router(incidents.router)
api_router.include_router(knowledge.router)
api_router.include_router(investigation_runs.router)
api_router.include_router(integrations.router)
