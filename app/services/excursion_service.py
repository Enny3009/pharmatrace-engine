from datetime import datetime, timezone
from decimal import Decimal
import hashlib
from typing import Any
import uuid
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.batch import Batch
from app.models.compliance import ComplianceIncident
from app.models.inventory import Inventory
from app.models.outbox import OutboxEvent
from app.models.temperature import TemperatureDevice, TemperatureExcursion, TemperatureRecord
from app.models.warehouse import StorageLocation

ZONE_THRESHOLDS: dict[str, tuple[Decimal, Decimal]] = {
    "AMBIENT_15_25C": (Decimal("15.00"), Decimal("25.00")),
    "REFRIGERATED_2_8C": (Decimal("2.00"), Decimal("8.00")),
    "FROZEN_MINUS_20C": (Decimal("-25.00"), Decimal("-15.00")),
    "ULTRA_LOW_MINUS_80C": (Decimal("-85.00"), Decimal("-70.00")),
    "CRYO_LN2": (Decimal("-196.00"), Decimal("-150.00")),
}


class ExcursionService:
    @staticmethod
    def hash_api_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    @classmethod
    async def process_temperature_reading(
        cls,
        db: AsyncSession,
        device_identifier: str,
        api_key: str,
        temperature: Decimal,
    ) -> TemperatureRecord:
        now = datetime.now(timezone.utc)
        api_key_hash = cls.hash_api_key(api_key)

        # 1. Authenticate Device
        stmt_dev = select(TemperatureDevice).where(
            TemperatureDevice.device_identifier == device_identifier
        )
        device = (await db.execute(stmt_dev)).scalar_one_or_none()
        if device is None or device.api_key_hash != api_key_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid IoT sensor credentials.",
            )

        device.last_seen_at = now

        # 2. Resolve Storage Location & Regulatory Thermal Thresholds
        stmt_loc = select(StorageLocation).where(StorageLocation.id == device.storage_location_id)
        location = (await db.execute(stmt_loc)).scalar_one()

        min_allowed, max_allowed = ZONE_THRESHOLDS.get(
            location.temperature_zone,
            (device.min_temperature, device.max_temperature),
        )

        is_breach = (temperature < min_allowed) or (temperature > max_allowed)
        record_status = "EXCURSION" if is_breach else "NORMAL"

        record = TemperatureRecord(
            organization_id=device.organization_id,
            storage_location_id=location.id,
            device_id=device.id,
            temperature=temperature,
            status=record_status,
            recorded_at=now,
        )
        db.add(record)

        # 3. Excursion Evaluation & Automated Quarantine
        if is_breach:
            delta = max(min_allowed - temperature, temperature - max_allowed)
            severity = "CRITICAL" if delta >= Decimal("5.00") else "HIGH"

            # Check for existing open excursion
            stmt_ex = (
                select(TemperatureExcursion)
                .where(
                    TemperatureExcursion.storage_location_id == location.id,
                    TemperatureExcursion.status == "OPEN",
                )
                .order_by(TemperatureExcursion.started_at.desc())
                .limit(1)
            )
            excursion = (await db.execute(stmt_ex)).scalar_one_or_none()

            if excursion is None:
                excursion = TemperatureExcursion(
                    organization_id=device.organization_id,
                    storage_location_id=location.id,
                    observed_temperature=temperature,
                    allowed_minimum=min_allowed,
                    allowed_maximum=max_allowed,
                    started_at=now,
                    duration_seconds=0,
                    severity=severity,
                    status="OPEN",
                )
                db.add(excursion)
                await db.flush()
            else:
                excursion.duration_seconds = int((now - excursion.started_at).total_seconds())
                excursion.observed_temperature = temperature
                if severity == "CRITICAL":
                    excursion.severity = "CRITICAL"

            # Auto-Quarantine Condition: Critical Delta (>=5°C) OR Breach Duration >= 15 min (900s)
            if delta >= Decimal("5.00") or excursion.duration_seconds >= 900:
                # Find all active inventory batches stored in this location
                stmt_inv = (
                    select(Inventory)
                    .where(Inventory.storage_location_id == location.id)
                    .with_for_update()
                )
                inventories = (await db.execute(stmt_inv)).scalars().all()

                compromised_batches: list[str] = []
                for inv in inventories:
                    stmt_b = select(Batch).where(Batch.id == inv.batch_id).with_for_update()
                    batch = (await db.execute(stmt_b)).scalar_one()
                    if batch.quality_status != "QUARANTINED":
                        batch.quality_status = "QUARANTINED"
                        batch.release_status = "UNRELEASED"
                        compromised_batches.append(batch.batch_number)

                # Log formal cGMP Compliance Incident
                incident = ComplianceIncident(
                    organization_id=device.organization_id,
                    incident_type="TEMPERATURE_EXCURSION",
                    severity=severity,
                    reference_type="TEMPERATURE_EXCURSION",
                    reference_id=excursion.id,
                    description=(
                        f"Cold-chain excursion detected at location {location.code}. "
                        f"Temp: {temperature}°C (Allowed: {min_allowed}°C to {max_allowed}°C). "
                        f"Batches quarantined: {', '.join(compromised_batches) or 'None (Empty Location)'}."
                    ),
                    status="OPEN",
                )
                db.add(incident)
                await db.flush()

                # Insert into Transactional Outbox for Celery notification dispatch
                outbox_event = OutboxEvent(
                    organization_id=device.organization_id,
                    event_type="COLD_CHAIN_EXCURSION_QUARANTINE",
                    aggregate_type="STORAGE_LOCATION",
                    aggregate_id=location.id,
                    payload={
                        "incident_id": str(incident.id),
                        "excursion_id": str(excursion.id),
                        "location_code": location.code,
                        "temperature": str(temperature),
                        "severity": severity,
                        "quarantined_batches": compromised_batches,
                    },
                    status="PENDING",
                )
                db.add(outbox_event)

        else:
            # If reading is back within normal limits, close open excursion
            stmt_open_ex = (
                select(TemperatureExcursion)
                .where(
                    TemperatureExcursion.storage_location_id == location.id,
                    TemperatureExcursion.status == "OPEN",
                )
            )
            open_excursions = (await db.execute(stmt_open_ex)).scalars().all()
            for ex in open_excursions:
                ex.ended_at = now
                ex.duration_seconds = int((now - ex.started_at).total_seconds())
                ex.status = "RESOLVED"

        await db.commit()
        await db.refresh(record)
        return record