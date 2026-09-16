# app/api/v1/approvals.py
from datetime import datetime, timezone
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import RequireRole, get_current_user
from app.core.context import get_request_id
from app.core.database import get_db
from app.models.approval import ApprovalRequest
from app.models.user import User
from app.schemas.approval import ApprovalDecisionRequest, ApprovalRequestRead
from app.schemas.common import PaginatedResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/approvals", tags=["Multi-Tiered Approval Workflows"])

require_approver = RequireRole(["OWNER", "ADMIN", "QA_OFFICER", "INVENTORY_MANAGER"])


@router.get(
    "",
    response_model=PaginatedResponse[ApprovalRequestRead],
    summary="List Approval Requests",
)
async def list_approvals(
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedResponse[ApprovalRequestRead]:
    base_query = select(ApprovalRequest).where(
        ApprovalRequest.organization_id == current_user.organization_id
    )
    if status_filter:
        base_query = base_query.where(ApprovalRequest.status == status_filter.upper())

    count_stmt = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        base_query.order_by(ApprovalRequest.requested_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list((await db.execute(stmt)).scalars().all())

    return PaginatedResponse(
        items=[ApprovalRequestRead.model_validate(it) for it in items],
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if total > 0 else 0,
    )


@router.post(
    "/{id}/approve",
    response_model=ApprovalRequestRead,
    summary="Approve Workflow Request (Enforces SoD)",
)
async def approve_request(
    id: uuid.UUID,
    payload: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_approver),
) -> ApprovalRequest:
    stmt = (
        select(ApprovalRequest)
        .where(
            ApprovalRequest.id == id,
            ApprovalRequest.organization_id == current_user.organization_id,
        )
        .with_for_update()
    )
    req = (await db.execute(stmt)).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found.")

    if req.requested_by == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Separation of Duties: User cannot approve their own requested workflow (CANNOT_APPROVE_OWN_WORK).",
        )

    if req.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Approval request already resolved with status '{req.status}'.",
        )

    req.status = "APPROVED"
    req.comments = payload.comments
    req.approved_at = datetime.now(timezone.utc)
    req.assigned_to = current_user.id

    await AuditService.append_audit_entry(
        db=db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="APPROVAL_REQUEST_APPROVED",
        entity_type="APPROVAL_REQUEST",
        entity_id=req.id,
        old_values={"status": "PENDING"},
        new_values={"status": "APPROVED", "comments": payload.comments},
        request_id=get_request_id(),
    )

    await db.commit()
    await db.refresh(req)
    return req


@router.post(
    "/{id}/reject",
    response_model=ApprovalRequestRead,
    summary="Reject Workflow Request",
)
async def reject_request(
    id: uuid.UUID,
    payload: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_approver),
) -> ApprovalRequest:
    stmt = (
        select(ApprovalRequest)
        .where(
            ApprovalRequest.id == id,
            ApprovalRequest.organization_id == current_user.organization_id,
        )
        .with_for_update()
    )
    req = (await db.execute(stmt)).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found.")

    req.status = "REJECTED"
    req.comments = payload.comments
    req.assigned_to = current_user.id

    await AuditService.append_audit_entry(
        db=db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="APPROVAL_REQUEST_REJECTED",
        entity_type="APPROVAL_REQUEST",
        entity_id=req.id,
        old_values={"status": "PENDING"},
        new_values={"status": "REJECTED", "comments": payload.comments},
        request_id=get_request_id(),
    )

    await db.commit()
    await db.refresh(req)
    return req