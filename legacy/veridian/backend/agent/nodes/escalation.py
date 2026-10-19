"""
agent/nodes/escalation.py — Graph B: Escalate Blocked/Ambiguous Tasks
======================================================================
Triggered when:
  - intent_parser classifies reply as BLOCKED, OR
  - turn_count >= 2 (infinite-loop guardrail — force escalate after 2 tries)

Actions:
  1. PATCH Jira ticket status to "Blocked"
  2. Tag the manager in Slack with full context about the blockage
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

# Configurable via env — defaults to #product-team
MANAGER_SLACK_CHANNEL = os.getenv("SLACK_MANAGER_CHANNEL", "#product-team")
MANAGER_SLACK_HANDLE = os.getenv("SLACK_MANAGER_HANDLE", "@manager")


def _get_jira_transition_id(ticket_key: str, target_name: str) -> Optional[str]:
    """Dynamically resolve Jira transition ID by name."""
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
            # Match "In Progress", "Blocked", "On Hold" etc. depending on project config
            if target_name.lower() in t.get("name", "").lower():
                return t["id"]
    except Exception as exc:
        logger.error("escalation: failed to fetch Jira transitions: %s", exc)
    return None


def _patch_jira_blocked(ticket_key: str) -> bool:
    """Attempt to move Jira ticket to a blocked/in-progress state."""
    jira_url = os.getenv("JIRA_URL", "").rstrip("/")
    email = os.getenv("JIRA_EMAIL", "")
    token = os.getenv("JIRA_API_TOKEN", "")

    if not all([jira_url, email, token, ticket_key]):
        logger.warning("escalation: Jira credentials missing — skipping PATCH.")
        return False

    # Try "Blocked" first, fall back to "In Progress" (most Jira projects don't have "Blocked" as a transition)
    transition_id = (
        _get_jira_transition_id(ticket_key, "Blocked")
        or _get_jira_transition_id(ticket_key, "In Progress")
    )

    if not transition_id:
        logger.warning(
            "escalation: no Blocked/In Progress transition found for %s — "
            "adding label only.",
            ticket_key,
        )
        # Fall back: add a "blocked" label to the ticket
        try:
            httpx.put(
                f"{jira_url}/rest/api/3/issue/{ticket_key}",
                json={"update": {"labels": [{"add": "veridian-blocked"}]}},
                auth=(email, token),
                headers={"Content-Type": "application/json"},
                timeout=10.0,
            ).raise_for_status()
            logger.info("escalation: added 'veridian-blocked' label to %s.", ticket_key)
        except Exception as exc:
            logger.error("escalation: label update also failed: %s", exc)
        return False

    try:
        resp = httpx.post(
            f"{jira_url}/rest/api/3/issue/{ticket_key}/transitions",
            json={"transition": {"id": transition_id}},
            auth=(email, token),
            headers={"Content-Type": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        logger.info("escalation: ⚠️ Jira %s → Blocked.", ticket_key)
        return True
    except Exception as exc:
        logger.error("escalation: Jira PATCH failed for %s: %s", ticket_key, exc)
        return False


def escalation_node(state: AgentState) -> dict:
    """
    Escalate a blocked or perpetually-ambiguous task to the manager.

    Triggered by:
      - intent == "BLOCKED"
      - intent == "AMBIGUOUS" AND turn_count >= 2 (loop guardrail)

    Returns: {} — Graph B terminates after escalation (→ END).
    """
    task_id = state.get("tracker_task_id")
    assignee = state.get("tracker_assignee", "Unknown")
    slack_reply = state.get("last_slack_reply", "(no reply)")
    intent = state.get("parsed_intent", "AMBIGUOUS")
    confidence = state.get("intent_confidence", 0.0)
    turn_count = state.get("turn_count", 0)

    # Resolve ticket key from tasks
    tasks = state.get("tasks", {})
    ticket_key = None
    ticket_url = "#"
    task_title = task_id or "Unknown task"

    if task_id and task_id in tasks:
        ticket_key = tasks[task_id].get("jira_ticket_id")
        ticket_url = tasks[task_id].get("jira_url", "#")
        task_title = tasks[task_id].get("title", task_id)

    # Determine escalation reason
    if turn_count >= 2:
        reason = (
            f"*Loop guardrail triggered* — {assignee} did not clarify status "
            f"after {turn_count} attempts."
        )
    elif intent == "BLOCKED":
        reason = f"*{assignee} reported a blocker* (confidence: {confidence:.0%})."
    else:
        reason = f"*Intent unclear* ({intent}) after {turn_count} Slack exchanges."

    logger.warning(
        "escalation_node: ⚠️ Escalating task '%s' (intent=%s, turn=%d). Reason: %s",
        task_id, intent, turn_count, reason,
    )

    # ── PATCH Jira to Blocked ────────────────────────────────────────────
    if ticket_key:
        _patch_jira_blocked(ticket_key)

    # ── Tag manager in Slack ────────────────────────────────────────────
    slack_token = os.getenv("SLACK_BOT_TOKEN")
    if slack_token:
        try:
            client = WebClient(token=slack_token)
            message = (
                f"🚨 *Veridian WorkOS — Escalation Alert*\n\n"
                f"{MANAGER_SLACK_HANDLE} — your attention is needed.\n\n"
                f"*Task:* <{ticket_url}|{ticket_key or task_title}>\n"
                f"*Assignee:* {assignee}\n"
                f"*Reason:* {reason}\n\n"
                f"*Last reply from {assignee}:*\n"
                f"> _{slack_reply[:300]}_\n\n"
                f"_Tracked by Veridian WorkOS · Graph B · turn {turn_count}_"
            )
            client.chat_postMessage(
                channel=MANAGER_SLACK_CHANNEL,
                text=message,
            )
            logger.info(
                "escalation_node: Manager notification posted to %s.",
                MANAGER_SLACK_CHANNEL,
            )
        except SlackApiError as exc:
            logger.error(
                "escalation_node: Slack escalation failed: %s",
                exc.response["error"],
            )
        except Exception as exc:
            logger.error("escalation_node: Slack error: %s", exc)

    # Graph B ends here — no state changes needed
    return {}
