# app/api/v1/compliance.py
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import RequireRole, get_current_user
from app.core.database import get_db
from app.models.compliance import ComplianceIncident, ComplianceRule
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.compliance import (
    ComplianceIncidentRead,
    ComplianceRuleCreate,
    ComplianceRuleRead,
    IncidentResolutionRequest,
)

router = APIRouter(prefix="/compliance", tags=["Regulatory Compliance Incidents & Rules"])

require_compliance = RequireRole(["OWNER", "ADMIN", "COMPLIANCE_OFFICER", "QA_OFFICER"])


@router.get(
    "/incidents",
    response_model=PaginatedResponse[ComplianceIncidentRead],
    summary="List Regulatory Deviations & Incidents",
)
async def list_incidents(
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance),
) -> PaginatedResponse[ComplianceIncidentRead]:
    base_query = select(ComplianceIncident).where(
        ComplianceIncident.organization_id == current_user.organization_id
    )
    if status_filter:
        base_query = base_query.where(ComplianceIncident.status == status_filter.upper())

    count_stmt = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        base_query.order_by(ComplianceIncident.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list((await db.execute(stmt)).scalars().all())

    return PaginatedResponse(
        items=[ComplianceIncidentRead.model_validate(it) for it in items],
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if total > 0 else 0,
    )


@router.post(
    "/incidents/{id}/resolve",
    response_model=ComplianceIncidentRead,
    summary="Resolve and Close Regulatory Compliance Incident",
)
async def resolve_incident(
    id: uuid.UUID,
    payload: IncidentResolutionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance),
) -> ComplianceIncident:
    stmt = (
        select(ComplianceIncident)
        .where(
            ComplianceIncident.id == id,
            ComplianceIncident.organization_id == current_user.organization_id,
        )
        .with_for_update()
    )
    incident = (await db.execute(stmt)).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found.")

    incident.status = "RESOLVED"
    incident.resolved_by = current_user.id
    incident.description = f"{incident.description} | CAPA Resolution: {payload.resolution_notes}"

    await db.commit()
    await db.refresh(incident)
    return incident


@router.get(
    "/rules",
    response_model=list[ComplianceRuleRead],
    summary="List Organization Compliance Monitoring Rules",
)
async def list_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance),
) -> list[ComplianceRule]:
    stmt = select(ComplianceRule).where(
        ComplianceRule.organization_id == current_user.organization_id
    )
    return list((await db.execute(stmt)).scalars().all())


@router.post(
    "/rules",
    response_model=ComplianceRuleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create Compliance Rule",
)
async def create_rule(
    payload: ComplianceRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_compliance),
) -> ComplianceRule:
    rule = ComplianceRule(
        organization_id=current_user.organization_id,
        name=payload.name,
        rule_type=payload.rule_type,
        configuration=payload.configuration,
        enabled=payload.enabled,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule