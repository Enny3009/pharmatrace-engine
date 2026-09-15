import hashlib
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import RequireRole, get_current_user
from app.core.database import get_db
from app.core.security import verify_password
from app.models.batch import Batch
from app.models.receipt import GoodsReceipt, GoodsReceiptItem
from app.models.signature import ElectronicSignature
from app.models.user import User
from app.schemas.batch import BatchRead, BatchReleaseRequest, BatchReleaseResponse
from app.schemas.signature import ElectronicSignatureRead
from app.services.audit_service import AuditService

router = APIRouter(prefix="/batches", tags=["Batches & 21 CFR Electronic Signatures"])

require_qa_release = RequireRole(["OWNER", "ADMIN", "QA_OFFICER"])


@router.get(
    "",
    response_model=list[BatchRead],
    summary="List Production Batches",
)
async def list_batches(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Batch]:
    stmt = (
        select(Batch)
        .where(Batch.organization_id == current_user.organization_id)
        .order_by(Batch.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get(
    "/{id}",
    response_model=BatchRead,
    summary="Get Batch Master",
)
async def get_batch(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Batch:
    stmt = select(Batch).where(
        Batch.id == id,
        Batch.organization_id == current_user.organization_id,
    )
    result = await db.execute(stmt)
    batch = result.scalar_one_or_none()
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found.",
        )
    return batch


@router.post(
    "/{id}/release",
    response_model=BatchReleaseResponse,
    summary="Execute 21 CFR Part 11 Electronic Dual-Auth Batch Release",
)
async def release_batch(
    id: uuid.UUID,
    payload: BatchReleaseRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_qa_release),
) -> BatchReleaseResponse:
    # 1. Interactive Dual-Factor Password Re-authentication (§ 11.200)
    if not verify_password(payload.reauth_password, current_user.password_hash):
        # Append security violation audit entry
        await AuditService.append_audit_entry(
            db=db,
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="UNAUTHORIZED_SIGNATURE_ATTEMPT",
            entity_type="BATCH",
            entity_id=id,
            old_values=None,
            new_values={"error": "Interactive password re-authentication failed."},
            request_id=request.headers.get("X-Request-ID"),
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Electronic signature authentication failed. Invalid password credentials.",
        )

    # 2. Fetch Batch Master
    stmt = (
        select(Batch)
        .where(
            Batch.id == id,
            Batch.organization_id == current_user.organization_id,
        )
        .with_for_update()
    )
    result = await db.execute(stmt)
    batch = result.scalar_one_or_none()
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Batch not found.",
        )

    # 3. Separation of Duties (SoD) Check:
    # Verify the approver was not the warehouse operator who received the goods receipt
    stmt_receipt = (
        select(GoodsReceipt.received_by)
        .join(GoodsReceiptItem, GoodsReceiptItem.goods_receipt_id == GoodsReceipt.id)
        .where(
            GoodsReceiptItem.product_id == batch.product_id,
            GoodsReceipt.organization_id == current_user.organization_id,
        )
    )
    receiver_ids = (await db.execute(stmt_receipt)).scalars().all()
    if current_user.id in receiver_ids and current_user.role.name not in ("OWNER", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Separation of Duties violation: Operator who received this product batch cannot sign off on final release (CANNOT_APPROVE_OWN_WORK).",
        )

    old_values = {
        "quality_status": batch.quality_status,
        "release_status": batch.release_status,
    }

    # 4. Compute State Snapshot SHA-256 Digest (§ 11.50)
    snapshot_data = {
        "batch_number": batch.batch_number,
        "lot_number": batch.lot_number,
        "product_id": str(batch.product_id),
        "manufacturing_date": batch.manufacturing_date.isoformat(),
        "expiry_date": batch.expiry_date.isoformat(),
        "quantity_available": str(batch.quantity_available),
        "release_notes": payload.release_notes,
    }
    snapshot_hash = hashlib.sha256(
        json.dumps(snapshot_data, sort_keys=True).encode("utf-8")
    ).hexdigest()

    client_ip = request.client.host if request.client else "127.0.0.1"

    # 5. Persist Electronic Signature Record
    sig = ElectronicSignature(
        organization_id=current_user.organization_id,
        entity_type="BATCH",
        entity_id=batch.id,
        user_id=current_user.id,
        signature_meaning=payload.signature_meaning.value,
        snapshot_payload_hash=snapshot_hash,
        ip_address=client_ip,
    )
    db.add(sig)

    # 6. Mutate Batch State
    batch.quality_status = "APPROVED"
    batch.release_status = "RELEASED"

    new_values = {
        "quality_status": batch.quality_status,
        "release_status": batch.release_status,
        "signature_id": str(sig.id),
        "snapshot_hash": snapshot_hash,
    }

    # 7. Append Chained Audit Entry to cryptographic ledger in same ACID transaction
    await AuditService.append_audit_entry(
        db=db,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="BATCH_FINAL_RELEASE_21CFR",
        entity_type="BATCH",
        entity_id=batch.id,
        old_values=old_values,
        new_values=new_values,
        request_id=request.headers.get("X-Request-ID"),
    )

    await db.commit()
    await db.refresh(batch)
    await db.refresh(sig)

    return BatchReleaseResponse(
        batch=BatchRead.model_validate(batch),
        signature=ElectronicSignatureRead.model_validate(sig),
    )