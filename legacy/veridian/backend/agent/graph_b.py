"""
agent/graph_b.py — Veridian WorkOS: Graph B (Async Slack/GitHub Tracker Loop)
===============================================================================
Graph B is event-driven and stateless between runs — it is triggered by
incoming Slack webhooks or GitHub push events and terminates after one
resolution (Done / Blocked / Escalated).

Two entry paths (both start at intent_parser_node or semantic_matcher_node):
  • Slack path:   webhook → intent_parser_node → route_intent → ...
  • GitHub path:  webhook → semantic_matcher_node → ticket_resolver_node

Graph B wiring:

    START
      │
      ▼
    intent_parser_node
      │
      ├─ COMPLETED ──────────────────→ ticket_resolver_node → END
      │
      ├─ BLOCKED ────────────────────→ escalation_node → END
      │
      └─ AMBIGUOUS (turn < 2) ───────→ slack_dm_node ──→ intent_parser_node
                                                              (loop, turn+1)
      └─ AMBIGUOUS (turn >= 2) ──────→ escalation_node → END  (guardrail)

semantic_matcher_node is registered as a node for the GitHub webhook path
and can be invoked as an alternative entry point by the FastAPI route.

Key design:
  - NO checkpointer for Graph B (stateless between webhook calls)
  - turn_count guardrail in route_intent prevents infinite Slack loops
  - semantic_matcher_node is wired to ticket_resolver_node for GitHub pushes

Usage:
    from agent.graph_b import graph_b

    # Slack webhook
    config = {"configurable": {"thread_id": f"slack-{task_id}-{turn}"}}
    graph_b.invoke(slack_state, config=config)

    # GitHub webhook (invoke semantic_matcher as starting node)
    graph_b_github.invoke(github_state, config=config)
"""

import logging

from langgraph.graph import StateGraph, START, END

from agent.state import AgentState

# ── Node imports ─────────────────────────────────────────────────────────────
from agent.nodes.intent_parser import intent_parser_node
from agent.nodes.ticket_resolver import ticket_resolver_node
from agent.nodes.escalation import escalation_node
from agent.nodes.slack_dm import slack_dm_node
from agent.nodes.semantic_matcher import semantic_matcher_node

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conditional routing
# ---------------------------------------------------------------------------

def route_intent(state: AgentState) -> str:
    """
    Route after intent_parser_node based on intent classification.

    Rules (enforced exactly as per Master Prompt):
      COMPLETED            → ticket_resolver_node  (mark Jira Done)
      BLOCKED              → escalation_node        (flag to manager)
      AMBIGUOUS + turn < 2 → slack_dm_node          (ask for clarification)
      AMBIGUOUS + turn >= 2→ escalation_node        (LOOP GUARDRAIL — force escalate)
    """
    intent = state.get("parsed_intent", "AMBIGUOUS")
    turn_count = state.get("turn_count", 0)
    confidence = state.get("intent_confidence", 0.0)

    logger.debug(
        "route_intent: intent=%s confidence=%.2f turn_count=%d",
        intent, confidence, turn_count,
    )

    if intent == "COMPLETED":
        logger.info("route_intent: COMPLETED → ticket_resolver_node.")
        return "ticket_resolver_node"

    if intent == "BLOCKED" or turn_count >= 2:
        reason = "BLOCKED intent" if intent == "BLOCKED" else f"loop guardrail (turn={turn_count})"
        logger.info("route_intent: %s → escalation_node.", reason)
        return "escalation_node"

    # AMBIGUOUS and turn_count < 2 — ask for clarification
    logger.info(
        "route_intent: AMBIGUOUS (turn=%d < 2) → slack_dm_node.", turn_count
    )
    return "slack_dm_node"


def route_after_semantic_match(state: AgentState) -> str:
    """
    Route after semantic_matcher_node (GitHub webhook path).

    If a confident match was found (tracker_task_id set) → ticket_resolver_node
    If no match → END (no ticket to update)
    """
    if state.get("tracker_task_id") and state.get("intent_confidence", 0) >= 0.6:
        logger.info(
            "route_after_semantic_match: match found (task=%s conf=%.2f) → ticket_resolver_node.",
            state.get("tracker_task_id"), state.get("intent_confidence", 0),
        )
        return "ticket_resolver_node"

    logger.info("route_after_semantic_match: no confident match → END.")
    return END


