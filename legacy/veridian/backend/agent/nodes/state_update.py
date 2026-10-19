"""
agent/nodes/state_update.py — 6K: Apply HITL Decisions to Tasks
================================================================
After the manager approves/modifies resolutions in the Next.js UI,
this node applies those decisions to the tasks dict, mutating assignees,
titles, and statuses as appropriate.
"""

import logging
from typing import Dict

from agent.state import AgentState

logger = logging.getLogger(__name__)


def state_update_node(state: AgentState) -> dict:
    """
    Apply each manager-approved decision from hitl_decisions to the tasks.

    hitl_decisions format: {task_id: approved_action_string}
    where approved_action_string is one of:
        "REFRAME"  — use reframed_title and reframed_description
        "REROUTE"  — overwrite assignee with rerouted_assignee
        "DEFER"    — set status = "DEFERRED"
        "OVERRIDE" — keep original, attach override_note
        "PROCEED"  — no change

    Returns:
        Partial state: {"tasks": updated_tasks_dict}
    """
    tasks = dict(state.get("tasks", {}))
    hitl_decisions: Dict[str, str] = state.get("hitl_decisions", {})

    if not hitl_decisions:
        logger.warning("state_update_node: no hitl_decisions in state — using AI resolutions.")
        # Fall back to AI-suggested actions from resolutions
        for resolution in state.get("resolutions", []):
            task_id = resolution.get("task_id")
            action = resolution.get("suggested_action", "PROCEED")
            if task_id:
                hitl_decisions[task_id] = action

    task_updates: Dict[str, dict] = {}

    for task_id, approved_action in hitl_decisions.items():
        if task_id not in tasks:
            logger.warning(
                "state_update_node: task_id '%s' in hitl_decisions not in tasks — skipping.",
                task_id,
            )
            continue

        task = dict(tasks[task_id])
        action = approved_action.upper().strip()

        if action == "REFRAME":
            # Overwrite title and description with AI-reframed versions
            if task.get("reframed_title"):
                original_title = task.get("title")
                task["title"] = task["reframed_title"]
                logger.info(
                    "state_update_node: REFRAME task '%s': '%s' → '%s'.",
                    task_id, original_title, task["title"],
                )
            else:
                logger.warning(
                    "state_update_node: REFRAME for task '%s' but no reframed_title set.",
                    task_id,
                )
            task["status"] = "READY"

        elif action == "REROUTE":
            # Overwrite assignee with the auto-routed replacement
            rerouted = task.get("rerouted_assignee")
            if rerouted:
                original_assignee = task.get("assignee")
                task["assignee"] = rerouted
                logger.info(
                    "state_update_node: REROUTE task '%s': '%s' → '%s'.",
                    task_id, original_assignee, rerouted,
                )
            else:
                logger.warning(
                    "state_update_node: REROUTE for task '%s' but no rerouted_assignee set.",
                    task_id,
                )
            task["status"] = "READY"

        elif action == "DEFER":
            task["status"] = "DEFERRED"
            logger.info("state_update_node: DEFER task '%s'.", task_id)

        elif action == "OVERRIDE":
            # Keep everything as-is — just mark as READY with override noted
            task["status"] = "READY"
            logger.info(
                "state_update_node: OVERRIDE task '%s' — proceeding with original.",
                task_id,
            )

        elif action == "PROCEED":
            task["status"] = "READY"
            logger.debug("state_update_node: PROCEED task '%s'.", task_id)

        else:
            logger.warning(
                "state_update_node: unknown action '%s' for task '%s' — defaulting to PROCEED.",
                action, task_id,
            )
            task["status"] = "READY"

        task["resolution_action"] = action
        task_updates[task_id] = task

    logger.info(
        "state_update_node: applied decisions to %d tasks.", len(task_updates)
    )

    return {"tasks": task_updates}
