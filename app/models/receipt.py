from decimal import Decimal
from typing import TYPE_CHECKING
import uuid
from sqlalchemy import ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.purchase_order import PurchaseOrder
    from app.models.user import User
    from app.models.warehouse import StorageLocation, Warehouse


class GoodsReceipt(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "goods_receipts"

    receipt_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING",
        nullable=False,
    )  # PENDING, INSPECTED, ACCEPTED, REJECTED

    # Foreign Keys
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    received_by: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Relationships
    purchase_order: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="goods_receipts")
    warehouse: Mapped["Warehouse"] = relationship("Warehouse")
    receiver: Mapped["User"] = relationship("User")
    items: Mapped[list["GoodsReceiptItem"]] = relationship(
        "GoodsReceiptItem",
        back_populates="goods_receipt",
        cascade="all, delete-orphan",
    )
    inspections: Mapped[list["Inspection"]] = relationship(
        "Inspection",
        back_populates="goods_receipt",
        cascade="all, delete-orphan",
    )


class GoodsReceiptItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "goods_receipt_items"

    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("goods_receipts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    storage_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("storage_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    quantity_accepted: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        default=Decimal("0.0000"),
        nullable=False,
    )
    quantity_rejected: Mapped[Decimal] = mapped_column(
        Numeric(12, 4),
        default=Decimal("0.0000"),
        nullable=False,
    )

    # Relationships
    goods_receipt: Mapped["GoodsReceipt"] = relationship("GoodsReceipt", back_populates="items")
    product: Mapped["Product"] = relationship("Product")
    storage_location: Mapped["StorageLocation"] = relationship("StorageLocation")


class Inspection(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "inspections"

    result: Mapped[str] = mapped_column(String(32), nullable=False)  # PASSED, FAILED, CONDITIONAL
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Foreign Keys
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("goods_receipts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inspector_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Relationships
    goods_receipt: Mapped["GoodsReceipt"] = relationship("GoodsReceipt", back_populates="inspections")
    inspector: Mapped["User"] = relationship("User")