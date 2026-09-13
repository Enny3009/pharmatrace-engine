from datetime import datetime, timedelta, timezone
import hashlib
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.organization import Organization
from app.models.user import Role, User
from app.schemas.auth import (
    LoginRequest,
    TenantRegisterRequest,
    TokenResponse,
    UserProfileRead,
)

router = APIRouter(prefix="/auth", tags=["Authentication & Tenant Provisioning"])

DEFAULT_ROLES = [
    ("OWNER", "Enterprise Tenant Owner with full administrative control"),
    ("ADMIN", "System Administrator managing configurations and users"),
    ("QA_OFFICER", "Quality Assurance Officer authorized for 21 CFR batch releases"),
    ("LAB_TECHNICIAN", "Laboratory Technician handling formulation and execution"),
    ("COMPLIANCE_OFFICER", "Regulatory Compliance Auditor with ALCOA+ oversight"),
    ("WAREHOUSE_STAFF", "Operations personnel managing physical stock movements"),
]


@router.post(
    "/register",
    response_model=UserProfileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Onboard Organization and Primary Admin",
)
async def register_tenant(
    payload: TenantRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> User:
    # 1. Check uniqueness of license_number
    stmt_license = select(Organization).where(
        Organization.license_number == payload.license_number
    )
    result = await db.execute(stmt_license)
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An organization with this regulatory license number is already registered.",
        )

    # 2. Compute Genesis Hash for Organization Audit Chain
    genesis_payload = f"{payload.license_number}:{payload.legal_name}:{datetime.now(timezone.utc).isoformat()}:{uuid.uuid4()}"
    genesis_hash = hashlib.sha256(genesis_payload.encode()).hexdigest()

    # 3. Create Organization
    org = Organization(
        name=payload.organization_name,
        legal_name=payload.legal_name,
        license_number=payload.license_number,
        genesis_hash=genesis_hash,
        status="ACTIVE",
    )
    db.add(org)
    await db.flush()  # Populates org.id

    # 4. Provision default roles for this tenant
    created_roles: dict[str, Role] = {}
    for role_name, role_desc in DEFAULT_ROLES:
        role = Role(
            organization_id=org.id,
            name=role_name,
            description=role_desc,
        )
        db.add(role)
        created_roles[role_name] = role

    await db.flush()

    # 5. Create Root Admin User assigned to OWNER role
    admin_user = User(
        organization_id=org.id,
        role_id=created_roles["OWNER"].id,
        email=payload.admin_email.lower().strip(),
        password_hash=hash_password(payload.admin_password),
        first_name=payload.admin_first_name,
        last_name=payload.admin_last_name,
        is_active=True,
    )
    db.add(admin_user)
    await db.commit()

    # Query back user with relationships loaded
    stmt_user = (
        select(User)
        .where(User.id == admin_user.id)
        .options(selectinload(User.role), selectinload(User.organization))
    )
    res = await db.execute(stmt_user)
    return res.scalar_one()


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate User with Lockout Protection (§ 11.300)",
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    stmt = (
        select(User)
        .where(User.email == payload.email.lower().strip())
        .options(selectinload(User.role))
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if user is None:
        # Constant-time mitigation against timing attacks
        verify_password("fake_password", "$argon2id$v=19$m=65536,t=3,p=4$dGVzdHNhbHQ$dGVzdGhhc2g")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    # Check if locked
    if user.locked_until and user.locked_until > now:
        remaining = int((user.locked_until - now).total_seconds() / 60)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account locked due to 5 consecutive failed attempts. Try again in {remaining} minute(s).",
        )

    # Verify Password
    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.locked_until = now + timedelta(minutes=15)
            user.failed_login_attempts = 0
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account has been locked for 15 minutes due to 5 consecutive failed authentication attempts.",
            )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    # Successful login: reset failed attempts
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    await db.commit()

    claims = {
        "org_id": str(user.organization_id),
        "role": user.role.name,
        "email": user.email,
    }
    access_token = create_access_token(subject=str(user.id), claims=claims)
    refresh_token = create_refresh_token(subject=str(user.id), claims=claims)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get(
    "/me",
    response_model=UserProfileRead,
    summary="Get Authenticated Identity and Tenant Context",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user