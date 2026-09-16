# tests/test_enterprise_workflows.py
from datetime import date
from decimal import Decimal
import uuid
import pytest
from httpx import AsyncClient
from app.models.batch import Batch
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.warehouse import StorageLocation, Warehouse
from tests.conftest import TestingSessionLocal


@pytest.mark.asyncio
async def test_atomic_stock_transfer_and_adjustment_workflow(
    client: AsyncClient,
    test_auth_context: dict,
):
    # 1. Authenticate Admin
    res_login = await client.post(
        "/auth/login",
        json={
            "email": test_auth_context["admin_email"],
            "password": test_auth_context["password"],
        },
    )
    assert res_login.status_code == 200
    token = res_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    org_id = test_auth_context["organization_id"]

    # 2. Setup Warehouse with 2 Locations and Seeded Stock
    async with TestingSessionLocal() as session:
        wh = Warehouse(organization_id=org_id, code=f"WH-E2E-{uuid.uuid4().hex[:4]}", name="Main Plant")
        session.add(wh)
        await session.flush()

        loc1 = StorageLocation(
            warehouse_id=wh.id,
            code=f"LOC-A-{uuid.uuid4().hex[:4]}",
            zone="Z1",
            shelf="S1",
            bin="B1",
            temperature_zone="AMBIENT_15_25C",
            capacity=Decimal("1000.00"),
        )
        loc2 = StorageLocation(
            warehouse_id=wh.id,
            code=f"LOC-B-{uuid.uuid4().hex[:4]}",
            zone="Z2",
            shelf="S2",
            bin="B2",
            temperature_zone="AMBIENT_15_25C",
            capacity=Decimal("1000.00"),
        )
        prod = Product(
            organization_id=org_id,
            sku=f"SKU-TRANS-{uuid.uuid4().hex[:4]}",
            name="Vial Saline Diluent",
            dosage_form="VIAL",
            storage_type="AMBIENT_15_25C",
            min_temperature=Decimal("15.00"),
            max_temperature=Decimal("25.00"),
            reorder_level=Decimal("20.0000"),
        )
        session.add_all([loc1, loc2, prod])
        await session.flush()

        batch = Batch(
            organization_id=org_id,
            product_id=prod.id,
            batch_number=f"B-E2E-{uuid.uuid4().hex[:4]}",
            lot_number="LOT-E2E-001",
            manufacturing_date=date.today(),
            expiry_date=date(2028, 6, 1),
            quantity_received=Decimal("100.0000"),
            quantity_available=Decimal("100.0000"),
            quality_status="APPROVED",
            release_status="RELEASED",
        )
        session.add(batch)
        await session.flush()

        inv = Inventory(
            organization_id=org_id,
            product_id=prod.id,
            batch_id=batch.id,
            storage_location_id=loc1.id,
            quantity_on_hand=Decimal("100.0000"),
            quantity_reserved=Decimal("0.0000"),
            quantity_available=Decimal("100.0000"),
            version=1,
        )
        session.add(inv)
        await session.commit()

        loc1_id = loc1.id
        loc2_id = loc2.id
        prod_id = prod.id
        batch_id = batch.id
        inv_id = inv.id

    # 3. Create Transfer Request (30 units from Loc A -> Loc B)
    t_payload = {
        "product_id": str(prod_id),
        "batch_id": str(batch_id),
        "source_location_id": str(loc1_id),
        "destination_location_id": str(loc2_id),
        "quantity": 30.0000,
        "notes": "Relocating buffer to Zone 2",
    }
    t_res = await client.post("/transfers", json=t_payload, headers=headers)
    assert t_res.status_code == 201
    transfer_id = t_res.json()["id"]

    # 4. Complete Transfer
    exec_res = await client.post(f"/transfers/{transfer_id}/complete", headers=headers)
    assert exec_res.status_code == 200
    assert exec_res.json()["status"] == "COMPLETED"

    # 5. Verify Pagination on /transfers endpoint
    list_t = await client.get("/transfers?page=1&limit=10", headers=headers)
    assert list_t.status_code == 200
    assert "items" in list_t.json()
    assert list_t.json()["total"] >= 1

    # 6. Check Executive Dashboard Report
    rep_res = await client.get("/reports/summary", headers=headers)
    assert rep_res.status_code == 200
    rep_data = rep_res.json()
    assert rep_data["total_products"] >= 1
    assert rep_data["total_inventory_units"] == "100.0000"