"""
FastAPI application entry point.

Main API server for Stocker trading platform.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from stocker.core.config import settings
from stocker.core.logging import setup_logging
from stocker.core.database import close_db
from stocker.core.redis import close_redis

# Setup logging
setup_logging()

# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Systematic Trading Platform - Volatility-Targeted Trend-Following",
    debug=settings.DEBUG,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    """Run on application startup."""
    pass  # Database initialization handled by Alembic


@app.on_event("shutdown")
async def shutdown() -> None:
    """Run on application shutdown."""
    await close_db()
    await close_redis()


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "message": f"Welcome to {settings.APP_NAME} API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }


from stocker.api.sse import router as sse_router
from stocker.api.portfolio import router as portfolio_router
from stocker.api.signals import router as signals_router
from stocker.api.orders import router as orders_router

app.include_router(sse_router, prefix="/api/v1", tags=["stream"])
app.include_router(portfolio_router, prefix="/api/v1/portfolio", tags=["portfolio"])
app.include_router(signals_router, prefix="/api/v1/signals", tags=["signals"])
app.include_router(orders_router, prefix="/api/v1/orders", tags=["orders"])

# TODO: Include admin router when created
# app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
