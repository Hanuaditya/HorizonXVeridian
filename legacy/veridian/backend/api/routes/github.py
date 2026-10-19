"""
api/routes/github.py — POST /api/github-webhook
================================================
Receives GitHub push webhooks, verifies the secret, and routes each
commit through Graph B's semantic_matcher entry point to find and
update the matching Jira ticket.

Returns 200 immediately — Graph B runs as a BackgroundTask.
"""

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from agent.graph_b import graph_b_github
from api.sse import sse_manager

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# GitHub signature verification
# ---------------------------------------------------------------------------

def _verify_github_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Verify GitHub HMAC-SHA256 webhook signature.
    Header format: "sha256=<hex_digest>"
    """
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        logger.warning("github_webhook: GITHUB_WEBHOOK_SECRET not set — skipping verification.")
        return True  # Dev mode

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header)


# ---------------------------------------------------------------------------
# Background task — runs Graph B (GitHub / semantic_matcher path)
# ---------------------------------------------------------------------------

async def _run_graph_b_github(
    commit_message: str,
    branch: str,
    author: str,
    repo: str,
    tasks_snapshot: Dict[str, Any],
) -> None:
    """
    Invoke Graph B starting at semantic_matcher_node.
    The combined commit + branch string goes into last_slack_reply
    (semantic_matcher reads from this field).
    """
    # Build a rich commit description for the semantic matcher
    search_text = (
        f"GitHub commit by {author} on branch '{branch}' in '{repo}':\n"
        f"{commit_message}"
    )

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
        "turn_count": 0,
        "tracker_task_id": None,          # semantic_matcher will set this
        "tracker_assignee": author,
        "last_slack_reply": search_text,  # semantic_matcher reads from here
        "parsed_intent": None,
        "intent_confidence": None,
    }

    config = {"configurable": {"thread_id": f"github-{repo}-{hash(commit_message)}"}}

    try:
        logger.info(
            "_run_graph_b_github: matching commit '%s…' by '%s' on '%s'.",
            commit_message[:80], author, branch,
        )
        graph_b_github.invoke(initial_state, config=config)
    except Exception as exc:
        logger.error(
            "_run_graph_b_github: Graph B (GitHub) error: %s", exc, exc_info=True
        )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.post("/github-webhook")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """
    POST /api/github-webhook

    Accepts GitHub push events. For each commit in the push:
      - Verifies the HMAC-SHA256 signature
      - Extracts commit message, author, and branch
      - Runs Graph B semantic_matcher in background to find + update Jira ticket

    Returns 200 immediately.
    """
    raw_body = await request.body()

    # ── Verify GitHub signature ──────────────────────────────────────────
    sig_header = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_github_signature(raw_body, sig_header):
        raise HTTPException(status_code=403, detail="Invalid GitHub webhook signature.")

    # ── Only handle push events ──────────────────────────────────────────
    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type not in ("push", "pull_request"):
        return Response(
            content=json.dumps({"status": "ignored", "event": event_type}),
            media_type="application/json",
            status_code=200,
        )

    try:
        payload: Dict[str, Any] = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    # ── Extract push context ─────────────────────────────────────────────
    repo = payload.get("repository", {}).get("full_name", "unknown-repo")
    ref = payload.get("ref", "refs/heads/main")
    branch = ref.replace("refs/heads/", "")
    commits: List[Dict[str, Any]] = payload.get("commits", [])

    if not commits:
        return Response(
            content=json.dumps({"status": "no_commits"}),
            media_type="application/json",
            status_code=200,
        )

    logger.info(
        "github_webhook: %d commit(s) on '%s/%s'.", len(commits), repo, branch
    )

    # ── Dispatch one background task per commit ──────────────────────────
    for commit in commits:
        commit_message: str = commit.get("message", "").strip()
        author: str = (
            commit.get("author", {}).get("name")
            or commit.get("author", {}).get("username")
            or "unknown"
        )

        if not commit_message:
            continue

        background_tasks.add_task(
            _run_graph_b_github,
            commit_message=commit_message,
            branch=branch,
            author=author,
            repo=repo,
            tasks_snapshot={},   # In production: load open tasks from DB
        )

    return Response(
        content=json.dumps({
            "status": "processing",
            "commits_queued": len(commits),
            "repo": repo,
            "branch": branch,
        }),
        media_type="application/json",
        status_code=200,
    )
