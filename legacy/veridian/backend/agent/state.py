"""
agent/state.py — Veridian WorkOS LangGraph Agent State
=======================================================
Defines the complete AgentState TypedDict used across all nodes in
Graph A (synchronous meeting pipeline) and Graph B (async Slack loop).

KEY DESIGN DECISION — parallel-safe task reducer:
The four firewall nodes (hr_checker, finance_checker, security_checker,
capacity_checker) execute simultaneously in LangGraph's parallel fan-out.
Each node only knows about its own fields (e.g., hr_status, finance_flag).
Without a custom reducer, they would overwrite each other's work because
LangGraph merges partial state dicts during fan-in.

Solution: `update_tasks_reducer`
  - Keyed by task_id (not a list) so updates are O(1) lookups.
  - Deep-merges at the field level: only non-None values overwrite existing.
  - This means hr_checker can safely write hr_status while finance_checker
    simultaneously writes finance_flag — neither destroys the other's data.
"""

import operator
from typing import Annotated, List, Dict, Optional, Literal, Any
from typing_extensions import TypedDict


# ---------------------------------------------------------------------------
# Sub-TypedDicts (building blocks of AgentState)
# ---------------------------------------------------------------------------

class DecisionItem(TypedDict):
    """A key decision captured from the meeting transcript (not a task)."""
    decision: str          # Plain-English statement of the decision made
    context_quote: str     # Verbatim transcript quote for provenance


class FirewallResult(TypedDict):
    """Raw output from a single checker node for a single task."""
    task_id: str
    conflict_type: Literal["HR", "BUDGET", "SECURITY", "CAPACITY", "NONE"]
    blocked: bool
    reason: str           # Human-readable explanation of the block
    provenance_tag: str   # e.g. "BambooHR connector · synced 2 mins ago"
    confidence: Optional[float]  # Used by security_checker (cosine similarity)


class AIResolution(TypedDict):
    """
    Output from resolution_generator_node for a single task.
    Maps the detected conflict to a specific remediation action.
    """
    task_id: str
    conflict_type: Literal["HR", "BUDGET", "SECURITY", "CAPACITY", "NONE"]
    provenance_tag: str
    suggested_action: Literal["REFRAME", "REROUTE", "DEFER", "OVERRIDE", "PROCEED"]
    new_payload: Optional[Dict[str, Any]]  # Carries reframed/rerouted data


class Task(TypedDict):
    """
    The canonical task object — mutates as it flows through the pipeline.

    Phase 1 fields (set by extractor_node):
        task_id, title, assignee, resource_type, transcript_quote, status

    Phase 2 fields (set in parallel by firewall nodes):
        hr_status, hr_provenance
        finance_flag, finance_provenance
        security_flag, security_confidence, security_provenance
        capacity_flag, capacity_provenance
        rerouted_assignee  (set by auto_router_node)

    Phase 2.5 fields (set by resolution_generator_node):
        resolution_action, reframed_title, reframed_description

    Phase 4 fields (set by dispatcher_node):
        jira_ticket_id, jira_url, slack_dm_sent
    """

    # ── Phase 1: Extraction ──────────────────────────────────────────────
    task_id: str
    title: str
    assignee: str          # "UNASSIGNED" if not determinable from transcript
    resource_type: str     # e.g. "compute", "api_integration", "unknown"
    transcript_quote: str  # Verbatim snippet that surfaced this task
    status: Literal["PENDING", "DEFERRED", "CANCELLED", "READY"]

    # ── Phase 2: HR Checker ──────────────────────────────────────────────
    hr_status: Optional[str]        # ACTIVE | ON_PATERNITY_LEAVE | NOT_FOUND | …
    hr_provenance: Optional[str]    # e.g. "BambooHR connector · synced 5 mins ago"

    # ── Phase 2: Finance Checker ─────────────────────────────────────────
    finance_flag: Optional[str]     # e.g. "Budget $0 for category: enterprise_compute"
    finance_provenance: Optional[str]  # e.g. "Google Sheets · Q3 Budget tab · synced …"

    # ── Phase 2: Security Checker ────────────────────────────────────────
    security_flag: Optional[str]    # e.g. "Violates SEC-POL-089: Deploy to staging …"
    security_confidence: Optional[float]  # Cosine similarity score (0–1)
    security_provenance: Optional[str]    # e.g. "RAG · SEC-POL-089 · similarity 0.87 …"

    # ── Phase 2: Capacity Checker ────────────────────────────────────────
    capacity_flag: Optional[str]    # e.g. "Dov: 3/2 tickets (NEW_HIRE threshold)"
    capacity_provenance: Optional[str]  # e.g. "Jira API · live query"

    # ── Phase 2.5: Auto-Router ───────────────────────────────────────────
    rerouted_assignee: Optional[str]  # Selected by auto_router_node from employees table

    # ── Phase 2.5: Resolution Generator ─────────────────────────────────
    resolution_action: Optional[str]  # REFRAME | REROUTE | DEFER | OVERRIDE | PROCEED
    reframed_title: Optional[str]
    reframed_description: Optional[str]  # Full Jira description with policy compliance steps

    # ── Phase 4: Dispatcher ──────────────────────────────────────────────
    jira_ticket_id: Optional[str]
    jira_url: Optional[str]
    slack_dm_sent: Optional[bool]


