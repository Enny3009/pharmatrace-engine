# app/api/v1/inventory.py
from decimal import Decimal
import uuid
from fastapi import APIRouter, Depends, Query, status
import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import RequireRole, get_current_user
from app.core.database import get_db
from app.core.redis import get_redis
from app.models.inventory import Inventory, StockMovement
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.inventory import (
    FEFOResponse,
    InventoryRead,
    StockIssueRequest,
    StockMovementRead,
)
from app.services.inventory_service import InventoryService

router = APIRouter(tags=["Physical Inventory & Stock Allocations"])

require_inventory_staff = RequireRole(["OWNER", "ADMIN", "WAREHOUSE_STAFF", "LAB_TECHNICIAN"])


@router.get(
    "/inventory",
    response_model=PaginatedResponse[InventoryRead],
    summary="List Organization Physical Stock Matrix",
)
async def list_inventory(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[InventoryRead]:
    count_stmt = select(func.count(Inventory.id)).where(
        Inventory.organization_id == current_user.organization_id
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Inventory)
        .where(Inventory.organization_id == current_user.organization_id)
        .order_by(Inventory.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list((await db.execute(stmt)).scalars().all())

    return PaginatedResponse(
        items=[InventoryRead.model_validate(it) for it in items],
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if total > 0 else 0,
    )


@router.get(
    "/products/{id}/fefo",
    response_model=FEFOResponse,
    summary="FEFO Stock Recommendation Engine",
)
async def get_fefo_recommendation(
    id: uuid.UUID,
    quantity: Decimal = Query(..., gt=0, description="Desired allocation quantity"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FEFOResponse:
    return await InventoryService.get_fefo_recommendation(
        db=db,
        organization_id=current_user.organization_id,
        product_id=id,
        requested_quantity=quantity,
    )


@router.post(
    "/stock-movements/issue",
    response_model=StockMovementRead,
    status_code=status.HTTP_201_CREATED,
    summary="Issue Stock (Guarded by Two-Tier Concurrency Lock)",
)
async def issue_stock(
    payload: StockIssueRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    current_user: User = Depends(require_inventory_staff),
) -> StockMovement:
    return await InventoryService.issue_stock_guarded(
        db=db,
        redis=redis,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        payload=payload,
    )


@router.get(
    "/stock-movements",
    response_model=PaginatedResponse[StockMovementRead],
    summary="List Immutable Stock Movements Audit Trail",
)
async def list_stock_movements(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[StockMovementRead]:
    count_stmt = select(func.count(StockMovement.id)).where(
        StockMovement.organization_id == current_user.organization_id
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(StockMovement)
        .where(StockMovement.organization_id == current_user.organization_id)
        .order_by(StockMovement.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list((await db.execute(stmt)).scalars().all())

    return PaginatedResponse(
        items=[StockMovementRead.model_validate(it) for it in items],
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if total > 0 else 0,
    )