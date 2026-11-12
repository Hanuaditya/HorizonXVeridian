"""POST /api/github-webhook — Strict X-Hub-Signature-256 verification & Graph B commit matcher."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status

from agent.graph_b import graph_b_github
from api.sse import sse_manager
from core.config import get_settings
from core.store import record_webhook_event_once

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_github_signature(raw_body: bytes, signature_header: str) -> bool:
    """Verify GitHub X-Hub-Signature-256 header. STRICTLY rejects when secret is missing."""
    settings = get_settings()
    secret = settings.github_webhook_secret
    if not secret or "placeholder" in secret.lower():
        logger.error("github_webhook: GITHUB_WEBHOOK_SECRET missing -> rejecting request.")
        return False

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


async def _run_github_graph_b(
    org_id: str,
    repo: str,
    branch: str,
    author: str,
    commit_message: str,
    delivery_id: str,
) -> None:
    search_text = f"GitHub commit by {author} on {branch} in {repo}: {commit_message}"
    thread_id = f"github-{delivery_id or repo}"
    try:
        out = graph_b_github.invoke({
            "org_id": org_id,
            "thread_id": thread_id,
            "tracker_assignee": author,
            "last_slack_reply": search_text,
            "is_demo": get_settings().demo_mode,
        })
        await sse_manager.push_event(
            thread_id,
            "tracker_update",
            {
                "source": "github",
                "repo": repo,
                "author": author,
                "intent": out.get("parsed_intent"),
                "confidence": out.get("intent_confidence"),
                "updates": out.get("tracker_updates", []),
            },
            org_id=org_id,
        )
    except Exception as exc:
        logger.error("Graph B (GitHub) background error: %s", exc, exc_info=True)


@router.post("/github-webhook")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    raw_body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not verify_github_signature(raw_body, sig):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing GitHub webhook secret / signature.",
        )

    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    if delivery_id and not record_webhook_event_once("github", delivery_id):
        return Response(
            content=json.dumps({"status": "duplicate_ignored", "delivery_id": delivery_id}),
            media_type="application/json",
            status_code=200,
        )

    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type not in ("push", "pull_request"):
        return Response(
            content=json.dumps({"status": "ignored", "event": event_type}),
            media_type="application/json",
            status_code=200,
        )

    try:
        payload: Dict[str, Any] = json.loads(raw_body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.") from exc

    repo = payload.get("repository", {}).get("full_name", "unknown-repo")
    branch = payload.get("ref", "refs/heads/main").replace("refs/heads/", "")
    org_id = str(payload.get("org_id") or "org_demo_horizon")
    commits: List[Dict[str, Any]] = payload.get("commits", [])

    for c in commits:
        author = c.get("author", {}).get("name") or c.get("author", {}).get("username") or "unknown"
        msg = c.get("message", "")
        if msg:
            background_tasks.add_task(_run_github_graph_b, org_id, repo, branch, author, msg, delivery_id)

    return Response(content=json.dumps({"status": "accepted", "commits": len(commits)}), media_type="application/json", status_code=200)

