from datetime import datetime
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict


class AuditLedgerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID
    old_values: dict[str, Any] | None
    new_values: dict[str, Any]
    previous_hash: str
    current_hash: str
    created_at: datetime


class IntegrityVerificationResponse(BaseModel):
    verified: bool
    total_records_verified: int | None = None
    tampered_row_id: int | None = None
    action: str | None = None
    error: str | None = None
    genesis_hash: str | None = None
    latest_head_hash: str | None = None