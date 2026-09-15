from decimal import Decimal
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.deps import RequireRole, get_current_user
from app.core.database import get_db
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.purchase_order import POCreate, PORead

router = APIRouter(prefix="/purchase-orders", tags=["Purchase Orders & Procurement"])

require_procurement = RequireRole(["OWNER", "ADMIN", "PROCUREMENT_OFFICER"])
require_approver = RequireRole(["OWNER", "ADMIN", "QA_OFFICER"])


@router.post(
    "",
    response_model=PORead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Purchase Order Draft",
)
async def create_purchase_order(
    payload: POCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_procurement),
) -> PurchaseOrder:
    # 1. PO Number uniqueness per organization
    stmt_po = select(PurchaseOrder).where(
        PurchaseOrder.organization_id == current_user.organization_id,
        PurchaseOrder.po_number == payload.po_number.strip().upper(),
    )
    if (await db.execute(stmt_po)).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Purchase order '{payload.po_number}' already exists.",
        )

    # 2. Verify supplier exists and compliance_status == APPROVED
    stmt_sup = select(Supplier).where(
        Supplier.id == payload.supplier_id,
        Supplier.organization_id == current_user.organization_id,
    )
    supplier = (await db.execute(stmt_sup)).scalar_one_or_none()
    if supplier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found.",
        )
    if supplier.compliance_status != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot order from unapproved supplier. Status is '{supplier.compliance_status}'.",
        )

    # 3. Validate products and calculate total
    total = Decimal("0.00")
    po_items: list[PurchaseOrderItem] = []

    for item in payload.items:
        stmt_prod = select(Product).where(
            Product.id == item.product_id,
            Product.organization_id == current_user.organization_id,
        )
        product = (await db.execute(stmt_prod)).scalar_one_or_none()
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID '{item.product_id}' not found.",
            )

        line_cost = (item.ordered_quantity * item.unit_cost).quantize(Decimal("0.01"))
        total += line_cost

        po_items.append(
            PurchaseOrderItem(
                product_id=product.id,
                ordered_quantity=item.ordered_quantity,
                unit_cost=item.unit_cost,
            )
        )

    po = PurchaseOrder(
        organization_id=current_user.organization_id,
        supplier_id=supplier.id,
        po_number=payload.po_number.strip().upper(),
        status="DRAFT",
        total=total,
        created_by=current_user.id,
        items=po_items,
    )
    db.add(po)
    await db.commit()

    stmt_load = (
        select(PurchaseOrder)
        .where(PurchaseOrder.id == po.id)
        .options(selectinload(PurchaseOrder.items))
    )
    return (await db.execute(stmt_load)).scalar_one()


@router.post(
    "/{id}/submit",
    response_model=PORead,
    summary="Submit PO for Quality/Management Approval",
)
async def submit_purchase_order(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_procurement),
) -> PurchaseOrder:
    stmt = (
        select(PurchaseOrder)
        .where(
            PurchaseOrder.id == id,
            PurchaseOrder.organization_id == current_user.organization_id,
        )
        .options(selectinload(PurchaseOrder.items))
    )
    po = (await db.execute(stmt)).scalar_one_or_none()
    if po is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase order not found.",
        )
    if po.status != "DRAFT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only DRAFT purchase orders can be submitted. Current status: {po.status}",
        )

    po.status = "PENDING_APPROVAL"
    await db.commit()
    await db.refresh(po)
    return po


@router.post(
    "/{id}/approve",
    response_model=PORead,
    summary="Approve Purchase Order (Enforces Separation of Duties)",
)
async def approve_purchase_order(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_approver),
) -> PurchaseOrder:
    stmt = (
        select(PurchaseOrder)
        .where(
            PurchaseOrder.id == id,
            PurchaseOrder.organization_id == current_user.organization_id,
        )
        .options(selectinload(PurchaseOrder.items))
    )
    po = (await db.execute(stmt)).scalar_one_or_none()
    if po is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase order not found.",
        )

    # 21 CFR SoD Guard: Creator cannot approve their own procurement order
    if po.created_by == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Separation of Duties violation: You cannot approve a Purchase Order you created (CANNOT_APPROVE_OWN_WORK).",
        )

    if po.status != "PENDING_APPROVAL":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve PO with status '{po.status}'. Must be PENDING_APPROVAL.",
        )

    po.status = "APPROVED"
    po.approved_by = current_user.id
    await db.commit()
    await db.refresh(po)
    return po


@router.get(
    "",
    response_model=list[PORead],
    summary="List Purchase Orders",
)
async def list_purchase_orders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PurchaseOrder]:
    stmt = (
        select(PurchaseOrder)
        .where(PurchaseOrder.organization_id == current_user.organization_id)
        .options(selectinload(PurchaseOrder.items))
        .order_by(PurchaseOrder.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())