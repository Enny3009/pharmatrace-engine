# app/services/transfer_service.py
from datetime import datetime, timezone
from decimal import Decimal
import uuid
from fastapi import HTTPException, status
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.context import get_request_id
from app.core.redis import DistributedLock
from app.models.batch import Batch
from app.models.inventory import Inventory, StockMovement
from app.models.transfer import StockTransfer
from app.schemas.transfer import StockTransferCreate
from app.services.audit_service import AuditService


class TransferService:
    @classmethod
    async def create_transfer(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: StockTransferCreate,
    ) -> StockTransfer:
        if payload.source_location_id == payload.destination_location_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and destination locations must be distinct.",
            )

        transfer = StockTransfer(
            organization_id=organization_id,
            product_id=payload.product_id,
            batch_id=payload.batch_id,
            source_location_id=payload.source_location_id,
            destination_location_id=payload.destination_location_id,
            quantity=payload.quantity,
            notes=payload.notes,
            requested_by=user_id,
            status="PENDING",
        )
        db.add(transfer)
        await db.commit()
        await db.refresh(transfer)
        return transfer

    @classmethod
    async def complete_transfer(
        cls,
        db: AsyncSession,
        redis: aioredis.Redis,
        organization_id: uuid.UUID,
        transfer_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> StockTransfer:
        stmt = (
            select(StockTransfer)
            .where(
                StockTransfer.id == transfer_id,
                StockTransfer.organization_id == organization_id,
            )
            .with_for_update()
        )
        transfer = (await db.execute(stmt)).scalar_one_or_none()
        if not transfer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer not found.")

        if transfer.status in ("COMPLETED", "CANCELLED"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transfer cannot be executed from state {transfer.status}.",
            )

        # Multi-location atomic execution guarded by ordered distributed locks
        lock_keys = sorted([
            f"location:{transfer.source_location_id}",
            f"location:{transfer.destination_location_id}",
        ])

        async with DistributedLock(redis, lock_keys[0]), DistributedLock(redis, lock_keys[1]):
            # 1. Fetch Source Inventory
            stmt_src = (
                select(Inventory)
                .where(
                    Inventory.organization_id == organization_id,
                    Inventory.product_id == transfer.product_id,
                    Inventory.batch_id == transfer.batch_id,
                    Inventory.storage_location_id == transfer.source_location_id,
                )
                .with_for_update()
            )
            src_inv = (await db.execute(stmt_src)).scalar_one_or_none()

            if not src_inv or src_inv.quantity_available < transfer.quantity:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Insufficient available stock at source location to complete transfer.",
                )

            # 2. Fetch or initialize Destination Inventory
            stmt_dst = (
                select(Inventory)
                .where(
                    Inventory.organization_id == organization_id,
                    Inventory.product_id == transfer.product_id,
                    Inventory.batch_id == transfer.batch_id,
                    Inventory.storage_location_id == transfer.destination_location_id,
                )
                .with_for_update()
            )
            dst_inv = (await db.execute(stmt_dst)).scalar_one_or_none()

            if not dst_inv:
                dst_inv = Inventory(
                    organization_id=organization_id,
                    product_id=transfer.product_id,
                    batch_id=transfer.batch_id,
                    storage_location_id=transfer.destination_location_id,
                    quantity_on_hand=Decimal("0.0000"),
                    quantity_reserved=Decimal("0.0000"),
                    quantity_available=Decimal("0.0000"),
                    quantity_damaged=Decimal("0.0000"),
                    quantity_quarantined=Decimal("0.0000"),
                    version=1,
                )
                db.add(dst_inv)
                await db.flush()

            # 3. Mutate balances atomically
            src_inv.quantity_on_hand -= transfer.quantity
            src_inv.quantity_available = src_inv.quantity_on_hand - src_inv.quantity_reserved
            src_inv.version += 1

            dst_inv.quantity_on_hand += transfer.quantity
            dst_inv.quantity_available = dst_inv.quantity_on_hand - dst_inv.quantity_reserved
            dst_inv.version += 1

            # 4. Write Immutable Stock Movement Leg
            src_move = StockMovement(
                organization_id=organization_id,
                inventory_id=src_inv.id,
                product_id=transfer.product_id,
                batch_id=transfer.batch_id,
                storage_location_id=transfer.source_location_id,
                movement_type="TRANSFER",
                quantity=-transfer.quantity,
                reference_type="STOCK_TRANSFER",
                reference_id=transfer.id,
                reason=f"Transfer to {transfer.destination_location_id}",
                performed_by=user_id,
            )
            dst_move = StockMovement(
                organization_id=organization_id,
                inventory_id=dst_inv.id,
                product_id=transfer.product_id,
                batch_id=transfer.batch_id,
                storage_location_id=transfer.destination_location_id,
                movement_type="TRANSFER",
                quantity=transfer.quantity,
                reference_type="STOCK_TRANSFER",
                reference_id=transfer.id,
                reason=f"Transfer from {transfer.source_location_id}",
                performed_by=user_id,
            )
            db.add_all([src_move, dst_move])

            transfer.status = "COMPLETED"
            transfer.completed_at = datetime.now(timezone.utc)
            transfer.approved_by = user_id

            await AuditService.append_audit_entry(
                db=db,
                organization_id=organization_id,
                user_id=user_id,
                action="STOCK_TRANSFER_COMPLETED",
                entity_type="TRANSFER",
                entity_id=transfer.id,
                old_values={"status": "PENDING"},
                new_values={"status": "COMPLETED", "quantity": str(transfer.quantity)},
                request_id=get_request_id(),
            )

            await db.commit()
            await db.refresh(transfer)
            return transfer