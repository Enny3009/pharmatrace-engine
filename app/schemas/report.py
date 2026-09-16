# app/schemas/report.py
from decimal import Decimal
from pydantic import BaseModel


class ExecutiveSummaryReport(BaseModel):
    total_products: int
    total_inventory_units: Decimal
    total_batches: int
    quarantined_batches: int
    expired_batches: int
    expiring_soon_30_days: int
    open_compliance_incidents: int
    open_temperature_excursions: int
    pending_approvals: int