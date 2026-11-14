"""Unified in-memory thread store for Veridian Bot conversations.

Provides deterministic, zero-lag (<20ms) buckets for:
- "manager"
- "catchme_if"
- "resigo"
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

DEMO_BOT_THREADS: Dict[str, List[Dict[str, Any]]] = {
    "manager": [],
    "catchme_if": [],
    "resigo": [],
}

_PENDING_CHECKIN_TASKS: Set[asyncio.Task] = set()


def get_demo_bucket(auth_or_identifier: Any, current_name: str = "") -> str:
    """Canonical Bucket Resolver:
    - If auth.role == "org:admin" or identifier/name contains "hanu" or "manager" -> "manager"
    - If identifier/name contains "catchme" -> "catchme_if"
    - If identifier/name contains "resigo" -> "resigo"
    - Default fallback for admin/manager contexts -> "manager"
    """
    role = ""
    ident_parts = [str(current_name or "")]
    if hasattr(auth_or_identifier, "role"):
        role = str(getattr(auth_or_identifier, "role") or "")
        ident_parts.append(str(getattr(auth_or_identifier, "user_id", "") or ""))
        ident_parts.append(str(getattr(auth_or_identifier, "email", "") or ""))
    elif isinstance(auth_or_identifier, str):
        ident_parts.append(auth_or_identifier)

    blob = " ".join(ident_parts).lower()

    if role == "org:admin" or "manager" in blob or "hanu" in blob:
        return "manager"
    if "resigo" in blob:
        return "resigo"
    if "catchme" in blob:
        return "catchme_if"
    if role == "org:member" or "emp" in blob or "member" in blob or "employee" in blob:
        return "catchme_if"
    return "manager"


def append_demo_bot_message(
    bucket: str,
    role: str,
    sender: str,
    recipient: str,
    text: str,
    kind: str = "message",
    task_id: Optional[str] = None,
    jira_key: Optional[str] = None,
    client_msg_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append a message to the target DEMO_BOT_THREADS bucket idempotently."""
    bucket_key = bucket if bucket in DEMO_BOT_THREADS else get_demo_bucket(bucket)
    thread = DEMO_BOT_THREADS.setdefault(bucket_key, [])

    if client_msg_id:
        for existing in thread:
            if existing.get("client_msg_id") == client_msg_id:
                return existing

    msg = {
        "id": str(uuid.uuid4()),
        "client_msg_id": client_msg_id or "",
        "org_id": "org_demo_horizon",
        "thread_id": f"veridian-bot:{bucket_key}",
        "role": role,
        "sender": sender,
        "recipient": recipient,
        "text": text,
        "kind": kind,
        "task_id": task_id,
        "jira_key": jira_key,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    thread.append(msg)
    return msg


def get_demo_bot_messages(bucket: str) -> List[Dict[str, Any]]:
    """Return all messages for the specified bucket."""
    bucket_key = bucket if bucket in DEMO_BOT_THREADS else get_demo_bucket(bucket)
    return list(DEMO_BOT_THREADS.get(bucket_key, []))


def register_checkin_timer(task: asyncio.Task) -> None:
    """Track an active background check-in timer."""
    _PENDING_CHECKIN_TASKS.add(task)
    task.add_done_callback(_PENDING_CHECKIN_TASKS.discard)


def cancel_pending_checkin_timers() -> None:
    """Cancel all active background timers on reset."""
    for t in list(_PENDING_CHECKIN_TASKS):
        if not t.done():
            t.cancel()
    _PENDING_CHECKIN_TASKS.clear()


def reset_demo_bot_threads() -> None:
    """Clear all in-memory demo threads and cancel timers."""
    cancel_pending_checkin_timers()
    for key in DEMO_BOT_THREADS:
        DEMO_BOT_THREADS[key].clear()
    logger.info("DEMO_BOT_THREADS cleanly reset for manager, catchme_if, and resigo.")
