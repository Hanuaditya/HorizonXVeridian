"""6G: Org-scoped auto-router selecting least-loaded ACTIVE employee."""

from __future__ import annotations

import logging
from typing import Dict

from agent.state import AgentState, Task
from core.store import find_least_loaded_active_employee

logger = logging.getLogger(__name__)

NON_ACTIVE_STATUSES = {
    "ON_PATERNITY_LEAVE",
    "ON_MATERNITY_LEAVE",
    "ON_LEAVE",
    "TERMINATED",
    "INACTIVE",
    "NOT_FOUND",
}


def auto_router_node(state: AgentState) -> dict:
    """Assign least-loaded ACTIVE employee for tasks with capacity or leave flags."""
    org_id = state.get("org_id") or "org_demo_horizon"
    tasks = state.get("tasks", {})
    updates: Dict[str, Task] = {}

    for task_id, task in tasks.items():
        hr_status = task.get("hr_status")
        needs_reroute = bool(task.get("capacity_flag")) or (
            hr_status in NON_ACTIVE_STATUSES
        )
        if not needs_reroute:
            continue

        current_assignee = task.get("assignee", "UNASSIGNED")
        best = find_least_loaded_active_employee(org_id=org_id, exclude_name=current_assignee)
        if not best:
            continue

        new_assignee = best["full_name"]
        load = int(best.get("capacity_cache", 0))
        updates[task_id] = Task(
            rerouted_assignee=new_assignee,
            capacity_provenance=(
                f"Auto-router · '{current_assignee}' unavailable/overloaded -> "
                f"'{new_assignee}' ({load} open tickets)"
            ),
        )
        logger.info("auto_router_node: task='%s' rerouted '%s' -> '%s'", task_id, current_assignee, new_assignee)

    return {"tasks": updates}
