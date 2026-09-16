# app/api/v1/notifications.py
from datetime import datetime, timezone
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.notification import NotificationRead

router = APIRouter(prefix="/notifications", tags=["Regulatory Alerts & Notifications"])


@router.get(
    "",
    response_model=PaginatedResponse[NotificationRead],
    summary="List User Notifications",
)
async def list_notifications(
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[NotificationRead]:
    base_query = select(Notification).where(
        Notification.organization_id == current_user.organization_id,
        Notification.user_id == current_user.id,
    )
    if unread_only:
        base_query = base_query.where(Notification.read_at.is_(None))

    count_stmt = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        base_query.order_by(Notification.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list((await db.execute(stmt)).scalars().all())

    return PaginatedResponse(
        items=[NotificationRead.model_validate(it) for it in items],
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if total > 0 else 0,
    )


@router.post(
    "/{id}/read",
    response_model=NotificationRead,
    summary="Mark Notification as Read",
)
async def mark_read(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Notification:
    stmt = (
        select(Notification)
        .where(
            Notification.id == id,
            Notification.user_id == current_user.id,
        )
    )
    notif = (await db.execute(stmt)).scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")

    notif.read_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(notif)
    return notif


@router.post(
    "/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark All Notifications Read",
)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    stmt = (
        update(Notification)
        .where(
            Notification.organization_id == current_user.organization_id,
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(timezone.utc))
    )
    await db.execute(stmt)
    await db.commit()