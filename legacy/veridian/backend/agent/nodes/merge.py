"""
agent/nodes/merge.py — 6H: Synchronization Barrier (Fan-In)
============================================================
Passive node that acts as the explicit synchronization point after the
parallel fan-out phase. LangGraph routes all four checker outputs through
update_tasks_reducer before this node executes — so by the time merge_node
runs, AgentState["tasks"] already contains every checker's results merged.

This node logs the completion of all parallel checks and optionally writes
an audit trail entry to Supabase.
"""

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client

from agent.state import AgentState

load_dotenv()
logger = logging.getLogger(__name__)


def merge_node(state: AgentState) -> dict:
    """
    Synchronization barrier. All parallel checkers have completed by the
    time LangGraph calls this node. State is already merged by the reducer.

    This node:
      - Logs a summary of all flags raised across all tasks
      - Writes an audit trail entry to Supabase
      - Returns {} (no state changes — purely a checkpoint)
    """
    tasks = state.get("tasks", {})
    meeting_id = state.get("meeting_id", "unknown")

    # ── Summarise flags ───────────────────────────────────────────────────
    flag_summary = []
    for task_id, task in tasks.items():
        flags = []
        if task.get("hr_status") and task["hr_status"] not in ("ACTIVE", "QUERY_ERROR"):
            flags.append(f"HR={task['hr_status']}")
        if task.get("finance_flag"):
            flags.append("FINANCE")
        if task.get("security_flag"):
            flags.append(f"SECURITY(conf={task.get('security_confidence', 0):.2f})")
        if task.get("capacity_flag"):
            flags.append("CAPACITY")

        if flags:
            flag_summary.append(f"  [{task_id}] {task.get('title','?')[:40]} → {', '.join(flags)}")

    if flag_summary:
        logger.warning(
            "merge_node: 🔀 All checks complete for meeting '%s'. Flags raised:\n%s",
            meeting_id,
            "\n".join(flag_summary),
        )
    else:
        logger.info(
            "merge_node: ✅ All checks complete for meeting '%s'. No flags raised — "
            "all %d tasks clear.",
            meeting_id, len(tasks),
        )

    # ── Write audit trail entry ───────────────────────────────────────────
    try:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        if url and key:
            supabase = create_client(url, key)
            supabase.table("audit_trail").insert(
                {
                    "meeting_id": meeting_id,
                    "event_type": "PARALLEL_CHECKS_COMPLETE",
                    "agent_node": "merge_node",
                    "detail": (
                        f"{len(tasks)} tasks checked · "
                        f"{len(flag_summary)} flagged"
                    ),
                    "confidence": None,
                    "provenance": "LangGraph fan-in",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ).execute()
    except Exception as exc:
        # Audit trail failure must never block the pipeline
        logger.debug("merge_node: audit trail write failed (non-critical): %s", exc)

    # Passive node — no state changes
    return {}
