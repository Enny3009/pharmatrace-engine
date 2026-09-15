from datetime import datetime
from decimal import Decimal
from enum import Enum
import uuid
from pydantic import BaseModel, ConfigDict, Field


class POStatusEnum(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class POItemCreate(BaseModel):
    product_id: uuid.UUID
    ordered_quantity: Decimal = Field(..., gt=0, decimal_places=4, examples=[500.0000])
    unit_cost: Decimal = Field(..., gt=0, decimal_places=2, examples=[125.50])


class POItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    ordered_quantity: Decimal
    received_quantity: Decimal
    unit_cost: Decimal


class POCreate(BaseModel):
    supplier_id: uuid.UUID
    po_number: str = Field(..., min_length=3, max_length=64, examples=["PO-2026-00891"])
    items: list[POItemCreate] = Field(..., min_length=1)


class PORead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    supplier_id: uuid.UUID
    po_number: str
    status: POStatusEnum
    total: Decimal
    created_by: uuid.UUID
    approved_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    items: list[POItemRead] = []