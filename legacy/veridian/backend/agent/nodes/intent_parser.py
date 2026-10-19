"""
agent/nodes/intent_parser.py — Graph B: Slack Reply Intent Classification
==========================================================================
Uses Nvidia NIM structured_output to classify the human's Slack reply
into COMPLETED, BLOCKED, or AMBIGUOUS, with a confidence score.

This node is the entry point for Graph B and re-runs on each loop iteration
(after slack_dm_node asks for clarification).
"""

import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field

from agent.llm_client import structured_output
from agent.state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schema for intent classification
# ---------------------------------------------------------------------------

class IntentOutput(BaseModel):
    intent: Literal["COMPLETED", "BLOCKED", "AMBIGUOUS"] = Field(
        description=(
            "COMPLETED = human confirms task is done (e.g. 'I'm done', '100%', 'finished'). "
            "BLOCKED = human reports a blocker (e.g. 'stuck', 'can't proceed', 'need help'). "
            "AMBIGUOUS = unclear or partial progress (e.g. '80% done', 'working on it', 'maybe')."
        )
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description=(
            "How confident you are in the classification. "
            "Use >= 0.8 for clear signals. < 0.8 for ambiguous messages."
        ),
    )
    extracted_percentage: Optional[float] = Field(
        default=None,
        description="If the human mentions a %, extract it (e.g. '80% done' → 80.0). Else null.",
    )
    reasoning: str = Field(
        description="One concise sentence explaining why you chose this intent.",
    )


INTENT_SYSTEM_PROMPT = """You are an intent classifier for an enterprise AI task tracker.

A human replied to a Slack message about a work task. Classify their reply.

CLASSIFICATION RULES:
- COMPLETED: The person says the task is fully done. Strong signals: "done", "finished",
  "complete", "deployed", "merged", "100%", "closed it", "all good", "shipped".
- BLOCKED: The person reports they cannot proceed. Strong signals: "stuck", "blocked",
  "can't", "need help", "waiting on", "issue", "problem", "error", "failed".
- AMBIGUOUS: Anything else — partial progress, vague updates, questions, silence.
  Examples: "almost done", "80% done", "working on it", "will do", "soon".

CONFIDENCE:
- >= 0.8 for unambiguous signals
- 0.5-0.79 for reasonably clear signals
- < 0.5 for very unclear messages"""


def intent_parser_node(state: AgentState) -> dict:
    """
    Classify the latest Slack reply from state["last_slack_reply"].

    Returns:
        {"parsed_intent": "COMPLETED"|"BLOCKED"|"AMBIGUOUS",
         "intent_confidence": float}
    """
    slack_reply = state.get("last_slack_reply", "")
    assignee = state.get("tracker_assignee", "Unknown")
    task_id = state.get("tracker_task_id", "unknown")
    turn = state.get("turn_count", 0)

    if not slack_reply:
        logger.warning(
            "intent_parser_node: no last_slack_reply in state — defaulting to AMBIGUOUS."
        )
        return {"parsed_intent": "AMBIGUOUS", "intent_confidence": 0.0}

    messages = [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Task: {task_id} | Assignee: {assignee} | Turn: {turn + 1}\n\n"
                f"Slack reply to classify:\n\"{slack_reply}\""
            ),
        },
    ]

    logger.info(
        "intent_parser_node: classifying reply from '%s' (turn %d): '%s…'",
        assignee, turn + 1, slack_reply[:80],
    )

    try:
        result: IntentOutput = structured_output(messages, IntentOutput)
    except Exception as exc:
        logger.error("intent_parser_node: LLM classification failed: %s", exc)
        return {"parsed_intent": "AMBIGUOUS", "intent_confidence": 0.0}

    logger.info(
        "intent_parser_node: '%s' → intent=%s confidence=%.2f | %s",
        assignee, result.intent, result.confidence, result.reasoning,
    )

    return {
        "parsed_intent": result.intent,
        "intent_confidence": result.confidence,
    }
