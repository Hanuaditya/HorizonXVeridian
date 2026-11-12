"""6G: Org-scoped auto-router selecting least-loaded ACTIVE employee."""

from __future__ import annotations

import logging
from typing import Dict

from agent.state import AgentState, Task
from core.store import find_best_domain_replacement

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
    """Suggest best domain-matched ACTIVE employee with lowest workload (suggest-only until Manager approves)."""
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
        task_text = f"{task.get('title', '')} {task.get('transcript_quote', '')}"
        best = find_best_domain_replacement(
            org_id=org_id,
            task_text=task_text,
            resource_type=str(task.get("resource_type") or ""),
            exclude_name=current_assignee,
        )
        if not best:
            continue

        new_assignee = best["full_name"]
        load = int(best.get("active_task_count") or best.get("capacity_cache") or 0)
        matched_skills = best.get("matched_skills") or best.get("domain_skills") or []
        skills_str = ", ".join(matched_skills) if matched_skills else "general engineering"
        leave_rec = (
            f"{current_assignee} is currently on leave. Suggested replacement: {new_assignee} "
            f"(Domain match: {skills_str}, Lowest workload: {load} active tasks). "
            "Review and click Approve to redirect and create their Jira ticket."
        )
        updates[task_id] = Task(
            rerouted_assignee=new_assignee,
            leave_recommendation=leave_rec,
            capacity_provenance=(
                f"Smart Redirect · '{current_assignee}' unavailable -> "
                f"'{new_assignee}' (skills: {skills_str}; {load} active tasks)"
            ),
        )
        logger.info("auto_router_node: task='%s' suggested '%s' -> '%s'", task_id, current_assignee, new_assignee)

    return {"tasks": updates}

