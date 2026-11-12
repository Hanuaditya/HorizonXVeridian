"""6C: Org-scoped HR status check node (parallel firewall branch)."""

from __future__ import annotations

import logging
from typing import Dict

from agent.state import AgentState, Task
from core.store import lookup_hr_employee

logger = logging.getLogger(__name__)


def hr_checker_node(state: AgentState) -> dict:
    """Query org-scoped hr_employees for each assignee's employment/leave status."""
    org_id = state.get("org_id") or "org_demo_horizon"
    tasks = state.get("tasks", {})
    updates: Dict[str, Task] = {}

    for task_id, task in tasks.items():
        assignee = task.get("assignee", "UNASSIGNED")
        if not assignee or assignee.upper() == "UNASSIGNED":
            continue

        row = lookup_hr_employee(org_id=org_id, assignee_name=assignee)
        if not row:
            updates[task_id] = Task(
                hr_status="NOT_FOUND",
                hr_provenance=f"BambooHR connector · '{assignee}' not found for org",
            )
            continue

        hr_status = row.get("status", "UNKNOWN")
        src = row.get("last_synced_from", "BambooHR connector")
        leave_note = f" (until {row['leave_until']})" if row.get("leave_until") else ""
        updates[task_id] = Task(
            hr_status=hr_status,
            hr_provenance=f"{src} · status={hr_status}{leave_note}",
        )
        logger.info("hr_checker_node: task='%s' org='%s' -> hr_status=%s", task_id, org_id, hr_status)

    return {"tasks": updates}

