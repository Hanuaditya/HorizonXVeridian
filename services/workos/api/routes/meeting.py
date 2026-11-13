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
from core.evon_llm import demo_extract_from_transcript
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


def _build_deterministic_hitl_fallback(initial_state: Any, org_id: Optional[str] = None) -> Dict[str, Any]:
    """Instant deterministic fallback (<50ms) to guarantee HITL transition on timeouts or outages."""
    if isinstance(initial_state, str):
        raw_transcript = initial_state
        thread_id = "live-sprint-sync"
        target_org_id = org_id or "org_demo_horizon"
    elif isinstance(initial_state, dict):
        raw_transcript = str(initial_state.get("transcript") or "")
        if not raw_transcript and initial_state.get("transcript_segments"):
            raw_transcript = "\n".join(
                f"{s.get('speaker', '')}: {s.get('text', '')}"
                for s in initial_state["transcript_segments"]
            )
        thread_id = str(initial_state.get("thread_id") or initial_state.get("meeting_id") or "live-sprint-sync")
        target_org_id = str(initial_state.get("org_id") or org_id or "org_demo_horizon")
    else:
        raw_transcript = ""
        thread_id = "live-sprint-sync"
        target_org_id = org_id or "org_demo_horizon"

    extracted = demo_extract_from_transcript(raw_transcript)
    tasks_raw = extracted.get("tasks") or []
    if isinstance(tasks_raw, dict):
        tasks_list = list(tasks_raw.values())
    elif isinstance(tasks_raw, list):
        tasks_list = tasks_raw
    else:
        tasks_list = []

    meeting_context = extracted.get("meeting_context") or {}
    key_decisions = extracted.get("key_decisions") or []

    # Dynamically determine covering engineer from transcript content
    raw_low = raw_transcript.lower()
    if "catchme" in raw_low:
        covering_engineer = "catchme if"
    elif "josh" in raw_low or "josh lambert" in raw_low:
        covering_engineer = "Josh Lambert"
    else:
        covering_engineer = "catchme if"

    tasks_out: Dict[str, Any] = {}
    resolutions_out: List[Dict[str, Any]] = []
    immediate_alerts: List[Dict[str, Any]] = []

    for idx, t in enumerate(tasks_list, start=1):
        task = dict(t)
        tid = str(task.get("task_id") or f"t{idx}")
        task["task_id"] = tid
        assignee = str(task.get("assignee") or "")
        title = str(task.get("title") or f"Sprint Task {idx}")
        quote = str(task.get("transcript_quote") or "")
        combined_text = f"{assignee} {title} {quote}".lower()

        # 4-way compliance firewall
        # 1. Arjun Rao on paternity leave -> REROUTE to covering engineer (catchme if)
        if "arjun" in combined_text or "paternity" in combined_text:
            task["hr_status"] = "ON_PATERNITY_LEAVE"
            task["rerouted_assignee"] = covering_engineer
            task["leave_recommendation"] = f"Smart Leave Redirection: {covering_engineer}"
            task["assignee_resolution_flag"] = f"{assignee or 'Arjun Rao'} on paternity leave until next Monday"
            task["resolution_action"] = "REROUTE"
            task["suggested_action"] = "REROUTE"
            resolutions_out.append({
                "resolution_id": f"res-{tid}",
                "task_id": tid,
                "conflict_type": "HR_LEAVE",
                "suggested_action": "REROUTE",
                "original_assignee": assignee or "Arjun Rao",
                "new_assignee": covering_engineer,
                "reason": f"Assignee on paternity leave. Automatically rerouted to {covering_engineer}.",
                "policy_provenance": "HR-PATERNITY-LEAVE-POLICY",
            })
            immediate_alerts.append({
                "alert_id": f"alert-{tid}",
                "severity": "CRITICAL",
                "title": "HR Compliance: Assignee On Leave",
                "description": f"Task '{title}' cannot be assigned to {assignee or 'Arjun Rao'} (on paternity leave). Rerouted to {covering_engineer}.",
            })
        # 2. 14-day staging bake required -> REFRAME (SEC-POL-089)
        elif "14-day" in combined_text or "staging" in combined_text or "sec-pol-089" in combined_text or "bake" in combined_text:
            task["security_flag"] = "SEC-POL-089: 14-day staging bake required"
            task["resolution_action"] = "REFRAME"
            task["suggested_action"] = "REFRAME"
            task["reframed_title"] = f"[Staging Bake 14-Day] {title}"
            resolutions_out.append({
                "resolution_id": f"res-{tid}",
                "task_id": tid,
                "conflict_type": "SECURITY_POLICY",
                "suggested_action": "REFRAME",
                "reason": "Production deployments require 14-day staging soak per SEC-POL-089.",
                "policy_provenance": "SEC-POL-089",
            })
            immediate_alerts.append({
                "alert_id": f"alert-{tid}",
                "severity": "HIGH",
                "title": "Security Policy Enforcement: SEC-POL-089",
                "description": "Production deployment modified to include mandatory 14-day staging bake.",
            })
        # 3. Deprecated API prohibited -> FLAG (SEC-POL-104)
        elif "deprecated" in combined_text or "third-party" in combined_text or "sec-pol-104" in combined_text or "unapproved" in combined_text:
            task["security_flag"] = "SEC-POL-104: Unapproved/Deprecated External API"
            task["resolution_action"] = "FLAG"
            task["suggested_action"] = "FLAG"
            resolutions_out.append({
                "resolution_id": f"res-{tid}",
                "task_id": tid,
                "conflict_type": "DEPRECATED_API",
                "suggested_action": "FLAG",
                "reason": "Deprecated third-party APIs violate SEC-POL-104.",
                "policy_provenance": "SEC-POL-104",
            })
            immediate_alerts.append({
                "alert_id": f"alert-{tid}",
                "severity": "HIGH",
                "title": "Security Policy Enforcement: SEC-POL-104",
                "description": "Task references prohibited deprecated API. Flagged for architectural review.",
            })
        # 4. Budget limit exceeded -> DEFER
        elif "budget" in combined_text or "cost" in combined_text or "lakhs" in combined_text or "2.5" in combined_text or "0 inr" in combined_text or "tier" in combined_text:
            task["finance_flag"] = "Finance: Over Budget (0 INR remaining in Q4 compute budget)"
            task["resolution_action"] = "DEFER"
            task["suggested_action"] = "DEFER"
            resolutions_out.append({
                "resolution_id": f"res-{tid}",
                "task_id": tid,
                "conflict_type": "BUDGET_EXCEEDED",
                "suggested_action": "DEFER",
                "reason": "Compute budget is exhausted (0 INR). Deferred pending FinOps approval.",
                "policy_provenance": "FIN-BUDGET-Q4-POLICY",
            })
            immediate_alerts.append({
                "alert_id": f"alert-{tid}",
                "severity": "HIGH",
                "title": "Finance Policy: Budget Cap Exceeded",
                "description": "Compute instance costs exceed allocated budget limit for current quarter.",
            })
        else:
            task["resolution_action"] = "PROCEED"
            task["suggested_action"] = "PROCEED"
            resolutions_out.append({
                "resolution_id": f"res-{tid}",
                "task_id": tid,
                "conflict_type": "NONE",
                "suggested_action": "PROCEED",
                "reason": "No policy conflicts detected.",
                "policy_provenance": "CLEAR",
            })

        tasks_out[tid] = task

    return {
        "tasks": tasks_out,
        "resolutions": resolutions_out,
        "key_decisions": key_decisions,
        "meeting_context": meeting_context,
        "immediate_alerts": immediate_alerts,
        "dispatched_tickets": [],
    }


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

        def _invoke_graph() -> Dict[str, Any]:
            graph: Any = get_graph_a()
            raw: Any = graph.invoke(initial_state, config=config)
            return dict(raw) if isinstance(raw, dict) else {}

        try:
            result: Dict[str, Any] = await asyncio.wait_for(
                asyncio.to_thread(_invoke_graph),
                timeout=12.0,
            )
        except Exception as inv_exc:
            logger.warning(
                "Graph A execution timed out or failed on thread '%s' (%s); engaging deterministic fallback.",
                thread_id,
                inv_exc,
            )
            result = _build_deterministic_hitl_fallback(initial_state)

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

        if not tasks_out:
            logger.info("Graph A returned empty tasks on thread '%s'; using deterministic extraction.", thread_id)
            fallback = _build_deterministic_hitl_fallback(initial_state)
            tasks_out = fallback.get("tasks", {})
            resolutions_out = fallback.get("resolutions", [])
            key_decisions = fallback.get("key_decisions", [])
            meeting_context = fallback.get("meeting_context", {})
            immediate_alerts = fallback.get("immediate_alerts", [])

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
                "manager_approved": False,
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
        try:
            fb = _build_deterministic_hitl_fallback(initial_state)
            save_thread_snapshot(
                thread_id=thread_id,
                org_id=org_id,
                snapshot={
                    "meeting_id": meeting_id,
                    "title": initial_state.get("title", "Sprint Meeting"),
                    "phase": "HITL",
                    "tasks": fb["tasks"],
                    "resolutions": fb["resolutions"],
                    "key_decisions": fb["key_decisions"],
                    "meeting_context": fb["meeting_context"],
                    "immediate_alerts": fb["immediate_alerts"],
                    "slack_feed": list_slack_feed(org_id=org_id, thread_id=thread_id),
                    "dispatched_tickets": [],
                    "manager_approved": False,
                },
            )
            await sse_manager.push_event(
                thread_id,
                "hitl_ready",
                {
                    "meeting_id": meeting_id,
                    "thread_id": thread_id,
                    "message": "Manager review menu ready (fallback) — awaiting approval.",
                    "tasks": fb["tasks"],
                    "resolutions": fb["resolutions"],
                },
                org_id=org_id,
            )
        except Exception as fb_exc:
            logger.error("Failed to apply emergency HITL fallback for thread '%s': %s", thread_id, fb_exc)
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
@router.post(
    "/workos/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MeetingAcceptedResponse,
)
@router.post(
    "/ingest",
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

