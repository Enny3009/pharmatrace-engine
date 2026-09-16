# app/models/transfer.py
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
import uuid
from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.batch import Batch
    from app.models.inventory import Inventory
    from app.models.product import Product
    from app.models.user import User
    from app.models.warehouse import StorageLocation


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InventoryAdjustment(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "inventory_adjustments"

    requested_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    actual_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    difference: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)  # PENDING, APPROVED, REJECTED, COMPLETED
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
    requested_by: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    inventory: Mapped["Inventory"] = relationship("Inventory")
    requester: Mapped["User"] = relationship("User", foreign_keys=[requested_by])
    approver: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by])


class StockTransfer(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "stock_transfers"

    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)  # PENDING, APPROVED, IN_TRANSIT, COMPLETED, CANCELLED
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("batches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("storage_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    destination_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("storage_locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    product: Mapped["Product"] = relationship("Product")
    batch: Mapped["Batch"] = relationship("Batch")
    source_location: Mapped["StorageLocation"] = relationship("StorageLocation", foreign_keys=[source_location_id])
    destination_location: Mapped["StorageLocation"] = relationship("StorageLocation", foreign_keys=[destination_location_id])