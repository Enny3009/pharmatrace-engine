# app/core/idempotency.py
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any
from fastapi import Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.idempotency import IdempotencyKey
from app.models.user import User


class IdempotentOperation:
    """
    Guarantees safe API retries by caching HTTP responses against an organization-scoped key.
    """

    @classmethod
    async def check_or_set(
        cls,
        db: AsyncSession,
        request: Request,
        current_user: User,
        idempotency_key: str | None,
        request_body: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not idempotency_key:
            return None

        body_hash = hashlib.sha256(
            json.dumps(request_body, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        stmt = select(IdempotencyKey).where(
            IdempotencyKey.organization_id == current_user.organization_id,
            IdempotencyKey.idempotency_key == idempotency_key,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if existing:
            if existing.expires_at < now:
                await db.delete(existing)
                await db.commit()
                return None

            if existing.request_hash != body_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key reused with different request payload.",
                )
            return {
                "status_code": existing.response_status,
                "body": existing.response_body,
            }

        return None

    @classmethod
    async def record_response(
        cls,
        db: AsyncSession,
        organization_id: Any,
        idempotency_key: str | None,
        request_path: str,
        request_body: dict[str, Any],
        status_code: int,
        response_body: dict[str, Any],
    ) -> None:
        if not idempotency_key:
            return

        body_hash = hashlib.sha256(
            json.dumps(request_body, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        rec = IdempotencyKey(
            organization_id=organization_id,
            idempotency_key=idempotency_key,
            request_path=request_path,
            request_hash=body_hash,
            response_status=status_code,
            response_body=response_body,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.add(rec)
        await db.commit()