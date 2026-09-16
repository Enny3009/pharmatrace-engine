# app/workers/compliance_tasks.py
import asyncio
from datetime import date, timedelta
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.batch import Batch
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.user import User
from app.services.audit_service import AuditService
from app.workers.celery_app import celery_app


async def _sweep_audit() -> dict[str, bool]:
    results = {}
    async with AsyncSessionLocal() as session:
        stmt = select(Organization.id).where(Organization.status == "ACTIVE")
        org_ids = (await session.execute(stmt)).scalars().all()

        for org_id in org_ids:
            res = await AuditService.verify_chain_integrity(session, org_id)
            results[str(org_id)] = res.get("verified", False)

    return results


async def _sweep_expiring_batches() -> int:
    affected_count = 0
    today = date.today()
    warning_threshold = today + timedelta(days=30)

    async with AsyncSessionLocal() as session:
        # 1. Transition strictly expired batches
        stmt_expired = (
            select(Batch)
            .where(
                Batch.expiry_date <= today,
                Batch.quality_status.notin_(["EXPIRED", "RECALLED"]),
            )
            .with_for_update()
        )
        expired_batches = (await session.execute(stmt_expired)).scalars().all()

        for batch in expired_batches:
            batch.quality_status = "EXPIRED"
            batch.release_status = "UNRELEASED"
            affected_count += 1

        # 2. Sweep lots approaching 30-day expiration window & notify QA/Compliance
        stmt_warning = (
            select(Batch)
            .where(
                Batch.expiry_date > today,
                Batch.expiry_date <= warning_threshold,
                Batch.quality_status == "APPROVED",
            )
        )
        warning_batches = (await session.execute(stmt_warning)).scalars().all()

        for w_batch in warning_batches:
            stmt_users = (
                select(User.id)
                .join(User.role)
                .where(
                    User.organization_id == w_batch.organization_id,
                    User.is_active.is_(True),
                )
            )
            user_ids = (await session.execute(stmt_users)).scalars().all()

            for uid in user_ids:
                notif = Notification(
                    organization_id=w_batch.organization_id,
                    user_id=uid,
                    type="EXPIRY_WARNING",
                    title=f"Batch {w_batch.batch_number} Expiring Soon",
                    message=(
                        f"Batch {w_batch.batch_number} (Lot: {w_batch.lot_number}) expires "
                        f"on {w_batch.expiry_date.isoformat()}. First-Expiry action required."
                    ),
                    severity="HIGH",
                )
                session.add(notif)

        await session.commit()

    return affected_count


@celery_app.task(name="app.workers.compliance_tasks.sweep_audit_integrity")
def sweep_audit_integrity() -> dict[str, bool]:
    return asyncio.run(_sweep_audit())


@celery_app.task(name="app.workers.compliance_tasks.sweep_expiring_batches")
def sweep_expiring_batches() -> int:
    return asyncio.run(_sweep_expiring_batches())