import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


def utc_now() -> datetime:
    """Deterministic timezone-aware UTC clock provider."""
    return datetime.now(timezone.utc)


class UUIDPrimaryKeyMixin:
    """Enforces UUIDv4 primary keys across all domain entities."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        sort_order=-100,
    )


class TimestampMixin:
    """Enforces immutable creation and update audit timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        sort_order=90,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
        sort_order=91,
    )


class TenantMixin:
    """Enforces strict foreign key boundary to the parent organization."""

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        index=True,
        sort_order=-90,
    )