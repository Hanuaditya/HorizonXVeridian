"""
api/routes/slack.py — POST /api/slack-webhook
==============================================
Receives Slack Event API webhooks, verifies the signing secret,
and routes to Graph B (Slack intent parser loop).

CRITICAL: Slack requires a 200 OK within 3 seconds or it will retry.
We return 200 immediately and run Graph B as a BackgroundTask.

Handles:
  - url_verification challenge (Slack setup)
  - message events from users (reply tracking)
"""

import hashlib
import hmac
import logging
import os
import time
import uuid
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel

from agent.graph_b import graph_b
from api.sse import sse_manager

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Slack signature verification
# ---------------------------------------------------------------------------

def _verify_slack_signature(request_body: bytes, timestamp: str, signature: str) -> bool:
    """
    Verify Slack's HMAC-SHA256 request signature.
    Rejects requests older than 5 minutes (replay attack prevention).
    """
    signing_secret = os.getenv("SLACK_SIGNING_SECRET", "")
    if not signing_secret:
        logger.warning("slack_webhook: SLACK_SIGNING_SECRET not set — skipping verification.")
        return True  # Dev mode: skip verification

    # Reject stale requests (> 5 minutes old)
    try:
        if abs(time.time() - float(timestamp)) > 300:
            logger.warning("slack_webhook: stale request timestamp — possible replay attack.")
            return False
    except ValueError:
        return False

    base_string = f"v0:{timestamp}:{request_body.decode('utf-8')}"
    computed = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, signature)


# ---------------------------------------------------------------------------
# Background task — runs Graph B (Slack path)
# ---------------------------------------------------------------------------

async def _run_graph_b_slack(
    thread_id: str,
    tracker_task_id: str,
    tracker_assignee: str,
    slack_reply: str,
    turn_count: int,
    tasks_snapshot: Dict[str, Any],
) -> None:
    """Run Graph B for a Slack message reply."""
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: Dict[str, Any] = {
        "meeting_id": "",
        "transcript": "",
        "tasks": tasks_snapshot,
        "key_decisions": [],
        "meeting_context": {},
        "resolutions": [],
        "interrupt_payload": None,
        "hitl_decisions": {},
        "dispatched_tickets": [],
        "manager_approved": False,
        "turn_count": turn_count,
        "tracker_task_id": tracker_task_id,
        "tracker_assignee": tracker_assignee,
        "last_slack_reply": slack_reply,
        "parsed_intent": None,
        "intent_confidence": None,
    }

    try:
        logger.info(
            "_run_graph_b_slack: invoking Graph B for assignee='%s' reply='%s…'",
            tracker_assignee, slack_reply[:60],
        )
        graph_b.invoke(initial_state, config=config)
    except Exception as exc:
        logger.error(
            "_run_graph_b_slack: Graph B error for thread '%s': %s", thread_id, exc, exc_info=True
        )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/slack-webhook")
async def slack_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """
    POST /api/slack-webhook

    Entry point for Slack Event API webhooks.
    Returns 200 immediately — Graph B runs as background task.
    """
    raw_body = await request.body()
    payload: Dict[str, Any] = {}

    try:
        import json
        payload = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    # ── Slack URL verification challenge (one-time setup) ────────────────
    if payload.get("type") == "url_verification":
        logger.info("slack_webhook: responding to URL verification challenge.")
        return Response(
            content=payload.get("challenge", ""),
            media_type="text/plain",
        )

    # ── Verify Slack signature ───────────────────────────────────────────
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not _verify_slack_signature(raw_body, timestamp, signature):
        raise HTTPException(status_code=403, detail="Invalid Slack signature.")

    # ── Parse message event ──────────────────────────────────────────────
    event = payload.get("event", {})
    event_type = event.get("type", "")

    # Ignore bot messages and non-message events
    if event_type != "message" or event.get("bot_id"):
        return Response(content="ok", media_type="text/plain", status_code=200)

    user_text: str = event.get("text", "").strip()
    user_id: str = event.get("user", "")
    channel: str = event.get("channel", "")
    thread_ts: str = event.get("thread_ts") or event.get("ts", "")

    if not user_text:
        return Response(content="ok", media_type="text/plain", status_code=200)

    # Build a stable thread_id from channel + thread_ts for Graph B state
    thread_id = f"slack-{channel}-{thread_ts}"

    logger.info(
        "slack_webhook: message from '%s' in '%s': '%s…'",
        user_id, channel, user_text[:80],
    )

    # NOTE: In production, look up the tracker_task_id from a DB keyed on
    # the channel/thread_ts. Here we use the channel as the task_id hint.
    background_tasks.add_task(
        _run_graph_b_slack,
        thread_id=thread_id,
        tracker_task_id=channel,          # API layer maps channel → task_id in production
        tracker_assignee=user_id,
        slack_reply=user_text,
        turn_count=0,                     # Fresh invocation — Graph B is stateless per call
        tasks_snapshot={},               # Populated from DB lookup in production
    )

    # ── Return 200 immediately — CRITICAL for Slack 3-second SLA ─────────
    return Response(content="ok", media_type="text/plain", status_code=200)
