# app/api/v1/adjustments.py
import uuid
from fastapi import APIRouter, Depends, Query, status
import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import RequireRole, get_current_user
from app.core.database import get_db
from app.core.redis import get_redis
from app.models.transfer import InventoryAdjustment
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.transfer import InventoryAdjustmentCreate, InventoryAdjustmentRead
from app.services.adjustment_service import AdjustmentService

router = APIRouter(prefix="/inventory/adjustments", tags=["Inventory Adjustments"])

require_staff = RequireRole(["OWNER", "ADMIN", "INVENTORY_MANAGER", "WAREHOUSE_STAFF"])
require_approver = RequireRole(["OWNER", "ADMIN", "INVENTORY_MANAGER", "QA_OFFICER"])


@router.post(
    "",
    response_model=InventoryAdjustmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Request Stock Level Adjustment",
)
async def request_adjustment(
    payload: InventoryAdjustmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_staff),
) -> InventoryAdjustment:
    return await AdjustmentService.request_adjustment(
        db=db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        payload=payload,
    )


@router.post(
    "/{id}/approve",
    response_model=InventoryAdjustmentRead,
    summary="Approve and Execute Inventory Adjustment (Enforces SoD)",
)
async def approve_adjustment(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    current_user: User = Depends(require_approver),
) -> InventoryAdjustment:
    return await AdjustmentService.execute_adjustment(
        db=db,
        redis=redis,
        organization_id=current_user.organization_id,
        adjustment_id=id,
        approver_id=current_user.id,
    )


@router.get(
    "",
    response_model=PaginatedResponse[InventoryAdjustmentRead],
    summary="List Inventory Adjustments",
)
async def list_adjustments(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[InventoryAdjustmentRead]:
    count_stmt = select(func.count(InventoryAdjustment.id)).where(
        InventoryAdjustment.organization_id == current_user.organization_id
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(InventoryAdjustment)
        .where(InventoryAdjustment.organization_id == current_user.organization_id)
        .order_by(InventoryAdjustment.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list((await db.execute(stmt)).scalars().all())

    return PaginatedResponse(
        items=[InventoryAdjustmentRead.model_validate(it) for it in items],
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if total > 0 else 0,
    )