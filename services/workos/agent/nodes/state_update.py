"""6K: Apply approved/overridden HITL decisions to tasks before dispatch."""

from __future__ import annotations

import logging
from typing import Dict

from agent.state import AgentState, Task
from core.store import upsert_tasks, write_audit_trail

logger = logging.getLogger(__name__)


def state_update_node(state: AgentState) -> dict:
    """Translate HITL/AI decisions into final dispatchable task states."""
    org_id = state.get("org_id") or "org_demo_horizon"
    meeting_id = state.get("meeting_id", "unknown")
    thread_id = state.get("thread_id", meeting_id)
    decisions = state.get("hitl_decisions", {})
    resolutions = {r["task_id"]: r for r in state.get("resolutions", [])}
    tasks = state.get("tasks", {})
    updates: Dict[str, Task] = {}

    for task_id, task in tasks.items():
        action = (
            decisions.get(task_id)
            or (resolutions.get(task_id) or {}).get("suggested_action")
            or task.get("resolution_action")
            or "PROCEED"
        ).upper()

        if action == "DEFER":
            updates[task_id] = Task(status="DEFERRED", resolution_action="DEFER")
        elif action == "CANCEL":
            updates[task_id] = Task(status="CANCELLED", resolution_action="CANCEL")
        elif action == "REROUTE":
            new_assignee = task.get("rerouted_assignee") or task.get("assignee")
            updates[task_id] = Task(
                status="READY",
                resolution_action="REROUTE",
                assignee=new_assignee,
            )
        else:
            updates[task_id] = Task(status="READY", resolution_action=action)

    merged = {k: {**tasks.get(k, {}), **v} for k, v in updates.items()}
    upsert_tasks(org_id=org_id, meeting_id=meeting_id, thread_id=thread_id, tasks=merged)
    write_audit_trail(
        org_id=org_id,
        meeting_id=meeting_id,
        thread_id=thread_id,
        event_type="HITL_APPLIED",
        agent_node="state_update_node",
        detail=f"Applied decisions: {decisions}",
        provenance_tag="Manager HITL decision",
        actor_id=state.get("approver_user_id"),
    )
    return {"tasks": updates}

