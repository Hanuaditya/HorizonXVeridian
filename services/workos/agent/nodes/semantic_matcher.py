"""Graph B: GitHub commit semantic matcher (scoped to committer's open tickets + margin check)."""

from __future__ import annotations

import logging
from typing import Dict

from agent.state import AgentState
from core.config import get_settings
from core.embeddings import get_embedding
from core.store import query_open_tasks_semantic, write_audit_trail

logger = logging.getLogger(__name__)


def semantic_matcher_node(state: AgentState) -> dict:
    """Match commit message against assignee's open tickets using threshold + runner-up margin."""
    settings = get_settings()
    org_id = state.get("org_id") or "org_demo_horizon"
    commit_text = state.get("last_slack_reply") or ""
    committer = state.get("tracker_assignee")

    emb = get_embedding(commit_text, dim=settings.embedding_dim)
    matches = query_open_tasks_semantic(
        org_id=org_id,
        query_embedding=emb,
        assignee=committer,
        threshold=settings.commit_match_threshold,
        limit=3,
    )

    if not matches:
        return {
            "parsed_intent": "AMBIGUOUS",
            "intent_confidence": 0.0,
            "intent_reason": "No open ticket met COMMIT_MATCH_THRESHOLD",
            "tracker_task_id": None,
        }

    top = matches[0]
    top_score = float(top.get("similarity", 0.0))
    runner_up_score = float(matches[1].get("similarity", 0.0)) if len(matches) > 1 else 0.0
    margin = top_score - runner_up_score

    if len(matches) > 1 and margin < settings.commit_match_margin:
        write_audit_trail(
            org_id=org_id,
            meeting_id=top.get("meeting_id", "github"),
            task_id=top.get("task_id"),
            event_type="COMMIT_MATCH_AMBIGUOUS",
            agent_node="semantic_matcher_node",
            detail=f"Top={top_score:.3f}, 2nd={runner_up_score:.3f}, margin={margin:.3f} < {settings.commit_match_margin}",
            confidence=top_score,
            provenance_tag="GitHub Semantic Matcher Guard",
        )
        return {
            "parsed_intent": "AMBIGUOUS",
            "intent_confidence": top_score,
            "intent_reason": f"Ambiguous commit match (margin {margin:.2f} < {settings.commit_match_margin:.2f})",
            "tracker_task_id": top.get("task_id"),
        }

    return {
        "parsed_intent": "COMPLETE",
        "intent_confidence": top_score,
        "intent_reason": f"Unambiguous commit match to {top.get('jira_key') or top.get('task_id')}",
        "tracker_task_id": top.get("task_id"),
    }

