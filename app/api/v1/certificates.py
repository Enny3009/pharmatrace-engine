import io
import uuid
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import RequireRole, get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.certificate_service import CertificateService

router = APIRouter(prefix="/certificates", tags=["Certificates of Analysis (21 CFR CoA)"])

require_qa = RequireRole(["OWNER", "ADMIN", "QA_OFFICER", "COMPLIANCE_OFFICER"])


@router.get(
    "/{batch_id}/download",
    summary="Compile and Stream 21 CFR Part 11 Signed Certificate of Analysis (PDF)",
)
async def download_certificate(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_qa),
) -> Response:
    pdf_bytes = await CertificateService.compile_batch_coa_pdf(
        db=db,
        organization_id=current_user.organization_id,
        batch_id=batch_id,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename=Certificate_of_Analysis_{batch_id}.pdf"
        },
    )