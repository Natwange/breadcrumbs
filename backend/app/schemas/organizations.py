import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrganizationSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    timezone: str
    default_severity: str | None
    preferences: dict | None
    notes: str | None


class OrganizationSettingsUpdate(BaseModel):
    timezone: str | None = None
    default_severity: str | None = None
    preferences: dict | None = None
    notes: str | None = None


class OrganizationMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    role: str
    status: str
    created_at: datetime


class InvitationCreate(BaseModel):
    email: str
    role: str = "member"


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str
    status: str
    token: str
    expires_at: datetime | None
    created_at: datetime


class MemberRoleUpdate(BaseModel):
    role: str
