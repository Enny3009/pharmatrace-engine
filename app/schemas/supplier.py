from datetime import datetime
from enum import Enum
import uuid
from pydantic import BaseModel, ConfigDict, Field


class SupplierComplianceStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    UNDER_REVIEW = "UNDER_REVIEW"
    REJECTED = "REJECTED"


class SupplierCreate(BaseModel):
    supplier_code: str = Field(..., min_length=2, max_length=64, examples=["SUP-LONZA-01"])
    name: str = Field(..., min_length=2, max_length=255, examples=["Lonza Biologics AG"])


class SupplierUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    compliance_status: SupplierComplianceStatus | None = None
    status: str | None = None


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    supplier_code: str
    name: str
    status: str
    compliance_status: SupplierComplianceStatus
    created_at: datetime
    updated_at: datetime