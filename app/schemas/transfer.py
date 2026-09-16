# app/schemas/transfer.py
from datetime import datetime
from decimal import Decimal
import uuid
from pydantic import BaseModel, ConfigDict, Field


class StockTransferCreate(BaseModel):
    product_id: uuid.UUID
    batch_id: uuid.UUID
    source_location_id: uuid.UUID
    destination_location_id: uuid.UUID
    quantity: Decimal = Field(..., gt=0, decimal_places=4)
    notes: str | None = None


class StockTransferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    product_id: uuid.UUID
    batch_id: uuid.UUID
    source_location_id: uuid.UUID
    destination_location_id: uuid.UUID
    quantity: Decimal
    status: str
    notes: str | None
    requested_by: uuid.UUID
    approved_by: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None


class InventoryAdjustmentCreate(BaseModel):
    inventory_id: uuid.UUID
    actual_quantity: Decimal = Field(..., ge=0, decimal_places=4)
    reason: str = Field(..., min_length=5, max_length=500)


class InventoryAdjustmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    inventory_id: uuid.UUID
    requested_quantity: Decimal
    actual_quantity: Decimal
    difference: Decimal
    reason: str
    status: str
    requested_by: uuid.UUID
    approved_by: uuid.UUID | None
    created_at: datetime
    approved_at: datetime | None