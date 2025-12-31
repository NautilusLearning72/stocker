"""
Metrics API endpoint for observability dashboard.

Provides:
- Summary statistics for metrics
- Real-time metrics stream via SSE
- Historical metrics query
"""
import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from stocker.core.metrics import metrics, MetricEvent
from stocker.core.redis import get_async_redis, StreamNames

router = APIRouter()


class MetricsSummary(BaseModel):
    """Summary of metrics over a time period."""
    period_hours: int
    total_events: int
    by_category: dict
    by_event: dict
    confirmation_rate: Optional[float]
    trailing_stops_triggered: int
    sector_caps_applied: int
    correlation_throttles: int
    orders_created: int
    orders_skipped: int


class MetricEventResponse(BaseModel):
    """Single metric event for API response."""
    timestamp: str
    category: str
    event_type: str
    symbol: Optional[str]
    portfolio_id: str
    value: float
    metadata: dict


@router.get("/summary", response_model=MetricsSummary)
async def get_metrics_summary(
    hours: int = Query(default=24, ge=1, le=168, description="Hours of history to include")
) -> MetricsSummary:
    """
    Get aggregated summary of recent metrics.

    Returns counts and rates for all metric categories.
    """
    summary = metrics.get_summary(hours=hours)
    return MetricsSummary(**summary)


@router.get("/events", response_model=List[MetricEventResponse])
async def get_recent_events(
    category: Optional[str] = Query(default=None, description="Filter by category"),
    event_type: Optional[str] = Query(default=None, description="Filter by event type"),
    symbol: Optional[str] = Query(default=None, description="Filter by symbol"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max events to return"),
    hours: int = Query(default=24, ge=1, le=168, description="Hours of history")
) -> List[MetricEventResponse]:
    """
    Get recent metric events with optional filtering.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    buffer = metrics.get_buffer()

    # Filter events
    events = []
    for event in reversed(buffer):  # Most recent first
        if event.timestamp < cutoff:
            continue
        if category and event.category != category:
            continue
        if event_type and event.event_type != event_type:
            continue
        if symbol and event.symbol != symbol:
            continue

        events.append(MetricEventResponse(
            timestamp=event.timestamp.isoformat(),
            category=event.category,
            event_type=event.event_type,
            symbol=event.symbol,
            portfolio_id=event.portfolio_id,
            value=event.value,
            metadata=event.metadata
        ))

        if len(events) >= limit:
            break

    return events


@router.get("/categories")
async def get_categories() -> dict:
    """
    Get available metric categories and event types.
    """
    return {
        "categories": {
            "signal": [
                "generated",
                "confirmation_check"
            ],
            "exit": [
                "trailing_stop_triggered",
                "atr_exit_triggered",
                "persistence_blocked"
            ],
            "diversification": [
                "sector_cap_applied",
                "asset_class_cap_applied",
                "correlation_throttle"
            ],
            "order": [
                "sizing",
                "skipped",
                "created"
            ],
            "risk": [
                "single_cap_applied",
                "gross_exposure_scaled",
                "drawdown_scaling",
                "kill_switch_triggered"
            ],
            "pipeline": [
                "batch_processed"
            ]
        }
    }


@router.get("/stream")
async def stream_metrics(
    category: Optional[str] = Query(default=None, description="Filter by category")
):
    """
    Server-Sent Events stream of real-time metrics.

    Connect to receive live metric events as they occur.
    """
    async def event_generator():
        """Generate SSE events from Redis stream."""
        redis = await get_async_redis()
        last_id = "$"  # Start from latest

        # Send initial connection event
        yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

        while True:
            try:
                # Read from metrics stream
                result = await redis.xread(
                    {StreamNames.METRICS: last_id},
                    count=10,
                    block=5000  # 5 second timeout
                )

                if result:
                    for stream_name, messages in result:
                        for message_id, data in messages:
                            last_id = message_id

                            # Parse metric event
                            try:
                                event_data = json.loads(data.get("data", "{}"))

                                # Filter by category if specified
                                if category and event_data.get("category") != category:
                                    continue

                                yield f"event: metric\ndata: {json.dumps(event_data)}\n\n"

                            except json.JSONDecodeError:
                                continue

                else:
                    # Send ping to keep connection alive
                    yield f"event: ping\ndata: {json.dumps({'time': datetime.now(timezone.utc).isoformat()})}\n\n"

            except asyncio.CancelledError:
                break
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
                await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/clear")
async def clear_metrics_buffer() -> dict:
    """
    Clear the in-memory metrics buffer.

    Use for testing or after reviewing accumulated metrics.
    """
    count = metrics.clear_buffer()
    return {
        "status": "cleared",
        "events_cleared": count
    }


@router.get("/health")
async def metrics_health() -> dict:
    """
    Health check for metrics system.
    """
    buffer_size = len(metrics.get_buffer())
    redis_connected = metrics.redis is not None

    return {
        "status": "healthy",
        "buffer_size": buffer_size,
        "redis_connected": redis_connected,
        "enabled": metrics._enabled
    }
