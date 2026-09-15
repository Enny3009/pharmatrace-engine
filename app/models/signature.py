from datetime import datetime, timezone
import uuid
from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TenantMixin, UUIDPrimaryKeyMixin


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ElectronicSignature(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """
    FDA 21 CFR Part 11 Electronic Signature record.
    Permanently binds an authenticated user, timestamp, meaning, and data digest.
    """

    __tablename__ = "electronic_signatures"

    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    signature_meaning: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )  # AUTHORED, COMPOUNDED, VERIFIED, QC_APPROVED, FINAL_RELEASE, QUARANTINE_HOLD
    snapshot_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)

    # Foreign Keys
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )