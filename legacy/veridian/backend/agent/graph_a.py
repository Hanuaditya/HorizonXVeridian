"""
agent/graph_a.py — Veridian WorkOS: Graph A (Synchronous Meeting Pipeline)
===========================================================================
Wires all 12 nodes into a complete LangGraph StateGraph with:

  Phase 1:   START → ingest_node → (idempotency check) → extractor_node
  Phase 2:   extractor_node → [PARALLEL FAN-OUT] → HR / Finance / Security / Capacity
  Phase 2.5: capacity_checker → (conditional) → auto_router_node? → merge_node
             merge_node → resolution_generator_node
  Phase 3:   resolution_generator_node → (conditional) → hitl_interrupt_node?
  Phase 4:   hitl_interrupt_node → state_update_node → dispatcher_node → END

Key LangGraph patterns used:
  • Parallel Fan-Out:   Multiple add_edge() calls from extractor_node to the 4 checkers.
  • Fan-In via Reducer: update_tasks_reducer in AgentState merges all parallel results.
  • HITL:              interrupt_before=["hitl_interrupt_node"] pauses at that node
                       and serialises state to MemorySaver checkpointer.
  • Conditional Edges:  route_capacity() and route_resolution() drive branching.

Usage:
    from agent.graph_a import build_graph_a
    graph = build_graph_a()

    # Run (Graph A will pause at hitl_interrupt_node)
    config = {"configurable": {"thread_id": "meeting-m_123"}}
    result = graph.invoke(initial_state, config=config)

    # Resume after human approves
    from langgraph.types import Command
    graph.invoke(Command(resume=hitl_decisions), config=config)
"""

import logging

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
# Production swap:
# from langgraph.checkpoint.postgres import PostgresSaver

from agent.state import AgentState

# ── Node imports ─────────────────────────────────────────────────────────────
from agent.nodes.ingest import ingest_node
from agent.nodes.extractor import extractor_node
from agent.nodes.hr_checker import hr_checker_node
from agent.nodes.finance_checker import finance_checker_node
from agent.nodes.security_checker import security_checker_node
from agent.nodes.capacity_checker import capacity_checker_node
from agent.nodes.auto_router import auto_router_node
from agent.nodes.merge import merge_node
from agent.nodes.resolution_generator import resolution_generator_node
from agent.nodes.hitl_interrupt import hitl_interrupt_node
from agent.nodes.state_update import state_update_node
from agent.nodes.dispatcher import dispatcher_node

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conditional routing functions
# ---------------------------------------------------------------------------

def route_ingest(state: AgentState) -> str:
    """
    After ingest_node:
      - If meeting was already processed → END (idempotency drop)
      - Otherwise → extractor_node
    """
    if state.get("__drop__"):
        logger.info("route_ingest: duplicate meeting detected → dropping.")
        return END
    return "extractor_node"


def route_capacity(state: AgentState) -> str:
    """
    After capacity_checker_node:
      - If ANY task has a capacity_flag → auto_router_node (find new assignee)
      - Otherwise → merge_node (proceed directly to fan-in)

    Note: HR-flagged tasks (not ACTIVE) are also routed through auto_router
    to find a replacement, even if capacity_checker didn't set the flag.
    This handles ON_PATERNITY_LEAVE cases where the assignee is unavailable.
    """
    tasks = state.get("tasks", {})
    for task in tasks.values():
        if task.get("capacity_flag"):
            logger.debug("route_capacity: capacity flag found → auto_router_node.")
            return "auto_router_node"
        # Also trigger auto-router for non-active HR statuses
        hr_status = task.get("hr_status")
        if hr_status and hr_status not in ("ACTIVE", "NOT_FOUND", "QUERY_ERROR", None):
            logger.debug(
                "route_capacity: hr_status=%s → auto_router_node.", hr_status
            )
            return "auto_router_node"
    return "merge_node"