# ---------------------------------------------------------------------------
# Custom reducer for parallel-safe task updates
# ---------------------------------------------------------------------------

def update_tasks_reducer(
    current: Dict[str, Task],
    update: Dict[str, Task],
) -> Dict[str, Task]:
    """
    Merges two tasks dicts safely during LangGraph's parallel fan-in.

    Rules:
      1. If update contains a task_id not in current → add it wholesale.
      2. If task_id already exists → deep-merge at field level.
         Only non-None values from `update` overwrite `current`.
         This ensures hr_checker's hr_status is never erased by
         finance_checker's partial dict (which would have hr_status=None).

    Called automatically by LangGraph's state reducer machinery because
    `tasks` is declared as Annotated[Dict[str, Task], update_tasks_reducer].

    Args:
        current:  The existing tasks dict in AgentState.
        update:   The partial dict returned by a node (may only contain
                  a subset of fields for a subset of tasks).

    Returns:
        Merged dict — safe to call from concurrent threads/coroutines.
    """
    merged = dict(current)

    for task_id, task_update in update.items():
        if task_id in merged:
            # Deep merge: only overwrite fields where the incoming value is
            # non-None. This prevents a checker node from accidentally
            # wiping out another checker's result with a None default.
            existing = dict(merged[task_id])
            for key, value in task_update.items():
                if value is not None:
                    existing[key] = value
            merged[task_id] = existing  # type: ignore[assignment]
        else:
            # Brand-new task (e.g., added by extractor_node)
            merged[task_id] = task_update

    return merged


# ---------------------------------------------------------------------------
# Main AgentState — the single source of truth for both Graph A & Graph B
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """
    Master state TypedDict passed to every node in both graphs.

    Graph A (synchronous meeting pipeline) uses all sections.
    Graph B (async Slack tracker loop) uses only the tracker section and
    whatever task fields it needs to update via Jira PATCH calls.

    Note: `tasks` is Annotated with update_tasks_reducer so that LangGraph
    merges partial updates instead of replacing the whole dict. All other
    fields use last-write-wins semantics (default LangGraph behavior).
    """

    # ── Phase 1: Ingestion ───────────────────────────────────────────────
    meeting_id: str    # Unique meeting identifier — used for idempotency guard
    transcript: str    # Raw meeting transcript text from the webhook payload

    # ── Phase 1: Extraction ──────────────────────────────────────────────
    # IMPORTANT: Annotated with update_tasks_reducer for parallel safety.
    tasks: Annotated[Dict[str, Task], update_tasks_reducer]

    key_decisions: List[DecisionItem]   # Decisions captured but not made into tasks
    meeting_context: Dict[str, Any]     # TL;DR fields: title, date, attendees, bullets

    # ── Phase 2.5: Resolutions ───────────────────────────────────────────
    resolutions: List[AIResolution]     # One AIResolution per task with a flag

    # ── Phase 3: HITL ────────────────────────────────────────────────────
    interrupt_payload: Optional[Dict[str, Any]]  # Serialized state streamed to Next.js
    hitl_decisions: Dict[str, str]  # task_id → approved_action (from human UI)

    # ── Phase 4: Dispatch ────────────────────────────────────────────────
    dispatched_tickets: List[Dict[str, Any]]  # Jira ticket summaries for audit trail
    manager_approved: bool  # Set True by hitl_interrupt_node on resumption

    # ── Graph B: Async Tracker ───────────────────────────────────────────
    turn_count: int                      # Slack conversation turns (prevents infinite loop)
    tracker_task_id: Optional[str]       # Task being tracked in Graph B
    tracker_assignee: Optional[str]      # Assignee whose Slack reply triggered Graph B
    last_slack_reply: Optional[str]      # Raw Slack message text for intent_parser_node
    parsed_intent: Optional[str]         # COMPLETED | BLOCKED | AMBIGUOUS (set by intent_parser_node)
    intent_confidence: Optional[float]   # LLM confidence score for the parsed intent (0–1)
