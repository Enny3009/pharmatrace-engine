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


class Product(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    generic_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dosage_form: Mapped[str] = mapped_column(String(64), nullable=False)  # VIAL, TABLET, AMPOULE, SUSPENSION
    storage_type: Mapped[str] = mapped_column(String(32), nullable=False)
    min_temperature: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    max_temperature: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    requires_temperature_monitoring: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reorder_level: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    # Foreign Keys
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("organization_id", "sku", name="uq_products_org_sku"),
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="products")