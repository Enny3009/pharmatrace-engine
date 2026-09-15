from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import RequireRole, get_current_user
from app.core.database import get_db
from app.models.audit import AuditLedger
from app.models.user import User
from app.schemas.audit import AuditLedgerRead, IntegrityVerificationResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit-ledger", tags=["Cryptographic Audit Ledger (ALCOA+)"])

require_compliance = RequireRole(["OWNER", "ADMIN", "COMPLIANCE_OFFICER", "QA_OFFICER"])


@router.get(
    "",
    response_model=list[AuditLedgerRead],
    summary="List Hash-Chained Audit Ledger",
)
async def list_audit_ledger(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance),
) -> list[AuditLedger]:
    stmt = (
        select(AuditLedger)
        .where(AuditLedger.organization_id == current_user.organization_id)
        .order_by(AuditLedger.id.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "/verify-integrity",
    response_model=IntegrityVerificationResponse,
    summary="Traverse and Mathematically Verify Complete SHA-256 Audit Hash Chain",
)
async def verify_audit_integrity(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance),
) -> IntegrityVerificationResponse:
    report = await AuditService.verify_chain_integrity(
        db=db,
        organization_id=current_user.organization_id,
    )
    return IntegrityVerificationResponse(**report)