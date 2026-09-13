from datetime import datetime, timezone
import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import Role, User

# Bearer token extractor
security_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Resolves the authenticated user from the bearer token.
    Enforces active status and checks account lockout rules.
    """
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or token expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exception
        user_id_raw: str = payload.get("sub", "")
        user_id = uuid.UUID(user_id_raw)
    except (jwt.PyJWTError, ValueError):
        raise credentials_exception

    # Query user with eager-loaded role and organization
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.role),
            selectinload(User.organization),
        )
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    # Enforce 21 CFR Part 11 Account Lockout Check
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account locked due to excessive failed attempts until {user.locked_until.isoformat()}.",
        )

    return user


class RequireRole:
    """RBAC Dependency: Restricts endpoint access to specific authorized roles."""

    def __init__(self, allowed_roles: list[str]) -> None:
        self.allowed_roles = set(allowed_roles)

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.name not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Requires one of: {', '.join(sorted(self.allowed_roles))}",
            )
        return current_user