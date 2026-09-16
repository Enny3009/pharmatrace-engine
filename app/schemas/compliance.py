# app/schemas/compliance.py
from datetime import datetime
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field


class ComplianceRuleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=128)
    rule_type: str = Field(..., examples=["TEMPERATURE_THRESHOLD", "EXPIRY_WINDOW", "ADJUSTMENT_LIMIT"])
    configuration: dict[str, Any]
    enabled: bool = True


class ComplianceRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    rule_type: str
    configuration: dict[str, Any]
    enabled: bool


class ComplianceIncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    incident_type: str
    severity: str
    reference_type: str
    reference_id: uuid.UUID
    description: str
    status: str
    assigned_to: uuid.UUID | None
    resolved_by: uuid.UUID | None
    created_at: datetime


class IncidentResolutionRequest(BaseModel):
    resolution_notes: str = Field(..., min_length=5, max_length=1000)