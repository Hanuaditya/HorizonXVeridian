"""
agent/nodes/semantic_matcher.py — Graph B: GitHub Commit → Jira Ticket Matching
=================================================================================
Uses Nvidia NIM structured_output to semantically match an incoming GitHub
push payload (commit message + branch name) to the most relevant open Jira
ticket in AgentState["tasks"], returning a confidence score.

This node is triggered by the GitHub webhook and runs independently of the
Slack loop — it is wired as an alternative START path in Graph B.
"""

import logging
from typing import List, Optional

from pydantic import BaseModel, Field

from agent.llm_client import structured_output
from agent.state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schema for semantic matching output
# ---------------------------------------------------------------------------

class TicketMatch(BaseModel):
    matched_task_id: Optional[str] = Field(
        default=None,
        description=(
            "The task_id from the provided list that best matches the commit message. "
            "Set to null if no task matches with confidence >= 0.6."
        ),
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description=(
            "How confident you are in this match (0=no match, 1=exact match). "
            "Use >= 0.8 for very clear matches, 0.6-0.79 for plausible, < 0.6 for no match."
        ),
    )
    matched_task_title: Optional[str] = Field(
        default=None,
        description="Title of the matched task, for logging and Slack notifications.",
    )
    reasoning: str = Field(
        description="One sentence explaining why this commit matches (or doesn't match) the task.",
    )


SEMANTIC_MATCHER_SYSTEM_PROMPT = """You are a commit-to-ticket semantic matcher for an enterprise AI system.

Given a GitHub commit message (and optional branch name), identify which open Jira ticket
it most likely relates to.

MATCHING RULES:
- Match based on semantic similarity of the work described, not just keyword overlap.
- A commit like "fix: elasticsearch staging config" → matches "Deploy Elastic to Staging [14-day quarantine]"
- A commit "feat: GDPR anonymization script for merge requests" → matches a security/GDPR task
- Branch names containing ticket IDs (e.g. "feature/VER-42") are strong matching signals.
- If no task is a reasonable match (confidence < 0.6), return matched_task_id as null.

CONFIDENCE GUIDE:
- 0.9-1.0: Commit message directly references the task by name or ticket ID
- 0.8-0.89: Strong semantic overlap, likely the same work
- 0.6-0.79: Plausible match, related work
- < 0.6: No clear match — do not match"""


def semantic_matcher_node(state: AgentState) -> dict:
    """
    Match an incoming GitHub commit to the most relevant open Jira task.

    Reads from state:
      - last_slack_reply: repurposed to carry the GitHub commit message/branch
        (the API layer normalises GitHub payloads into this field before invoking)
      - tasks: Dict[str, Task] — all open tasks to match against

    Returns:
        {"tracker_task_id": matched_task_id, "intent_confidence": confidence}
        or {} if no match found (graph will route to escalation or terminate)
    """
    commit_message = state.get("last_slack_reply", "")
    tasks = state.get("tasks", {})

    if not commit_message:
        logger.warning("semantic_matcher_node: no commit message in last_slack_reply.")
        return {}

    if not tasks:
        logger.warning("semantic_matcher_node: no open tasks to match against.")
        return {}

    # ── Build task list for LLM context ─────────────────────────────────
    task_list_lines: List[str] = []
    for task_id, task in tasks.items():
        # Only match against dispatched (READY) tasks that have Jira tickets
        if task.get("status") not in ("READY", "PENDING"):
            continue
        task_list_lines.append(
            f"  - task_id: {task_id} | "
            f"title: {task.get('title', 'N/A')} | "
            f"assignee: {task.get('assignee', 'N/A')} | "
            f"jira: {task.get('jira_ticket_id', 'N/A')}"
        )

    if not task_list_lines:
        logger.info("semantic_matcher_node: no READY/PENDING tasks to match.")
        return {}

    task_list_str = "\n".join(task_list_lines)

    messages = [
        {"role": "system", "content": SEMANTIC_MATCHER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"GitHub commit message:\n\"{commit_message}\"\n\n"
                f"Open Jira tickets to match against:\n{task_list_str}"
            ),
        },
    ]

    logger.info(
        "semantic_matcher_node: matching commit '%s…' against %d tasks.",
        commit_message[:80], len(task_list_lines),
    )

    try:
        result: TicketMatch = structured_output(messages, TicketMatch)
    except Exception as exc:
        logger.error("semantic_matcher_node: LLM matching failed: %s", exc)
        return {}

    logger.info(
        "semantic_matcher_node: match=%s conf=%.2f | %s",
        result.matched_task_id, result.confidence, result.reasoning,
    )

    if not result.matched_task_id or result.confidence < 0.6:
        logger.info(
            "semantic_matcher_node: confidence %.2f below threshold — no match.",
            result.confidence,
        )
        return {}

    return {
        "tracker_task_id": result.matched_task_id,
        "intent_confidence": result.confidence,
        # Signal to downstream nodes that this came from GitHub, not Slack
        "parsed_intent": "COMPLETED",   # GitHub push = task progress confirmed
    }
