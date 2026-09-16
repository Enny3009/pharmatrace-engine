# app/schemas/approval.py
from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, Field


class ApprovalDecisionRequest(BaseModel):
    comments: str = Field(..., min_length=3, max_length=500)


class ApprovalRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    request_type: str
    reference_type: str
    reference_id: uuid.UUID
    status: str
    comments: str | None
    requested_by: uuid.UUID
    assigned_to: uuid.UUID | None
    requested_at: datetime
    approved_at: datetime | None