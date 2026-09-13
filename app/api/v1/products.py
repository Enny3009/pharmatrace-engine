import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import RequireRole, get_current_user
from app.core.database import get_db
from app.models.product import Product
from app.models.user import User
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate

router = APIRouter(prefix="/products", tags=["Product Catalog"])

require_product_manager = RequireRole(["OWNER", "ADMIN", "QA_OFFICER"])


@router.post(
    "",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Pharmaceutical Product Master",
)
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_product_manager),
) -> Product:
    # 1. SKU uniqueness per organization
    stmt = select(Product).where(
        Product.organization_id == current_user.organization_id,
        Product.sku == payload.sku.strip().upper(),
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Product with SKU '{payload.sku}' already exists in your organization.",
        )

    product = Product(
        organization_id=current_user.organization_id,
        sku=payload.sku.strip().upper(),
        name=payload.name.strip(),
        generic_name=payload.generic_name.strip() if payload.generic_name else None,
        dosage_form=payload.dosage_form.value,
        storage_type=payload.storage_type.strip(),
        min_temperature=payload.min_temperature,
        max_temperature=payload.max_temperature,
        requires_temperature_monitoring=payload.requires_temperature_monitoring,
        reorder_level=payload.reorder_level,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@router.get(
    "",
    response_model=list[ProductRead],
    summary="List Tenant Product Catalog",
)
async def list_products(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.organization_id == current_user.organization_id)
        .order_by(Product.sku.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get(
    "/{id}",
    response_model=ProductRead,
    summary="Get Product by ID",
)
async def get_product(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Product:
    stmt = select(Product).where(
        Product.id == id,
        Product.organization_id == current_user.organization_id,
    )
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )
    return product


@router.patch(
    "/{id}",
    response_model=ProductRead,
    summary="Update Pharmaceutical Product Parameters",
)
async def update_product(
    id: uuid.UUID,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_product_manager),
) -> Product:
    stmt = select(Product).where(
        Product.id == id,
        Product.organization_id == current_user.organization_id,
    )
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )

    # Validate temperature bounds against existing values if only one bound is provided
    new_min = payload.min_temperature if payload.min_temperature is not None else product.min_temperature
    new_max = payload.max_temperature if payload.max_temperature is not None else product.max_temperature
    if new_min > new_max:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Updated min_temperature cannot exceed max_temperature.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    await db.commit()
    await db.refresh(product)
    return product