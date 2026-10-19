"""
agent/nodes/resolution_generator.py — 6I: AI Resolution via Pydantic Tool Calling
===================================================================================
For each task with one or more firewall flags, calls the Nvidia NIM LLM
to generate a structured resolution — REFRAME, REROUTE, DEFER, OVERRIDE,
or PROCEED — based on the strict mapping rules from the Master Prompt.
"""

import logging
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from agent.llm_client import structured_output
from agent.state import AgentState, AIResolution

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schema for resolution output
# ---------------------------------------------------------------------------

class ResolutionOutput(BaseModel):
    suggested_action: Literal["REFRAME", "REROUTE", "DEFER", "OVERRIDE", "PROCEED"] = Field(
        description=(
            "Resolution action: "
            "REFRAME=rewrite task to comply with policy, "
            "REROUTE=reassign to new person, "
            "DEFER=postpone to next budget cycle, "
            "OVERRIDE=acknowledge issue, note async review, keep assignee, "
            "PROCEED=no issues found."
        )
    )
    reframed_title: Optional[str] = Field(
        default=None,
        description="New concise Jira ticket title. Required when action=REFRAME.",
    )
    reframed_description: Optional[str] = Field(
        default=None,
        description=(
            "Full Jira ticket description with policy-compliant steps. "
            "Required when action=REFRAME. Must reference the exact policy violated."
        ),
    )
    new_assignee: Optional[str] = Field(
        default=None,
        description="New assignee name. Required when action=REROUTE.",
    )
    defer_reason: Optional[str] = Field(
        default=None,
        description="Reason for deferral. Required when action=DEFER.",
    )
    override_note: Optional[str] = Field(
        default=None,
        description=(
            "Acknowledgement note explaining why the task proceeds despite the flag. "
            "Required when action=OVERRIDE."
        ),
    )


# ---------------------------------------------------------------------------
# System prompt (resolution mapping rules embedded)
# ---------------------------------------------------------------------------

RESOLUTION_SYSTEM_PROMPT = """You are the AI Resolution Engine for Veridian WorkOS, \
an enterprise AI Chief of Staff.

Your job is to evaluate a task and its compliance flags, then decide the correct action.

MANDATORY RESOLUTION MAPPING RULES (apply in this priority order):
1. If hr_status is ON_PATERNITY_LEAVE or ON_MATERNITY_LEAVE → action=OVERRIDE
   - Keep the original assignee in override_note
   - Write a note acknowledging the leave and scheduling async review on return
2. If finance_flag mentions "$0 budget" → action=DEFER
   - Write a defer_reason explaining the budget constraint and suggest Q4 review
3. If security_flag is present → action=REFRAME
   - Write a NEW reframed_title (e.g. "Deploy X to Staging [14-day quarantine]")
   - Write a full reframed_description as a proper Jira ticket with steps that comply
     with the violated policy. Reference the exact policy ID in the description.
4. If capacity_flag is present → action=REROUTE
   - Set new_assignee to the rerouted_assignee value provided in the task data
5. If no flags at all → action=PROCEED (all fields null)

WRITING STANDARDS:
- reframed_description must be a complete, professional Jira ticket description
- Always reference policy IDs (e.g. SEC-POL-089) explicitly
- Be specific about timelines and staging requirements
- Do NOT invent policy content — only reframe based on the provided flag text"""


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def _has_flags(task: dict) -> bool:
    """Return True if any firewall checker raised a flag on this task."""
    return any([
        task.get("finance_flag"),
        task.get("security_flag"),
        task.get("capacity_flag"),
        task.get("hr_status") and task["hr_status"] not in (
            "ACTIVE", "NOT_FOUND", "QUERY_ERROR", None
        ),
    ])


def _build_task_context(task: dict) -> str:
    """Build a concise context string for the LLM prompt."""
    lines = [
        f"Task ID: {task.get('task_id')}",
        f"Title: {task.get('title')}",
        f"Assignee: {task.get('assignee')}",
        f"Resource Type: {task.get('resource_type')}",
        f"Transcript Quote: \"{task.get('transcript_quote', '')}\"",
        "",
        "FIREWALL FLAGS:",
    ]

    if task.get("hr_status"):
        lines.append(f"  HR Status: {task['hr_status']} (source: {task.get('hr_provenance', 'BambooHR')})")
    if task.get("finance_flag"):
        lines.append(f"  Finance Flag: {task['finance_flag']} (source: {task.get('finance_provenance', 'Google Sheets')})")
    if task.get("security_flag"):
        lines.append(
            f"  Security Flag: {task['security_flag']} "
            f"(confidence: {task.get('security_confidence', 0):.2f}, "
            f"source: {task.get('security_provenance', 'RAG')})"
        )
    if task.get("capacity_flag"):
        lines.append(
            f"  Capacity Flag: {task['capacity_flag']} "
            f"(source: {task.get('capacity_provenance', 'Jira')})"
        )
    if task.get("rerouted_assignee"):
        lines.append(f"  Rerouted Assignee (auto-selected): {task['rerouted_assignee']}")

    return "\n".join(lines)


