import asyncio
from datetime import date
from decimal import Decimal
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.models.batch import Batch
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.warehouse import StorageLocation, Warehouse
from tests.conftest import TestingSessionLocal


@pytest.mark.asyncio
async def test_concurrent_stock_issuance_prevents_negative_balance(
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
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    org_id = test_auth_context["organization_id"]

    async with TestingSessionLocal() as session:
        wh = Warehouse(organization_id=org_id, code=f"WH-T-{uuid.uuid4().hex[:4]}", name="Test WH")
        session.add(wh)
        await session.flush()

        loc = StorageLocation(
            warehouse_id=wh.id,
            code=f"LOC-T-{uuid.uuid4().hex[:4]}",
            zone="COLD",
            shelf="S1",
            bin="B1",
            temperature_zone="REFRIGERATED_2_8C",
            capacity=Decimal("1000.00"),
        )
        prod = Product(
            organization_id=org_id,
            sku=f"SKU-T-{uuid.uuid4().hex[:4]}",
            name="Test Sterile Vials",
            dosage_form="VIAL",
            storage_type="REFRIGERATED_2_8C",
            min_temperature=Decimal("2.00"),
            max_temperature=Decimal("8.00"),
            reorder_level=Decimal("50.0000"),
        )
        session.add_all([loc, prod])
        await session.flush()

        batch = Batch(
            organization_id=org_id,
            product_id=prod.id,
            batch_number=f"B-STRESS-{uuid.uuid4().hex[:4]}",
            lot_number="LOT-STRESS",
            manufacturing_date=date.today(),
            expiry_date=date(2028, 1, 1),
            quantity_received=Decimal("500.0000"),
            quantity_available=Decimal("500.0000"),
            quality_status="APPROVED",
            release_status="RELEASED",
        )
        session.add(batch)
        await session.flush()

        inv = Inventory(
            organization_id=org_id,
            product_id=prod.id,
            batch_id=batch.id,
            storage_location_id=loc.id,
            quantity_on_hand=Decimal("500.0000"),
            quantity_reserved=Decimal("0.0000"),
            quantity_available=Decimal("500.0000"),
            quantity_damaged=Decimal("0.0000"),
            quantity_quarantined=Decimal("0.0000"),
            version=1,
        )
        session.add(inv)
        await session.commit()
        inv_id = inv.id

    async def dispatch_issue():
        payload = {
            "inventory_id": str(inv_id),
            "quantity": 100.0000,
            "reference_type": "BATCH_ALLOCATION",
            "reference_id": str(uuid.uuid4()),
            "reason": "Concurrent Stress Test Run",
        }
        return await client.post("/stock-movements/issue", json=payload, headers=headers)

    responses = await asyncio.gather(*[dispatch_issue() for _ in range(10)])

    successes = [r for r in responses if r.status_code == 201]
    rejections = [r for r in responses if r.status_code in (422, 400, 409)]

    assert len(successes) == 5
    assert len(rejections) == 5

    async with TestingSessionLocal() as session:
        stmt = select(Inventory).where(Inventory.id == inv_id)
        updated_inv = (await session.execute(stmt)).scalar_one()
        assert updated_inv.quantity_on_hand == Decimal("0.0000")
        assert updated_inv.quantity_available == Decimal("0.0000")
        assert updated_inv.version == 6