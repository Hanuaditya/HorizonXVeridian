"""
api/routes/meeting.py — POST /api/meeting-ended
================================================
Receives meeting webhook, initialises AgentState, kicks off Graph A in
a background task (returns 200 immediately), and returns the thread_id
so the frontend can open the SSE stream.
"""

import logging
import uuid
from typing import Dict, Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from agent.graph_a import graph_a
from agent.state import AgentState
from api.sse import sse_manager

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class MeetingWebhookRequest(BaseModel):
    meeting_id: str
    transcript: str


class MeetingWebhookResponse(BaseModel):
    status: str
    thread_id: str
    meeting_id: str


# ---------------------------------------------------------------------------
# Background task — runs Graph A
# ---------------------------------------------------------------------------

async def _run_graph_a(thread_id: str, initial_state: Dict[str, Any]) -> None:
    """
    Invoke Graph A asynchronously. Pushes SSE events at each major step.
    Graph pauses automatically at hitl_interrupt_node (interrupt_before).
    """
    config = {"configurable": {"thread_id": thread_id}}
    meeting_id = initial_state.get("meeting_id", thread_id)

    try:
        await sse_manager.push_event(thread_id, "processing_started", {
            "meeting_id": meeting_id,
            "message": "Graph A started — ingesting transcript…",
        })

        # Graph A runs synchronously inside the background task.
        # It will pause at hitl_interrupt_node — invoke returns partial state.
        # The frontend resumes via POST /api/hitl-resume.
        result = graph_a.invoke(initial_state, config=config)

        # Detect if graph dropped (duplicate meeting)
        if result and result.get("__drop__"):
            await sse_manager.push_event(thread_id, "error", {
                "error": f"Meeting '{meeting_id}' was already processed (idempotency drop).",
            })
            await sse_manager.push_complete(thread_id)
            return

        # Check if graph paused at HITL interrupt
        # When interrupted, result is a snapshot — tasks and resolutions are populated
        if result and result.get("tasks"):
            tasks_out = result.get("tasks", {})
            resolutions_out = result.get("resolutions", [])
            needs_hitl = any(
                r.get("suggested_action") != "PROCEED"
                for r in resolutions_out
            )

            await sse_manager.push_event(thread_id, "resolution_ready", {
                "tasks": tasks_out,
                "resolutions": resolutions_out,
                "key_decisions": result.get("key_decisions", []),
                "meeting_context": result.get("meeting_context", {}),
            })

            if needs_hitl:
                await sse_manager.push_event(thread_id, "hitl_ready", {
                    "meeting_id": meeting_id,
                    "thread_id": thread_id,
                    "message": "Graph paused — awaiting manager approval.",
                    "tasks": tasks_out,
                    "resolutions": resolutions_out,
                    "key_decisions": result.get("key_decisions", []),
                    "meeting_context": result.get("meeting_context", {}),
                })
                # Do NOT push complete — graph is paused, not done
                return

        # Graph ran to completion without HITL pause (all tasks PROCEED)
        await sse_manager.push_event(thread_id, "dispatched", {
            "dispatched_tickets": (result or {}).get("dispatched_tickets", []),
            "message": "All tasks dispatched — no human review required.",
        })
        await sse_manager.push_complete(thread_id)

    except Exception as exc:
        logger.error(
            "Graph A error for thread '%s': %s", thread_id, exc, exc_info=True
        )
        await sse_manager.push_error(thread_id, str(exc))


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/meeting-ended", response_model=MeetingWebhookResponse)
async def meeting_ended(
    body: MeetingWebhookRequest,
    background_tasks: BackgroundTasks,
) -> MeetingWebhookResponse:
    """
    POST /api/meeting-ended

    Trigger point for Graph A. Returns immediately with thread_id so the
    frontend can open GET /api/stream/{thread_id} for real-time updates.
    """
    thread_id = f"meeting-{body.meeting_id}-{uuid.uuid4().hex[:8]}"

    # Register SSE queue before starting background task
    sse_manager.register(thread_id)

    # Build initial AgentState (TypedDict-compatible dict)
    initial_state: Dict[str, Any] = {
        "meeting_id": body.meeting_id,
        "transcript": body.transcript,
        "tasks": {},
        "key_decisions": [],
        "meeting_context": {},
        "resolutions": [],
        "interrupt_payload": None,
        "hitl_decisions": {},
        "dispatched_tickets": [],
        "manager_approved": False,
        "turn_count": 0,
        "tracker_task_id": None,
        "tracker_assignee": None,
        "last_slack_reply": None,
        "parsed_intent": None,
        "intent_confidence": None,
    }

    logger.info(
        "POST /api/meeting-ended: meeting_id='%s' → thread_id='%s'.",
        body.meeting_id, thread_id,
    )

    # Kick off Graph A — returns 200 immediately
    background_tasks.add_task(_run_graph_a, thread_id, initial_state)

    return MeetingWebhookResponse(
        status="processing",
        thread_id=thread_id,
        meeting_id=body.meeting_id,
    )
