"""POST /api/meeting-ended (HMAC signed) & authenticated /api/demo/meeting-ended runner."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from agent.graph_a import get_graph_a
from api.auth import AuthContext, require_auth, require_manager
from api.sse import sse_manager
from connectors.slack_ops import send_manager_review_menu
from contracts.meeting_ended import MeetingEndedPayload
from core.config import get_settings
from core.store import list_slack_feed, save_thread_snapshot

logger = logging.getLogger(__name__)
router = APIRouter()


class MeetingAcceptedResponse(BaseModel):
    status: str = "accepted"
    thread_id: str
    meeting_id: str
    org_id: str


class DemoMeetingRequest(BaseModel):
    meeting_id: Optional[str] = None
    title: str = "Hinglish Enterprise Sprint Sync"
    transcript: str
    participants: List[Dict[str, str]] = Field(default_factory=list)


def verify_service_hmac(raw_body: bytes, signature_header: str, timestamp_header: str) -> bool:
    """Verify HMAC-SHA256 + timestamp replay window (<= MAX_HMAC_SKEW_SECONDS). Rejects if secret missing."""
    settings = get_settings()
    secret = settings.shared_hmac_secret
    if not secret:
        logger.error("verify_service_hmac: SHARED_HMAC_SECRET is unset -> rejecting request.")
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    try:
        ts = float(timestamp_header)
        if abs(time.time() - ts) > settings.max_hmac_skew_seconds:
            logger.warning("verify_service_hmac: expired timestamp (replay guard).")
            return False
    except (TypeError, ValueError):
        return False

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


async def run_graph_a_background(thread_id: str, initial_state: Dict[str, Any]) -> None:
    """Execute Graph A in background, saving state snapshots & streaming contract SSE events."""
    org_id = initial_state["org_id"]
    meeting_id = initial_state["meeting_id"]
    config = {"configurable": {"thread_id": thread_id}}

    try:
        await sse_manager.push_event(
            thread_id,
            "processing_started",
            {
                "stage": "ingesting",
                "meeting_id": meeting_id,
                "title": initial_state.get("title", "Meeting"),
                "message": "Ingesting transcript and resolving assignees...",
            },
            org_id=org_id,
        )

        save_thread_snapshot(
            thread_id=thread_id,
            org_id=org_id,
            snapshot={
                "meeting_id": meeting_id,
                "title": initial_state.get("title"),
                "phase": "INGESTING",
                "tasks": {},
                "resolutions": [],
                "key_decisions": [],
                "meeting_context": {},
                "dispatched_tickets": [],
            },
        )

        graph = get_graph_a()
        result = await asyncio.to_thread(graph.invoke, initial_state, config=config)

        if result and result.get("__drop__"):
            await sse_manager.push_error(
                thread_id,
                f"Meeting '{meeting_id}' was already processed (idempotency drop).",
                org_id=org_id,
            )
            return

        tasks_out = (result or {}).get("tasks", {})
        resolutions_out = (result or {}).get("resolutions", [])
        key_decisions = (result or {}).get("key_decisions", [])
        meeting_context = (result or {}).get("meeting_context", {})
        immediate_alerts = (result or {}).get("immediate_alerts", [])
        dispatched = (result or {}).get("dispatched_tickets", [])

        needs_hitl = bool(tasks_out) or any(r.get("suggested_action") != "PROCEED" for r in resolutions_out)
        phase = "HITL" if needs_hitl else "COMPLETE"

        if needs_hitl:
            await asyncio.to_thread(
                send_manager_review_menu,
                org_id,
                thread_id,
                meeting_id,
                str(initial_state.get("title") or "Sprint Meeting"),
                tasks_out,
                resolutions_out,
            )

        slack_feed = list_slack_feed(org_id=org_id, thread_id=thread_id)
        save_thread_snapshot(
            thread_id=thread_id,
            org_id=org_id,
            snapshot={
                "meeting_id": meeting_id,
                "title": initial_state.get("title"),
                "phase": phase,
                "tasks": tasks_out,
                "resolutions": resolutions_out,
                "key_decisions": key_decisions,
                "meeting_context": meeting_context,
                "immediate_alerts": immediate_alerts,
                "slack_feed": slack_feed,
                "dispatched_tickets": dispatched,
            },
        )

        await sse_manager.push_event(
            thread_id,
            "resolution_ready",
            {
                "meeting_id": meeting_id,
                "tasks": tasks_out,
                "resolutions": resolutions_out,
                "key_decisions": key_decisions,
                "meeting_context": meeting_context,
                "immediate_alerts": immediate_alerts,
                "slack_feed": slack_feed,
            },
            org_id=org_id,
        )

        if needs_hitl:
            await sse_manager.push_event(
                thread_id,
                "hitl_ready",
                {
                    "meeting_id": meeting_id,
                    "thread_id": thread_id,
                    "message": "Manager review menu sent to Slack — awaiting approval before creating Jira tickets.",
                    "tasks": tasks_out,
                    "resolutions": resolutions_out,
                    "key_decisions": key_decisions,
                    "meeting_context": meeting_context,
                    "immediate_alerts": immediate_alerts,
                    "slack_feed": slack_feed,
                },
                org_id=org_id,
            )
            return

        await sse_manager.push_event(
            thread_id,
            "dispatched",
            {
                "meeting_id": meeting_id,
                "dispatched_tickets": dispatched,
                "message": "All clear tasks dispatched.",
            },
            org_id=org_id,
        )
        await sse_manager.push_complete(thread_id, org_id=org_id)

    except Exception as exc:
        logger.error("Graph A execution error on thread '%s': %s", thread_id, exc, exc_info=True)
        await sse_manager.push_error(thread_id, str(exc), org_id=org_id)


@router.post(
    "/meeting-ended",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MeetingAcceptedResponse,
)
async def meeting_ended_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> MeetingAcceptedResponse:
    """Service-to-service entry point consuming signed MeetingEndedPayload."""
    raw_body = await request.body()
    sig = request.headers.get("X-Signature", "")
    ts = request.headers.get("X-Timestamp", "")
    if not verify_service_hmac(raw_body, sig, ts):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired X-Signature / X-Timestamp.",
        )

    try:
        payload = MeetingEndedPayload.model_validate_json(raw_body)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid MeetingEndedPayload contract: {exc}",
        ) from exc

    thread_id = f"meeting-{payload.meeting_id}-{uuid.uuid4().hex[:8]}"
    sse_manager.register(thread_id, org_id=payload.org_id)

    initial_state: Dict[str, Any] = {
        "org_id": payload.org_id,
        "meeting_id": payload.meeting_id,
        "thread_id": thread_id,
        "title": payload.title,
        "transcript": "",
        "transcript_segments": [s.model_dump() for s in payload.transcript],
        "participants": [p.model_dump() for p in payload.participants],
        "tasks": {},
        "key_decisions": [],
        "meeting_context": {},
        "resolutions": [],
        "dispatched_tickets": [],
        "manager_approved": False,
        "turn_count": 0,
    }

    background_tasks.add_task(run_graph_a_background, thread_id, initial_state)
    return MeetingAcceptedResponse(
        status="accepted",
        thread_id=thread_id,
        meeting_id=payload.meeting_id,
        org_id=payload.org_id,
    )


@router.post(
    "/demo/meeting-ended",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MeetingAcceptedResponse,
)
async def demo_meeting_ended(
    body: DemoMeetingRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_auth),
) -> MeetingAcceptedResponse:
    """Authenticated trigger for running demo/UI transcripts through Graph A in the caller's org."""
    settings = get_settings()
    if not settings.demo_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo trigger is disabled when DEMO_MODE=false.",
        )

    meeting_id = body.meeting_id or f"demo-{uuid.uuid4().hex[:8]}"
    thread_id = f"meeting-{meeting_id}-{uuid.uuid4().hex[:8]}"
    sse_manager.register(thread_id, org_id=auth.org_id)

    initial_state: Dict[str, Any] = {
        "org_id": auth.org_id,
        "meeting_id": meeting_id,
        "thread_id": thread_id,
        "title": body.title,
        "transcript": body.transcript,
        "participants": body.participants,
        "is_demo": True,
        "tasks": {},
        "key_decisions": [],
        "meeting_context": {},
        "resolutions": [],
        "dispatched_tickets": [],
        "manager_approved": False,
        "turn_count": 0,
    }

    background_tasks.add_task(run_graph_a_background, thread_id, initial_state)
    return MeetingAcceptedResponse(
        status="accepted",
        thread_id=thread_id,
        meeting_id=meeting_id,
        org_id=auth.org_id,
    )


