import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.deps import RequireRole, get_current_user
from app.core.database import get_db
from app.core.security import hash_password
from app.models.user import Role, User
from app.schemas.auth import RoleRead
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/users", tags=["User Management & Roles"])

require_admin = RequireRole(["OWNER", "ADMIN"])


@router.get(
    "/roles",
    response_model=list[RoleRead],
    summary="List Organization Roles",
)
async def list_roles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Role]:
    stmt = (
        select(Role)
        .where(Role.organization_id == current_user.organization_id)
        .order_by(Role.name.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Organization User (Admin Only)",
)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> User:
    # 1. Check email uniqueness within the organization
    stmt_email = select(User).where(
        User.organization_id == current_user.organization_id,
        User.email == payload.email.lower().strip(),
    )
    if (await db.execute(stmt_email)).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{payload.email}' already exists.",
        )

    # 2. Resolve Role
    stmt_role = select(Role).where(
        Role.organization_id == current_user.organization_id,
        Role.name == payload.role_name.strip().upper(),
    )
    role = (await db.execute(stmt_role)).scalar_one_or_none()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{payload.role_name}' does not exist in your organization.",
        )

    user = User(
        organization_id=current_user.organization_id,
        role_id=role.id,
        email=payload.email.lower().strip(),
        password_hash=hash_password(payload.password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        is_active=True,
    )
    db.add(user)
    await db.commit()

    stmt_load = (
        select(User)
        .where(User.id == user.id)
        .options(selectinload(User.role))
    )
    return (await db.execute(stmt_load)).scalar_one()


@router.get(
    "",
    response_model=list[UserRead],
    summary="List Organization Users",
)
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[User]:
    stmt = (
        select(User)
        .where(User.organization_id == current_user.organization_id)
        .options(selectinload(User.role))
        .order_by(User.first_name.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())