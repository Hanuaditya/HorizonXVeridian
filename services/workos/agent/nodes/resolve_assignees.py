"""Speaker & assignee resolution node: maps extracted names/speakers to org employees."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agent.state import AgentState, Task
from core.store import list_employees

logger = logging.getLogger(__name__)


def _match_employee(candidate: str, employees: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    clean = (candidate or "").strip().lower()
    if not clean or clean in {"unassigned", "unknown", "none", "tbd"}:
        return None

    exact = [e for e in employees if (e.get("full_name") or "").lower() == clean]
    if len(exact) == 1:
        return exact[0]

    prefix_or_part = [
        e
        for e in employees
        if clean in (e.get("full_name") or "").lower().split()
        or (e.get("full_name") or "").lower().startswith(clean)
    ]
    if len(prefix_or_part) == 1:
        return prefix_or_part[0]

    # Ambiguous (2+) or not found -> return None so we never guess
    return None


def resolve_assignees_node(state: AgentState) -> dict:
    """Resolve assignees against org's employees table; flag unresolved cases for HITL."""
    org_id = state.get("org_id") or "org_demo_horizon"
    tasks = state.get("tasks", {})
    employees = list_employees(org_id=org_id)
    participants = state.get("participants") or []
    updates: Dict[str, Task] = {}

    for task_id, task in tasks.items():
        raw_assignee = task.get("assignee", "UNASSIGNED")
        matched = _match_employee(raw_assignee, employees)

        if matched is not None:
            updates[task_id] = Task(
                assignee=matched["full_name"],
                assignee_user_id=matched.get("clerk_user_id"),
                assignee_resolution_flag=None,
            )
            continue

        # Try matching participant list -> employee by email or display name
        part_matches = [
            p
            for p in participants
            if raw_assignee.lower() in (p.get("display_name") or "").lower()
        ]
        if len(part_matches) == 1:
            part = part_matches[0]
            updates[task_id] = Task(
                assignee=part.get("display_name", raw_assignee),
                assignee_user_id=part.get("clerk_user_id"),
                assignee_resolution_flag=None,
            )
            continue

        # Explicitly flag unresolved or ambiguous assignees for HITL — never guess!
        updates[task_id] = Task(
            assignee="UNASSIGNED" if not raw_assignee else raw_assignee,
            assignee_user_id=None,
            assignee_resolution_flag="UNRESOLVED_ASSIGNEE",
        )
        logger.info("resolve_assignees_node: task '%s' assignee '%s' unresolved -> HITL.", task_id, raw_assignee)

    return {"tasks": updates}