def route_resolution(state: AgentState) -> str:
    """
    After resolution_generator_node:
      - If ANY resolution is not PROCEED → hitl_interrupt_node (pause for human)
      - If ALL are PROCEED → state_update_node (skip HITL, dispatch immediately)
    """
    resolutions = state.get("resolutions", [])
    for resolution in resolutions:
        if resolution.get("suggested_action") != "PROCEED":
            logger.info(
                "route_resolution: non-PROCEED resolution found (%s) → hitl_interrupt_node.",
                resolution.get("suggested_action"),
            )
            return "hitl_interrupt_node"
    logger.info("route_resolution: all resolutions are PROCEED → state_update_node.")
    return "state_update_node"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph_a():
    """
    Compile and return the Graph A StateGraph.

    Compilation includes:
      - MemorySaver checkpointer for HITL state persistence
        (swap to PostgresSaver for multi-process production deployment)
      - interrupt_before=["hitl_interrupt_node"] so the graph pauses
        BEFORE entering the HITL node, allowing the API to stream state
        to the Next.js frontend before the interrupt() call is made.

    Returns:
        A compiled LangGraph CompiledStateGraph ready for invoke() calls.
    """
    builder = StateGraph(AgentState)

    # ── Register all 12 nodes ────────────────────────────────────────────
    builder.add_node("ingest_node",               ingest_node)
    builder.add_node("extractor_node",            extractor_node)
    builder.add_node("hr_checker_node",           hr_checker_node)
    builder.add_node("finance_checker_node",      finance_checker_node)
    builder.add_node("security_checker_node",     security_checker_node)
    builder.add_node("capacity_checker_node",     capacity_checker_node)
    builder.add_node("auto_router_node",          auto_router_node)
    builder.add_node("merge_node",                merge_node)
    builder.add_node("resolution_generator_node", resolution_generator_node)
    builder.add_node("hitl_interrupt_node",       hitl_interrupt_node)
    builder.add_node("state_update_node",         state_update_node)
    builder.add_node("dispatcher_node",           dispatcher_node)

    # ── Phase 1: Ingestion ───────────────────────────────────────────────
    # START → ingest_node → (idempotency check) → extractor_node or END
    builder.add_edge(START, "ingest_node")
    builder.add_conditional_edges(
        "ingest_node",
        route_ingest,
        # Explicit path map (required when END is a possible destination)
        {END: END, "extractor_node": "extractor_node"},
    )

    # ── Phase 2: Parallel Fan-Out (Agentic Firewall) ─────────────────────
    # extractor_node → all 4 checkers simultaneously
    # LangGraph executes parallel branches and merges via update_tasks_reducer
    builder.add_edge("extractor_node", "hr_checker_node")
    builder.add_edge("extractor_node", "finance_checker_node")
    builder.add_edge("extractor_node", "security_checker_node")
    builder.add_edge("extractor_node", "capacity_checker_node")

    # ── Phase 2.5: Capacity/Auto-Router conditional ──────────────────────
    # capacity_checker result: over threshold → auto_router_node, else → merge_node
    builder.add_conditional_edges(
        "capacity_checker_node",
        route_capacity,
        {
            "auto_router_node": "auto_router_node",
            "merge_node":       "merge_node",
        },
    )
    # auto_router feeds back into the fan-in merger
    builder.add_edge("auto_router_node", "merge_node")

    # ── Phase 2: Fan-In (all parallel paths → merge_node) ────────────────
    # HR, Finance, Security all converge here
    # (capacity_checker converges via conditional edge above)
    builder.add_edge("hr_checker_node",       "merge_node")
    builder.add_edge("finance_checker_node",  "merge_node")
    builder.add_edge("security_checker_node", "merge_node")

    # ── Phase 2.5: Resolution Generation ────────────────────────────────
    builder.add_edge("merge_node", "resolution_generator_node")

    # ── Phase 3: HITL conditional ────────────────────────────────────────
    # Any non-PROCEED resolution → pause for human review
    # All-clear → skip HITL, go straight to dispatch
    builder.add_conditional_edges(
        "resolution_generator_node",
        route_resolution,
        {
            "hitl_interrupt_node": "hitl_interrupt_node",
            "state_update_node":   "state_update_node",
        },
    )

    # ── Phase 3 → 4: Post-HITL linear pipeline ──────────────────────────
    builder.add_edge("hitl_interrupt_node", "state_update_node")
    builder.add_edge("state_update_node",   "dispatcher_node")
    builder.add_edge("dispatcher_node",     END)

    # ── Compile with HITL checkpointer ───────────────────────────────────
    # MemorySaver: in-process, suitable for development and demos.
    # For multi-worker production: swap to PostgresSaver pointed at Supabase.
    checkpointer = MemorySaver()

    compiled = builder.compile(
        checkpointer=checkpointer,
        # interrupt_before pauses the graph BEFORE executing hitl_interrupt_node.
        # The API layer reads state from the checkpointer and streams it to Next.js.
        # Resumption: graph.invoke(Command(resume=decisions), config=thread_config)
        interrupt_before=["hitl_interrupt_node"],
    )

    logger.info("Graph A compiled successfully.")
    return compiled


# ---------------------------------------------------------------------------
# Singleton graph instance (import-time compilation)
# ---------------------------------------------------------------------------

graph_a = build_graph_a()


# ---------------------------------------------------------------------------
# Mermaid diagram helper (for debugging / README)
# ---------------------------------------------------------------------------

def print_graph_diagram() -> None:
    """Print the Mermaid diagram of Graph A to stdout."""
    try:
        diagram = graph_a.get_graph().draw_mermaid()
        print("\n=== Graph A: Mermaid Diagram ===")
        print(diagram)
        print("================================\n")
    except Exception as exc:
        print(f"Could not render diagram: {exc}")


# ---------------------------------------------------------------------------
# Quick compile verification (run directly: python -m agent.graph_a)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    print("Building Graph A…")
    g = build_graph_a()
    print("✅ Graph A compiled successfully.")
    print(f"   Nodes: {list(g.get_graph().nodes.keys())}")
    print_graph_diagram()
