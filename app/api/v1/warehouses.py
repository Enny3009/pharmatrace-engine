import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.deps import RequireRole, get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.warehouse import StorageLocation, Warehouse
from app.schemas.warehouse import (
    StorageLocationCreate,
    StorageLocationRead,
    WarehouseCreate,
    WarehouseRead,
)

router = APIRouter(prefix="/warehouses", tags=["Warehouses & Locations"])

# RBAC guard: modifications require administrative or inventory roles
require_warehouse_manager = RequireRole(["OWNER", "ADMIN", "INVENTORY_MANAGER"])


@router.post(
    "",
    response_model=WarehouseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Facility Warehouse",
)
async def create_warehouse(
    payload: WarehouseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_warehouse_manager),
) -> Warehouse:
    # 1. Uniqueness check within the tenant
    stmt = select(Warehouse).where(
        Warehouse.organization_id == current_user.organization_id,
        Warehouse.code == payload.code.strip().upper(),
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Warehouse code '{payload.code}' already exists in your organization.",
        )

    warehouse = Warehouse(
        organization_id=current_user.organization_id,
        code=payload.code.strip().upper(),
        name=payload.name.strip(),
        temperature_controlled=payload.temperature_controlled,
        status="ACTIVE",
    )
    db.add(warehouse)
    await db.commit()

    # Re-fetch with eager loaded relationships
    stmt_load = (
        select(Warehouse)
        .where(Warehouse.id == warehouse.id)
        .options(selectinload(Warehouse.storage_locations))
    )
    res = await db.execute(stmt_load)
    return res.scalar_one()


@router.get(
    "",
    response_model=list[WarehouseRead],
    summary="List Tenant Warehouses",
)
async def list_warehouses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Warehouse]:
    stmt = (
        select(Warehouse)
        .where(Warehouse.organization_id == current_user.organization_id)
        .options(selectinload(Warehouse.storage_locations))
        .order_by(Warehouse.code.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get(
    "/{id}",
    response_model=WarehouseRead,
    summary="Get Warehouse by ID",
)
async def get_warehouse(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Warehouse:
    stmt = (
        select(Warehouse)
        .where(
            Warehouse.id == id,
            Warehouse.organization_id == current_user.organization_id,
        )
        .options(selectinload(Warehouse.storage_locations))
    )
    result = await db.execute(stmt)
    warehouse = result.scalar_one_or_none()
    if warehouse is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found.",
        )
    return warehouse


@router.post(
    "/{id}/locations",
    response_model=StorageLocationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add Storage Location to Warehouse",
)
async def create_storage_location(
    id: uuid.UUID,
    payload: StorageLocationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_warehouse_manager),
) -> StorageLocation:
    # 1. Verify warehouse belongs to user's organization
    stmt_wh = select(Warehouse).where(
        Warehouse.id == id,
        Warehouse.organization_id == current_user.organization_id,
    )
    wh_result = await db.execute(stmt_wh)
    warehouse = wh_result.scalar_one_or_none()
    if warehouse is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found.",
        )

    # 2. Check code uniqueness within warehouse
    stmt_loc = select(StorageLocation).where(
        StorageLocation.warehouse_id == warehouse.id,
        StorageLocation.code == payload.code.strip().upper(),
    )
    loc_result = await db.execute(stmt_loc)
    if loc_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Storage location code '{payload.code}' already exists in this warehouse.",
        )

    location = StorageLocation(
        warehouse_id=warehouse.id,
        code=payload.code.strip().upper(),
        zone=payload.zone.strip().upper(),
        shelf=payload.shelf.strip().upper(),
        bin=payload.bin.strip().upper(),
        temperature_zone=payload.temperature_zone.value,
        capacity=payload.capacity,
        status="ACTIVE",
    )
    db.add(location)
    await db.commit()
    await db.refresh(location)
    return location


@router.get(
    "/{id}/locations",
    response_model=list[StorageLocationRead],
    summary="List Storage Locations for Warehouse",
)
async def list_warehouse_locations(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[StorageLocation]:
    # 1. Verify warehouse ownership
    stmt_wh = select(Warehouse).where(
        Warehouse.id == id,
        Warehouse.organization_id == current_user.organization_id,
    )
    wh_result = await db.execute(stmt_wh)
    if wh_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found.",
        )

    stmt = (
        select(StorageLocation)
        .where(StorageLocation.warehouse_id == id)
        .order_by(StorageLocation.code.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())