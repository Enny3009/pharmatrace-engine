# app/api/v1/router.py
from fastapi import APIRouter
from app.api.v1 import (
    adjustments,
    approvals,
    audit,
    auth,
    batches,
    certificates,
    compliance,
    inventory,
    notifications,
    products,
    purchase_orders,
    receipts,
    reports,
    suppliers,
    temperature,
    transfers,
    users,
    warehouses,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(warehouses.router)
api_router.include_router(products.router)
api_router.include_router(suppliers.router)
api_router.include_router(purchase_orders.router)
api_router.include_router(receipts.router)
api_router.include_router(inventory.router)
api_router.include_router(adjustments.router)
api_router.include_router(transfers.router)
api_router.include_router(batches.router)
api_router.include_router(approvals.router)
api_router.include_router(compliance.router)
api_router.include_router(notifications.router)
api_router.include_router(reports.router)
api_router.include_router(audit.router)
api_router.include_router(temperature.router)
api_router.include_router(certificates.router)