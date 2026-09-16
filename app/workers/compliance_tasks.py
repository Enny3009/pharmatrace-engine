import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.organization import Organization
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


@celery_app.task(name="app.workers.compliance_tasks.sweep_audit_integrity")
def sweep_audit_integrity() -> dict[str, bool]:
    return asyncio.run(_sweep_audit())