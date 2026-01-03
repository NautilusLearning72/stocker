from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import asyncio
import logging
import os
import json
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
from redis.asyncio import Redis
from stocker.core.config import settings
from stocker.core.metrics import metrics

logger = logging.getLogger(__name__)

def _redact_db_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        username = parts.username or ""
        password = parts.password
        hostname = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
        auth = ""
        if username:
            auth = f"{username}:{'***' if password else ''}@"
        netloc = f"{auth}{hostname}{port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        return url

class BaseStreamConsumer(ABC):
    """Base class for Redis Stream consumers."""

    def __init__(
        self,
        redis_url: str,
        stream_name: str,
        consumer_group: str,
        consumer_name: Optional[str] = None,
        block_ms: int = 5000,
        batch_count: int = 1
    ):
        self.redis_url = redis_url
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name or f"{consumer_group}-{os.getpid()}"
        self.block_ms = block_ms
        self.batch_count = batch_count
        self._running = False
        self.redis: Optional[Redis] = None

    async def start(self) -> None:
        """Start consuming from the stream."""
        self.redis = Redis.from_url(self.redis_url, decode_responses=True)
        logger.info("Using database %s", _redact_db_url(settings.DATABASE_URL))
        
        # Connect metrics emitter to Redis for cross-process visibility
        metrics.set_redis(self.redis)
        
        # Create consumer group if not exists
        try:
            # MKSTREAM=True creates the stream if it doesn't exist
            # id='0' means create group pointing to beginning of stream? 
            # Usually '$' for new messages only, but '0' for replay. 
            # Ideally we want '$' for a live system, but '0' is safer for dev to catch up.
            # Let's use '0' (beginning) to process everything since start of stream creation.
            await self.redis.xgroup_create(
                self.stream_name, self.consumer_group, id="0", mkstream=True
            )
            logger.info(f"Created consumer group {self.consumer_group} on {self.stream_name}")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.info(f"Consumer group {self.consumer_group} already exists")
            else:
                logger.error(f"Error creating consumer group: {e}")

        self._running = True
        logger.info(f"Consumer {self.consumer_name} starting on {self.stream_name}")
        await self._consume_loop()

    async def _consume_loop(self) -> None:
        """Main consumption loop."""
        if not self.redis:
            raise RuntimeError("Redis client not initialized")
            
        while self._running:
            try:
                # Read from group
                # '>' means messages never delivered to other consumers in this group
                messages = await self.redis.xreadgroup(
                    self.consumer_group,
                    self.consumer_name,
                    {self.stream_name: ">"},
                    count=self.batch_count,
                    block=self.block_ms,
                )
                
                if not messages:
                    # No new messages, maybe check pending messages (claim)
                    # For simplicity v1, we skip claiming pending messages of dead consumers
                    continue
                    
                for stream_name, stream_messages in messages:
                    for message_id, data in stream_messages:
                        await self._process_with_retry(message_id, data)
                        
            except asyncio.CancelledError:
                self._running = False
                break
            except Exception as e:
                logger.error(f"Error in consume loop: {e}")
                await asyncio.sleep(5) # Backoff

    async def _process_with_retry(
        self, message_id: str, data: Dict[str, Any], max_retries: int = 3
    ) -> None:
        """Process message with retry logic."""
        if not self.redis:
            return

        for attempt in range(max_retries):
            try:
                await self.process_message(message_id, data)
                await self.redis.xack(self.stream_name, self.consumer_group, message_id)
                return
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{max_retries} failed for msg {message_id}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    await self._send_to_dlq(message_id, data, str(e))
                    # ACK it so we don't get stuck forever? 
                    # Yes, move to DLQ and ACK from main stream.
                    await self.redis.xack(self.stream_name, self.consumer_group, message_id)

    async def _send_to_dlq(
        self, message_id: str, data: Dict[str, Any], error: str
    ) -> None:
        """Send failed message to dead letter queue."""
        if not self.redis:
            return
            
        dlq_stream = f"{self.stream_name}-dlq"
        await self.redis.xadd(dlq_stream, {
            "original_id": message_id,
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
            "payload": json.dumps(data) # Store original payload safely
        })
        logger.error(f"Sent {message_id} to DLQ: {dlq_stream}")

    @abstractmethod
    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        """Process a single message. Must be implemented by subclass."""
        pass

    async def is_kill_switch_active(self, portfolio_id: str) -> bool:
        """Check if kill switch is active for this portfolio.
        
        Returns True if trading should be halted.
        """
        if not self.redis:
            return False
            
        try:
            kill_switch_data = await self.redis.get(f"kill_switch:{portfolio_id}")
            if kill_switch_data:
                data = json.loads(kill_switch_data)
                if data.get("active", False):
                    source = data.get("source", "unknown")
                    logger.warning(
                        f"Kill switch active for {portfolio_id}: {data.get('reason', 'unknown')} ({source})"
                    )
                    return True
        except Exception as e:
            logger.error(f"Error checking kill switch: {e}")
            # On error, be conservative and don't block trading
            
        return False

    async def stop(self) -> None:
        """Gracefully stop the consumer."""
        self._running = False
        if self.redis:
            await self.redis.close()