def resolution_generator_node(state: AgentState) -> dict:
    """
    Evaluate each flagged task and generate a structured resolution.

    Returns:
        Partial state dict with:
          - tasks: {task_id: {resolution_action, reframed_title, reframed_description}}
          - resolutions: List[AIResolution] (appended to existing list)
    """
    tasks = state.get("tasks", {})
    existing_resolutions: List[AIResolution] = list(state.get("resolutions", []))

    task_updates: Dict[str, dict] = {}
    new_resolutions: List[AIResolution] = []

    for task_id, task in tasks.items():

        # ── Clear tasks get PROCEED without calling the LLM ─────────────
        if not _has_flags(task):
            logger.debug(
                "resolution_generator_node: task '%s' is CLEAR → PROCEED.", task_id
            )
            task_updates[task_id] = {"resolution_action": "PROCEED"}
            new_resolutions.append(AIResolution(
                task_id=task_id,
                conflict_type="NONE",
                provenance_tag="No flags raised",
                suggested_action="PROCEED",
                new_payload=None,
            ))
            continue

        # ── Build LLM context for flagged task ───────────────────────────
        task_context = _build_task_context(task)
        messages = [
            {"role": "system", "content": RESOLUTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Evaluate this flagged task and provide the correct resolution:\n\n"
                    f"{task_context}"
                ),
            },
        ]

        logger.info(
            "resolution_generator_node: calling NIM for task '%s' (flags: HR=%s, FIN=%s, SEC=%s, CAP=%s).",
            task_id,
            task.get("hr_status"),
            bool(task.get("finance_flag")),
            bool(task.get("security_flag")),
            bool(task.get("capacity_flag")),
        )

        try:
            resolution: ResolutionOutput = structured_output(messages, ResolutionOutput)
        except Exception as exc:
            logger.error(
                "resolution_generator_node: LLM call failed for task '%s': %s",
                task_id, exc,
            )
            # Fail safe — mark as needing human review
            task_updates[task_id] = {"resolution_action": "OVERRIDE"}
            continue

        action = resolution.suggested_action

        # ── Determine conflict_type for AIResolution ─────────────────────
        if task.get("security_flag"):
            conflict_type = "SECURITY"
        elif task.get("finance_flag"):
            conflict_type = "BUDGET"
        elif task.get("capacity_flag"):
            conflict_type = "CAPACITY"
        elif task.get("hr_status") and task["hr_status"] not in ("ACTIVE", None):
            conflict_type = "HR"
        else:
            conflict_type = "NONE"

        # ── Build provenance tag ─────────────────────────────────────────
        provenance_parts = []
        if task.get("security_provenance"):
            provenance_parts.append(task["security_provenance"])
        if task.get("finance_provenance"):
            provenance_parts.append(task["finance_provenance"])
        if task.get("hr_provenance"):
            provenance_parts.append(task["hr_provenance"])
        provenance_tag = " | ".join(provenance_parts) or "Veridian AI Resolution"

        # ── Build the new_payload for AIResolution ───────────────────────
        new_payload: dict = {"action": action}
        if resolution.reframed_title:
            new_payload["reframed_title"] = resolution.reframed_title
        if resolution.reframed_description:
            new_payload["reframed_description"] = resolution.reframed_description
        if resolution.new_assignee:
            new_payload["new_assignee"] = resolution.new_assignee
        if resolution.defer_reason:
            new_payload["defer_reason"] = resolution.defer_reason
        if resolution.override_note:
            new_payload["override_note"] = resolution.override_note

        # ── Update task state fields ─────────────────────────────────────
        task_update: dict = {"resolution_action": action}
        if resolution.reframed_title:
            task_update["reframed_title"] = resolution.reframed_title
        if resolution.reframed_description:
            task_update["reframed_description"] = resolution.reframed_description
        if action == "REROUTE" and task.get("rerouted_assignee"):
            task_update["rerouted_assignee"] = task["rerouted_assignee"]

        task_updates[task_id] = task_update

        new_resolutions.append(AIResolution(
            task_id=task_id,
            conflict_type=conflict_type,
            provenance_tag=provenance_tag,
            suggested_action=action,
            new_payload=new_payload,
        ))

        logger.info(
            "resolution_generator_node: task '%s' → %s (conflict: %s).",
            task_id, action, conflict_type,
        )

    return {
        "tasks": task_updates,
        "resolutions": existing_resolutions + new_resolutions,
    }
