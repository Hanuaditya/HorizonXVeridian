"""Contract-compliant SSE manager with Last-Event-ID replay buffer and 15s heartbeats."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from contracts.sse_events import SSEEventEnvelope

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 15
MAX_QUEUE_SIZE = 200
MAX_HISTORY_PER_THREAD = 100


class SSEManager:
    """Manages per-thread event queues, org scoping, and numbered SSE replay buffers."""

    def __init__(self) -> None:
        self._queues: Dict[str, List[asyncio.Queue]] = {}
        self._history: Dict[str, List[tuple[int, Dict[str, Any]]]] = {}
        self._thread_orgs: Dict[str, str] = {}
        self._seq: Dict[str, int] = {}

    def register(self, thread_id: str, org_id: Optional[str] = None) -> None:
        if thread_id not in self._queues:
            self._queues[thread_id] = []
        if thread_id not in self._history:
            self._history[thread_id] = []
        if org_id:
            self._thread_orgs[thread_id] = org_id

    def get_thread_org(self, thread_id: str) -> Optional[str]:
        return self._thread_orgs.get(thread_id)

    async def push_event(
        self,
        thread_id: str,
        event_type: str,
        payload: Dict[str, Any],
        org_id: Optional[str] = None,
    ) -> int:
        self.register(thread_id, org_id=org_id)
        next_id = self._seq.get(thread_id, 0) + 1
        self._seq[thread_id] = next_id

        envelope = SSEEventEnvelope(
            event_type=event_type,  # type: ignore[arg-type]
            thread_id=thread_id,
            payload=payload,
        ).model_dump(mode="json")

        history = self._history[thread_id]
        history.append((next_id, envelope))
        if len(history) > MAX_HISTORY_PER_THREAD:
            del history[0]

        for queue in list(self._queues.get(thread_id, [])):
            try:
                queue.put_nowait((next_id, envelope))
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait((next_id, envelope))
                except Exception:
                    pass
        return next_id

    async def push_complete(self, thread_id: str, org_id: Optional[str] = None) -> None:
        await self.push_event(
            thread_id,
            "complete",
            {"message": "Workflow complete."},
            org_id=org_id,
        )
        for queue in list(self._queues.get(thread_id, [])):
            await queue.put(None)

    async def push_error(self, thread_id: str, error: str, org_id: Optional[str] = None) -> None:
        await self.push_event(thread_id, "error", {"error": error}, org_id=org_id)
        for queue in list(self._queues.get(thread_id, [])):
            await queue.put(None)

    async def stream_events(
        self,
        thread_id: str,
        last_event_id: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        self.register(thread_id)
        queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self._queues[thread_id].append(queue)

        try:
            # Replay missed events when reconnecting with Last-Event-ID (or initial replay from 0)
            since_id = last_event_id if last_event_id is not None else 0
            for eid, envelope in list(self._history.get(thread_id, [])):
                if eid > since_id:
                    yield f"id: {eid}\ndata: {json.dumps(envelope, default=str)}\n\n"
                    if envelope.get("event_type") == "complete":
                        return

            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL_SECONDS)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue

                if item is None:
                    break
                eid, envelope = item
                yield f"id: {eid}\ndata: {json.dumps(envelope, default=str)}\n\n"
                if envelope.get("event_type") in ("complete", "error"):
                    break
        finally:
            if thread_id in self._queues and queue in self._queues[thread_id]:
                self._queues[thread_id].remove(queue)


sse_manager = SSEManager()
