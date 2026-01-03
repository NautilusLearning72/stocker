"""
Admin API Router.

Provides endpoints for managing strategy configuration.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Literal

from fastapi import APIRouter, HTTPException
from sqlalchemy import text, select
from redis.exceptions import ResponseError
from pydantic import BaseModel

from stocker.services.config_service import config_service, TRADING_PARAMS
from stocker.services.portfolio_sync_service import PortfolioSyncService
from stocker.core.database import AsyncSessionLocal
from stocker.core.redis import get_async_redis, StreamNames
from stocker.core.config import settings
from stocker.models.order import Order

router = APIRouter()
logger = logging.getLogger(__name__)


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


class KillSwitchStatusResponse(BaseModel):
    portfolio_id: str
    active: bool
    triggered_at: Optional[str] = None
    reason: Optional[str] = None
    source: Optional[Literal["auto", "manual"]] = None


class KillSwitchActionRequest(BaseModel):
    portfolio_id: str = "main"
    reason: Optional[str] = None


class KillSwitchResetRequest(BaseModel):
    portfolio_id: str = "main"


class KillSwitchActionResponse(KillSwitchStatusResponse):
    cancelled_orders: int = 0


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
        ("Exit Consumer", StreamNames.MARKET_BARS, "exit-evaluators"),
        ("Portfolio Consumer", StreamNames.SIGNALS, "portfolio-managers"),
        ("Order Consumer", StreamNames.TARGETS, "order-managers"),
        ("Broker Consumer", StreamNames.ORDERS, "brokers"),
        ("Ledger Consumer", StreamNames.FILLS, "accountants"),
        ("Performance Consumer", StreamNames.TARGETS, "performance-trackers"),
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


@router.get("/kill-switch/status", response_model=KillSwitchStatusResponse)
async def get_kill_switch_status(portfolio_id: str = "main") -> KillSwitchStatusResponse:
    try:
        redis = await get_async_redis()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=_short_error(exc)) from exc

    status = await _load_kill_switch_status(redis, portfolio_id)
    return status


@router.post("/kill-switch/activate", response_model=KillSwitchActionResponse)
async def activate_kill_switch(body: KillSwitchActionRequest) -> KillSwitchActionResponse:
    try:
        redis = await get_async_redis()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=_short_error(exc)) from exc

    existing = await _read_kill_switch(redis, body.portfolio_id)
    if existing and existing.get("active", False):
        return _build_kill_switch_action_response(body.portfolio_id, existing, 0)

    reason = (body.reason or "").strip() or "Manual halt requested"
    triggered_at = datetime.utcnow().isoformat()
    state = {
        "active": True,
        "triggered_at": triggered_at,
        "reason": reason,
        "source": "manual",
    }

    await redis.set(_kill_switch_key(body.portfolio_id), json.dumps(state))
    cancelled_orders = await _cancel_pending_orders(body.portfolio_id)

    await _publish_alert(
        redis,
        "CRITICAL",
        "KILL SWITCH ACTIVATED",
        f"Reason: {reason}. Cancelled {cancelled_orders} pending orders. "
        "Trading halted until manual override.",
    )
    await _publish_kill_switch_update(redis, body.portfolio_id, state, cancelled_orders)

    logger.warning(
        "Kill switch manually activated for %s (cancelled %s orders).",
        body.portfolio_id,
        cancelled_orders,
    )

    return _build_kill_switch_action_response(body.portfolio_id, state, cancelled_orders)


@router.post("/kill-switch/reset", response_model=KillSwitchStatusResponse)
async def reset_kill_switch(body: KillSwitchResetRequest) -> KillSwitchStatusResponse:
    try:
        redis = await get_async_redis()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=_short_error(exc)) from exc

    await redis.delete(_kill_switch_key(body.portfolio_id))

    await _publish_alert(
        redis,
        "INFO",
        "Kill switch reset",
        f"Kill switch for {body.portfolio_id} has been manually reset. Trading resumed.",
    )
    await _publish_kill_switch_update(
        redis,
        body.portfolio_id,
        {
            "active": False,
            "triggered_at": None,
            "reason": None,
            "source": None,
        },
    )

    logger.info("Kill switch reset for %s.", body.portfolio_id)

    return KillSwitchStatusResponse(portfolio_id=body.portfolio_id, active=False)


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


def _kill_switch_key(portfolio_id: str) -> str:
    return f"kill_switch:{portfolio_id}"


async def _read_kill_switch(redis, portfolio_id: str) -> Optional[Dict[str, Any]]:
    raw = await redis.get(_kill_switch_key(portfolio_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Failed to decode kill switch state for %s.", portfolio_id)
        return None


async def _load_kill_switch_status(redis, portfolio_id: str) -> KillSwitchStatusResponse:
    data = await _read_kill_switch(redis, portfolio_id) or {}
    active = bool(data.get("active", False))
    return KillSwitchStatusResponse(
        portfolio_id=portfolio_id,
        active=active,
        triggered_at=data.get("triggered_at") if active else None,
        reason=data.get("reason") if active else None,
        source=data.get("source") if active else None,
    )


def _build_kill_switch_action_response(
    portfolio_id: str,
    data: Dict[str, Any],
    cancelled_orders: int,
) -> KillSwitchActionResponse:
    active = bool(data.get("active", False))
    return KillSwitchActionResponse(
        portfolio_id=portfolio_id,
        active=active,
        triggered_at=data.get("triggered_at") if active else None,
        reason=data.get("reason") if active else None,
        source=data.get("source") if active else None,
        cancelled_orders=cancelled_orders,
    )


async def _cancel_pending_orders(portfolio_id: str) -> int:
    cancelled = 0

    async with AsyncSessionLocal() as session:
        stmt = select(Order).where(
            Order.portfolio_id == portfolio_id,
            Order.status.in_(["NEW", "PENDING", "PENDING_EXECUTION"]),
        )
        result = await session.execute(stmt)
        pending_orders = result.scalars().all()

        for order in pending_orders:
            order.status = "CANCELLED"
            cancelled += 1

        await session.commit()

    return cancelled


async def _publish_alert(redis, level: str, title: str, message: str) -> None:
    await redis.xadd(
        StreamNames.ALERTS,
        {
            "level": level,
            "title": title,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


async def _publish_kill_switch_update(
    redis,
    portfolio_id: str,
    state: Dict[str, Any],
    cancelled_orders: Optional[int] = None,
) -> None:
    payload = {
        "portfolio_id": portfolio_id,
        "kill_switch_active": bool(state.get("active", False)),
        "kill_switch_reason": state.get("reason"),
        "kill_switch_source": state.get("source"),
        "triggered_at": state.get("triggered_at"),
    }
    if cancelled_orders is not None:
        payload["cancelled_orders"] = cancelled_orders
    await redis.publish(
        "ui-updates",
        json.dumps(
            {
                "type": "kill_switch_update",
                "payload": payload,
            }
        ),
    )


# ---------- Backfill Endpoint ----------


class BackfillRequest(BaseModel):
    """Request schema for on-demand price backfill."""
    symbols: List[str]
    days: int = 200


class DataQualityAlertResponse(BaseModel):
    """Response schema for data quality alerts."""
    symbol: str
    date: str
    issue_type: str
    message: str
    severity: str


class BackfillResponse(BaseModel):
    """Response schema for backfill operation."""
    symbols_requested: int
    records_processed: int
    alerts: List[DataQualityAlertResponse]


@router.post("/backfill", response_model=BackfillResponse)
async def trigger_backfill(payload: BackfillRequest):
    """
    Trigger an on-demand price history backfill for specified symbols.
    
    This fetches historical daily bars from yfinance and stores them in the database.
    Default is 200 days of history (required for strategy lookback).
    """
    from datetime import date, timedelta
    from stocker.services.market_data_service import MarketDataService

    symbols = [s.upper().strip() for s in payload.symbols if s.strip()]
    if not symbols:
        return BackfillResponse(
            symbols_requested=0,
            records_processed=0,
            alerts=[],
        )

    end_date = date.today()
    start_date = end_date - timedelta(days=payload.days)

    service = MarketDataService(provider_name="yfinance")
    records_processed, alerts = await service.fetch_and_store_daily_bars(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
    )

    return BackfillResponse(
        symbols_requested=len(symbols),
        records_processed=records_processed,
        alerts=[
            DataQualityAlertResponse(
                symbol=a.symbol,
                date=str(a.date),
                issue_type=a.issue_type,
                message=a.message,
                severity=a.severity,
            )
            for a in alerts
        ],
    )

