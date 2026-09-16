# app/api/v1/transfers.py
import uuid
from fastapi import APIRouter, Depends, Query, status
import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import RequireRole, get_current_user
from app.core.database import get_db
from app.core.redis import get_redis
from app.models.transfer import StockTransfer
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.transfer import StockTransferCreate, StockTransferRead
from app.services.transfer_service import TransferService

router = APIRouter(prefix="/transfers", tags=["Warehouse Stock Transfers"])

require_warehouse = RequireRole(["OWNER", "ADMIN", "WAREHOUSE_STAFF", "INVENTORY_MANAGER"])


@router.post(
    "",
    response_model=StockTransferRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Stock Transfer Request",
)
async def create_transfer(
    payload: StockTransferCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_warehouse),
) -> StockTransfer:
    return await TransferService.create_transfer(
        db=db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        payload=payload,
    )


@router.post(
    "/{id}/complete",
    response_model=StockTransferRead,
    summary="Execute and Materialize Stock Transfer with Atomic Row Locks",
)
async def complete_transfer(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    current_user: User = Depends(require_warehouse),
) -> StockTransfer:
    return await TransferService.complete_transfer(
        db=db,
        redis=redis,
        organization_id=current_user.organization_id,
        transfer_id=id,
        user_id=current_user.id,
    )


@router.get(
    "",
    response_model=PaginatedResponse[StockTransferRead],
    summary="List Organization Transfers",
)
async def list_transfers(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[StockTransferRead]:
    count_stmt = (
        select(func.count(StockTransfer.id))
        .where(StockTransfer.organization_id == current_user.organization_id)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(StockTransfer)
        .where(StockTransfer.organization_id == current_user.organization_id)
        .order_by(StockTransfer.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list((await db.execute(stmt)).scalars().all())

    return PaginatedResponse(
        items=[StockTransferRead.model_validate(it) for it in items],
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if total > 0 else 0,
    )