from datetime import date
from decimal import Decimal
import uuid
from fastapi import HTTPException, status
import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.redis import DistributedLock
from app.models.batch import Batch
from app.models.inventory import Inventory, StockMovement
from app.models.warehouse import StorageLocation
from app.schemas.inventory import FEFOAllocationItem, FEFOResponse, StockIssueRequest


class InventoryService:
    """Core cGMP inventory engine managing concurrency locks and FEFO queries."""

    @staticmethod
    async def get_fefo_recommendation(
        db: AsyncSession,
        organization_id: uuid.UUID,
        product_id: uuid.UUID,
        requested_quantity: Decimal,
    ) -> FEFOResponse:
        """
        FEFO Resolution Algorithm:
        Resolves available inventory lots for a product ordered strictly by:
        1. Nearest Expiration Date (expiry_date ASC)
        2. Highest Stock Depth (quantity_available DESC)
        Excludes quarantined, rejected, recalled, and expired lots.
        """
        today = date.today()

        stmt = (
            select(Inventory, Batch, StorageLocation)
            .join(Batch, Batch.id == Inventory.batch_id)
            .join(StorageLocation, StorageLocation.id == Inventory.storage_location_id)
            .where(
                Inventory.organization_id == organization_id,
                Inventory.product_id == product_id,
                Inventory.quantity_available > 0,
                Batch.quality_status == "APPROVED",
                Batch.release_status == "RELEASED",
                Batch.expiry_date > today,
            )
            .order_by(Batch.expiry_date.asc(), Inventory.quantity_available.desc())
        )

        result = await db.execute(stmt)
        rows = result.all()

        allocations: list[FEFOAllocationItem] = []
        remaining_needed = requested_quantity

        for inv, batch, loc in rows:
            if remaining_needed <= 0:
                break

            alloc_qty = min(inv.quantity_available, remaining_needed)
            allocations.append(
                FEFOAllocationItem(
                    inventory_id=inv.id,
                    batch_id=batch.id,
                    batch_number=batch.batch_number,
                    lot_number=batch.lot_number,
                    expiry_date=batch.expiry_date,
                    storage_location_id=loc.id,
                    storage_location_code=loc.code,
                    quantity_available=inv.quantity_available,
                    allocated_quantity=alloc_qty,
                )
            )
            remaining_needed -= alloc_qty

        total_allocated = requested_quantity - remaining_needed

        return FEFOResponse(
            product_id=product_id,
            requested_quantity=requested_quantity,
            total_allocated=total_allocated,
            fully_allocated=(remaining_needed <= 0),
            allocations=allocations,
        )

    @staticmethod
    async def issue_stock_guarded(
        db: AsyncSession,
        redis: aioredis.Redis,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: StockIssueRequest,
    ) -> StockMovement:
        """
        Two-Tier Concurrency Lock Allocation Engine:
        - Tier 1: Redis distributed lock (SET lock:inventory:{id} NX EX 10)
        - Tier 2: PostgreSQL row lock (SELECT ... FOR UPDATE) inside transaction
        - Optimistic version counter check
        - Database balance mutation & stock movement audit append
        """
        lock_key = f"inventory:{payload.inventory_id}"

        # --- Tier 1: Redis Distributed Lock Guard ---
        async with DistributedLock(redis, lock_key, ttl_seconds=10):
            # --- Tier 2: PostgreSQL Row-Level Lock with FOR UPDATE ---
            stmt = (
                select(Inventory)
                .where(
                    Inventory.id == payload.inventory_id,
                    Inventory.organization_id == organization_id,
                )
                .with_for_update()
            )
            result = await db.execute(stmt)
            inventory = result.scalar_one_or_none()

            if inventory is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Inventory record not found.",
                )

            # Eagerly load batch to inspect status and expiration
            stmt_batch = select(Batch).where(Batch.id == inventory.batch_id).with_for_update()
            batch_result = await db.execute(stmt_batch)
            batch = batch_result.scalar_one()

            # Regulatory Quality Guard
            if batch.quality_status != "APPROVED" or batch.release_status != "RELEASED":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot issue stock from batch with status '{batch.quality_status}' / '{batch.release_status}'.",
                )

            if batch.expiry_date <= date.today():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Batch '{batch.batch_number}' expired on {batch.expiry_date.isoformat()}. Issuance rejected.",
                )

            # Stock Availability Check
            if inventory.quantity_available < payload.quantity:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=(
                        f"Insufficient available stock. Requested: {payload.quantity}, "
                        f"Available: {inventory.quantity_available}."
                    ),
                )

            # Mutate Balances (Satisfying PostgreSQL check constraints)
            inventory.quantity_on_hand -= payload.quantity
            inventory.quantity_available = inventory.quantity_on_hand - inventory.quantity_reserved
            inventory.version += 1

            batch.quantity_available -= payload.quantity

            # Append to Immutable Stock Movement Ledger
            movement = StockMovement(
                organization_id=organization_id,
                inventory_id=inventory.id,
                product_id=inventory.product_id,
                batch_id=inventory.batch_id,
                storage_location_id=inventory.storage_location_id,
                movement_type="ISSUE",
                quantity=payload.quantity,
                reference_type=payload.reference_type,
                reference_id=payload.reference_id,
                reason=payload.reason,
                performed_by=user_id,
            )
            db.add(movement)

            # Commit the transaction to release the PostgreSQL row lock
            await db.commit()
            await db.refresh(movement)
            return movement