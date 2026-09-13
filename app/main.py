from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and graceful shutdown lifecycle hooks."""
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="21 CFR Part 11 Compliant Pharmaceutical Inventory & Regulatory Ledger Engine",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount primary v1 routing topology
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"], status_code=status.HTTP_200_OK)
async def health_check() -> dict[str, str]:
    """Lightweight orchestrator readiness check."""
    return {"status": "HEALTHY", "service": settings.APP_NAME}