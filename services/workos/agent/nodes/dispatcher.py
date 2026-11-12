"""6L: Idempotent, per-task isolated Jira ticket & Slack DM dispatcher."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from agent.state import AgentState, Task
from core.config import get_settings
from core.evon_llm import resolve_jira_project_key, resolve_slack_channel
from core.store import upsert_slack_thread, upsert_tasks, write_audit_trail

logger = logging.getLogger(__name__)


def _has_real_jira_creds() -> bool:
    settings = get_settings()
    return bool(
        settings.jira_base_url
        and settings.jira_email
        and settings.jira_api_token
        and "yourcompany" not in settings.jira_base_url.lower()
        and "placeholder" not in settings.jira_api_token.lower()
    )


def _has_real_slack_creds() -> bool:
    settings = get_settings()
    return bool(
        settings.slack_bot_token
        and "placeholder" not in settings.slack_bot_token.lower()
    )


def _create_jira_issue(
    title: str,
    description: str,
    assignee: str,
    task_id: str,
) -> Dict[str, str]:
    settings = get_settings()
    project_key = resolve_jira_project_key()  # Strict config allow-list; never LLM output!

    if not _has_real_jira_creds():
        if settings.demo_mode:
            num = "".join(c for c in task_id if c.isdigit()) or "1"
            key = f"{project_key}-{100 + int(num)}"
            return {
                "ticket_id": key,
                "url": f"https://veridian-demo.atlassian.net/browse/{key}",
                "mode": "demo_mock",
            }
        raise EnvironmentError("Jira credentials required when DEMO_MODE=false.")

    endpoint = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue"
    payload: Dict[str, Any] = {
        "fields": {
            "project": {"key": project_key},
            "summary": title,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
            },
            "issuetype": {"name": "Task"},
            "labels": ["horizon-veridian", "meeting-extracted"],
        }
    }
    resp = httpx.post(
        endpoint,
        json=payload,
        auth=(settings.jira_email, settings.jira_api_token),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    key = str(data.get("key") or f"{project_key}-0")
    return {
        "ticket_id": key,
        "url": f"{settings.jira_base_url.rstrip('/')}/browse/{key}",
        "mode": "live_jira",
    }


def _resolve_live_slack_channel(client: Any, preferred_channel: str) -> str:
    """Resolve Slack channel ID cleanly, falling back to accessible workspace channels."""
    pref_clean = (preferred_channel or "").strip().lstrip("#").lower()
    fallback_order = ["all-veridian-workos", "general", "new-channel", "social"]
    try:
        resp = client.conversations_list(
            types="public_channel",
            exclude_archived=True,
            limit=200,
        )
        channels = resp.get("channels") or []
    except Exception as exc:
        logger.warning("Slack conversations_list failed (%s); using configured '%s'", exc, preferred_channel)
        return preferred_channel

    if not channels:
        return preferred_channel

    chosen = None
    for ch in channels:
        if (ch.get("id") or "").lower() == pref_clean or (ch.get("name") or "").lower() == pref_clean:
            chosen = ch
            break

    if chosen is None:
        by_name = {(ch.get("name") or "").lower(): ch for ch in channels}
        for name in fallback_order:
            if name in by_name:
                chosen = by_name[name]
                break
        if chosen is None:
            chosen = next((ch for ch in channels if ch.get("is_member")), channels[0])

    ch_id = str(chosen.get("id") or preferred_channel)
    if chosen and not chosen.get("is_member") and not chosen.get("is_private"):
        try:
            client.conversations_join(channel=ch_id)
        except Exception as join_exc:
            logger.debug("Slack conversations_join(%s) skipped: %s", ch_id, join_exc)
    return ch_id


def _send_slack_notification(
    assignee: str,
    ticket_id: str,
    ticket_url: str,
    quote: str,
) -> tuple[bool, str, str]:
    """Send assignee Slack DM or record mock Slack delivery in DEMO_MODE."""
    settings = get_settings()
    channel = resolve_slack_channel("summary")
    if not _has_real_slack_creds():
        if settings.demo_mode:
            return True, channel, f"demo_ts_{ticket_id}"
        return False, channel, ""

    from slack_sdk import WebClient

    client = WebClient(token=settings.slack_bot_token)
    resolved_channel = _resolve_live_slack_channel(client, channel)
    msg = client.chat_postMessage(
        channel=resolved_channel,
        text=(
            f"New ticket *{ticket_id}* assigned to *{assignee}*: {ticket_url}\n"
            f"> \"{quote}\""
        ),
    )
    return True, resolved_channel, str(msg.get("ts") or "")


def dispatcher_node(state: AgentState) -> dict:
    """Create Jira tickets and Slack notifications idempotently with per-task error isolation."""
    org_id = state.get("org_id") or "org_demo_horizon"
    meeting_id = state.get("meeting_id", "unknown")
    thread_id = state.get("thread_id", meeting_id)
    tasks = state.get("tasks", {})

    dispatched: List[Dict[str, Any]] = list(state.get("dispatched_tickets", []))
    already_dispatched_ids = {d["task_id"] for d in dispatched if d.get("jira_key")}
    updates: Dict[str, Task] = {}

    for task_id, task in tasks.items():
        if task.get("status") in {"DEFERRED", "CANCELLED"}:
            continue

        # Idempotency guard: if ticket already created for task_id, never duplicate!
        if task.get("jira_ticket_id") or task_id in already_dispatched_ids:
            logger.info("dispatcher_node: task '%s' already dispatched (%s) -> skipping.", task_id, task.get("jira_ticket_id"))
            continue

        final_title = task.get("reframed_title") or task.get("title") or "Action Item"
        final_desc = (
            task.get("reframed_description")
            or f"Meeting Quote: {task.get('transcript_quote', '')}"
        )
        final_assignee = task.get("rerouted_assignee") or task.get("assignee") or "UNASSIGNED"

        try:
            jira_res = _create_jira_issue(
                title=final_title,
                description=final_desc,
                assignee=final_assignee,
                task_id=task_id,
            )
            slack_ok, slack_ch, slack_ts = _send_slack_notification(
                assignee=final_assignee,
                ticket_id=jira_res["ticket_id"],
                ticket_url=jira_res["url"],
                quote=task.get("transcript_quote", ""),
            )

            updates[task_id] = Task(
                status="DISPATCHED",
                jira_ticket_id=jira_res["ticket_id"],
                jira_url=jira_res["url"],
                slack_dm_sent=slack_ok,
            )
            dispatched.append({
                "task_id": task_id,
                "title": final_title,
                "assignee": final_assignee,
                "jira_key": jira_res["ticket_id"],
                "jira_url": jira_res["url"],
                "slack_sent": slack_ok,
                "mode": jira_res["mode"],
            })

            if slack_ts:
                upsert_slack_thread(
                    org_id=org_id,
                    thread_id=thread_id,
                    task_id=task_id,
                    jira_key=jira_res["ticket_id"],
                    slack_channel=slack_ch,
                    slack_thread_ts=slack_ts,
                    assignee=final_assignee,
                    turn_count=0,
                    status="OPEN",
                )

            write_audit_trail(
                org_id=org_id,
                meeting_id=meeting_id,
                thread_id=thread_id,
                task_id=task_id,
                event_type="TICKET_DISPATCHED",
                agent_node="dispatcher_node",
                detail=f"Created {jira_res['ticket_id']} assigned to {final_assignee}",
                provenance_tag=f"Jira Dispatcher ({jira_res['mode']})",
                actor_id=state.get("approver_user_id"),
            )
        except Exception as exc:
            # Per-task isolation: record error on this task without aborting siblings
            logger.error("dispatcher_node: task '%s' dispatch failed: %s", task_id, exc)
            updates[task_id] = Task(dispatch_error=str(exc))
            write_audit_trail(
                org_id=org_id,
                meeting_id=meeting_id,
                thread_id=thread_id,
                task_id=task_id,
                event_type="DISPATCH_FAILED",
                agent_node="dispatcher_node",
                detail=str(exc),
                provenance_tag="Jira Dispatcher Error",
            )

    merged = {k: {**tasks.get(k, {}), **v} for k, v in updates.items()}
    upsert_tasks(org_id=org_id, meeting_id=meeting_id, thread_id=thread_id, tasks=merged)
    return {
        "tasks": updates,
        "dispatched_tickets": dispatched,
    }

