"""
agent/nodes/ingest.py — 6A: Idempotency guard & ingestion
==========================================================
Checks if the meeting has already been processed.
If yes, signals the graph to drop. If new, registers it and passes through.
"""

import logging
import os
from datetime import datetime, timezone

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


def ingest_node(state: AgentState) -> dict:
    """
    Idempotency check. Prevents double-processing of the same meeting.

    Returns:
        {"__drop__": True}                        if already processed
        {"meeting_id": ..., "transcript": ...}    if new meeting
    """
    meeting_id: str = state["meeting_id"]
    supabase = _get_supabase()

    # ── Check if this meeting was already processed ──────────────────────
    try:
        result = (
            supabase.table("processed_meetings")
            .select("meeting_id, processed_at")
            .eq("meeting_id", meeting_id)
            .execute()
        )
        if result.data:
            logger.info(
                "ingest_node: meeting '%s' already processed at %s — dropping.",
                meeting_id,
                result.data[0].get("processed_at"),
            )
            return {"__drop__": True}

    except Exception as exc:  # noqa: BLE001
        logger.error("ingest_node: Supabase query error — %s", exc)
        raise

    # ── New meeting — register it ────────────────────────────────────────
    try:
        supabase.table("processed_meetings").insert(
            {
                "meeting_id": meeting_id,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "task_count": 0,  # Will be updated by extractor
            }
        ).execute()
        logger.info("ingest_node: registered new meeting '%s'.", meeting_id)

    except Exception as exc:  # noqa: BLE001
        logger.error("ingest_node: failed to register meeting — %s", exc)
        raise

    return {
        "meeting_id": state["meeting_id"],
        "transcript": state["transcript"],
    }
