"""
Admin API Router.

Provides endpoints for managing strategy configuration.
"""

from typing import Dict, List, Optional, Literal
from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from redis.exceptions import ResponseError
from pydantic import BaseModel

from stocker.services.config_service import config_service, TRADING_PARAMS
from stocker.services.portfolio_sync_service import PortfolioSyncService
from stocker.core.database import AsyncSessionLocal
from stocker.core.redis import get_async_redis, StreamNames
from stocker.core.config import settings

router = APIRouter()


# ---------- Pydantic Schemas ----------

class ConfigResponse(BaseModel):
    """Response schema for configuration entries."""
    key: str
    value: str
    value_type: str
    category: str
    description: Optional[str]

    class Config:
        from_attributes = True


class ConfigUpdate(BaseModel):
    """Request schema for updating a single config value."""
    value: str


class BulkConfigUpdate(BaseModel):
    """Request schema for updating multiple config values."""
    updates: Dict[str, str]


class ConfigMetadata(BaseModel):
    """Metadata about a config parameter for UI rendering."""
    key: str
    value_type: str
    category: str
    description: str
    tooltip: Optional[str] = None
    min: Optional[float] = None
    max: Optional[float] = None
    options: Optional[List[str]] = None


class ServiceHealth(BaseModel):
    name: str
    status: Literal["healthy", "warning", "error"]
    last_heartbeat: str
    message: Optional[str] = None


class PortfolioSyncRequest(BaseModel):
    portfolio_id: str = "main"


class PortfolioSyncResponse(BaseModel):
    portfolio_id: str
    orders_created: int
    orders_updated: int
    fills_created: int
    holdings_refreshed: int
    portfolio_state_updated: bool
    synced_at: str


# ---------- Endpoints ----------

@router.get("/config", response_model=List[ConfigResponse])
async def list_config():
    """Get all configuration entries."""
    configs = await config_service.get_all()
    return configs


@router.get("/config/categories", response_model=List[str])
async def list_categories():
    """Get list of configuration categories."""
    categories = await config_service.get_categories()
    return categories


@router.get("/config/metadata", response_model=List[ConfigMetadata])
async def get_config_metadata():
    """Get metadata for all configuration parameters (for UI rendering)."""
    return [
        ConfigMetadata(
            key=key,
            value_type=meta["value_type"],
            category=meta["category"],
            description=meta["description"],
            tooltip=meta.get("tooltip"),
            min=meta.get("min"),
            max=meta.get("max"),
            options=meta.get("options"),
        )
        for key, meta in TRADING_PARAMS.items()
    ]


@router.get("/config/category/{category}", response_model=List[ConfigResponse])
async def get_config_by_category(category: str):
    """Get configuration entries for a specific category."""
    configs = await config_service.get_by_category(category)
    if not configs:
        raise HTTPException(status_code=404, detail=f"No configs found for category: {category}")
    return configs


@router.get("/config/{key}", response_model=ConfigResponse)
async def get_config(key: str):
    """Get a single configuration entry by key."""
    config = await config_service.get(key)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Config not found: {key}")
    return config


@router.put("/config/{key}", response_model=ConfigResponse)
async def update_config(key: str, body: ConfigUpdate):
    """
    Update a single configuration value.

    Note: Changes take effect after application restart.
    """
    try:
        config = await config_service.update(key, body.value)
        if config is None:
            raise HTTPException(status_code=404, detail=f"Config not found: {key}")
        return config
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/config", response_model=List[ConfigResponse])
async def bulk_update_config(body: BulkConfigUpdate):
    """
    Update multiple configuration values at once.

    Note: Changes take effect after application restart.
    """
    if not body.updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    try:
        configs = await config_service.bulk_update(body.updates)
        return configs
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/health", response_model=List[ServiceHealth])
async def get_system_health() -> List[ServiceHealth]:
    services: List[ServiceHealth] = [
        ServiceHealth(name="API", status="healthy", last_heartbeat="Just now"),
    ]

    # PostgreSQL health
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        services.append(ServiceHealth(name="PostgreSQL", status="healthy", last_heartbeat="Just now"))
    except Exception as exc:
        services.append(
            ServiceHealth(
                name="PostgreSQL",
                status="error",
                last_heartbeat="Unavailable",
                message=_short_error(exc),
            )
        )

    # Redis health
    redis = None
    try:
        redis = await get_async_redis()
        await redis.ping()
        services.append(ServiceHealth(name="Redis Streams", status="healthy", last_heartbeat="Just now"))
    except Exception as exc:
        services.append(
            ServiceHealth(
                name="Redis Streams",
                status="error",
                last_heartbeat="Unavailable",
                message=_short_error(exc),
            )
        )

    # Consumer health (idle time from Redis consumer groups)
    consumers = [
        ("Signal Consumer", StreamNames.MARKET_BARS, "signal-processors"),
        ("Portfolio Consumer", StreamNames.SIGNALS, "portfolio-managers"),
        ("Order Consumer", StreamNames.TARGETS, "order-managers"),
        ("Broker Consumer", StreamNames.ORDERS, "brokers"),
        ("Ledger Consumer", StreamNames.FILLS, "accountants"),
        ("Monitor Consumer", StreamNames.PORTFOLIO_STATE, "monitors"),
    ]

    for name, stream, group in consumers:
        if redis is None:
            services.append(
                ServiceHealth(
                    name=name,
                    status="error",
                    last_heartbeat="Unavailable",
                    message="Redis unavailable",
                )
            )
            continue
        try:
            info = await redis.xinfo_consumers(stream, group)
        except ResponseError:
            services.append(
                ServiceHealth(
                    name=name,
                    status="error",
                    last_heartbeat="Unavailable",
                    message="No consumer group",
                )
            )
            continue
        except Exception as exc:
            services.append(
                ServiceHealth(
                    name=name,
                    status="error",
                    last_heartbeat="Unavailable",
                    message=_short_error(exc),
                )
            )
            continue

        if not info:
            services.append(
                ServiceHealth(
                    name=name,
                    status="error",
                    last_heartbeat="Unavailable",
                    message="No consumers registered",
                )
            )
            continue

        idle_ms = min(int(row.get("idle", 0)) for row in info)
        status = _status_for_idle(idle_ms)
        last_heartbeat = _format_idle(idle_ms)
        message = None
        if status != "healthy":
            message = f"Idle for {last_heartbeat}"

        services.append(
            ServiceHealth(
                name=name,
                status=status,
                last_heartbeat=last_heartbeat,
                message=message,
            )
        )

    return services


@router.post("/portfolio-sync", response_model=PortfolioSyncResponse)
async def sync_portfolio(body: PortfolioSyncRequest) -> PortfolioSyncResponse:
    service = PortfolioSyncService()
    try:
        result = await service.sync_portfolio(body.portfolio_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_short_error(exc)) from exc
    return PortfolioSyncResponse(**result)


def _format_idle(idle_ms: int) -> str:
    if idle_ms <= 1000:
        return "Just now"
    seconds = idle_ms // 1000
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    return f"{hours}h ago"


def _status_for_idle(idle_ms: int) -> Literal["healthy", "warning", "error"]:
    idle_sec = idle_ms / 1000
    if idle_sec <= settings.HEALTH_CONSUMER_WARN_SEC:
        return "healthy"
    if idle_sec <= settings.HEALTH_CONSUMER_ERROR_SEC:
        return "warning"
    return "error"


def _short_error(exc: Exception) -> str:
    return str(exc).splitlines()[0] if str(exc) else "Unavailable"
