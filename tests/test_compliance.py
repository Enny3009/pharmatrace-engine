from decimal import Decimal
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.models.audit import AuditLedger
from app.models.product import Product
from app.models.supplier import Supplier
from app.services.audit_service import AuditService
from tests.conftest import TestingSessionLocal


@pytest.mark.asyncio
async def test_separation_of_duties_prevents_po_self_approval(
    client: AsyncClient,
    test_auth_context: dict,
):
    login_res = await client.post(
        "/auth/login",
        json={
            "email": test_auth_context["admin_email"],
            "password": test_auth_context["password"],
        },
    )
    admin_token = login_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    async with TestingSessionLocal() as session:
        sup = Supplier(
            organization_id=test_auth_context["organization_id"],
            supplier_code=f"SUP-TEST-{uuid.uuid4().hex[:4]}",
            name="Test Qualified Supplier",
            compliance_status="APPROVED",
        )
        prod = Product(
            organization_id=test_auth_context["organization_id"],
            sku=f"SKU-SOD-{uuid.uuid4().hex[:4]}",
            name="Test Product SoD",
            dosage_form="VIAL",
            storage_type="REFRIGERATED_2_8C",
            min_temperature=Decimal("2.00"),
            max_temperature=Decimal("8.00"),
            reorder_level=Decimal("50.0000"),
        )
        session.add_all([sup, prod])
        await session.commit()
        sup_id = sup.id
        prod_id = prod.id

    po_payload = {
        "supplier_id": str(sup_id),
        "po_number": f"PO-SOD-{uuid.uuid4().hex[:4]}",
        "items": [
            {
                "product_id": str(prod_id),
                "ordered_quantity": 100.0,
                "unit_cost": 25.0,
            }
        ],
    }
    po_res = await client.post("/purchase-orders", json=po_payload, headers=admin_headers)
    assert po_res.status_code == 201
    po_id = po_res.json()["id"]

    submit_res = await client.post(f"/purchase-orders/{po_id}/submit", headers=admin_headers)
    assert submit_res.status_code == 200

    approve_res = await client.post(f"/purchase-orders/{po_id}/approve", headers=admin_headers)
    assert approve_res.status_code == 403
    assert "CANNOT_APPROVE_OWN_WORK" in approve_res.json()["detail"]


@pytest.mark.asyncio
async def test_cryptographic_audit_ledger_detects_database_tampering(
    test_auth_context: dict,
):
    org_id = test_auth_context["organization_id"]

    async with TestingSessionLocal() as session:
        entry1 = await AuditService.append_audit_entry(
            db=session,
            organization_id=org_id,
            user_id=test_auth_context["admin_id"],
            action="FORMULATION_START",
            entity_type="BATCH",
            entity_id=uuid.uuid4(),
            old_values=None,
            new_values={"stage": "MIXING"},
        )
        await session.flush()

        await AuditService.append_audit_entry(
            db=session,
            organization_id=org_id,
            user_id=test_auth_context["admin_id"],
            action="FORMULATION_END",
            entity_type="BATCH",
            entity_id=uuid.uuid4(),
            old_values={"stage": "MIXING"},
            new_values={"stage": "COMPLETED"},
        )
        await session.commit()
        entry1_id = entry1.id

    async with TestingSessionLocal() as session:
        report_valid = await AuditService.verify_chain_integrity(session, org_id)
        assert report_valid["verified"] is True
        assert report_valid["total_records_verified"] >= 2

    # Malicious database update bypass simulation
    async with TestingSessionLocal() as session:
        stmt = select(AuditLedger).where(AuditLedger.id == entry1_id)
        entry = (await session.execute(stmt)).scalar_one()
        entry.new_values = {"stage": "TAMPERED_DIRECT_SQL"}
        await session.commit()

    async with TestingSessionLocal() as session:
        report_tampered = await AuditService.verify_chain_integrity(session, org_id)
        assert report_tampered["verified"] is False
        assert report_tampered["tampered_row_id"] == entry1_id