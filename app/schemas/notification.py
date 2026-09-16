# app/schemas/notification.py
from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    type: str
    title: str
    message: str
    severity: str
    read_at: datetime | None
    created_at: datetime