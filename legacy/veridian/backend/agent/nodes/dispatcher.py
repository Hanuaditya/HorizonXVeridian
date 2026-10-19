"""
agent/nodes/dispatcher.py — 6L: Jira Ticket Creation + Slack Notifications
===========================================================================
The final execution node. For each non-DEFERRED task:
  1. Creates a Jira issue via REST API (POST /rest/api/3/issue)
  2. Sends a Slack DM to the assignee with the ticket link + transcript quote
  3. Posts a full meeting summary to the #product-team Slack channel

Returns {"dispatched_tickets": [...]} for the audit trail.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from agent.state import AgentState

load_dotenv()
logger = logging.getLogger(__name__)

SLACK_CHANNEL = "#product-team"   # Configurable — override with env var


# ---------------------------------------------------------------------------
# Jira helpers
# ---------------------------------------------------------------------------

def _get_jira_auth() -> tuple:
    email = os.getenv("JIRA_EMAIL", "")
    token = os.getenv("JIRA_API_TOKEN", "")
    return (email, token)


def _create_jira_ticket(
    title: str,
    description: str,
    assignee_display_name: str,
    project_key: str,
    jira_url: str,
) -> Optional[Dict[str, str]]:
    """
    POST /rest/api/3/issue to create a Jira ticket.
    Returns {"ticket_id": ..., "url": ...} or None on failure.
    """
    endpoint = f"{jira_url.rstrip('/')}/rest/api/3/issue"
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": title,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            },
            "issuetype": {"name": "Task"},
            "labels": ["veridian-auto", "meeting-extracted"],
        }
    }

    # Add assignee if displayName is not UNASSIGNED
    if assignee_display_name and assignee_display_name.upper() != "UNASSIGNED":
        payload["fields"]["assignee"] = {"displayName": assignee_display_name}

    try:
        response = httpx.post(
            endpoint,
            json=payload,
            auth=_get_jira_auth(),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=15.0,
        )
        response.raise_for_status()
        data = response.json()
        ticket_key = data.get("key", "UNKNOWN")
        ticket_url = f"{jira_url.rstrip('/')}/browse/{ticket_key}"
        logger.info("dispatcher: Created Jira ticket %s → %s", ticket_key, ticket_url)
        return {"ticket_id": ticket_key, "url": ticket_url}

    except httpx.HTTPStatusError as exc:
        logger.error(
            "dispatcher: Jira ticket creation failed (HTTP %d): %s",
            exc.response.status_code,
            exc.response.text[:300],
        )
        return None
    except Exception as exc:
        logger.error("dispatcher: Jira request error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Slack helpers
# ---------------------------------------------------------------------------

def _get_slack_client() -> Optional[WebClient]:
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        logger.warning("dispatcher: SLACK_BOT_TOKEN not set — Slack DMs disabled.")
        return None
    return WebClient(token=token)


def _send_slack_dm(
    client: WebClient,
    assignee: str,
    ticket_url: str,
    transcript_quote: str,
    reframe_note: Optional[str] = None,
) -> bool:
    """
    Send a DM to @assignee with the new Jira ticket link and context.
    """
    
    # ── DEMO GUARDRAIL: ONLY DM SPECIFIC PEOPLE ──
    allowed_demo_users = ["josh", "scott"]
    target_username = assignee.split()[0].lower()
    
    if target_username not in allowed_demo_users:
        logger.info("dispatcher: Slack DM skipped for @%s (not in demo list).", target_username)
        return False

    text_parts = [
        f"👋 Hey *{assignee}* — Veridian WorkOS just assigned you a new ticket.",
        f"",
        f"🎫 *Ticket:* {ticket_url}",
        f"",
        f"📝 *Why you were assigned:*",
        f'"{transcript_quote}"',
    ]
    if reframe_note:
        text_parts += ["", f"⚠️ *Note:* {reframe_note}"]

    text = "\n".join(text_parts)

    try:
        # Lookup the true Slack ID via the API as @username DMing is deprecated
        users = client.users_list()["members"]
        user_id = None
        for u in users:
            if u.get("is_bot") or u.get("deleted"):
                continue
            
            p = u.get("profile", {})
            d_name = p.get("display_name", "").lower()
            r_name = p.get("real_name", "").split()[0].lower() if p.get("real_name") else ""
            u_name = u.get("name", "").lower()
            
            if target_username in [d_name, r_name, u_name]:
                user_id = u["id"]
                break
                
        if not user_id:
            logger.warning("dispatcher: Slack user '%s' could not be found via lookup.", target_username)
            return False

        # Send the DM exactly to the resolved user_id
        client.chat_postMessage(channel=user_id, text=text)
        logger.info("dispatcher: Slack DM successfully sent to %s (User ID: %s).", target_username, user_id)
        return True
        
    except SlackApiError as exc:
        logger.warning(
            "dispatcher: Slack DM to '%s' failed: %s",
            assignee, exc.response["error"],
        )
        return False


def _post_meeting_summary(
    client: WebClient,
    state: AgentState,
    dispatched: List[Dict[str, Any]],
    deferred: List[Dict[str, Any]],
) -> None:
    """
    Post a comprehensive meeting summary to the configured Slack channel.
    """
    channel = os.getenv("SLACK_SUMMARY_CHANNEL", SLACK_CHANNEL)
    ctx = state.get("meeting_context", {})
    decisions = state.get("key_decisions", [])

    # Build TL;DR section
    bullets = ctx.get("tldr_bullets", [])
    tldr_text = "\n".join(f"• {b}" for b in bullets) if bullets else "No summary available."

    # Build tickets section
    ticket_lines = []
    for t in dispatched:
        ticket_lines.append(
            f"• <{t['jira_url']}|{t['jira_ticket_id']}> — {t['title']} → {t['assignee']}"
        )
    tickets_text = "\n".join(ticket_lines) if ticket_lines else "_No tickets created._"

    # Build deferred section
    deferred_lines = [
        f"• {t['title']} (DEFERRED — {t.get('reframed_description', 'budget/policy constraint')})"
        for t in deferred
    ]
    deferred_text = "\n".join(deferred_lines) if deferred_lines else "_None._"

    # Build decisions section
    decision_lines = [f"• {d.get('decision', '')}" for d in decisions]
    decisions_text = "\n".join(decision_lines) if decision_lines else "_No decisions recorded._"

    summary = (
        f"*🤖 Veridian WorkOS — Meeting Summary*\n"
        f"*Meeting:* {ctx.get('title', 'Unknown')} | {ctx.get('date', '')}\n"
        f"*Attendees:* {', '.join(ctx.get('attendees', []))}\n\n"
        f"*📋 TL;DR*\n{tldr_text}\n\n"
        f"*🎫 Tickets Created ({len(dispatched)})*\n{tickets_text}\n\n"
        f"*⏱ Deferred Tasks ({len(deferred)})*\n{deferred_text}\n\n"
        f"*✅ Key Decisions*\n{decisions_text}"
    )

    try:
        client.chat_postMessage(channel=channel, text=summary)
        logger.info("dispatcher: Meeting summary posted to %s.", channel)
    except SlackApiError as exc:
        logger.error(
            "dispatcher: Failed to post summary to %s: %s",
            channel, exc.response["error"],
        )


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def dispatcher_node(state: AgentState) -> dict:
    """
    Final execution node — creates Jira tickets and sends Slack notifications.

    Skips DEFERRED tasks (status=="DEFERRED" or resolution_action=="DEFER").
    Returns {"dispatched_tickets": [...]} for the audit trail.
    """
    tasks = state.get("tasks", {})
    jira_url = os.getenv("JIRA_URL", "").rstrip("/")
    project_key = os.getenv("JIRA_PROJECT_KEY", "VER")
    slack_client = _get_slack_client()

    dispatched_tickets: List[Dict[str, Any]] = []
    deferred_tasks: List[Dict[str, Any]] = []
    task_updates: Dict[str, dict] = {}

    for task_id, task in tasks.items():
        status = task.get("status", "PENDING")
        resolution = task.get("resolution_action", "PROCEED")

        # ── Skip deferred tasks ──────────────────────────────────────────
        if status == "DEFERRED" or resolution == "DEFER":
            logger.info("dispatcher: task '%s' is DEFERRED — skipping Jira creation.", task_id)
            deferred_tasks.append(task)
            continue

        # ── Resolve final title and description ──────────────────────────
        final_title = task.get("reframed_title") or task.get("title", "Untitled Task")
        final_description = (
            task.get("reframed_description")
            or task.get("title", "No description available.")
        )
        assignee = task.get("assignee", "UNASSIGNED")
        transcript_quote = task.get("transcript_quote", "")

        # ── Create Jira ticket ───────────────────────────────────────────
        jira_result = None
        if jira_url and project_key:
            jira_result = _create_jira_ticket(
                title=final_title,
                description=final_description,
                assignee_display_name=assignee,
                project_key=project_key,
                jira_url=jira_url,
            )
        else:
            logger.warning(
                "dispatcher: JIRA_URL or JIRA_PROJECT_KEY not set — "
                "skipping Jira creation for task '%s'.",
                task_id,
            )

        ticket_id = jira_result["ticket_id"] if jira_result else f"VERIDIAN-{task_id}"
        ticket_url = jira_result["url"] if jira_result else "#"

        # ── Send Slack DM to assignee ────────────────────────────────────
        slack_sent = False
        reframe_note = None
        if resolution == "REFRAME":
            reframe_note = (
                f"This task was reframed by Veridian WorkOS to comply with "
                f"corporate policy. Original: \"{task.get('title')}\"."
            )
        elif resolution == "REROUTE":
            original = task.get("rerouted_assignee")
            reframe_note = f"You were auto-assigned by Veridian (original: {original or 'unknown'})."

        if slack_client and assignee.upper() != "UNASSIGNED":
            slack_sent = _send_slack_dm(
                client=slack_client,
                assignee=assignee,
                ticket_url=ticket_url,
                transcript_quote=transcript_quote,
                reframe_note=reframe_note,
            )

        # ── Record dispatch result ───────────────────────────────────────
        ticket_record = {
            "task_id": task_id,
            "title": final_title,
            "assignee": assignee,
            "jira_ticket_id": ticket_id,
            "jira_url": ticket_url,
            "slack_dm_sent": slack_sent,
            "resolution_action": resolution,
        }
        dispatched_tickets.append(ticket_record)
        task_updates[task_id] = {
            "jira_ticket_id": ticket_id,
            "jira_url": ticket_url,
            "slack_dm_sent": slack_sent,
            "status": "READY",
        }

        logger.info(
            "dispatcher: ✅ task '%s' → Jira %s (Slack DM: %s).",
            task_id, ticket_id, "sent" if slack_sent else "skipped",
        )

    # ── Post meeting summary to Slack channel ────────────────────────────
    if slack_client:
        _post_meeting_summary(
            client=slack_client,
            state=state,
            dispatched=dispatched_tickets,
            deferred=deferred_tasks,
        )

    logger.info(
        "dispatcher: 🏁 Done. %d tickets created, %d deferred.",
        len(dispatched_tickets), len(deferred_tasks),
    )

    return {
        "tasks": task_updates,
        "dispatched_tickets": dispatched_tickets,
    }
