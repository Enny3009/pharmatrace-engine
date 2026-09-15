import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import RequireRole, get_current_user
from app.core.database import get_db
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate

router = APIRouter(prefix="/suppliers", tags=["Suppliers & Vendor Qualification"])

require_procurement = RequireRole(["OWNER", "ADMIN", "PROCUREMENT_OFFICER"])
require_qa = RequireRole(["OWNER", "ADMIN", "QA_OFFICER", "COMPLIANCE_OFFICER"])


@router.post(
    "",
    response_model=SupplierRead,
    status_code=status.HTTP_201_CREATED,
    summary="Onboard New Supplier (Pending Qualification)",
)
async def create_supplier(
    payload: SupplierCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_procurement),
) -> Supplier:
    stmt = select(Supplier).where(
        Supplier.organization_id == current_user.organization_id,
        Supplier.supplier_code == payload.supplier_code.strip().upper(),
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Supplier code '{payload.supplier_code}' already exists.",
        )

    supplier = Supplier(
        organization_id=current_user.organization_id,
        supplier_code=payload.supplier_code.strip().upper(),
        name=payload.name.strip(),
        compliance_status="PENDING",
        status="ACTIVE",
    )
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return supplier


@router.get(
    "",
    response_model=list[SupplierRead],
    summary="List Qualified Suppliers",
)
async def list_suppliers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Supplier]:
    stmt = (
        select(Supplier)
        .where(Supplier.organization_id == current_user.organization_id)
        .order_by(Supplier.name.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "/{id}/approve",
    response_model=SupplierRead,
    summary="Approve Vendor Compliance Status (QA Guard)",
)
async def approve_supplier(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_qa),
) -> Supplier:
    stmt = select(Supplier).where(
        Supplier.id == id,
        Supplier.organization_id == current_user.organization_id,
    )
    result = await db.execute(stmt)
    supplier = result.scalar_one_or_none()
    if supplier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier not found.",
        )

    supplier.compliance_status = "APPROVED"
    await db.commit()
    await db.refresh(supplier)
    return supplier