"""Schemas for the Phase 11 integrations API.

None of these expose credentials. Provider availability is a boolean derived
from backend env configuration; token values are never serialized.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.resources import IntegrationConnectionOut


class ProviderStatusOut(BaseModel):
    provider: str
    configured: bool


class IntegrationsListOut(BaseModel):
    connections: list[IntegrationConnectionOut]
    providers: list[ProviderStatusOut]


class IntegrationTestOut(BaseModel):
    provider: str
    configured: bool
    ok: bool
    detail: str
