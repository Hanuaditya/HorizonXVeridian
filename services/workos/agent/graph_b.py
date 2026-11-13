"""Graph B: Closed-loop Slack intent tracking & GitHub semantic commit matching."""

from __future__ import annotations

from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from agent.nodes.intent_parser import intent_parser_node
from agent.nodes.semantic_matcher import semantic_matcher_node
from agent.nodes.ticket_resolver import escalation_node, ticket_resolver_node
from agent.state import AgentState


def _route_after_slack_intent(state: AgentState) -> str:
    intent = state.get("parsed_intent") or "AMBIGUOUS"
    turn_count = int(state.get("turn_count", 0))
    if intent == "BLOCKED" or (intent in {"PARTIAL", "AMBIGUOUS"} and turn_count >= 2):
        return "escalation_node"
    return "ticket_resolver_node"


def build_graph_b_slack():
    builder = StateGraph(cast(Any, AgentState))
    builder.add_node("intent_parser_node", intent_parser_node)
    builder.add_node("ticket_resolver_node", ticket_resolver_node)
    builder.add_node("escalation_node", escalation_node)

    builder.add_edge(START, "intent_parser_node")
    builder.add_conditional_edges(
        "intent_parser_node",
        _route_after_slack_intent,
        {"escalation_node": "escalation_node", "ticket_resolver_node": "ticket_resolver_node"},
    )
    builder.add_edge("ticket_resolver_node", END)
    builder.add_edge("escalation_node", END)
    return builder.compile()


def build_graph_b_github():
    builder = StateGraph(cast(Any, AgentState))
    builder.add_node("semantic_matcher_node", semantic_matcher_node)
    builder.add_node("ticket_resolver_node", ticket_resolver_node)

    builder.add_edge(START, "semantic_matcher_node")
    builder.add_edge("semantic_matcher_node", "ticket_resolver_node")
    builder.add_edge("ticket_resolver_node", END)
    return builder.compile()


graph_b_slack = build_graph_b_slack()
graph_b_github = build_graph_b_github()

