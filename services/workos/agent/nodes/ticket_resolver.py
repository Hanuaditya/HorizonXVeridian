"""Graph B: Jira & Supabase ticket closure / blocker escalation + anti-loop handler."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from agent.state import AgentState
from core.evon_llm import resolve_slack_channel
from core.store import update_task_status_by_id, upsert_slack_thread, write_audit_trail

logger = logging.getLogger(__name__)


def ticket_resolver_node(state: AgentState) -> dict:
    """Resolve ticket as Done when intent=COMPLETE; else emit clarifying or blocker state."""
    org_id = state.get("org_id") or "org_demo_horizon"
    task_id = state.get("tracker_task_id") or "unknown"
    thread_id = state.get("thread_id") or "closed-loop"
    intent = state.get("parsed_intent") or "AMBIGUOUS"
    turn_count = int(state.get("turn_count", 0))
    assignee = state.get("tracker_assignee") or "assignee"

    updates_list: List[Dict[str, Any]] = list(state.get("tracker_updates", []))
    now_iso = datetime.now(timezone.utc).isoformat()

    if intent == "COMPLETE" and task_id != "unknown":
        update_task_status_by_id(org_id=org_id, task_id=task_id, status="DONE")
        event_summary = {
            "task_id": task_id,
            "status": "DONE",
            "intent": intent,
            "confidence": state.get("intent_confidence"),
            "reason": state.get("intent_reason"),
            "updated_at": now_iso,
        }
        updates_list.append(event_summary)
        write_audit_trail(
            org_id=org_id,
            meeting_id=thread_id,
            thread_id=thread_id,
            task_id=task_id,
            event_type="TICKET_AUTO_CLOSED",
            agent_node="ticket_resolver_node",
            detail=state.get("intent_reason") or "Marked DONE",
            confidence=state.get("intent_confidence"),
            provenance_tag="Graph B Closed Loop",
        )
    else:
        if task_id != "unknown" and intent == "BLOCKED":
            update_task_status_by_id(org_id=org_id, task_id=task_id, status="BLOCKED")
        event_summary = {
            "task_id": task_id,
            "status": "BLOCKED" if intent == "BLOCKED" else "NEEDS_CLARIFICATION",
            "intent": intent,
            "turn_count": turn_count,
            "assignee": assignee,
            "reason": state.get("intent_reason"),
            "updated_at": now_iso,
        }
        updates_list.append(event_summary)

    if state.get("slack_channel") and state.get("slack_thread_ts"):
        upsert_slack_thread(
            org_id=org_id,
            thread_id=thread_id,
            task_id=task_id,
            jira_key=None,
            slack_channel=state["slack_channel"] or resolve_slack_channel("summary"),
            slack_thread_ts=state["slack_thread_ts"] or thread_id,
            assignee=assignee,
            turn_count=turn_count,
            status="DONE" if intent == "COMPLETE" else "ESCALATED" if turn_count >= 2 or intent == "BLOCKED" else "OPEN",
        )

    return {"tracker_updates": updates_list}


def escalation_node(state: AgentState) -> dict:
    """Escalate blocked tasks or anti-loop turn_count >= 2 threads to manager channel."""
    org_id = state.get("org_id") or "org_demo_horizon"
    task_id = state.get("tracker_task_id") or "unknown"
    thread_id = state.get("thread_id") or "closed-loop"
    turn_count = int(state.get("turn_count", 0))
    channel = resolve_slack_channel("manager")

    if task_id != "unknown":
        update_task_status_by_id(org_id=org_id, task_id=task_id, status="BLOCKED")

    reason = (
        f"Anti-loop escalation after {turn_count} turns"
        if turn_count >= 2
        else f"Blocker reported: {state.get('intent_reason')}"
    )
    write_audit_trail(
        org_id=org_id,
        meeting_id=thread_id,
        thread_id=thread_id,
        task_id=task_id,
        event_type="MANAGER_ESCALATED",
        agent_node="escalation_node",
        detail=f"Escalated to {channel}: {reason}",
        provenance_tag="Graph B Escalation",
    )
    updates_list = list(state.get("tracker_updates", []))
    updates_list.append({
        "task_id": task_id,
        "status": "ESCALATED",
        "channel": channel,
        "reason": reason,
        "turn_count": turn_count,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"tracker_updates": updates_list}
