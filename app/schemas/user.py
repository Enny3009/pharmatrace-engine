from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.schemas.auth import RoleRead


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    role_name: str = Field(
        ...,
        description="Must be one of: ADMIN, QA_OFFICER, LAB_TECHNICIAN, COMPLIANCE_OFFICER, WAREHOUSE_STAFF",
        examples=["QA_OFFICER"],
    )


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    is_active: bool
    role: RoleRead
    created_at: datetime