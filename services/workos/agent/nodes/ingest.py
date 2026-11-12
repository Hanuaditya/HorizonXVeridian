"""6A: Org-scoped idempotency guard & meeting ingestion node."""

from __future__ import annotations

import logging
from typing import Any, Dict

from agent.state import AgentState
from core.store import is_meeting_processed, mark_meeting_processed, write_audit_trail

logger = logging.getLogger(__name__)


def _segments_to_text(segments: list[Dict[str, Any]]) -> str:
    lines = []
    for seg in segments:
        speaker = seg.get("speaker") or "SPEAKER"
        text = str(seg.get("text") or "").strip()
        start = float(seg.get("start") or 0.0)
        mins, secs = divmod(int(start), 60)
        if text:
            lines.append(f"[{mins:02d}:{secs:02d} - {speaker}]: {text}")
    return "\n".join(lines)


def ingest_node(state: AgentState) -> dict:
    """Verify meeting_id has not been processed for org_id; register if new."""
    org_id = state.get("org_id") or "org_demo_horizon"
    meeting_id = state["meeting_id"]
    thread_id = state.get("thread_id", meeting_id)

    if is_meeting_processed(org_id=org_id, meeting_id=meeting_id):
        logger.info("ingest_node: duplicate meeting_id='%s' for org='%s' -> dropping.", meeting_id, org_id)
        return {"__drop__": True}

    mark_meeting_processed(org_id=org_id, meeting_id=meeting_id, thread_id=thread_id, task_count=0)
    write_audit_trail(
        org_id=org_id,
        meeting_id=meeting_id,
        thread_id=thread_id,
        event_type="MEETING_INGESTED",
        agent_node="ingest_node",
        detail=f"Registered meeting '{meeting_id}'",
        provenance_tag="Signed meeting.ended contract",
    )

    transcript_text = state.get("transcript") or ""
    if not transcript_text and state.get("transcript_segments"):
        transcript_text = _segments_to_text(state["transcript_segments"])

    return {
        "org_id": org_id,
        "transcript": transcript_text,
    }

