import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import RequireRole, get_current_user
from app.core.database import get_db
from app.models.temperature import TemperatureDevice, TemperatureExcursion, TemperatureRecord
from app.models.user import User
from app.schemas.temperature import (
    TemperatureDeviceCreate,
    TemperatureDeviceRead,
    TemperatureExcursionRead,
    TemperatureIngestRequest,
    TemperatureRecordRead,
)
from app.services.excursion_service import ExcursionService

router = APIRouter(prefix="/temperature", tags=["Cold-Chain IoT & Temperature Excursions"])

require_facility_manager = RequireRole(["OWNER", "ADMIN", "WAREHOUSE_STAFF"])


@router.post(
    "/devices",
    response_model=TemperatureDeviceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register IoT Temperature Monitoring Device",
)
async def create_temperature_device(
    payload: TemperatureDeviceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_facility_manager),
) -> TemperatureDevice:
    stmt = select(TemperatureDevice).where(
        TemperatureDevice.device_identifier == payload.device_identifier.strip()
    )
    if (await db.execute(stmt)).scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Device identifier '{payload.device_identifier}' is already registered.",
        )

    device = TemperatureDevice(
        organization_id=current_user.organization_id,
        storage_location_id=payload.storage_location_id,
        device_identifier=payload.device_identifier.strip(),
        api_key_hash=ExcursionService.hash_api_key(payload.api_key),
        min_temperature=payload.min_temperature,
        max_temperature=payload.max_temperature,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


@router.post(
    "/ingest",
    response_model=TemperatureRecordRead,
    status_code=status.HTTP_200_OK,
    summary="IoT Bridge Sensor Ingestion Endpoint",
)
async def ingest_temperature(
    payload: TemperatureIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> TemperatureRecord:
    return await ExcursionService.process_temperature_reading(
        db=db,
        device_identifier=payload.device_identifier,
        api_key=payload.api_key,
        temperature=payload.temperature,
    )


@router.get(
    "/records",
    response_model=list[TemperatureRecordRead],
    summary="List Temperature Records",
)
async def list_temperature_records(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TemperatureRecord]:
    stmt = (
        select(TemperatureRecord)
        .where(TemperatureRecord.organization_id == current_user.organization_id)
        .order_by(TemperatureRecord.recorded_at.desc())
        .limit(100)
    )
    return list((await db.execute(stmt)).scalars().all())


@router.get(
    "/excursions",
    response_model=list[TemperatureExcursionRead],
    summary="List Thermal Excursion Incidents",
)
async def list_temperature_excursions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TemperatureExcursion]:
    stmt = (
        select(TemperatureExcursion)
        .where(TemperatureExcursion.organization_id == current_user.organization_id)
        .order_by(TemperatureExcursion.started_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())