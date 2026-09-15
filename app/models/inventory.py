from decimal import Decimal
from typing import TYPE_CHECKING
import uuid
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.batch import Batch
    from app.models.product import Product
    from app.models.user import User
    from app.models.warehouse import StorageLocation


class Inventory(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "inventory"

    quantity_on_hand: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        default=Decimal("0.0000"),
        nullable=False,
    )
    quantity_reserved: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        default=Decimal("0.0000"),
        nullable=False,
    )
    quantity_available: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        default=Decimal("0.0000"),
        nullable=False,
    )
    quantity_damaged: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        default=Decimal("0.0000"),
        nullable=False,
    )
    quantity_quarantined: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        default=Decimal("0.0000"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

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
    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    storage_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("storage_locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Integrity Constraints: Hard database guarantees preventing negative stock
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "batch_id",
            "storage_location_id",
            name="uq_inventory_prod_batch_loc",
        ),
        CheckConstraint("quantity_on_hand >= 0", name="chk_inv_qty_on_hand_positive"),
        CheckConstraint("quantity_reserved >= 0", name="chk_inv_qty_reserved_positive"),
        CheckConstraint("quantity_available >= 0", name="chk_inv_qty_available_positive"),
        CheckConstraint("quantity_damaged >= 0", name="chk_inv_qty_damaged_positive"),
        CheckConstraint("quantity_quarantined >= 0", name="chk_inv_qty_quarantined_positive"),
        CheckConstraint(
            "quantity_available = (quantity_on_hand - quantity_reserved)",
            name="chk_inv_balance_equation",
        ),
    )

    # Relationships
    product: Mapped["Product"] = relationship("Product")
    batch: Mapped["Batch"] = relationship("Batch", back_populates="inventories")
    storage_location: Mapped["StorageLocation"] = relationship("StorageLocation")
    movements: Mapped[list["StockMovement"]] = relationship(
        "StockMovement",
        back_populates="inventory",
        cascade="all, delete-orphan",
    )


class StockMovement(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Immutable cGMP stock ledger entry tracking every physical mutation."""

    __tablename__ = "stock_movements"

    movement_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )  # RECEIPT, ISSUE, TRANSFER, ADJUSTMENT, RETURN, DAMAGE, EXPIRY, QUARANTINE, RELEASE
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    reference_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )  # PURCHASE_ORDER, GOODS_RECEIPT, ADJUSTMENT, TRANSFER, BATCH_ALLOCATION
    reference_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Foreign Keys
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inventory_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("inventory.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    storage_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("storage_locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    performed_by: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Relationships
    inventory: Mapped["Inventory"] = relationship("Inventory", back_populates="movements")
    operator: Mapped["User"] = relationship("User")