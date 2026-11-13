"""Graph A: MeetingEnded -> Extract -> Resolve Assignees -> Parallel Firewall -> Merge -> Resolve -> HITL -> Dispatch."""

from __future__ import annotations

import logging
from typing import Any, Optional, cast

from langgraph.graph import END, START, StateGraph

from agent.checkpointer import build_checkpointer
from agent.nodes.auto_router import auto_router_node
from agent.nodes.capacity_checker import capacity_checker_node
from agent.nodes.dispatcher import dispatcher_node
from agent.nodes.extractor import extractor_node
from agent.nodes.finance_checker import finance_checker_node
from agent.nodes.hitl_interrupt import hitl_interrupt_node
from agent.nodes.hr_checker import hr_checker_node
from agent.nodes.ingest import ingest_node
from agent.nodes.merge import merge_node
from agent.nodes.resolution_generator import resolution_generator_node
from agent.nodes.resolve_assignees import resolve_assignees_node
from agent.nodes.security_checker import security_checker_node
from agent.nodes.state_update import state_update_node
from agent.state import AgentState

logger = logging.getLogger(__name__)


def route_ingest(state: AgentState) -> str:
    if state.get("__drop__"):
        return END
    return "extractor_node"


def route_capacity_or_hr(state: AgentState) -> str:
    tasks = state.get("tasks", {})
    for task in tasks.values():
        if task.get("capacity_flag"):
            return "auto_router_node"
        hr_status = task.get("hr_status")
        if hr_status and hr_status not in ("ACTIVE", "NOT_FOUND", "QUERY_ERROR", None):
            return "auto_router_node"
    return "merge_node"


def route_resolution(state: AgentState) -> str:
    """Block Jira creation & employee assignment DMs until explicit Manager approval."""
    if state.get("tasks"):
        return "hitl_interrupt_node"
    resolutions = state.get("resolutions", [])
    for res in resolutions:
        if res.get("suggested_action") != "PROCEED":
            return "hitl_interrupt_node"
    return "state_update_node"


def build_graph_a(checkpointer: Optional[Any] = None, db_path: Optional[str] = None):
    """Compile Graph A with persistent checkpointer and HITL interrupt_before."""
    builder = StateGraph(cast(Any, AgentState))

    builder.add_node("ingest_node", ingest_node)
    builder.add_node("extractor_node", extractor_node)
    builder.add_node("resolve_assignees_node", resolve_assignees_node)
    builder.add_node("hr_checker_node", hr_checker_node)
    builder.add_node("finance_checker_node", finance_checker_node)
    builder.add_node("security_checker_node", security_checker_node)
    builder.add_node("capacity_checker_node", capacity_checker_node)
    builder.add_node("auto_router_node", auto_router_node)
    builder.add_node("merge_node", merge_node)
    builder.add_node("resolution_generator_node", resolution_generator_node)
    builder.add_node("hitl_interrupt_node", hitl_interrupt_node)
    builder.add_node("state_update_node", state_update_node)
    builder.add_node("dispatcher_node", dispatcher_node)

    builder.add_edge(START, "ingest_node")
    builder.add_conditional_edges(
        "ingest_node",
        route_ingest,
        {END: END, "extractor_node": "extractor_node"},
    )
    builder.add_edge("extractor_node", "resolve_assignees_node")

    # Parallel 4-way compliance firewall fan-out
    builder.add_edge("resolve_assignees_node", "hr_checker_node")
    builder.add_edge("resolve_assignees_node", "finance_checker_node")
    builder.add_edge("resolve_assignees_node", "security_checker_node")
    builder.add_edge("resolve_assignees_node", "capacity_checker_node")

    # Synchronization into merge_node (wait for all 4 parallel branches before routing!)
    builder.add_edge("hr_checker_node", "merge_node")
    builder.add_edge("finance_checker_node", "merge_node")
    builder.add_edge("security_checker_node", "merge_node")
    builder.add_edge("capacity_checker_node", "merge_node")

    builder.add_conditional_edges(
        "merge_node",
        route_capacity_or_hr,
        {
            "auto_router_node": "auto_router_node",
            "merge_node": "resolution_generator_node",
        },
    )
    builder.add_edge("auto_router_node", "resolution_generator_node")
    builder.add_conditional_edges(
        "resolution_generator_node",
        route_resolution,
        {"hitl_interrupt_node": "hitl_interrupt_node", "state_update_node": "state_update_node"},
    )
    builder.add_edge("hitl_interrupt_node", "state_update_node")
    builder.add_edge("state_update_node", "dispatcher_node")
    builder.add_edge("dispatcher_node", END)

    saver = checkpointer or build_checkpointer(db_path=db_path)
    return builder.compile(
        checkpointer=saver,
        interrupt_before=["hitl_interrupt_node"],
    )


_default_graph_a = None


def get_graph_a():
    global _default_graph_a
    if _default_graph_a is None:
        _default_graph_a = build_graph_a()
    return _default_graph_a


def reset_graph_a_cache() -> None:
    global _default_graph_a
    _default_graph_a = None
