"""
agent/nodes/slack_dm.py — Graph B: Ask Assignee for Status Clarification
=========================================================================
Triggered when intent is AMBIGUOUS and turn_count < 2.
Sends a targeted Slack DM asking the assignee for a clearer status update,
then increments turn_count before looping back to intent_parser_node.
"""

import logging
import os

from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from agent.state import AgentState

load_dotenv()
logger = logging.getLogger(__name__)

# Clarification messages vary by turn to avoid sounding robotic
CLARIFICATION_TEMPLATES = [
    # Turn 1 (first follow-up)
    (
        "👋 Hey *{assignee}*, quick check-in on *<{ticket_url}|{task_title}>*.\n\n"
        "Could you give me a clearer status? Just reply with one of:\n"
        "• *Done* — if it's fully complete ✅\n"
        "• *Blocked* — if you're stuck and need help 🚫\n"
        "• A percentage — e.g. *80% done* 📊"
    ),
    # Turn 2 (final attempt before escalation)
    (
        "⚠️ *{assignee}* — last check before I escalate to your manager.\n\n"
        "Ticket: *<{ticket_url}|{task_title}>*\n\n"
        "Please reply *Done* or *Blocked* so I can update Jira accurately. "
        "If I don't get a clear answer, I'll flag this for manager review. 🙏"
    ),
]


def slack_dm_node(state: AgentState) -> dict:
    """
    Send a Slack DM to the assignee requesting a clearer status update.
    Increments turn_count so route_intent can apply the loop guardrail.

    Returns:
        {"turn_count": incremented_count}
    """
    assignee = state.get("tracker_assignee", "there")
    task_id = state.get("tracker_task_id")
    turn_count = state.get("turn_count", 0)
    intent = state.get("parsed_intent", "AMBIGUOUS")
    confidence = state.get("intent_confidence", 0.0)

    # Resolve task details
    tasks = state.get("tasks", {})
    ticket_url = "#"
    task_title = task_id or "your task"

    if task_id and task_id in tasks:
        ticket_url = tasks[task_id].get("jira_url", "#")
        task_title = tasks[task_id].get("title", task_id)

    # Pick clarification template based on turn (0-indexed)
    template_idx = min(turn_count, len(CLARIFICATION_TEMPLATES) - 1)
    message = CLARIFICATION_TEMPLATES[template_idx].format(
        assignee=assignee,
        ticket_url=ticket_url,
        task_title=task_title[:60],
    )

    logger.info(
        "slack_dm_node: sending clarification DM to '%s' (turn %d, intent=%s, conf=%.2f).",
        assignee, turn_count + 1, intent, confidence,
    )

    # ── Send Slack DM ────────────────────────────────────────────────────
    slack_token = os.getenv("SLACK_BOT_TOKEN")
    if slack_token:
        try:
            client = WebClient(token=slack_token)
            client.chat_postMessage(
                channel=f"@{assignee.split()[0].lower()}",
                text=message,
            )
            logger.info(
                "slack_dm_node: clarification DM sent to '@%s'.",
                assignee.split()[0].lower(),
            )
        except SlackApiError as exc:
            logger.error(
                "slack_dm_node: Slack DM failed: %s", exc.response["error"]
            )
        except Exception as exc:
            logger.error("slack_dm_node: Slack error: %s", exc)
    else:
        logger.warning("slack_dm_node: SLACK_BOT_TOKEN not set — DM skipped.")

    # ── Increment turn_count (critical for loop guardrail) ───────────────
    new_turn_count = turn_count + 1
    logger.info(
        "slack_dm_node: turn_count %d → %d. Graph B loops back to intent_parser.",
        turn_count, new_turn_count,
    )

    return {"turn_count": new_turn_count}
