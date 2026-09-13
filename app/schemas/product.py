from datetime import datetime
from decimal import Decimal
from enum import Enum
import uuid
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DosageFormEnum(str, Enum):
    VIAL = "VIAL"
    TABLET = "TABLET"
    AMPOULE = "AMPOULE"
    SUSPENSION = "SUSPENSION"
    PREFILLED_SYRINGE = "PREFILLED_SYRINGE"


class ProductCreate(BaseModel):
    sku: str = Field(..., min_length=3, max_length=100, examples=["SKU-VAX-001"])
    name: str = Field(..., min_length=2, max_length=255, examples=["Novis-mRNA Spike Antigen"])
    generic_name: str | None = Field(None, max_length=255)
    dosage_form: DosageFormEnum
    storage_type: str = Field(..., min_length=2, max_length=32, examples=["REFRIGERATED_2_8C"])
    min_temperature: Decimal = Field(..., decimal_places=2, examples=[2.00])
    max_temperature: Decimal = Field(..., decimal_places=2, examples=[8.00])
    requires_temperature_monitoring: bool = True
    reorder_level: Decimal = Field(..., ge=0, decimal_places=4, examples=[500.0000])

    @model_validator(mode="after")
    def validate_temperature_bounds(self) -> "ProductCreate":
        if self.min_temperature > self.max_temperature:
            raise ValueError("min_temperature cannot be strictly greater than max_temperature")
        return self


class ProductUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    generic_name: str | None = None
    storage_type: str | None = None
    min_temperature: Decimal | None = None
    max_temperature: Decimal | None = None
    requires_temperature_monitoring: bool | None = None
    reorder_level: Decimal | None = None

    @model_validator(mode="after")
    def validate_temperature_bounds(self) -> "ProductUpdate":
        if (
            self.min_temperature is not None
            and self.max_temperature is not None
            and self.min_temperature > self.max_temperature
        ):
            raise ValueError("min_temperature cannot be strictly greater than max_temperature")
        return self


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    sku: str
    name: str
    generic_name: str | None
    dosage_form: DosageFormEnum
    storage_type: str
    min_temperature: Decimal
    max_temperature: Decimal
    requires_temperature_monitoring: bool
    reorder_level: Decimal
    created_at: datetime
    updated_at: datetime