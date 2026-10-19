"""
api/routes/hitl.py — POST /api/hitl-resume
============================================
Resumes a paused Graph A with the manager's decisions from the Next.js UI.
Uses LangGraph's Command(resume=...) pattern to continue from the
hitl_interrupt_node checkpoint.
"""

import logging
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from langgraph.types import Command

from agent.graph_a import graph_a
from api.sse import sse_manager

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class HITLResumeRequest(BaseModel):
    thread_id: str
    hitl_decisions: Dict[str, str]   # {task_id: "REFRAME" | "REROUTE" | "DEFER" | "PROCEED" | "OVERRIDE"}


class HITLResumeResponse(BaseModel):
    status: str
    thread_id: str
    message: str


# ---------------------------------------------------------------------------
# Background task — resumes Graph A
# ---------------------------------------------------------------------------

async def _resume_graph_a(thread_id: str, hitl_decisions: Dict[str, str]) -> None:
    """
    Resume Graph A from the hitl_interrupt_node checkpoint.

    LangGraph pattern:
        graph_a.invoke(Command(resume=decisions), config=thread_config)

    The graph continues from where interrupt() was called inside hitl_interrupt_node,
    returning `hitl_decisions` as the `human_response` value.
    """
    config = {"configurable": {"thread_id": thread_id}}

    try:
        await sse_manager.push_event(thread_id, "hitl_resuming", {
            "message": "Manager approved. Resuming dispatch pipeline…",
            "decisions": hitl_decisions,
        })

        logger.info(
            "_resume_graph_a: resuming thread '%s' with %d decisions.",
            thread_id, len(hitl_decisions),
        )

        # Resume — Command(resume=...) feeds the value back into interrupt()
        result = graph_a.invoke(
            Command(resume=hitl_decisions),
            config=config,
        )

        dispatched = (result or {}).get("dispatched_tickets", [])
        logger.info(
            "_resume_graph_a: thread '%s' complete. %d tickets dispatched.",
            thread_id, len(dispatched),
        )

        await sse_manager.push_event(thread_id, "dispatched", {
            "dispatched_tickets": dispatched,
            "meeting_id": (result or {}).get("meeting_id", ""),
            "message": f"{len(dispatched)} ticket(s) created in Jira. Slack DMs sent.",
        })
        await sse_manager.push_complete(thread_id)

    except Exception as exc:
        logger.error(
            "_resume_graph_a: error resuming thread '%s': %s", thread_id, exc, exc_info=True
        )
        await sse_manager.push_error(thread_id, str(exc))


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/hitl-resume", response_model=HITLResumeResponse)
async def hitl_resume(
    body: HITLResumeRequest,
    background_tasks: BackgroundTasks,
) -> HITLResumeResponse:
    """
    POST /api/hitl-resume

    Called by the Next.js Command Center UI when the manager clicks "Approve".
    Resumes the paused Graph A in a background task, returns 200 immediately.
    """
    thread_id = body.thread_id

    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required.")

    if not body.hitl_decisions:
        raise HTTPException(
            status_code=400,
            detail="hitl_decisions cannot be empty. Provide at least one task decision.",
        )

    logger.info(
        "POST /api/hitl-resume: thread='%s' decisions=%s",
        thread_id, body.hitl_decisions,
    )

    # Re-register SSE queue in case the frontend reconnected
    sse_manager.register(thread_id)

    # Resume Graph A — returns 200 immediately
    background_tasks.add_task(_resume_graph_a, thread_id, body.hitl_decisions)

    return HITLResumeResponse(
        status="resuming",
        thread_id=thread_id,
        message="Graph A resuming. Watch the SSE stream for dispatch updates.",
    )
