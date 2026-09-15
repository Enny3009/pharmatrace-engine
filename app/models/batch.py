from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING
import uuid
from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.inventory import Inventory
    from app.models.product import Product
    from app.models.supplier import Supplier


class Batch(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "batches"

    batch_number: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    lot_number: Mapped[str] = mapped_column(String(128), nullable=False)
    manufacturing_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    quantity_available: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    quantity_quarantined: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        default=Decimal("0.0000"),
        nullable=False,
    )
    quality_status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING",
        nullable=False,
    )  # PENDING, APPROVED, QUARANTINED, REJECTED, EXPIRED, RECALLED
    release_status: Mapped[str] = mapped_column(
        String(32),
        default="UNRELEASED",
        nullable=False,
    )  # UNRELEASED, RELEASED

    # Foreign Keys
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("product_id", "batch_number", name="uq_batches_product_batch_number"),
    )

    # Relationships
    product: Mapped["Product"] = relationship("Product")
    supplier: Mapped["Supplier | None"] = relationship("Supplier")
    inventories: Mapped[list["Inventory"]] = relationship("Inventory", back_populates="batch")