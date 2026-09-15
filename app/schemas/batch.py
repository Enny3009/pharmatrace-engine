from datetime import date, datetime
from decimal import Decimal
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.signature import ElectronicSignatureRead, SignatureMeaningEnum


class BatchReleaseRequest(BaseModel):
    reauth_password: str = Field(..., min_length=1, description="Dual-Factor Argon2id Plaintext Password Re-authentication")
    signature_meaning: SignatureMeaningEnum = Field(..., examples=["FINAL_RELEASE"])
    release_notes: str = Field(..., min_length=5, max_length=500, examples=["Batch quality tests passed. Release authorized."])


class BatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    product_id: uuid.UUID
    supplier_id: uuid.UUID | None
    batch_number: str
    lot_number: str
    manufacturing_date: date
    expiry_date: date
    quantity_received: Decimal
    quantity_available: Decimal
    quantity_quarantined: Decimal
    quality_status: str
    release_status: str
    created_at: datetime


class BatchReleaseResponse(BaseModel):
    batch: BatchRead
    signature: ElectronicSignatureRead