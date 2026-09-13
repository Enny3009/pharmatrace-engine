from fastapi import APIRouter
from app.api.v1 import auth, products, warehouses

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(warehouses.router)
api_router.include_router(products.router)