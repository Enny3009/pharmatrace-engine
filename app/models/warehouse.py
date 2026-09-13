from decimal import Decimal
from typing import TYPE_CHECKING
import uuid
from sqlalchemy import (
    Boolean,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organization import Organization


class Warehouse(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "warehouses"

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    temperature_controlled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)

    # Foreign Keys
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_warehouses_org_code"),
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="warehouses")
    storage_locations: Mapped[list["StorageLocation"]] = relationship(
        "StorageLocation",
        back_populates="warehouse",
        cascade="all, delete-orphan",
    )


class StorageLocation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "storage_locations"

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    zone: Mapped[str] = mapped_column(String(32), nullable=False)
    shelf: Mapped[str] = mapped_column(String(32), nullable=False)
    bin: Mapped[str] = mapped_column(String(32), nullable=False)
    temperature_zone: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )  # AMBIENT_15_25C, REFRIGERATED_2_8C, FROZEN_MINUS_20C, ULTRA_LOW_MINUS_80C, CRYO_LN2
    capacity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)

    # Foreign Keys
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("warehouse_id", "code", name="uq_locations_warehouse_code"),
    )

    # Relationships
    warehouse: Mapped["Warehouse"] = relationship("Warehouse", back_populates="storage_locations")