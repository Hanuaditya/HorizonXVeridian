"""POST /api/slack-webhook — Strict Slack signature verification, dedupe & Graph B dispatch."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status

from agent.graph_b import graph_b_slack
from api.sse import sse_manager
from core.config import get_settings
from core.store import get_slack_thread, record_webhook_event_once

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_slack_signature(raw_body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack v0 HMAC-SHA256 signature. STRICTLY rejects when secret is missing."""
    settings = get_settings()
    secret = settings.slack_signing_secret
    if not secret or "placeholder" in secret.lower():
        logger.error("slack_webhook: SLACK_SIGNING_SECRET missing -> rejecting request.")
        return False

    try:
        if abs(time.time() - float(timestamp)) > 300:
            return False
    except (TypeError, ValueError):
        return False

    base_string = f"v0:{timestamp}:{raw_body.decode('utf-8')}"
    computed = "v0=" + hmac.new(
        secret.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, signature or "")


async def _run_slack_graph_b(
    org_id: str,
    thread_id: str,
    task_id: str,
    assignee: str,
    slack_channel: str,
    slack_thread_ts: str,
    reply_text: str,
    turn_count: int,
) -> None:
    try:
        out = graph_b_slack.invoke({
            "org_id": org_id,
            "thread_id": thread_id,
            "tracker_task_id": task_id,
            "tracker_assignee": assignee,
            "slack_channel": slack_channel,
            "slack_thread_ts": slack_thread_ts,
            "last_slack_reply": reply_text,
            "turn_count": turn_count,
            "is_demo": get_settings().demo_mode,
        })
        await sse_manager.push_event(
            thread_id,
            "tracker_update",
            {
                "source": "slack",
                "task_id": task_id,
                "intent": out.get("parsed_intent"),
                "confidence": out.get("intent_confidence"),
                "updates": out.get("tracker_updates", []),
            },
            org_id=org_id,
        )
    except Exception as exc:
        logger.error("Graph B (Slack) background error: %s", exc, exc_info=True)


@router.post("/slack-webhook")
async def slack_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """Receive Slack events: verify signature strictly, dedupe event_id, ack <3s."""
    raw_body = await request.body()
    ts = request.headers.get("X-Slack-Request-Timestamp", "")
    sig = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_signature(raw_body, ts, sig):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing Slack signing secret / signature.",
        )

    try:
        payload: Dict[str, Any] = json.loads(raw_body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.") from exc

    if payload.get("type") == "url_verification":
        return Response(content=str(payload.get("challenge", "")), media_type="text/plain")

    event_id = str(payload.get("event_id") or "")
    if event_id and not record_webhook_event_once("slack", event_id):
        return Response(
            content=json.dumps({"status": "duplicate_ignored", "event_id": event_id}),
            media_type="application/json",
            status_code=200,
        )

    event = payload.get("event") or {}
    if event.get("type") != "message" or event.get("bot_id"):
        return Response(content="ok", media_type="text/plain", status_code=200)

    channel = str(event.get("channel") or "#product-team")
    thread_ts = str(event.get("thread_ts") or event.get("ts") or "")
    org_id = str(payload.get("org_id") or "org_demo_horizon")

    existing_thread = get_slack_thread(org_id=org_id, slack_channel=channel, slack_thread_ts=thread_ts)
    graph_thread_id = (existing_thread or {}).get("thread_id") or f"slack-{thread_ts}"
    task_id = (existing_thread or {}).get("task_id") or str(event.get("task_id") or "unknown")
    assignee = (existing_thread or {}).get("assignee") or str(event.get("user") or "assignee")
    prev_turns = int((existing_thread or {}).get("turn_count") or 0)

    background_tasks.add_task(
        _run_slack_graph_b,
        org_id,
        graph_thread_id,
        task_id,
        assignee,
        channel,
        thread_ts,
        str(event.get("text") or ""),
        prev_turns,
    )
    return Response(content=json.dumps({"status": "accepted"}), media_type="application/json", status_code=200)
