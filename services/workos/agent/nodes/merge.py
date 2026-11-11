"""6H: Fan-in synchronization barrier writing org-scoped audit trail & snapshot."""

from __future__ import annotations

import logging
from typing import List

from agent.state import AgentState
from core.store import upsert_tasks, write_audit_trail

logger = logging.getLogger(__name__)


def merge_node(state: AgentState) -> dict:
    """Persist merged parallel firewall results to tasks & audit_trail."""
    org_id = state.get("org_id") or "org_demo_horizon"
    meeting_id = state.get("meeting_id", "unknown")
    thread_id = state.get("thread_id", meeting_id)
    tasks = state.get("tasks", {})

    flagged_lines: List[str] = []
    for task_id, task in tasks.items():
        flags = []
        if task.get("assignee_resolution_flag"):
            flags.append(task["assignee_resolution_flag"])
        if task.get("hr_status") and task["hr_status"] not in ("ACTIVE", None):
            flags.append(f"HR={task['hr_status']}")
        if task.get("finance_flag"):
            flags.append("FINANCE")
        if task.get("security_flag"):
            flags.append("SECURITY")
        if task.get("capacity_flag"):
            flags.append("CAPACITY")
        if flags:
            flagged_lines.append(f"{task_id}:{','.join(flags)}")

    upsert_tasks(org_id=org_id, meeting_id=meeting_id, thread_id=thread_id, tasks=tasks)
    write_audit_trail(
        org_id=org_id,
        meeting_id=meeting_id,
        thread_id=thread_id,
        event_type="PARALLEL_CHECKS_COMPLETE",
        agent_node="merge_node",
        detail=f"{len(tasks)} tasks checked · {len(flagged_lines)} flagged ({'; '.join(flagged_lines)})",
        provenance_tag="LangGraph parallel firewall fan-in",
    )
    return {}
