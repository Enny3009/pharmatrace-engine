from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import uuid
from pydantic import BaseModel, ConfigDict, Field


class ReceiptStatusEnum(str, Enum):
    PENDING = "PENDING"
    INSPECTED = "INSPECTED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class InspectionResultEnum(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    CONDITIONAL = "CONDITIONAL"


class GoodsReceiptItemCreate(BaseModel):
    product_id: uuid.UUID
    storage_location_id: uuid.UUID
    quantity_received: Decimal = Field(..., gt=0, decimal_places=4, examples=[500.0000])


class GoodsReceiptItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    storage_location_id: uuid.UUID
    quantity_received: Decimal
    quantity_accepted: Decimal
    quantity_rejected: Decimal


class GoodsReceiptCreate(BaseModel):
    purchase_order_id: uuid.UUID
    warehouse_id: uuid.UUID
    receipt_number: str = Field(..., min_length=3, max_length=64, examples=["GR-2026-00441"])
    items: list[GoodsReceiptItemCreate] = Field(..., min_length=1)


class InspectionCreate(BaseModel):
    result: InspectionResultEnum
    notes: str | None = Field(None, max_length=1000)
    # Batch formulation parameters required upon passing inspection
    batch_number: str = Field(..., min_length=2, max_length=128, examples=["BATCH-SPK-2026-A1"])
    lot_number: str = Field(..., min_length=2, max_length=128, examples=["LOT-LONZA-992"])
    manufacturing_date: date
    expiry_date: date


class InspectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    goods_receipt_id: uuid.UUID
    inspector_id: uuid.UUID
    result: InspectionResultEnum
    notes: str | None
    created_at: datetime


class GoodsReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    purchase_order_id: uuid.UUID
    warehouse_id: uuid.UUID
    receipt_number: str
    status: ReceiptStatusEnum
    received_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    items: list[GoodsReceiptItemRead] = []
    inspections: list[InspectionRead] = []