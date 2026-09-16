from datetime import datetime, timezone
from decimal import Decimal
import uuid
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TenantMixin, UUIDPrimaryKeyMixin
from app.models.warehouse import StorageLocation


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TemperatureDevice(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "temperature_devices"

    device_identifier: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    min_temperature: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    max_temperature: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Foreign Keys
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("storage_locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    storage_location: Mapped["StorageLocation"] = relationship("StorageLocation")


class TemperatureRecord(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "temperature_records"

    temperature: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="NORMAL",
        nullable=False,
    )  # NORMAL, WARNING, EXCURSION
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )

    # Foreign Keys
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("storage_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("temperature_devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class TemperatureExcursion(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "temperature_excursions"

    observed_temperature: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    allowed_minimum: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    allowed_maximum: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    status: Mapped[str] = mapped_column(
        String(32),
        default="OPEN",
        nullable=False,
    )  # OPEN, INVESTIGATING, RESOLVED, CLOSED
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Foreign Keys
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_location_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("storage_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )