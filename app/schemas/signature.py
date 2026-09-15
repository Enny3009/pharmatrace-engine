from datetime import datetime
from enum import Enum
import uuid
from pydantic import BaseModel, ConfigDict, Field


class SignatureMeaningEnum(str, Enum):
    AUTHORED = "AUTHORED"
    COMPOUNDED = "COMPOUNDED"
    VERIFIED = "VERIFIED"
    QC_APPROVED = "QC_APPROVED"
    FINAL_RELEASE = "FINAL_RELEASE"
    QUARANTINE_HOLD = "QUARANTINE_HOLD"


class ElectronicSignatureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    user_id: uuid.UUID
    signature_meaning: SignatureMeaningEnum
    snapshot_payload_hash: str
    signature_timestamp: datetime
    ip_address: str