import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
from redis.asyncio import Redis
from stocker.core.config import settings
from stocker.core.redis import get_async_redis

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/stream")
async def message_stream(request: Request) -> EventSourceResponse:
    """
    Server-Sent Events endpoint.
    Streams updates from Redis to connected clients.
    """
    async def event_generator() -> AsyncGenerator[dict, None]:
        redis = await get_async_redis()
        pubsub = redis.pubsub()
        
        # Subscribe to channels we want to broadcast to UI
        # We need the consumers to PUBLISH to these channels in addition to XADD streams
        # Or we can XREAD streams. PubSub is easier for "broadcast" to multiple UI clients.
        await pubsub.subscribe("ui-updates")
        
        try:
            # Yield initial connection message
            yield {
                "event": "connected",
                "data": json.dumps({"message": "Connected to Stocker Stream"})
            }
            
            while True:
                # Check for client disconnect
                if await request.is_disconnected():
                    break
                    
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                
                if message:
                    # Message format from Redis: {'type': 'message', 'pattern': None, 'channel': b'ui-updates', 'data': b'{...}'}
                    try:
                        data_str = message["data"].decode("utf-8")
                        # We expect data to be a JSON string with "type" and "payload"
                        yield {
                            "event": "update",
                            "data": data_str
                        }
                    except Exception as e:
                        logger.error(f"Error parsing message: {e}")
                        
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            logger.info("Stream connection cancelled")
        finally:
            await pubsub.unsubscribe("ui-updates")
            # We don't close the shared redis connection here, just the pubsub usage
            
    return EventSourceResponse(event_generator())
