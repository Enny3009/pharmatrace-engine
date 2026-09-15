from fastapi import APIRouter
from app.api.v1 import auth, products, purchase_orders, receipts, suppliers, users, warehouses

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(warehouses.router)
api_router.include_router(products.router)
api_router.include_router(suppliers.router)
api_router.include_router(purchase_orders.router)
api_router.include_router(receipts.router)