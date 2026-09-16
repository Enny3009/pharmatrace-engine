# app/api/v1/reports.py
from datetime import date, timedelta
from decimal import Decimal
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import RequireRole, get_current_user
from app.core.database import get_db
from app.models.approval import ApprovalRequest
from app.models.batch import Batch
from app.models.compliance import ComplianceIncident
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.temperature import TemperatureExcursion
from app.models.user import User
from app.schemas.report import ExecutiveSummaryReport

router = APIRouter(prefix="/reports", tags=["Compliance & Inventory Reports"])

require_auditor = RequireRole(["OWNER", "ADMIN", "QA_OFFICER", "COMPLIANCE_OFFICER", "INVENTORY_MANAGER"])


@router.get(
    "/summary",
    response_model=ExecutiveSummaryReport,
    summary="Executive Dashboard Operational & Regulatory Summary",
)
async def get_summary_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_auditor),
) -> ExecutiveSummaryReport:
    org_id = current_user.organization_id
    today = date.today()
    soon = today + timedelta(days=30)

    # 1. Products Count
    prod_stmt = select(func.count(Product.id)).where(Product.organization_id == org_id)
    total_products = (await db.execute(prod_stmt)).scalar() or 0

    # 2. Total Units On Hand
    inv_stmt = select(func.sum(Inventory.quantity_on_hand)).where(Inventory.organization_id == org_id)
    total_units = (await db.execute(inv_stmt)).scalar() or Decimal("0.0000")

    # 3. Batches counts
    batch_base = select(func.count(Batch.id)).where(Batch.organization_id == org_id)
    total_batches = (await db.execute(batch_base)).scalar() or 0

    quarantine_stmt = batch_base.where(Batch.quality_status == "QUARANTINED")
    quarantined_batches = (await db.execute(quarantine_stmt)).scalar() or 0

    expired_stmt = batch_base.where(Batch.expiry_date <= today)
    expired_batches = (await db.execute(expired_stmt)).scalar() or 0

    expiring_soon_stmt = batch_base.where(Batch.expiry_date > today, Batch.expiry_date <= soon)
    expiring_soon = (await db.execute(expiring_soon_stmt)).scalar() or 0

    # 4. Open Incidents & Excursions
    inc_stmt = select(func.count(ComplianceIncident.id)).where(
        ComplianceIncident.organization_id == org_id,
        ComplianceIncident.status == "OPEN",
    )
    open_incidents = (await db.execute(inc_stmt)).scalar() or 0

    exc_stmt = select(func.count(TemperatureExcursion.id)).where(
        TemperatureExcursion.organization_id == org_id,
        TemperatureExcursion.status == "OPEN",
    )
    open_excursions = (await db.execute(exc_stmt)).scalar() or 0

    # 5. Pending Approvals
    appr_stmt = select(func.count(ApprovalRequest.id)).where(
        ApprovalRequest.organization_id == org_id,
        ApprovalRequest.status == "PENDING",
    )
    pending_approvals = (await db.execute(appr_stmt)).scalar() or 0

    return ExecutiveSummaryReport(
        total_products=total_products,
        total_inventory_units=total_units,
        total_batches=total_batches,
        quarantined_batches=quarantined_batches,
        expired_batches=expired_batches,
        expiring_soon_30_days=expiring_soon,
        open_compliance_incidents=open_incidents,
        open_temperature_excursions=open_excursions,
        pending_approvals=pending_approvals,
    )