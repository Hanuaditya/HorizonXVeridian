"""6F: Org-scoped Jira capacity & workload checker (parallel firewall branch)."""

from __future__ import annotations

import logging
from typing import Dict, Optional

import httpx

from agent.state import AgentState, Task
from core.config import get_settings
from core.store import list_employees

logger = logging.getLogger(__name__)

NON_ACTIVE_STATUSES = {
    "ON_PATERNITY_LEAVE",
    "ON_MATERNITY_LEAVE",
    "ON_LEAVE",
    "TERMINATED",
    "INACTIVE",
    "NOT_FOUND",
}


def _get_live_jira_open_tickets(assignee: str) -> Optional[int]:
    settings = get_settings()
    if not all([settings.jira_base_url, settings.jira_email, settings.jira_api_token]):
        return None
    if "placeholder" in settings.jira_api_token.lower() or "yourcompany" in settings.jira_base_url.lower():
        return None

    jql = f'assignee="{assignee}" AND status!=Done'
    try:
        resp = httpx.get(
            f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search",
            params={"jql": jql, "maxResults": 0, "fields": "id"},
            auth=(settings.jira_email, settings.jira_api_token),
            timeout=10.0,
        )
        if resp.status_code == 404:
            return 0
        resp.raise_for_status()
        return int(resp.json().get("total", 0))
    except Exception as exc:
        logger.warning("capacity_checker_node: live Jira check failed (%s); using capacity cache.", exc)
        return None


def capacity_checker_node(state: AgentState) -> dict:
    """Check open tickets vs config-driven CAPACITY_LIMIT / CAPACITY_NEW_HIRE_LIMIT."""
    settings = get_settings()
    org_id = state.get("org_id") or "org_demo_horizon"
    tasks = state.get("tasks", {})
    employees = {e["full_name"].lower(): e for e in list_employees(org_id=org_id)}
    updates: Dict[str, Task] = {}

    for task_id, task in tasks.items():
        assignee = task.get("assignee", "UNASSIGNED")
        if not assignee or assignee.upper() == "UNASSIGNED":
            continue

        emp = employees.get(assignee.lower())
        emp_status = emp.get("status", "ACTIVE") if emp else "ACTIVE"
        if emp_status in NON_ACTIVE_STATUSES:
            continue

        threshold = (
            settings.capacity_new_hire_limit
            if emp_status == "NEW_HIRE"
            else settings.capacity_limit
        )
        live_count = _get_live_jira_open_tickets(assignee)
        ticket_count = (
            live_count
            if live_count is not None
            else int(emp.get("capacity_cache", 0) if emp else 0)
        )
        source_label = "Jira API live query" if live_count is not None else "Employees capacity cache"

        if ticket_count > threshold:
            flag = f"{assignee}: {ticket_count}/{threshold} open tickets ({emp_status} limit)"
            updates[task_id] = Task(
                capacity_flag=flag,
                capacity_provenance=f"{source_label} · {ticket_count}>{threshold}",
            )

    return {"tasks": updates}
