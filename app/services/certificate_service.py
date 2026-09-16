import io
import uuid
from fastapi import HTTPException, status
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.storage import upload_certificate_pdf
from app.models.batch import Batch
from app.models.organization import Organization
from app.models.product import Product
from app.models.signature import ElectronicSignature
from app.models.supplier import Supplier
from app.models.user import User


class CertificateService:
    @classmethod
    async def compile_batch_coa_pdf(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        batch_id: uuid.UUID,
    ) -> bytes:
        """
        Compiles an immutable 21 CFR Part 11 compliant Certificate of Analysis (CoA) PDF.
        """
        # 1. Fetch Batch, Signature, Product, and Organization
        stmt = (
            select(Batch)
            .where(
                Batch.id == batch_id,
                Batch.organization_id == organization_id,
            )
            .options(
                selectinload(Batch.product),
                selectinload(Batch.supplier),
            )
        )
        batch = (await db.execute(stmt)).scalar_one_or_none()
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found.")

        if batch.release_status != "RELEASED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot generate Certificate of Analysis for unreleased batch (Status: {batch.release_status}).",
            )

        # 2. Fetch Release Electronic Signature
        stmt_sig = (
            select(ElectronicSignature)
            .where(
                ElectronicSignature.entity_id == batch.id,
                ElectronicSignature.signature_meaning == "FINAL_RELEASE",
            )
            .order_by(ElectronicSignature.signature_timestamp.desc())
            .limit(1)
        )
        signature = (await db.execute(stmt_sig)).scalar_one_or_none()
        if signature is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No formal 21 CFR electronic signature record found for this batch release.",
            )

        # Fetch Signer
        stmt_user = select(User).where(User.id == signature.user_id).options(selectinload(User.role))
        signer = (await db.execute(stmt_user)).scalar_one()

        # Fetch Organization
        stmt_org = select(Organization).where(Organization.id == organization_id)
        org = (await db.execute(stmt_org)).scalar_one()

        # 3. ReportLab Document Construction
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0B2545"),
            alignment=1,
        )
        subtitle_style = ParagraphStyle(
            "DocSubTitle",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#134074"),
            alignment=1,
        )
        section_heading = ParagraphStyle(
            "SectionHeading",
            parent=styles["Heading2"],
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#0B2545"),
            spaceBefore=12,
            spaceAfter=6,
        )
        body_style = ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#1D2D44"),
        )
        mono_style = ParagraphStyle(
            "Mono",
            parent=styles["Normal"],
            fontSize=7,
            leading=9,
            fontName="Courier",
            textColor=colors.HexColor("#000000"),
        )

        elements = []

        # Header Block
        elements.append(Paragraph(f"<b>{org.legal_name.upper()}</b>", title_style))
        elements.append(
            Paragraph(
                f"cGMP REGULATORY CERTIFICATE OF ANALYSIS (CoA) • FDA EST: {org.license_number}",
                subtitle_style,
            )
        )
        elements.append(Spacer(1, 10))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0B2545")))
        elements.append(Spacer(1, 10))

        # Batch & Product Specification Table
        elements.append(Paragraph("1. PRODUCT SPECIFICATION & BATCH MASTER", section_heading))
        batch_table_data = [
            [
                Paragraph("<b>Product Name:</b>", body_style),
                Paragraph(batch.product.name, body_style),
                Paragraph("<b>SKU:</b>", body_style),
                Paragraph(batch.product.sku, body_style),
            ],
            [
                Paragraph("<b>Batch Number:</b>", body_style),
                Paragraph(batch.batch_number, body_style),
                Paragraph("<b>Lot Number:</b>", body_style),
                Paragraph(batch.lot_number, body_style),
            ],
            [
                Paragraph("<b>Dosage Form:</b>", body_style),
                Paragraph(batch.product.dosage_form, body_style),
                Paragraph("<b>Storage Type:</b>", body_style),
                Paragraph(batch.product.storage_type, body_style),
            ],
            [
                Paragraph("<b>Manufacturing Date:</b>", body_style),
                Paragraph(batch.manufacturing_date.isoformat(), body_style),
                Paragraph("<b>Expiration Date:</b>", body_style),
                Paragraph(batch.expiry_date.isoformat(), body_style),
            ],
            [
                Paragraph("<b>Released Quantity:</b>", body_style),
                Paragraph(f"{batch.quantity_available} Units", body_style),
                Paragraph("<b>Quality Status:</b>", body_style),
                Paragraph(f"<b>{batch.quality_status}</b>", body_style),
            ],
        ]
        t1 = Table(batch_table_data, colWidths=[110, 160, 110, 160])
        t1.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF4F8")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#8DA9C4")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(t1)
        elements.append(Spacer(1, 15))

        # 21 CFR Part 11 Electronic Signature Block (§ 11.50)
        elements.append(
            Paragraph("2. FDA 21 CFR PART 11 DUAL-AUTH ELECTRONIC RELEASE SIGNATURE", section_heading)
        )
        sig_data = [
            [
                Paragraph("<b>Authorized Signer:</b>", body_style),
                Paragraph(f"{signer.first_name} {signer.last_name} ({signer.email})", body_style),
            ],
            [
                Paragraph("<b>Assigned Role:</b>", body_style),
                Paragraph(signer.role.name, body_style),
            ],
            [
                Paragraph("<b>Signature Meaning:</b>", body_style),
                Paragraph(f"<b>{signature.signature_meaning}</b> (Legally Binding Release)", body_style),
            ],
            [
                Paragraph("<b>Timestamp (UTC):</b>", body_style),
                Paragraph(signature.signature_timestamp.isoformat(), body_style),
            ],
            [
                Paragraph("<b>Client IP Address:</b>", body_style),
                Paragraph(signature.ip_address, body_style),
            ],
            [
                Paragraph("<b>State Snapshot Digest (SHA-256):</b>", body_style),
                Paragraph(signature.snapshot_payload_hash, mono_style),
            ],
            [
                Paragraph("<b>Electronic Signature ID:</b>", body_style),
                Paragraph(str(signature.id), mono_style),
            ],
        ]
        t2 = Table(sig_data, colWidths=[160, 380])
        t2.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#0B2545")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(t2)
        elements.append(Spacer(1, 20))

        # Legal Attestation Footer
        attestation_text = (
            "ATTESTATION: I hereby certify that this pharmaceutical batch has been compounded, packaged, and "
            "inspected in strict compliance with current Good Manufacturing Practices (cGMP) regulations and FDA "
            "21 CFR Part 11 requirements. The mathematical SHA-256 snapshot bound herein reflects the tamper-evident "
            "production state recorded in the PharmaTrace cryptographic ledger."
        )
        elements.append(Paragraph(attestation_text, body_style))

        # Build document
        doc.build(elements)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        # 4. Upload to MinIO Storage
        object_key = f"{org.id}/{batch.batch_number}_CoA.pdf"
        upload_certificate_pdf(object_key, pdf_bytes)

        return pdf_bytes