@router.post(
    "/transcript-ingest",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MeetingAcceptedResponse,
)
async def ingest_live_transcript(
    body: DemoMeetingRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_manager),
) -> MeetingAcceptedResponse:
    """Manager-authenticated endpoint to ingest sprint transcripts in live or demo mode."""
    settings = get_settings()
    meeting_id = body.meeting_id or f"live-{uuid.uuid4().hex[:8]}"
    thread_id = f"meeting-{meeting_id}-{uuid.uuid4().hex[:8]}"
    sse_manager.register(thread_id, org_id=auth.org_id)

    initial_state: Dict[str, Any] = {
        "org_id": auth.org_id,
        "meeting_id": meeting_id,
        "thread_id": thread_id,
        "title": body.title,
        "transcript": body.transcript,
        "participants": body.participants,
        "is_demo": settings.demo_mode,
        "tasks": {},
        "key_decisions": [],
        "meeting_context": {},
        "resolutions": [],
        "dispatched_tickets": [],
        "immediate_alerts": [],
        "manager_approved": False,
        "turn_count": 0,
    }

    background_tasks.add_task(run_graph_a_background, thread_id, initial_state)
    return MeetingAcceptedResponse(
        status="accepted",
        thread_id=thread_id,
        meeting_id=meeting_id,
        org_id=auth.org_id,
    )

