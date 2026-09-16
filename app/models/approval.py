# app/models/approval.py
from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid
from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TenantMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ApprovalRequest(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "approval_requests"

    request_type: Mapped[str] = mapped_column(String(64), nullable=False)  # PURCHASE_ORDER, INVENTORY_ADJUSTMENT, STOCK_TRANSFER, BATCH_RELEASE
    reference_type: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)  # PENDING, APPROVED, REJECTED
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    requester: Mapped["User"] = relationship("User", foreign_keys=[requested_by])
    assignee: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_to])