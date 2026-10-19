"""
Auto-generated from packages/contracts/sse_events.schema.json
DO NOT EDIT DIRECTLY. Run `python packages/contracts/scripts/generate_contracts.py` to regenerate.
"""

from typing import Any, Dict, Literal
from pydantic import BaseModel, Field

SSEEventType = Literal[
    "processing_started",
    "resolution_ready",
    "hitl_ready",
    "dispatched",
    "tracker_update",
    "complete",
    "error",
]


class SSEEventEnvelope(BaseModel):
    event_type: SSEEventType = Field(..., description="Type of SSE event")
    thread_id: str = Field(..., description="LangGraph thread ID")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event payload data")
