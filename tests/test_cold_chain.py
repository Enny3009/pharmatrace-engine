from datetime import date
from decimal import Decimal
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.models.batch import Batch
from app.models.compliance import ComplianceIncident
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.temperature import TemperatureDevice
from app.models.warehouse import StorageLocation, Warehouse
from app.services.excursion_service import ExcursionService
from tests.conftest import TestingSessionLocal


@pytest.mark.asyncio
async def test_critical_thermal_spike_quarantines_batches(
    client: AsyncClient,
    test_auth_context: dict,
):
    org_id = test_auth_context["organization_id"]

    async with TestingSessionLocal() as session:
        wh = Warehouse(organization_id=org_id, code=f"WH-E-{uuid.uuid4().hex[:4]}", name="Cold WH")
        session.add(wh)
        await session.flush()

        loc = StorageLocation(
            warehouse_id=wh.id,
            code=f"LOC-COLD-{uuid.uuid4().hex[:4]}",
            zone="COLD",
            shelf="S2",
            bin="B2",
            temperature_zone="REFRIGERATED_2_8C",
            capacity=Decimal("1000.00"),
        )
        prod = Product(
            organization_id=org_id,
            sku=f"SKU-C-{uuid.uuid4().hex[:4]}",
            name="Insulin Master Stock",
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
            batch_number=f"B-INS-{uuid.uuid4().hex[:4]}",
            lot_number="LOT-INSULIN",
            manufacturing_date=date.today(),
            expiry_date=date(2028, 1, 1),
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
            storage_location_id=loc.id,
            quantity_on_hand=Decimal("100.0000"),
            quantity_reserved=Decimal("0.0000"),
            quantity_available=Decimal("100.0000"),
            quantity_damaged=Decimal("0.0000"),
            quantity_quarantined=Decimal("0.0000"),
            version=1,
        )
        session.add(inv)

        device_key = "secure_test_sensor_key_2026"
        device_id_str = f"IOT-DEV-{uuid.uuid4().hex[:6]}"
        device = TemperatureDevice(
            organization_id=org_id,
            storage_location_id=loc.id,
            device_identifier=device_id_str,
            api_key_hash=ExcursionService.hash_api_key(device_key),
            min_temperature=Decimal("2.00"),
            max_temperature=Decimal("8.00"),
        )
        session.add(device)
        await session.commit()
        batch_id = batch.id

    # Ingest Critical Thermal Spike (16.0°C into 2-8°C zone, delta = 8.0°C >= 5.0°C)
    ingest_payload = {
        "device_identifier": device_id_str,
        "api_key": device_key,
        "temperature": 16.00,
    }
    res = await client.post("/temperature/ingest", json=ingest_payload)
    assert res.status_code == 200
    assert res.json()["status"] == "EXCURSION"

    # Assert Batch has been automatically Quarantined
    async with TestingSessionLocal() as session:
        stmt_batch = select(Batch).where(Batch.id == batch_id)
        updated_batch = (await session.execute(stmt_batch)).scalar_one()
        assert updated_batch.quality_status == "QUARANTINED"
        assert updated_batch.release_status == "UNRELEASED"

        stmt_inc = select(ComplianceIncident).where(
            ComplianceIncident.organization_id == org_id,
            ComplianceIncident.incident_type == "TEMPERATURE_EXCURSION",
        )
        incident = (await session.execute(stmt_inc)).scalar_one_or_none()
        assert incident is not None
        assert incident.severity == "CRITICAL"