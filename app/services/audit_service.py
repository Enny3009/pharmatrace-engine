from datetime import datetime, timezone
import hashlib
import json
from typing import Any
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditLedger
from app.models.organization import Organization


class AuditService:
    @staticmethod
    def serialize_payload(payload: dict[str, Any] | None) -> str:
        """Deterministic JSON stringifier ensuring identical key ordering."""
        if payload is None:
            return ""
        return json.dumps(payload, sort_keys=True, default=str)

    @staticmethod
    def compute_sha256(raw_string: str) -> str:
        return hashlib.sha256(raw_string.encode("utf-8")).hexdigest()

    @classmethod
    async def append_audit_entry(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        user_id: uuid.UUID | None,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        old_values: dict[str, Any] | None,
        new_values: dict[str, Any],
        request_id: str | None = None,
    ) -> AuditLedger:
        """
        Appends an immutable audit entry bound to the organization's hash chain.
        Row locks the latest entry using FOR UPDATE to prevent concurrency forks.
        """
        # 1. Fetch latest audit hash for this tenant
        stmt_last = (
            select(AuditLedger.current_hash)
            .where(AuditLedger.organization_id == organization_id)
            .order_by(AuditLedger.id.desc())
            .limit(1)
            .with_for_update()
        )
        last_hash = (await db.execute(stmt_last)).scalar_one_or_none()

        # 2. If no entries exist yet, anchor to the organization's genesis_hash
        if not last_hash:
            stmt_org = select(Organization.genesis_hash).where(Organization.id == organization_id)
            last_hash = (await db.execute(stmt_org)).scalar_one()

        created_at = datetime.now(timezone.utc)
        payload_diff = {
            "old": old_values,
            "new": new_values,
        }
        diff_str = cls.serialize_payload(payload_diff)

        # 3. Cryptographic Chain Formulation
        raw_chain_string = (
            f"{last_hash}|{organization_id}|{user_id}|{action}|"
            f"{entity_type}|{entity_id}|{created_at.isoformat()}|{diff_str}"
        )
        current_hash = cls.compute_sha256(raw_chain_string)

        entry = AuditLedger(
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_values=old_values,
            new_values=new_values,
            previous_hash=last_hash,
            current_hash=current_hash,
            request_id=request_id,
            created_at=created_at,
        )
        db.add(entry)
        await db.flush()
        return entry

    @classmethod
    async def verify_chain_integrity(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
    ) -> dict[str, Any]:
        """
        Traverses the entire audit ledger from Genesis Hash forward.
        Detects deleted rows, modified records, or out-of-sequence entries.
        """
        stmt_org = select(Organization.genesis_hash).where(Organization.id == organization_id)
        genesis_hash = (await db.execute(stmt_org)).scalar_one_or_none()
        if not genesis_hash:
            return {"verified": False, "error": "Organization not found."}

        stmt = (
            select(AuditLedger)
            .where(AuditLedger.organization_id == organization_id)
            .order_by(AuditLedger.id.asc())
        )
        rows = (await db.execute(stmt)).scalars().all()

        expected_previous_hash = genesis_hash
        verified_count = 0

        for row in rows:
            # Check 1: Chain Linkage
            if row.previous_hash != expected_previous_hash:
                return {
                    "verified": False,
                    "tampered_row_id": row.id,
                    "action": row.action,
                    "error": f"Previous hash mismatch. Expected {expected_previous_hash}, got {row.previous_hash}.",
                    "verified_rows": verified_count,
                }

            # Check 2: Mathematical Digest Recalculation
            payload_diff = {
                "old": row.old_values,
                "new": row.new_values,
            }
            diff_str = cls.serialize_payload(payload_diff)
            raw_chain_string = (
                f"{row.previous_hash}|{row.organization_id}|{row.user_id}|{row.action}|"
                f"{row.entity_type}|{row.entity_id}|{row.created_at.isoformat()}|{diff_str}"
            )
            recalculated_hash = cls.compute_sha256(raw_chain_string)

            if row.current_hash != recalculated_hash:
                return {
                    "verified": False,
                    "tampered_row_id": row.id,
                    "action": row.action,
                    "error": f"Payload altered. Recalculated hash {recalculated_hash} does not match {row.current_hash}.",
                    "verified_rows": verified_count,
                }

            expected_previous_hash = row.current_hash
            verified_count += 1

        return {
            "verified": True,
            "total_records_verified": verified_count,
            "genesis_hash": genesis_hash,
            "latest_head_hash": expected_previous_hash,
        }