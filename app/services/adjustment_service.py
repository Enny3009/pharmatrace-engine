# app/services/adjustment_service.py
from datetime import datetime, timezone
from decimal import Decimal
import uuid
from fastapi import HTTPException, status
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.context import get_request_id
from app.core.redis import DistributedLock
from app.models.approval import ApprovalRequest
from app.models.inventory import Inventory, StockMovement
from app.models.transfer import InventoryAdjustment
from app.schemas.transfer import InventoryAdjustmentCreate
from app.services.audit_service import AuditService

# Configurable regulatory threshold: variance > 10 units triggers managerial approval
ADJUSTMENT_APPROVAL_THRESHOLD = Decimal("10.0000")


class AdjustmentService:
    @classmethod
    async def request_adjustment(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: InventoryAdjustmentCreate,
    ) -> InventoryAdjustment:
        stmt = (
            select(Inventory)
            .where(
                Inventory.id == payload.inventory_id,
                Inventory.organization_id == organization_id,
            )
        )
        inv = (await db.execute(stmt)).scalar_one_or_none()
        if not inv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory record not found.")

        current_qty = inv.quantity_on_hand
        diff = payload.actual_quantity - current_qty

        # Require approval if variance exceeds threshold
        needs_approval = abs(diff) >= ADJUSTMENT_APPROVAL_THRESHOLD

        adj = InventoryAdjustment(
            organization_id=organization_id,
            inventory_id=inv.id,
            requested_quantity=current_qty,
            actual_quantity=payload.actual_quantity,
            difference=diff,
            reason=payload.reason,
            status="PENDING" if needs_approval else "APPROVED",
            requested_by=user_id,
            approved_by=user_id if not needs_approval else None,
            approved_at=datetime.now(timezone.utc) if not needs_approval else None,
        )
        db.add(adj)
        await db.flush()

        if needs_approval:
            approval = ApprovalRequest(
                organization_id=organization_id,
                request_type="INVENTORY_ADJUSTMENT",
                reference_type="INVENTORY_ADJUSTMENT",
                reference_id=adj.id,
                requested_by=user_id,
                status="PENDING",
            )
            db.add(approval)

        await db.commit()
        await db.refresh(adj)
        return adj

    @classmethod
    async def execute_adjustment(
        cls,
        db: AsyncSession,
        redis: aioredis.Redis,
        organization_id: uuid.UUID,
        adjustment_id: uuid.UUID,
        approver_id: uuid.UUID,
    ) -> InventoryAdjustment:
        stmt = (
            select(InventoryAdjustment)
            .where(
                InventoryAdjustment.id == adjustment_id,
                InventoryAdjustment.organization_id == organization_id,
            )
            .with_for_update()
        )
        adj = (await db.execute(stmt)).scalar_one_or_none()
        if not adj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Adjustment record not found.")

        # SoD Guard: Initiator cannot approve high-variance adjustment
        if adj.requested_by == approver_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Separation of Duties violation: Initiator cannot approve their own adjustment (CANNOT_APPROVE_OWN_WORK).",
            )

        if adj.status == "COMPLETED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Adjustment already completed.")

        async with DistributedLock(redis, f"inventory:{adj.inventory_id}"):
            stmt_inv = (
                select(Inventory)
                .where(Inventory.id == adj.inventory_id)
                .with_for_update()
            )
            inv = (await db.execute(stmt_inv)).scalar_one()

            old_qty = inv.quantity_on_hand
            inv.quantity_on_hand = adj.actual_quantity
            inv.quantity_available = inv.quantity_on_hand - inv.quantity_reserved
            inv.version += 1

            if inv.quantity_available < 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Adjustment would result in negative available inventory balance.",
                )

            # Immutable Stock Movement
            move = StockMovement(
                organization_id=organization_id,
                inventory_id=inv.id,
                product_id=inv.product_id,
                batch_id=inv.batch_id,
                storage_location_id=inv.storage_location_id,
                movement_type="ADJUSTMENT",
                quantity=adj.difference,
                reference_type="INVENTORY_ADJUSTMENT",
                reference_id=adj.id,
                reason=adj.reason,
                performed_by=approver_id,
            )
            db.add(move)

            adj.status = "COMPLETED"
            adj.approved_by = approver_id
            adj.approved_at = datetime.now(timezone.utc)

            await AuditService.append_audit_entry(
                db=db,
                organization_id=organization_id,
                user_id=approver_id,
                action="INVENTORY_ADJUSTMENT_EXECUTED",
                entity_type="INVENTORY",
                entity_id=inv.id,
                old_values={"quantity_on_hand": str(old_qty)},
                new_values={"quantity_on_hand": str(inv.quantity_on_hand), "difference": str(adj.difference)},
                request_id=get_request_id(),
            )

            await db.commit()
            await db.refresh(adj)
            return adj