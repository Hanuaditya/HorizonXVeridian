"""POST /api/hitl-resume — Manager-only human-in-the-loop resume endpoint."""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from langgraph.types import Command
from pydantic import BaseModel

from agent.graph_a import get_graph_a
from api.auth import AuthContext, require_manager
from api.sse import sse_manager
from core.store import get_thread_snapshot, record_approval, save_thread_snapshot

logger = logging.getLogger(__name__)
router = APIRouter()


class HITLResumeRequest(BaseModel):
    thread_id: str
    hitl_decisions: Dict[str, str]


class HITLResumeResponse(BaseModel):
    status: str
    thread_id: str
    approved_by: str
    message: str


async def _resume_graph_a_background(
    thread_id: str,
    org_id: str,
    approver_user_id: str,
    hitl_decisions: Dict[str, str],
) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    try:
        graph = get_graph_a()
        result = graph.invoke(
            Command(resume={"decisions": hitl_decisions, "approver_user_id": approver_user_id}),
            config=config,
        )
        dispatched = (result or {}).get("dispatched_tickets", [])
        tasks_out = (result or {}).get("tasks", {})
        meeting_id = (result or {}).get("meeting_id", thread_id)

        save_thread_snapshot(
            thread_id=thread_id,
            org_id=org_id,
            snapshot={
                "meeting_id": meeting_id,
                "title": (result or {}).get("title"),
                "phase": "COMPLETE",
                "tasks": tasks_out,
                "resolutions": (result or {}).get("resolutions", []),
                "key_decisions": (result or {}).get("key_decisions", []),
                "meeting_context": (result or {}).get("meeting_context", {}),
                "dispatched_tickets": dispatched,
                "approver_user_id": approver_user_id,
            },
        )

        await sse_manager.push_event(
            thread_id,
            "dispatched",
            {
                "meeting_id": meeting_id,
                "approved_by": approver_user_id,
                "dispatched_tickets": dispatched,
                "tasks": tasks_out,
                "message": f"{len(dispatched)} ticket(s) dispatched.",
            },
            org_id=org_id,
        )
        await sse_manager.push_complete(thread_id, org_id=org_id)
    except Exception as exc:
        logger.error("_resume_graph_a_background failed: %s", exc, exc_info=True)
        await sse_manager.push_error(thread_id, str(exc), org_id=org_id)


@router.post("/hitl-resume", response_model=HITLResumeResponse)
async def hitl_resume(
    body: HITLResumeRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_manager),
) -> HITLResumeResponse:
    """Verify manager role + org ownership, log approver, and resume paused Graph A."""
    if not body.thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required.")
    if not body.hitl_decisions:
        raise HTTPException(status_code=400, detail="hitl_decisions cannot be empty.")

    snap = get_thread_snapshot(body.thread_id)
    thread_org = (snap or {}).get("org_id") or sse_manager.get_thread_org(body.thread_id)
    if not thread_org or thread_org != auth.org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Thread does not belong to the authenticated organization.",
        )

    meeting_id = (snap or {}).get("meeting_id") or body.thread_id
    record_approval(
        org_id=auth.org_id,
        thread_id=body.thread_id,
        meeting_id=meeting_id,
        decisions=body.hitl_decisions,
        approver_user_id=auth.user_id,
    )

    sse_manager.register(body.thread_id, org_id=auth.org_id)
    background_tasks.add_task(
        _resume_graph_a_background,
        body.thread_id,
        auth.org_id,
        auth.user_id,
        body.hitl_decisions,
    )

    return HITLResumeResponse(
        status="resuming",
        thread_id=body.thread_id,
        approved_by=auth.user_id,
        message="Manager approval recorded; Graph A resuming dispatch.",
    )
