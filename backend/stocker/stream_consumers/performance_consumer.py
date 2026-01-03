"""
Performance tracking consumer.

Listens to TARGETS stream for exit_triggered events and caches exit reasons
in Redis for the ledger consumer to pick up when positions close.

This enriches SignalPerformance records with detailed exit reasons like
"Trailing stop: 3.0x ATR from peak", "ATR exit: 2.0x ATR loss from entry", etc.
"""

import asyncio
import logging
from typing import Dict, Any

from stocker.stream_consumers.base import BaseStreamConsumer
from stocker.core.config import settings
from stocker.core.redis import StreamNames

logger = logging.getLogger(__name__)


class PerformanceConsumer(BaseStreamConsumer):
    """
    Captures exit reasons from TARGETS stream for signal performance tracking.

    Workflow:
    1. Listen for exit_triggered events on TARGETS stream
    2. Extract exit reason from event
    3. Cache in Redis with portfolio_id + symbol key
    4. LedgerConsumer retrieves reason when position actually closes
    """

    def __init__(self):
        super().__init__(
            redis_url=settings.REDIS_URL,
            stream_name=StreamNames.TARGETS,
            consumer_group="performance-trackers",
        )
        self._exit_reason_ttl_sec = 60 * 60 * 24 * 7  # 7 days

    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        """Process TARGETS stream events to cache exit reasons."""
        event_type = data.get("event_type")

        # Only process exit_triggered events
        if event_type != "exit_triggered":
            return

        portfolio_id = data.get("portfolio_id", "main")
        symbol = data.get("symbol")
        reason = data.get("reason", "exit_triggered")
        is_exit = data.get("is_exit")

        if not symbol:
            logger.warning("exit_triggered event missing symbol")
            return

        # Verify it's actually an exit (not just a target update)
        if is_exit != "true":
            return

        # Cache exit reason in Redis for ledger consumer
        if self.redis:
            await self._cache_exit_reason(portfolio_id, symbol, reason)
            logger.info(
                f"Cached exit reason for {symbol}: {reason}"
            )
        else:
            logger.warning("Redis not connected, cannot cache exit reason")

    async def _cache_exit_reason(
        self,
        portfolio_id: str,
        symbol: str,
        reason: str
    ) -> None:
        """Store exit reason in Redis hash with TTL."""
        hash_key = f"pending_exit_reasons:{portfolio_id}"

        # Store reason in hash
        await self.redis.hset(hash_key, symbol, reason)

        # Set/refresh TTL on hash
        await self.redis.expire(hash_key, self._exit_reason_ttl_sec)

        logger.debug(
            f"Stored exit reason in {hash_key}[{symbol}]: {reason}"
        )


async def main():
    """Run the performance consumer."""
    consumer = PerformanceConsumer()
    try:
        await consumer.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await consumer.stop()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(main())
