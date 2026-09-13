from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TenantRegisterRequest(BaseModel):
    # Organization Details
    organization_name: str = Field(..., min_length=2, max_length=255)
    legal_name: str = Field(..., min_length=2, max_length=255)
    license_number: str = Field(
        ...,
        min_length=3,
        max_length=128,
        description="FDA/DEA establishment identifier or state license",
    )

    # Initial Admin User Details
    admin_email: EmailStr
    admin_password: str = Field(..., min_length=12, max_length=128)
    admin_first_name: str = Field(..., min_length=1, max_length=100)
    admin_last_name: str = Field(..., min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    legal_name: str
    license_number: str
    genesis_hash: str
    status: str
    created_at: datetime


class UserProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    is_active: bool
    organization_id: uuid.UUID
    role: RoleRead
    organization: OrganizationRead