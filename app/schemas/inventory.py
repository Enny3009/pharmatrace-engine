from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import uuid
from pydantic import BaseModel, ConfigDict, Field


class MovementTypeEnum(str, Enum):
    RECEIPT = "RECEIPT"
    ISSUE = "ISSUE"
    TRANSFER = "TRANSFER"
    ADJUSTMENT = "ADJUSTMENT"
    RETURN = "RETURN"
    DAMAGE = "DAMAGE"
    EXPIRY = "EXPIRY"
    QUARANTINE = "QUARANTINE"
    RELEASE = "RELEASE"


class StockIssueRequest(BaseModel):
    inventory_id: uuid.UUID
    quantity: Decimal = Field(..., gt=0, decimal_places=4, examples=[250.0000])
    reference_type: str = Field(
        ...,
        examples=["BATCH_ALLOCATION"],
        description="Reasoning category (BATCH_ALLOCATION, DISPATCH, CLINICAL_TRIAL)",
    )
    reference_id: uuid.UUID = Field(..., description="ID of the work order or dispatch requisition")
    reason: str = Field(..., min_length=5, max_length=500, examples=["Formulation release for Vaccine Lot 2026-B"])


class FEFOAllocationItem(BaseModel):
    inventory_id: uuid.UUID
    batch_id: uuid.UUID
    batch_number: str
    lot_number: str
    expiry_date: date
    storage_location_id: uuid.UUID
    storage_location_code: str
    quantity_available: Decimal
    allocated_quantity: Decimal


class FEFOResponse(BaseModel):
    product_id: uuid.UUID
    requested_quantity: Decimal
    total_allocated: Decimal
    fully_allocated: bool
    allocations: list[FEFOAllocationItem]


class InventoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    product_id: uuid.UUID
    batch_id: uuid.UUID
    storage_location_id: uuid.UUID
    quantity_on_hand: Decimal
    quantity_reserved: Decimal
    quantity_available: Decimal
    quantity_damaged: Decimal
    quantity_quarantined: Decimal
    version: int
    created_at: datetime
    updated_at: datetime


class StockMovementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    inventory_id: uuid.UUID
    product_id: uuid.UUID
    batch_id: uuid.UUID
    storage_location_id: uuid.UUID
    movement_type: MovementTypeEnum
    quantity: Decimal
    reference_type: str
    reference_id: uuid.UUID
    reason: str
    performed_by: uuid.UUID
    created_at: datetime