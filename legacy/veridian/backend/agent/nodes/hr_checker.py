"""
agent/nodes/hr_checker.py — 6C: HR Status Verification
========================================================
Queries the hr_employees Supabase table directly via SQL to determine
each assignee's employment status. Layer 1 is complete — hr_employees
is fully populated. No mock server.

Parallel-safe: returns a partial Dict[task_id → partial Task] that is
merged by update_tasks_reducer in AgentState without overwriting other
checkers' fields.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict

from dotenv import load_dotenv
from supabase import create_client, Client

from agent.state import AgentState

load_dotenv()
logger = logging.getLogger(__name__)


def _get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise EnvironmentError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
    return create_client(url, key)


def _time_ago(dt_str: str) -> str:
    """Format a UTC ISO-8601 timestamp as a human-readable 'X ago' string."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = datetime.now(timezone.utc) - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return f"{seconds}s ago"
        elif seconds < 3600:
            return f"{seconds // 60} mins ago"
        elif seconds < 86400:
            return f"{seconds // 3600} hours ago"
        else:
            return f"{seconds // 86400} days ago"
    except Exception:
        return "recently"


def hr_checker_node(state: AgentState) -> dict:
    """
    For each task, query Supabase hr_employees for the assignee's status.

    Query used (as per Master Prompt spec):
        SELECT status, last_synced_from, synced_at
        FROM hr_employees
        WHERE LOWER(full_name) LIKE LOWER('%{assignee}%')

    Returns:
        Partial tasks dict: {task_id: {"hr_status": ..., "hr_provenance": ...}}
        Only contains entries for tasks whose assignee was checked.
    """
    supabase = _get_supabase()
    tasks = state.get("tasks", {})
    updates: Dict[str, dict] = {}

    for task_id, task in tasks.items():
        assignee: str = task.get("assignee", "UNASSIGNED")

        # ── Skip UNASSIGNED tasks ────────────────────────────────────────
        if not assignee or assignee.upper() == "UNASSIGNED":
            logger.debug("hr_checker_node: task '%s' is UNASSIGNED — skipping.", task_id)
            continue

        # ── Query Supabase hr_employees via SQL LIKE ─────────────────────
        try:
            result = (
                supabase.table("hr_employees")
                .select("status, last_synced_from, synced_at")
                .ilike("full_name", f"%{assignee}%")
                .execute()
            )
        except Exception as exc:
            logger.error(
                "hr_checker_node: Supabase query failed for '%s': %s",
                assignee, exc,
            )
            updates[task_id] = {
                "hr_status": "QUERY_ERROR",
                "hr_provenance": f"BambooHR connector · query error: {exc}",
            }
            continue

        if not result.data:
            # No match found — treat as unverified
            logger.warning(
                "hr_checker_node: assignee '%s' (task '%s') not found in hr_employees.",
                assignee, task_id,
            )
            updates[task_id] = {
                "hr_status": "NOT_FOUND",
                "hr_provenance": f"BambooHR connector · '{assignee}' not in HRIS",
            }
            continue

        # ── Match found ──────────────────────────────────────────────────
        row = result.data[0]
        hr_status: str = row.get("status", "UNKNOWN")
        synced_at: str = row.get("synced_at", "")
        last_synced_from: str = row.get("last_synced_from", "BambooHR connector")

        time_ago_str = _time_ago(synced_at) if synced_at else "unknown time"
        hr_provenance = f"{last_synced_from} · synced {time_ago_str}"

        logger.info(
            "hr_checker_node: task '%s' assignee '%s' → %s",
            task_id, assignee, hr_status,
        )

        updates[task_id] = {
            "hr_status": hr_status,
            "hr_provenance": hr_provenance,
        }

    return {"tasks": updates}
