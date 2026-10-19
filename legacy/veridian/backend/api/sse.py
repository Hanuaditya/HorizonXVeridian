"""
api/sse.py — Server-Sent Events Manager
========================================
Maintains a registry of asyncio.Queue instances keyed by thread_id.
Graph nodes push events in; the /api/stream/{thread_id} endpoint drains
them as SSE to the Next.js frontend.

Event format (JSON-encoded in the SSE `data` field):
    {
        "event_type": "task_extracted" | "firewall_update" | "resolution_ready"
                     | "hitl_ready" | "dispatched" | "error" | "complete",
        "thread_id":  str,
        "payload":    dict   # event-specific data
    }
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, Optional

logger = logging.getLogger(__name__)

# SSE heartbeat interval — keeps the connection alive through proxy timeouts
HEARTBEAT_INTERVAL_SECONDS = 15

# Maximum events buffered per thread before dropping old ones
MAX_QUEUE_SIZE = 100


class SSEManager:
    """
    Thread-safe (asyncio-safe) registry of per-thread event queues.

    Lifecycle:
      1. POST /api/meeting-ended creates a thread_id and registers it.
      2. GET  /api/stream/{thread_id} drains the queue as SSE.
      3. Graph background tasks call push_event() from any coroutine.
      4. Sentinel None pushed when graph finishes — stream closes cleanly.
    """

    def __init__(self) -> None:
        self._queues: Dict[str, asyncio.Queue] = {}

    def register(self, thread_id: str) -> None:
        """Create a new queue for this thread. Idempotent — safe to call twice."""
        if thread_id not in self._queues:
            self._queues[thread_id] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
            logger.debug("SSEManager: registered thread '%s'.", thread_id)

    def deregister(self, thread_id: str) -> None:
        """Remove the queue when the SSE connection closes."""
        self._queues.pop(thread_id, None)
        logger.debug("SSEManager: deregistered thread '%s'.", thread_id)

    async def push_event(
        self,
        thread_id: str,
        event_type: str,
        payload: dict,
    ) -> None:
        """
        Push a structured event onto the thread's queue.
        Creates the queue if it doesn't exist (e.g. graph step before client connects).
        """
        if thread_id not in self._queues:
            self.register(thread_id)

        event = {
            "event_type": event_type,
            "thread_id": thread_id,
            "payload": payload,
        }

        try:
            self._queues[thread_id].put_nowait(event)
            logger.debug(
                "SSEManager: pushed '%s' event to thread '%s'.",
                event_type, thread_id,
            )
        except asyncio.QueueFull:
            # Drop oldest event to make room
            try:
                self._queues[thread_id].get_nowait()
                self._queues[thread_id].put_nowait(event)
                logger.warning(
                    "SSEManager: queue full for thread '%s' — dropped oldest event.",
                    thread_id,
                )
            except Exception:
                pass

    async def push_complete(self, thread_id: str) -> None:
        """Push a 'complete' event then the None sentinel to close the stream."""
        await self.push_event(thread_id, "complete", {"message": "Graph execution complete."})
        if thread_id in self._queues:
            await self._queues[thread_id].put(None)  # Sentinel closes the generator

    async def push_error(self, thread_id: str, error: str) -> None:
        """Push an error event then close the stream."""
        await self.push_event(thread_id, "error", {"error": error})
        if thread_id in self._queues:
            await self._queues[thread_id].put(None)

    async def stream_events(
        self,
        thread_id: str,
    ) -> AsyncGenerator[str, None]:
        """
        Async generator that yields SSE-formatted strings.

        Yields:
            "data: {json}\\n\\n"  for each event
            ": heartbeat\\n\\n"   every HEARTBEAT_INTERVAL_SECONDS (keeps proxies alive)

        Terminates when:
            - A None sentinel is received from the queue
            - The client disconnects (GeneratorExit caught by FastAPI)
        """
        self.register(thread_id)
        queue = self._queues[thread_id]

        try:
            while True:
                try:
                    # Wait for event with heartbeat timeout
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=HEARTBEAT_INTERVAL_SECONDS,
                    )
                except asyncio.TimeoutError:
                    # Heartbeat — keeps SSE connection alive through nginx/load-balancer
                    yield ": heartbeat\n\n"
                    continue

                # None sentinel = graph is done, close the stream
                if event is None:
                    logger.info(
                        "SSEManager: stream for thread '%s' closed by sentinel.",
                        thread_id,
                    )
                    break

                # Yield SSE-formatted event
                data = json.dumps(event, default=str)
                yield f"data: {data}\n\n"

        except GeneratorExit:
            logger.info(
                "SSEManager: client disconnected from thread '%s'.",
                thread_id,
            )
        finally:
            self.deregister(thread_id)


# ---------------------------------------------------------------------------
# Singleton — imported by main.py and all route handlers
# ---------------------------------------------------------------------------
sse_manager = SSEManager()
