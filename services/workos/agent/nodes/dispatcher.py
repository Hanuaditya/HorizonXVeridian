"""6L: Idempotent, per-task isolated Jira ticket & Slack 1-on-1 DM dispatcher."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx  # noqa: F401 - retained for monkeypatch compatibility in tests

from agent.state import AgentState, Task
from connectors.jira_ops import create_jira_issue
from connectors.slack_ops import post_employee_assignment_dm
from core.store import upsert_slack_thread, upsert_tasks, write_audit_trail

logger = logging.getLogger(__name__)


def _create_jira_issue(
    title: str,
    description: str,
    assignee: str,
    task_id: str,
    commit_message: str = "",
) -> Dict[str, str]:
    # Compatibility wrapper so tests monkeypatching agent.nodes.dispatcher.httpx.post continue to work
    from core.config import get_settings
    from core.evon_llm import resolve_jira_project_key
    from connectors.jira_ops import _adf_doc, has_real_jira_creds

    settings = get_settings()
    if not has_real_jira_creds():
        return create_jira_issue(
            title=title,
            description=description,
            assignee=assignee,
            task_id=task_id,
            commit_message=commit_message,
        )

    project_key = resolve_jira_project_key()
    full_desc = description or ""
    if assignee:
        full_desc = f"Assigned Employee: {assignee}\n\n{full_desc}".strip()
    if commit_message:
        full_desc = f"{full_desc}\n\nProposed Commit Message:\n{commit_message}".strip()

    endpoint = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue"
    payload: Dict[str, Any] = {
        "fields": {
            "project": {"key": project_key},
            "summary": title,
            "description": _adf_doc(full_desc),
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
        "jira_status": "To Do",
    }


def _send_slack_notification(
    assignee: str,
    ticket_id: str,
    ticket_url: str,
    quote: str,
    org_id: str = "org_demo_horizon",
    thread_id: str = "closed-loop",
    task_id: str = "t1",
    task_title: str = "",
    commit_message: str = "",
) -> tuple[bool, str, str]:
    """Send 1-on-1 employee assignment DM via unified slack_ops."""
    return post_employee_assignment_dm(
        org_id=org_id,
        thread_id=thread_id,
        task_id=task_id,
        assignee=assignee,
        jira_key=ticket_id,
        jira_url=ticket_url,
        task_title=task_title or ticket_id,
        commit_message=commit_message or f"feat(sprint): {ticket_id}",
        quote=quote,
    )


def dispatcher_node(state: AgentState) -> dict:
    """Create Jira tickets and 1-on-1 Slack assignment DMs idempotently after Manager approval."""
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
        final_assignee = task.get("assignee") or "UNASSIGNED"
        if task.get("resolution_action") == "REROUTE" and task.get("rerouted_assignee"):
            final_assignee = str(task["rerouted_assignee"])
        commit_msg = task.get("proposed_commit_message") or f"feat(sprint): {final_title[:64].lower()}"

        try:
            jira_res = _create_jira_issue(
                title=final_title,
                description=final_desc,
                assignee=final_assignee,
                task_id=task_id,
                commit_message=commit_msg,
            )
            try:
                slack_ok, slack_ch, slack_ts = _send_slack_notification(
                    assignee=final_assignee,
                    ticket_id=jira_res["ticket_id"],
                    ticket_url=jira_res["url"],
                    quote=task.get("transcript_quote", ""),
                    org_id=org_id,
                    thread_id=thread_id,
                    task_id=task_id,
                    task_title=final_title,
                    commit_message=commit_msg,
                )
            except TypeError:
                slack_ok, slack_ch, slack_ts = _send_slack_notification(
                    assignee=final_assignee,
                    ticket_id=jira_res["ticket_id"],
                    ticket_url=jira_res["url"],
                    quote=task.get("transcript_quote", ""),
                )

            updates[task_id] = Task(
                status="DISPATCHED",
                assignee=final_assignee,
                jira_ticket_id=jira_res["ticket_id"],
                jira_url=jira_res["url"],
                jira_status=jira_res.get("jira_status", "To Do"),
                slack_dm_sent=slack_ok,
                progress_pct=0,
            )
            dispatched.append({
                "task_id": task_id,
                "title": final_title,
                "assignee": final_assignee,
                "jira_key": jira_res["ticket_id"],
                "jira_url": jira_res["url"],
                "jira_status": jira_res.get("jira_status", "To Do"),
                "commit_message": commit_msg,
                "slack_sent": slack_ok,
                "mode": jira_res["mode"],
                "progress_pct": 0,
            })

            upsert_slack_thread(
                org_id=org_id,
                thread_id=thread_id,
                task_id=task_id,
                jira_key=jira_res["ticket_id"],
                slack_channel=slack_ch,
                slack_thread_ts=slack_ts or f"ts_{jira_res['ticket_id']}",
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
