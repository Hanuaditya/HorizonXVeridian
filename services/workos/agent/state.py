"""LangGraph AgentState & parallel-safe field-level reducer for Horizon Veridian WorkOS."""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict


class DecisionItem(TypedDict):
    decision: str
    context_quote: str


class AIResolution(TypedDict):
    task_id: str
    conflict_type: Literal["HR", "BUDGET", "SECURITY", "CAPACITY", "UNRESOLVED_ASSIGNEE", "NONE"]
    provenance_tag: str
    suggested_action: Literal["REFRAME", "REROUTE", "DEFER", "OVERRIDE", "PROCEED"]
    new_payload: Optional[Dict[str, Any]]


class Task(TypedDict, total=False):
    task_id: str
    title: str
    assignee: str
    assignee_user_id: Optional[str]
    assignee_resolution_flag: Optional[str]
    resource_type: str
    transcript_quote: str
    status: Literal["PENDING", "DEFERRED", "CANCELLED", "READY", "DISPATCHED", "DONE", "BLOCKED", "UNRESOLVED_ASSIGNEE"]

    hr_status: Optional[str]
    hr_provenance: Optional[str]

    finance_flag: Optional[str]
    finance_provenance: Optional[str]

    security_flag: Optional[str]
    security_confidence: Optional[float]
    security_provenance: Optional[str]

    capacity_flag: Optional[str]
    capacity_provenance: Optional[str]

    rerouted_assignee: Optional[str]
    leave_recommendation: Optional[str]

    resolution_action: Optional[str]
    reframed_title: Optional[str]
    reframed_description: Optional[str]
    proposed_commit_message: Optional[str]

    jira_ticket_id: Optional[str]
    jira_url: Optional[str]
    jira_status: Optional[str]
    slack_dm_sent: Optional[bool]
    dispatch_error: Optional[str]

    progress_pct: Optional[int]
    completed_milestones: Optional[str]
    blockers: Optional[str]
    commit_summary: Optional[str]
    checkin_stage: Optional[int]
    awaiting_employee_reply: Optional[bool]


def update_tasks_reducer(
    current: Dict[str, Task],
    update: Dict[str, Task],
) -> Dict[str, Task]:
    """Deep-merge partial task dicts during parallel fan-in without clobbering sibling node fields."""
    merged: Dict[str, Task] = dict(current or {})
    for task_id, task_update in (update or {}).items():
        if task_id in merged:
            existing = dict(merged[task_id])
            for key, value in task_update.items():
                if value is not None:
                    existing[key] = value
            merged[task_id] = existing  # type: ignore[assignment]
        else:
            merged[task_id] = dict(task_update)  # type: ignore[assignment]
    return merged


class AgentState(TypedDict, total=False):
    org_id: str
    meeting_id: str
    thread_id: str
    title: str
    transcript: str
    transcript_segments: List[Dict[str, Any]]
    participants: List[Dict[str, Any]]
    is_demo: bool
    __drop__: bool

    tasks: Annotated[Dict[str, Task], update_tasks_reducer]
    key_decisions: List[DecisionItem]
    meeting_context: Dict[str, Any]

    resolutions: List[AIResolution]
    interrupt_payload: Optional[Dict[str, Any]]
    hitl_decisions: Dict[str, str]
    approver_user_id: Optional[str]
    dispatched_tickets: List[Dict[str, Any]]
    immediate_alerts: List[Dict[str, Any]]
    manager_approved: bool

    # Graph B closed-loop fields
    turn_count: int
    tracker_task_id: Optional[str]
    tracker_assignee: Optional[str]
    slack_channel: Optional[str]
    slack_thread_ts: Optional[str]
    last_slack_reply: Optional[str]
    parsed_intent: Optional[Literal["COMPLETE", "PARTIAL", "BLOCKED", "AMBIGUOUS"]]
    intent_confidence: Optional[float]
    intent_reason: Optional[str]
    tracker_updates: List[Dict[str, Any]]

