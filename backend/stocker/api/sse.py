import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
from stocker.core.redis import get_async_redis

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/stream-test")
async def stream_test(request: Request) -> EventSourceResponse:
    """Simple SSE test endpoint without Redis."""
    async def simple_generator() -> AsyncGenerator[dict, None]:
        yield {"event": "connected", "data": json.dumps({"message": "Test stream connected"})}
        count = 0
        while count < 100:
            await asyncio.sleep(2)
            count += 1
            yield {"event": "ping", "data": json.dumps({"count": count})}

    return EventSourceResponse(simple_generator(), ping=15)


@router.get("/stream")
async def message_stream(request: Request) -> EventSourceResponse:
    """
    Server-Sent Events endpoint.
    Streams updates from Redis to connected clients.
    """
    async def event_generator() -> AsyncGenerator[dict, None]:
        pubsub = None
        try:
            redis = await get_async_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe("ui-updates")

            # Yield initial connection message
            yield {
                "event": "connected",
                "data": json.dumps({"message": "Connected to Stocker Stream"})
            }

            while True:
                # Check for client disconnect using try/except pattern
                try:
                    disconnected = await request.is_disconnected()
                    if disconnected:
                        break
                except Exception:
                    # If we can't check disconnect status, continue anyway
                    pass

                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

                if message and message.get("data"):
                    try:
                        # With decode_responses=True, data is already a string
                        data_str = message["data"]
                        if isinstance(data_str, bytes):
                            data_str = data_str.decode("utf-8")
                        yield {
                            "event": "update",
                            "data": data_str
                        }
                    except Exception as e:
                        logger.error(f"Error parsing message: {e}")

                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.info("Stream connection cancelled")
        except Exception as e:
            logger.error(f"SSE generator error: {e}")
            # Yield error event before exiting
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }
        finally:
            if pubsub:
                try:
                    await pubsub.unsubscribe("ui-updates")
                except Exception:
                    pass

    return EventSourceResponse(event_generator(), ping=15)
