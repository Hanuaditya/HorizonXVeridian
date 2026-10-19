"""
agent/nodes/auto_router.py — 6G: Automatic Assignee Re-routing
===============================================================
Triggered when a task has a capacity_flag OR an hr_status that is not ACTIVE.
Queries the Supabase employees table (capacity cache) to find the least-loaded
ACTIVE employee and sets them as the rerouted_assignee.
"""

import logging
import os
from typing import Dict

from dotenv import load_dotenv
from supabase import create_client, Client

from agent.state import AgentState

load_dotenv()
logger = logging.getLogger(__name__)

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


def auto_router_node(state: AgentState) -> dict:
    """
    Find the least-loaded ACTIVE employee for tasks that need rerouting.

    Targets tasks where:
      - capacity_flag is set (over ticket threshold), OR
      - hr_status is not ACTIVE (leave, terminated, etc.)

    SQL used (as per Master Prompt):
        SELECT full_name, open_tickets, last_synced_from
        FROM employees
        WHERE status = 'ACTIVE'
        ORDER BY open_tickets ASC
        LIMIT 1

    Returns:
        Partial tasks dict: {task_id: {"rerouted_assignee": ..., "capacity_provenance": ...}}
    """
    supabase = _get_supabase()
    tasks = state.get("tasks", {})
    updates: Dict[str, dict] = {}

    # ── Find tasks that need rerouting ───────────────────────────────────
    tasks_needing_reroute = {
        task_id: task
        for task_id, task in tasks.items()
        if task.get("capacity_flag")
        or task.get("hr_status") in NON_ACTIVE_STATUSES
    }

    if not tasks_needing_reroute:
        logger.debug("auto_router_node: no tasks need rerouting.")
        return {}

    # ── Query Supabase for best available employee ────────────────────────
    try:
        result = (
            supabase.table("employees")
            .select("full_name, open_tickets, last_synced_from")
            .eq("status", "ACTIVE")
            .order("open_tickets", desc=False)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.error("auto_router_node: Supabase query failed — %s", exc)
        return {}

    if not result.data:
        logger.warning(
            "auto_router_node: no ACTIVE employees found in employees table. "
            "Cannot reroute."
        )
        return {}

    best = result.data[0]
    new_assignee: str = best.get("full_name", "UNASSIGNED")
    new_assignee_tickets: int = int(best.get("open_tickets", 0))
    synced_from: str = best.get("last_synced_from", "Jira API")

    logger.info(
        "auto_router_node: best available employee = '%s' (%d open tickets).",
        new_assignee, new_assignee_tickets,
    )

    # ── Apply rerouted_assignee to each flagged task ──────────────────────
    for task_id, task in tasks_needing_reroute.items():
        original_assignee = task.get("assignee", "UNASSIGNED")
        original_count = task.get("capacity_flag", "")  # Has the count string

        provenance = (
            f"Auto-router · '{original_assignee}' unavailable/overloaded "
            f"· '{new_assignee}' has {new_assignee_tickets} open tickets"
        )

        logger.info(
            "auto_router_node: task '%s' → rerouting from '%s' to '%s'.",
            task_id, original_assignee, new_assignee,
        )

        updates[task_id] = {
            "rerouted_assignee": new_assignee,
            "capacity_provenance": provenance,
        }

    return {"tasks": updates}
