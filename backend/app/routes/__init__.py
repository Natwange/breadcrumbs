from fastapi import APIRouter

from app.routes import (
    alerts,
    alerts_api,
    auth,
    embeddings_api,
    health,
    incidents,
    integrations,
    integrations_api,
    investigation_api,
    investigation_runs,
    knowledge,
    knowledge_api,
    organizations,
    postmortem_api,
    webhooks_api,
)

api_router = APIRouter()

# Public
api_router.include_router(health.router)
api_router.include_router(webhooks_api.router)

# Authenticated
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(alerts.router)
api_router.include_router(alerts_api.router)
api_router.include_router(incidents.router)
api_router.include_router(knowledge.router)
api_router.include_router(knowledge_api.router)
api_router.include_router(investigation_runs.router)
api_router.include_router(investigation_api.router)
api_router.include_router(embeddings_api.router)
api_router.include_router(postmortem_api.router)
api_router.include_router(integrations.router)
api_router.include_router(integrations_api.router)
