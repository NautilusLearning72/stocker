import asyncio
import logging
from typing import Dict, Any

from stocker.stream_consumers.base import BaseStreamConsumer
from stocker.core.config import settings
from stocker.core.redis import StreamNames

logger = logging.getLogger(__name__)

class MonitorConsumer(BaseStreamConsumer):
    """
    Listens for ALL events (or critical ones) to log/alert.
    Can be used to push updates to Frontend via WebSocket (later).
    """
    
    def __init__(self):
        # Listen to MULTIPLE streams if Base supports it? 
        # Base implementation takes single stream. 
        # We can spin up multiple consumers or modify Base.
        # For Phase 4, let's just monitor 'portfolio-state' or 'fills'
        super().__init__(
            redis_url=settings.REDIS_URL,
            stream_name=StreamNames.FILLS, # Monitor fills for now
            consumer_group="monitors"
        )

    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        event_type = data.get("event_type", "unknown")
        # Log High Visibility Event
        logger.info(f"👀 MONITOR: {event_type} - {data}")
        
        # TODO: Push to WebSocket for UI

if __name__ == "__main__":
    async def main():
        consumer = MonitorConsumer()
        try:
            await consumer.start()
        except KeyboardInterrupt:
            await consumer.stop()
    
    asyncio.run(main())
