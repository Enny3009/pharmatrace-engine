from decimal import Decimal
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.deps import RequireRole, get_current_user
from app.core.database import get_db
from app.models.batch import Batch
from app.models.inventory import Inventory, StockMovement
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.receipt import GoodsReceipt, GoodsReceiptItem, Inspection
from app.models.user import User
from app.models.warehouse import StorageLocation, Warehouse
from app.schemas.receipt import (
    GoodsReceiptCreate,
    GoodsReceiptRead,
    InspectionCreate,
    InspectionRead,
)

router = APIRouter(prefix="/goods-receipts", tags=["Goods Receipts & Receiving Inspection"])

require_receiving = RequireRole(["OWNER", "ADMIN", "WAREHOUSE_STAFF"])
require_qa = RequireRole(["OWNER", "ADMIN", "QA_OFFICER"])


@router.post(
    "",
    response_model=GoodsReceiptRead,
    status_code=status.HTTP_201_CREATED,
    summary="Log Goods Receipt against Approved PO",
)
async def create_goods_receipt(
    payload: GoodsReceiptCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_receiving),
) -> GoodsReceipt:
    # 1. Receipt number uniqueness
    stmt_num = select(GoodsReceipt).where(
        GoodsReceipt.organization_id == current_user.organization_id,
        GoodsReceipt.receipt_number == payload.receipt_number.strip().upper(),
    )
    if (await db.execute(stmt_num)).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Receipt number '{payload.receipt_number}' already exists.",
        )

    # 2. Check PO is APPROVED
    stmt_po = (
        select(PurchaseOrder)
        .where(
            PurchaseOrder.id == payload.purchase_order_id,
            PurchaseOrder.organization_id == current_user.organization_id,
        )
        .options(selectinload(PurchaseOrder.items))
    )
    po = (await db.execute(stmt_po)).scalar_one_or_none()
    if po is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase order not found.",
        )
    if po.status not in ("APPROVED", "PARTIALLY_RECEIVED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot receive goods for PO in '{po.status}' state. Must be APPROVED or PARTIALLY_RECEIVED.",
        )

    # 3. Check Warehouse
    stmt_wh = select(Warehouse).where(
        Warehouse.id == payload.warehouse_id,
        Warehouse.organization_id == current_user.organization_id,
    )
    if (await db.execute(stmt_wh)).scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found.",
        )

    # 4. Construct receipt items and validate locations
    receipt_items: list[GoodsReceiptItem] = []
    po_item_map = {item.product_id: item for item in po.items}

    for item in payload.items:
        if item.product_id not in po_item_map:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product '{item.product_id}' is not part of this Purchase Order.",
            )

        # Validate storage location exists in this warehouse
        stmt_loc = select(StorageLocation).where(
            StorageLocation.id == item.storage_location_id,
            StorageLocation.warehouse_id == payload.warehouse_id,
        )
        if (await db.execute(stmt_loc)).scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Storage location '{item.storage_location_id}' not found in warehouse.",
            )

        receipt_items.append(
            GoodsReceiptItem(
                product_id=item.product_id,
                storage_location_id=item.storage_location_id,
                quantity_received=item.quantity_received,
                quantity_accepted=Decimal("0.0000"),
                quantity_rejected=Decimal("0.0000"),
            )
        )

    receipt = GoodsReceipt(
        organization_id=current_user.organization_id,
        purchase_order_id=po.id,
        warehouse_id=payload.warehouse_id,
        receipt_number=payload.receipt_number.strip().upper(),
        received_by=current_user.id,
        status="PENDING",
        items=receipt_items,
    )
    db.add(receipt)
    await db.commit()

    stmt_load = (
        select(GoodsReceipt)
        .where(GoodsReceipt.id == receipt.id)
        .options(
            selectinload(GoodsReceipt.items),
            selectinload(GoodsReceipt.inspections),
        )
    )
    return (await db.execute(stmt_load)).scalar_one()


