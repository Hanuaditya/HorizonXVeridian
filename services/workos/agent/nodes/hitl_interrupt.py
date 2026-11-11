"""6J: Human-in-the-Loop interrupt node pausing Graph A until manager decision arrives."""

from __future__ import annotations

import logging
from typing import Any, Dict

from langgraph.types import interrupt

from agent.state import AgentState

logger = logging.getLogger(__name__)


def hitl_interrupt_node(state: AgentState) -> dict:
    """Pause Graph A execution via LangGraph interrupt() until manager approves/overrides."""
    meeting_id = state.get("meeting_id", "unknown")
    payload: Dict[str, Any] = {
        "meeting_id": meeting_id,
        "org_id": state.get("org_id"),
        "resolutions": state.get("resolutions", []),
        "tasks": state.get("tasks", {}),
    }

    human_response = interrupt(payload)

    decisions: Dict[str, str] = {}
    approver_user_id: str | None = None
    if isinstance(human_response, dict):
        if "decisions" in human_response and isinstance(human_response["decisions"], dict):
            decisions = {str(k): str(v) for k, v in human_response["decisions"].items()}
            approver_user_id = human_response.get("approver_user_id")
        else:
            decisions = {str(k): str(v) for k, v in human_response.items()}

    logger.info("hitl_interrupt_node: resumed meeting='%s' with %d decision(s).", meeting_id, len(decisions))
    return {
        "hitl_decisions": decisions,
        "approver_user_id": approver_user_id,
        "manager_approved": True,
    }
