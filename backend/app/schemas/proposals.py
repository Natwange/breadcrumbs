import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProposalCreate(BaseModel):
    proposal_type: str
    payload: dict | None = None
    confidence: float | None = None


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    proposal_type: str
    status: str
    confidence: float | None
    proposed_by: uuid.UUID | None
    reviewed_by: uuid.UUID | None
    created_at: datetime