# ---------------------------------------------------------------------------
# Graph B builder — Slack webhook path (primary)
# ---------------------------------------------------------------------------

def build_graph_b() -> object:
    """
    Build and compile Graph B for the Slack webhook / clarification loop.

    No checkpointer — Graph B is stateless between runs.
    Each webhook invocation starts fresh with the current task context.

    Returns:
        Compiled LangGraph StateGraph.
    """
    builder = StateGraph(AgentState)

    # ── Register all 5 nodes ─────────────────────────────────────────────
    builder.add_node("intent_parser_node",    intent_parser_node)
    builder.add_node("ticket_resolver_node",  ticket_resolver_node)
    builder.add_node("escalation_node",       escalation_node)
    builder.add_node("slack_dm_node",         slack_dm_node)
    builder.add_node("semantic_matcher_node", semantic_matcher_node)

    # ── Slack webhook entry point ─────────────────────────────────────────
    # START → intent_parser_node (classifier)
    builder.add_edge(START, "intent_parser_node")

    # ── Conditional routing from intent_parser ────────────────────────────
    # route_intent implements the turn_count >= 2 loop guardrail
    builder.add_conditional_edges(
        "intent_parser_node",
        route_intent,
        {
            "ticket_resolver_node": "ticket_resolver_node",
            "escalation_node":      "escalation_node",
            "slack_dm_node":        "slack_dm_node",
        },
    )

    # ── Terminal nodes ───────────────────────────────────────────────────
    builder.add_edge("ticket_resolver_node", END)
    builder.add_edge("escalation_node",      END)

    # ── Slack DM loop back ───────────────────────────────────────────────
    # slack_dm_node increments turn_count then loops back to re-classify
    builder.add_edge("slack_dm_node", "intent_parser_node")

    # ── Semantic matcher (GitHub path) ───────────────────────────────────
    # semantic_matcher_node is reachable as an alternative entry via
    # graph_b_github (see below) or direct node invocation from the API.
    builder.add_conditional_edges(
        "semantic_matcher_node",
        route_after_semantic_match,
        {
            "ticket_resolver_node": "ticket_resolver_node",
            END: END,
        },
    )

    compiled = builder.compile()  # No checkpointer — stateless
    logger.info("Graph B compiled successfully.")
    return compiled


# ---------------------------------------------------------------------------
# Graph B (GitHub entry) — semantic_matcher as the starting node
# ---------------------------------------------------------------------------

def build_graph_b_github() -> object:
    """
    Variant of Graph B for GitHub push webhook events.
    Starts at semantic_matcher_node instead of intent_parser_node.
    """
    builder = StateGraph(AgentState)

    builder.add_node("semantic_matcher_node", semantic_matcher_node)
    builder.add_node("ticket_resolver_node",  ticket_resolver_node)
    builder.add_node("escalation_node",       escalation_node)

    builder.add_edge(START, "semantic_matcher_node")
    builder.add_conditional_edges(
        "semantic_matcher_node",
        route_after_semantic_match,
        {
            "ticket_resolver_node": "ticket_resolver_node",
            END: END,
        },
    )
    builder.add_edge("ticket_resolver_node", END)
    builder.add_edge("escalation_node",      END)

    compiled = builder.compile()
    logger.info("Graph B (GitHub variant) compiled successfully.")
    return compiled


# ---------------------------------------------------------------------------
# Singleton exports — imported by FastAPI webhook routes
# ---------------------------------------------------------------------------

graph_b        = build_graph_b()         # Slack webhook path
graph_b_github = build_graph_b_github()  # GitHub push path


# ---------------------------------------------------------------------------
# Diagram helper
# ---------------------------------------------------------------------------

def print_graph_diagram() -> None:
    try:
        print("\n=== Graph B: Mermaid Diagram ===")
        print(graph_b.get_graph().draw_mermaid())
        print("================================\n")
    except Exception as exc:
        print(f"Could not render diagram: {exc}")


# ---------------------------------------------------------------------------
# Quick compile verification
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=logging.INFO)

    print("Building Graph B (Slack)…")
    g = build_graph_b()
    print("✅ Graph B (Slack) compiled.")
    print(f"   Nodes: {list(g.get_graph().nodes.keys())}")

    print("\nBuilding Graph B (GitHub)…")
    g2 = build_graph_b_github()
    print("✅ Graph B (GitHub) compiled.")
    print(f"   Nodes: {list(g2.get_graph().nodes.keys())}")

    print_graph_diagram()
