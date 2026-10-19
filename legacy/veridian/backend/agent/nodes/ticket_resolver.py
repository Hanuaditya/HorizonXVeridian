"""
agent/nodes/ticket_resolver.py — Graph B: Mark Jira Ticket as Done
====================================================================
Triggered when intent_parser classifies the Slack reply as COMPLETED.
PATCHes the Jira ticket status to Done via the transitions API,
then posts a confirmation message back to the Slack thread.
"""

import logging
import os
from typing import Optional

import httpx
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from agent.state import AgentState

load_dotenv()
logger = logging.getLogger(__name__)

JIRA_DONE_TRANSITION_NAME = "Done"


def _get_jira_transition_id(ticket_key: str, target_name: str = "Done") -> Optional[str]:
    """
    Fetch available transitions for the ticket and find the 'Done' transition ID.
    Jira transition IDs vary per project so we must look them up dynamically.
    """
    jira_url = os.getenv("JIRA_URL", "").rstrip("/")
    email = os.getenv("JIRA_EMAIL", "")
    token = os.getenv("JIRA_API_TOKEN", "")

    try:
        resp = httpx.get(
            f"{jira_url}/rest/api/3/issue/{ticket_key}/transitions",
            auth=(email, token),
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        for t in resp.json().get("transitions", []):
            if t.get("name", "").lower() == target_name.lower():
                return t["id"]
    except Exception as exc:
        logger.error("ticket_resolver: failed to fetch transitions: %s", exc)
    return None


def _patch_jira_done(ticket_key: str) -> bool:
    """
    POST /rest/api/3/issue/{key}/transitions to move ticket to Done.
    Returns True on success.
    """
    jira_url = os.getenv("JIRA_URL", "").rstrip("/")
    email = os.getenv("JIRA_EMAIL", "")
    token = os.getenv("JIRA_API_TOKEN", "")

    if not all([jira_url, email, token, ticket_key]):
        logger.warning("ticket_resolver: Jira credentials or ticket key missing — skipping.")
        return False

    transition_id = _get_jira_transition_id(ticket_key, JIRA_DONE_TRANSITION_NAME)
    if not transition_id:
        logger.error(
            "ticket_resolver: could not find '%s' transition for %s.",
            JIRA_DONE_TRANSITION_NAME, ticket_key,
        )
        return False

    try:
        resp = httpx.post(
            f"{jira_url}/rest/api/3/issue/{ticket_key}/transitions",
            json={"transition": {"id": transition_id}},
            auth=(email, token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        logger.info("ticket_resolver: ✅ Jira %s → Done.", ticket_key)
        return True
    except Exception as exc:
        logger.error("ticket_resolver: Jira PATCH failed for %s: %s", ticket_key, exc)
        return False


def ticket_resolver_node(state: AgentState) -> dict:
    """
    Mark the tracked Jira ticket as Done and confirm in Slack.

    Returns:
        Partial task update with jira_ticket_id status update.
    """
    task_id = state.get("tracker_task_id")
    assignee = state.get("tracker_assignee", "the assignee")
    slack_reply = state.get("last_slack_reply", "")
    confidence = state.get("intent_confidence", 1.0)

    # ── Resolve the Jira ticket key from tasks dict ──────────────────────
    tasks = state.get("tasks", {})
    ticket_key = None
    ticket_url = "#"

    if task_id and task_id in tasks:
        ticket_key = tasks[task_id].get("jira_ticket_id")
        ticket_url = tasks[task_id].get("jira_url", "#")

    logger.info(
        "ticket_resolver: COMPLETED detected (conf=%.2f) for task '%s' → Jira '%s'.",
        confidence, task_id, ticket_key,
    )

    # ── PATCH Jira to Done ───────────────────────────────────────────────
    jira_success = False
    if ticket_key:
        jira_success = _patch_jira_done(ticket_key)

    # ── Post Slack confirmation ──────────────────────────────────────────
    slack_token = os.getenv("SLACK_BOT_TOKEN")
    if slack_token and assignee:
        try:
            client = WebClient(token=slack_token)
            client.chat_postMessage(
                channel=f"@{assignee.split()[0].lower()}",
                text=(
                    f"✅ Got it, *{assignee}*!\n\n"
                    f"I've marked *<{ticket_url}|{ticket_key or task_id}>* as *Done* in Jira.\n"
                    f"Updated from your Slack reply: _\"{slack_reply[:120]}\"_\n\n"
                    f"_{f'Confidence: {confidence:.0%}' if confidence else ''}_"
                ),
            )
            logger.info("ticket_resolver: Slack confirmation sent to '%s'.", assignee)
        except SlackApiError as exc:
            logger.warning("ticket_resolver: Slack confirmation failed: %s", exc.response["error"])
        except Exception as exc:
            logger.warning("ticket_resolver: Slack error: %s", exc)

    # ── Update task state ────────────────────────────────────────────────
    updates = {}
    if task_id and task_id in tasks:
        updates[task_id] = {"status": "READY", "slack_dm_sent": True}

    return {"tasks": updates} if updates else {}
