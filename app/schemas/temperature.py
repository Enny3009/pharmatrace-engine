from datetime import datetime
from decimal import Decimal
import uuid
from pydantic import BaseModel, ConfigDict, Field


class TemperatureDeviceCreate(BaseModel):
    storage_location_id: uuid.UUID
    device_identifier: str = Field(..., min_length=3, max_length=128, examples=["IOT-TEMP-SENS-01"])
    api_key: str = Field(..., min_length=16, max_length=128, examples=["secret_sensor_key_2026_x8"])
    min_temperature: Decimal = Field(..., decimal_places=2, examples=[2.00])
    max_temperature: Decimal = Field(..., decimal_places=2, examples=[8.00])


class TemperatureDeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    storage_location_id: uuid.UUID
    device_identifier: str
    min_temperature: Decimal
    max_temperature: Decimal
    last_seen_at: datetime | None


class TemperatureIngestRequest(BaseModel):
    device_identifier: str
    api_key: str
    temperature: Decimal = Field(..., decimal_places=2, examples=[5.20])


class TemperatureRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    storage_location_id: uuid.UUID
    device_id: uuid.UUID
    temperature: Decimal
    status: str
    recorded_at: datetime


class TemperatureExcursionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    storage_location_id: uuid.UUID
    observed_temperature: Decimal
    allowed_minimum: Decimal
    allowed_maximum: Decimal
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int
    severity: str
    status: str