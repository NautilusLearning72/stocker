"""
Redis connection and stream management.

Provides Redis client for both sync and async operations.
"""

from typing import Optional
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from stocker.core.config import settings

# Synchronous Redis client (for Celery tasks)
redis_client: Optional[Redis] = None


def get_redis() -> Redis:
    """Get synchronous Redis client."""
    global redis_client
    if redis_client is None:
        redis_client = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
        )
    return redis_client


# Async Redis client (for stream consumers)
async_redis_client: Optional[AsyncRedis] = None


async def get_async_redis() -> AsyncRedis:
    """Get async Redis client."""
    global async_redis_client
    if async_redis_client is None:
        async_redis_client = AsyncRedis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
        )
    return async_redis_client


async def close_redis() -> None:
    """Close Redis connections."""
    global redis_client, async_redis_client

    if redis_client is not None:
        redis_client.close()
        redis_client = None

    if async_redis_client is not None:
        await async_redis_client.close()
        async_redis_client = None


# Redis Stream Names
class StreamNames:
    """Redis Stream names for the event bus."""

    MARKET_BARS = "market-bars"
    SIGNALS = "signals"
    TARGETS = "targets"
    ORDERS = "orders"
    FILLS = "fills"
    PORTFOLIO_STATE = "portfolio-state"
    ALERTS = "alerts"


# Consumer Group Names
class ConsumerGroups:
    """Consumer group names for Redis Streams."""

    SIGNAL_PROCESSORS = "signal-processors"
    PORTFOLIO_PROCESSORS = "portfolio-processors"
    ORDER_GENERATORS = "order-generators"
    BROKER_EXECUTORS = "broker-executors"
    LEDGER_PROCESSORS = "ledger-processors"
    SYSTEM_MONITORS = "system-monitors"
