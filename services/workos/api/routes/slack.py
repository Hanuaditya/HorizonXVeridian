"""POST /api/slack-webhook — Strict Slack signature verification, dedupe & Graph B dispatch."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status

from agent.graph_b import graph_b_slack
from api.sse import sse_manager
from connectors.sprint_loop import (
    build_default_hitl_decisions,
    confirm_task_completion_by_manager,
    process_employee_reply,
    reject_task_completion_by_manager,
    resume_graph_a_and_sync,
)
from core.config import get_settings
from core.store import get_slack_thread, get_thread_snapshot, record_approval, record_webhook_event_once

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
    reply_text = str(event.get("text") or "").strip()

    if task_id == "__MANAGER_REVIEW__" and reply_text.lower() in {"approve", "approved", "lgtm", "yes", "approve all"}:
        snap = get_thread_snapshot(graph_thread_id)
        if snap and snap.get("phase") == "HITL":
            decisions = build_default_hitl_decisions(snap)
            approver = f"slack:{event.get('user') or 'manager'}"
            record_approval(org_id, graph_thread_id, snap.get("meeting_id") or graph_thread_id, decisions, approver)
            sse_manager.register(graph_thread_id, org_id=org_id)
            background_tasks.add_task(resume_graph_a_and_sync, graph_thread_id, org_id, approver, decisions)
            return Response(content=json.dumps({"status": "approved_via_slack"}), media_type="application/json", status_code=200)

    if get_thread_snapshot(graph_thread_id) and task_id not in {"unknown", "__MANAGER_REVIEW__"}:
        background_tasks.add_task(
            process_employee_reply,
            org_id,
            graph_thread_id,
            task_id,
            reply_text,
            "slack",
            False,
            channel,
            thread_ts,
        )
    else:
        background_tasks.add_task(
            _run_slack_graph_b,
            org_id,
            graph_thread_id,
            task_id,
            assignee,
            channel,
            thread_ts,
            reply_text,
            prev_turns,
        )
    return Response(content=json.dumps({"status": "accepted"}), media_type="application/json", status_code=200)


_SEEN_SLACK_INTERACTIVE_ACTIONS: set[str] = set()


@router.post("/slack/interactivity")
async def slack_interactivity(
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """Handle Slack Block Kit interactive actions (Approve & Create Tickets)."""
    raw_body = await request.body()
    ts = request.headers.get("X-Slack-Request-Timestamp", "")
    sig = request.headers.get("X-Slack-Signature", "")

    if not verify_slack_signature(raw_body, ts, sig):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing Slack signing secret / signature.",
        )

    body_text = raw_body.decode("utf-8", errors="replace")
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/x-www-form-urlencoded" in content_type or body_text.startswith("payload="):
        form = urllib.parse.parse_qs(body_text)
        raw_payload = (form.get("payload") or ["{}"])[0]
        payload = json.loads(raw_payload)
    else:
        payload = json.loads(body_text or "{}")

    # Slack deduplication guard: ignore retry deliveries with identical trigger_id
    trigger_id = str(payload.get("trigger_id") or "").strip()
    if trigger_id and trigger_id in _SEEN_SLACK_INTERACTIVE_ACTIONS:
        logger.info("slack_interactivity: ignoring replayed Slack trigger_id '%s'", trigger_id)
        return Response(
            content=json.dumps({"status": "duplicate_ignored", "text": "Already processed."}),
            media_type="application/json",
            status_code=200,
        )
    if trigger_id:
        _SEEN_SLACK_INTERACTIVE_ACTIONS.add(trigger_id)

    actions = payload.get("actions") or []
    user_info = payload.get("user") or {}
    approver = f"slack:{user_info.get('username') or user_info.get('id') or 'manager'}"

    for action in actions:
        action_ts = str(action.get("action_ts") or "")
        thread_id = str(action.get("value") or "").strip()
        action_key = f"{thread_id}:{action_ts}"
        if action_key in _SEEN_SLACK_INTERACTIVE_ACTIONS:
            logger.info("slack_interactivity: ignoring replayed action_ts '%s'", action_key)
            return Response(
                content=json.dumps({"status": "duplicate_ignored"}),
                media_type="application/json",
                status_code=200,
            )
        if action_ts:
            _SEEN_SLACK_INTERACTIVE_ACTIONS.add(action_key)

        if action.get("action_id") == "approve_sprint_tickets":
            snap = get_thread_snapshot(thread_id)
            if not snap:
                raise HTTPException(status_code=404, detail=f"Thread '{thread_id}' not found.")
            org_id = str(snap.get("org_id") or "org_demo_horizon")
            if snap.get("phase") == "HITL":
                decisions = build_default_hitl_decisions(snap)
                record_approval(org_id, thread_id, snap.get("meeting_id") or thread_id, decisions, approver)
                sse_manager.register(thread_id, org_id=org_id)
                background_tasks.add_task(resume_graph_a_and_sync, thread_id, org_id, approver, decisions)
            return Response(
                content=json.dumps({
                    "response_type": "ephemeral",
                    "text": f"Approved sprint tickets for thread `{thread_id}` — creating Jira tickets and notifying employees now.",
                }),
                media_type="application/json",
                status_code=200,
            )

        if action.get("action_id") in {"confirm_task_done", "reject_task_done"}:
            val = str(action.get("value") or "")
            parts = val.split(":")
            tid = parts[0]
            subtask_id = parts[1] if len(parts) > 1 else ""
            snap = get_thread_snapshot(tid)
            org_id = str((snap or {}).get("org_id") or "org_demo_horizon")
            if action.get("action_id") == "confirm_task_done":
                background_tasks.add_task(confirm_task_completion_by_manager, org_id, tid, subtask_id, approver)
                return Response(
                    content=json.dumps({"response_type": "ephemeral", "text": f"Confirmed task `{subtask_id}` as Done."}),
                    media_type="application/json",
                    status_code=200,
                )
            else:
                background_tasks.add_task(reject_task_completion_by_manager, org_id, tid, subtask_id, approver, "Rework requested via Slack")
                return Response(
                    content=json.dumps({"response_type": "ephemeral", "text": f"Requested rework on task `{subtask_id}`."}),
                    media_type="application/json",
                    status_code=200,
                )

    return Response(content=json.dumps({"status": "ignored"}), media_type="application/json", status_code=200)

