from datetime import datetime
from decimal import Decimal
from enum import Enum
import uuid
from pydantic import BaseModel, ConfigDict, Field


class TemperatureZoneEnum(str, Enum):
    AMBIENT_15_25C = "AMBIENT_15_25C"
    REFRIGERATED_2_8C = "REFRIGERATED_2_8C"
    FROZEN_MINUS_20C = "FROZEN_MINUS_20C"
    ULTRA_LOW_MINUS_80C = "ULTRA_LOW_MINUS_80C"
    CRYO_LN2 = "CRYO_LN2"


class StorageLocationCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=64, examples=["CRYO-Z1-S04-B02"])
    zone: str = Field(..., min_length=1, max_length=32, examples=["ZONE-A"])
    shelf: str = Field(..., min_length=1, max_length=32, examples=["SHELF-04"])
    bin: str = Field(..., min_length=1, max_length=32, examples=["BIN-02"])
    temperature_zone: TemperatureZoneEnum
    capacity: Decimal = Field(..., gt=0, decimal_places=2, examples=[1000.00])


class StorageLocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    warehouse_id: uuid.UUID
    code: str
    zone: str
    shelf: str
    bin: str
    temperature_zone: TemperatureZoneEnum
    capacity: Decimal
    status: str
    created_at: datetime
    updated_at: datetime


class WarehouseCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=64, examples=["WH-BOS-01"])
    name: str = Field(..., min_length=2, max_length=255, examples=["Boston Biologics Central"])
    temperature_controlled: bool = True


class WarehouseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    code: str
    name: str
    temperature_controlled: bool
    status: str
    created_at: datetime
    updated_at: datetime
    storage_locations: list[StorageLocationRead] = []