@router.post(
    "/{id}/inspect",
    response_model=InspectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record Quality Inspection & Materialize Batches/Inventory",
)
async def inspect_goods_receipt(
    id: uuid.UUID,
    payload: InspectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_qa),
) -> Inspection:
    # 1. Fetch receipt with items and associated PO
    stmt = (
        select(GoodsReceipt)
        .where(
            GoodsReceipt.id == id,
            GoodsReceipt.organization_id == current_user.organization_id,
        )
        .options(
            selectinload(GoodsReceipt.items),
            selectinload(GoodsReceipt.purchase_order).selectinload(PurchaseOrder.items),
        )
    )
    receipt = (await db.execute(stmt)).scalar_one_or_none()
    if receipt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goods receipt not found.",
        )
    if receipt.status in ("ACCEPTED", "REJECTED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Goods receipt has already been finalized with status: {receipt.status}",
        )

    # 2. Record Inspection
    inspection = Inspection(
        organization_id=current_user.organization_id,
        goods_receipt_id=receipt.id,
        inspector_id=current_user.id,
        result=payload.result.value,
        notes=payload.notes,
    )
    db.add(inspection)

    if payload.result == payload.result.PASSED:
        receipt.status = "ACCEPTED"

        for r_item in receipt.items:
            r_item.quantity_accepted = r_item.quantity_received
            r_item.quantity_rejected = Decimal("0.0000")

            # A. Create Batch Master
            batch = Batch(
                organization_id=current_user.organization_id,
                product_id=r_item.product_id,
                supplier_id=receipt.purchase_order.supplier_id,
                batch_number=payload.batch_number.strip().upper(),
                lot_number=payload.lot_number.strip().upper(),
                manufacturing_date=payload.manufacturing_date,
                expiry_date=payload.expiry_date,
                quantity_received=r_item.quantity_accepted,
                quantity_available=r_item.quantity_accepted,
                quality_status="APPROVED",
                release_status="RELEASED",
            )
            db.add(batch)
            await db.flush()  # Populates batch.id

            # B. Materialize Physical Stock in Inventory
            inventory = Inventory(
                organization_id=current_user.organization_id,
                product_id=r_item.product_id,
                batch_id=batch.id,
                storage_location_id=r_item.storage_location_id,
                quantity_on_hand=r_item.quantity_accepted,
                quantity_reserved=Decimal("0.0000"),
                quantity_available=r_item.quantity_accepted,
                quantity_damaged=Decimal("0.0000"),
                quantity_quarantined=Decimal("0.0000"),
                version=1,
            )
            db.add(inventory)
            await db.flush()

            # C. Append to Immutable Stock Movement Ledger
            movement = StockMovement(
                organization_id=current_user.organization_id,
                inventory_id=inventory.id,
                product_id=r_item.product_id,
                batch_id=batch.id,
                storage_location_id=r_item.storage_location_id,
                movement_type="RECEIPT",
                quantity=r_item.quantity_accepted,
                reference_type="GOODS_RECEIPT",
                reference_id=receipt.id,
                reason="c-GMP Goods Receipt Quality Acceptance",
                performed_by=current_user.id,
            )
            db.add(movement)

            # D. Update PO line item received count
            for po_item in receipt.purchase_order.items:
                if po_item.product_id == r_item.product_id:
                    po_item.received_quantity += r_item.quantity_accepted

        # Check if PO is completely fulfilled
        all_received = all(
            it.received_quantity >= it.ordered_quantity
            for it in receipt.purchase_order.items
        )
        receipt.purchase_order.status = "RECEIVED" if all_received else "PARTIALLY_RECEIVED"

    else:
        receipt.status = "REJECTED"
        for r_item in receipt.items:
            r_item.quantity_accepted = Decimal("0.0000")
            r_item.quantity_rejected = r_item.quantity_received

    await db.commit()
    await db.refresh(inspection)
    return inspection


@router.get(
    "",
    response_model=list[GoodsReceiptRead],
    summary="List Goods Receipts",
)
async def list_goods_receipts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[GoodsReceipt]:
    stmt = (
        select(GoodsReceipt)
        .where(GoodsReceipt.organization_id == current_user.organization_id)
        .options(
            selectinload(GoodsReceipt.items),
            selectinload(GoodsReceipt.inspections),
        )
        .order_by(GoodsReceipt.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())