"""
agent/nodes/capacity_checker.py — 6F: Jira Ticket Load Checker
===============================================================
Queries the live Jira API to count open tickets for each task's assignee.
Applies a NEW_HIRE threshold of 2 tickets (vs. 10 for regular employees).

Note on parallel execution:
  hr_status is checked at runtime — if None (not yet set by hr_checker_node
  running in parallel), we proceed with the Jira check. The reducer will
  merge both checkers' results safely.
"""

import logging
import os
from typing import Dict, Optional

import httpx
from dotenv import load_dotenv
from supabase import create_client, Client

from agent.state import AgentState

load_dotenv()
logger = logging.getLogger(__name__)

REGULAR_THRESHOLD = 10
NEW_HIRE_THRESHOLD = 2

NON_ACTIVE_STATUSES = {
    "ON_PATERNITY_LEAVE",
    "ON_MATERNITY_LEAVE",
    "ON_LEAVE",
    "TERMINATED",
    "INACTIVE",
    "NOT_FOUND",
}


def _get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
    return create_client(url, key)


def _get_jira_open_tickets(assignee: str) -> Optional[int]:
    """
    Query Jira API for open ticket count for the given assignee.
    Returns the total count, or None if the query fails.
    """
    jira_url = os.getenv("JIRA_URL", "").rstrip("/")
    jira_email = os.getenv("JIRA_EMAIL")
    jira_token = os.getenv("JIRA_API_TOKEN")

    if not all([jira_url, jira_email, jira_token]):
        logger.warning("capacity_checker_node: Jira credentials not fully set — skipping.")
        return None

    jql = f'assignee="{assignee}" AND status!=Done'
    params = {"jql": jql, "maxResults": 0, "fields": "id"}

    try:
        response = httpx.get(
            f"{jira_url}/rest/api/3/search",
            params=params,
            auth=(jira_email, jira_token),
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        return int(data.get("total", 0))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            # Assignee not found in Jira — not necessarily an error
            logger.debug(
                "capacity_checker_node: no Jira user found for '%s'.", assignee
            )
            return 0
        logger.error(
            "capacity_checker_node: Jira API error for '%s': %s",
            assignee, exc,
        )
        return None
    except Exception as exc:
        logger.error(
            "capacity_checker_node: Jira request failed for '%s': %s",
            assignee, exc,
        )
        return None


def _get_employee_status(assignee: str, supabase: Client) -> str:
    """
    Check the employees table (capacity cache) to detect NEW_HIRE status.
    Falls back to "ACTIVE" if not found — threshold defaults to regular.
    """
    try:
        result = (
            supabase.table("employees")
            .select("status")
            .ilike("full_name", f"%{assignee}%")
            .execute()
        )
        if result.data:
            return result.data[0].get("status", "ACTIVE")
    except Exception as exc:
        logger.debug(
            "capacity_checker_node: employees table query failed for '%s': %s",
            assignee, exc,
        )
    return "ACTIVE"


def capacity_checker_node(state: AgentState) -> dict:
    """
    Live Jira capacity check for each task's assignee.

    Returns:
        Partial tasks dict: {task_id: {"capacity_flag": ..., "capacity_provenance": ...}}
        Only contains entries where the threshold is exceeded.
    """
    supabase = _get_supabase()
    tasks = state.get("tasks", {})
    updates: Dict[str, dict] = {}

    for task_id, task in tasks.items():
        assignee = task.get("assignee", "UNASSIGNED")

        if not assignee or assignee.upper() == "UNASSIGNED":
            continue

        # ── Skip if HR has already confirmed non-active status ───────────
        # (In parallel execution, hr_status may be None — that's fine,
        #  the resolver will handle contradictions later)
        hr_status = task.get("hr_status")
        if hr_status and hr_status in NON_ACTIVE_STATUSES:
            logger.debug(
                "capacity_checker_node: task '%s' assignee '%s' is %s — skipping.",
                task_id, assignee, hr_status,
            )
            continue

        # ── Determine threshold based on employee status ─────────────────
        emp_status = _get_employee_status(assignee, supabase)
        threshold = NEW_HIRE_THRESHOLD if emp_status == "NEW_HIRE" else REGULAR_THRESHOLD

        # ── Query Jira ───────────────────────────────────────────────────
        ticket_count = _get_jira_open_tickets(assignee)
        if ticket_count is None:
            # Query failed — don't block the task
            continue

        logger.info(
            "capacity_checker_node: '%s' has %d/%d open tickets (status=%s).",
            assignee, ticket_count, threshold, emp_status,
        )

        if ticket_count > threshold:
            capacity_flag = (
                f"{assignee}: {ticket_count}/{threshold} open tickets "
                f"({'NEW_HIRE' if emp_status == 'NEW_HIRE' else 'regular'} threshold)"
            )
            updates[task_id] = {
                "capacity_flag": capacity_flag,
                "capacity_provenance": "Jira API · live query",
            }
            logger.warning(
                "capacity_checker_node: 🚨 task '%s' flagged — %s",
                task_id, capacity_flag,
            )

    return {"tasks": updates}
