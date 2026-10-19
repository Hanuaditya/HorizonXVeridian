"""
agent/nodes/hitl_interrupt.py — 6J: Human-in-the-Loop Pause
=============================================================
Uses LangGraph's native `interrupt()` to pause graph execution.
The full state is serialized to the checkpointer (Supabase/memory).
The Next.js UI reads this payload via SSE and presents the Command Center cards.
Execution resumes when graph.invoke(Command(resume=...)) is called from the API.
"""

import logging
from typing import Any, Dict

from langgraph.types import interrupt

from agent.state import AgentState

logger = logging.getLogger(__name__)


def hitl_interrupt_node(state: AgentState) -> dict:
    """
    Pause the graph and serialise state for human review.

    The interrupt_payload contains everything the Next.js UI needs to
    render the four Generative UI cards:
      - Card 1 (TL;DR): meeting_context.tldr_bullets
      - Card 2 (Decisions Ledger): key_decisions
      - Card 3 (Command Center): tasks with flags + resolutions
      - Card 4 (Tracker): dispatched_tickets (empty at this point)

    Upon graph resumption, `human_response` will be a dict mapping
    task_id → approved_action string (e.g. {"t1": "REFRAME", "t2": "PROCEED"}).

    Returns:
        {"hitl_decisions": {task_id: action}, "manager_approved": True}
    """
    meeting_id = state.get("meeting_id", "unknown")
    tasks = state.get("tasks", {})
    resolutions = state.get("resolutions", [])

    # ── Count flags for logging ──────────────────────────────────────────
    flagged_count = sum(
        1 for r in resolutions
        if r.get("suggested_action") != "PROCEED"
    )
    logger.info(
        "hitl_interrupt_node: ⏸ PAUSING graph for meeting '%s'. "
        "%d/%d tasks need human review.",
        meeting_id, flagged_count, len(tasks),
    )

    # ── Build the interrupt payload sent to the Next.js frontend ─────────
    interrupt_payload: Dict[str, Any] = {
        "meeting_id": meeting_id,
        "meeting_context": state.get("meeting_context", {}),
        "tasks": dict(state.get("tasks", {})),
        "key_decisions": list(state.get("key_decisions", [])),
        "resolutions": list(resolutions),
    }

    # ── LangGraph native interrupt ────────────────────────────────────────
    # Graph execution halts here. State is checkpointed.
    # Resumes when the API calls:
    #   graph.invoke(Command(resume=human_decisions), config=thread_config)
    human_response: Dict[str, str] = interrupt(interrupt_payload)

    logger.info(
        "hitl_interrupt_node: ▶ RESUMED by manager for meeting '%s'. "
        "Decisions: %s",
        meeting_id, human_response,
    )

    return {
        "interrupt_payload": interrupt_payload,
        "hitl_decisions": human_response,
        "manager_approved": True,
    }
