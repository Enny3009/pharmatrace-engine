from datetime import datetime, timezone
from typing import Any
import uuid
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.base import TenantMixin, UUIDPrimaryKeyMixin


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ComplianceRule(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "compliance_rules"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )  # TEMPERATURE_THRESHOLD, EXPIRY_WINDOW, ADJUSTMENT_LIMIT
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class ComplianceIncident(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "compliance_incidents"

    incident_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )  # TEMPERATURE_EXCURSION, EXPIRED_PRODUCT, UNAUTHORIZED_ADJUSTMENT
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    reference_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="OPEN",
        nullable=False,
    )  # OPEN, ASSIGNED, RESOLVED, CLOSED
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )