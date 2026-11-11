"""6I: AI resolution generator (Gnani Evon 30B + Pydantic + DEMO_MODE rule synthesizer)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from agent.state import AIResolution, AgentState, Task
from core.evon_llm import structured_output, wrap_untrusted_data
from core.store import save_resolutions, upsert_tasks, write_audit_trail

logger = logging.getLogger(__name__)


class ResolutionOutput(BaseModel):
    suggested_action: Literal["REFRAME", "REROUTE", "DEFER", "OVERRIDE", "PROCEED"]
    reframed_title: Optional[str] = None
    reframed_description: Optional[str] = None
    new_assignee: Optional[str] = None
    defer_reason: Optional[str] = None
    override_note: Optional[str] = None


RESOLUTION_SYSTEM_PROMPT = """You are the Gnani Sovereign WorkOS Resolution Engine.
Evaluate the task and its verified compliance firewall flags, then decide the safest remediation:
- If budget is 0 / exhausted -> DEFER
- If security policy violation exists -> REFRAME to comply (e.g. 14-day staging soak referencing exact policy_id)
- If assignee is on leave/unavailable or overloaded and rerouted_assignee is available -> REROUTE
- If assignee is unresolved -> OVERRIDE (or REROUTE) pending manager review
- If no flags -> PROCEED
Never invent policy IDs or choose external Jira projects or Slack channels."""


def _has_flags(task: dict) -> bool:
    return bool(
        task.get("assignee_resolution_flag")
        or task.get("finance_flag")
        or task.get("security_flag")
        or task.get("capacity_flag")
        or (
            task.get("hr_status")
            and task["hr_status"] not in ("ACTIVE", "NOT_FOUND", "QUERY_ERROR", None)
        )
    )


def _deterministic_resolution(task: dict) -> ResolutionOutput:
    """Apply deterministic policy priority when running offline/DEMO_MODE."""
    if task.get("finance_flag"):
        return ResolutionOutput(
            suggested_action="DEFER",
            reframed_title=f"[Deferred] {task.get('title', 'Provision Compute')}",
            reframed_description=(
                f"Deferred due to exhausted budget ({task['finance_flag']}). "
                "Requires Q4 CFO / FinOps budget approval before provisioning."
            ),
            defer_reason=str(task["finance_flag"]),
        )
    if task.get("security_flag"):
        rerouted = task.get("rerouted_assignee") or task.get("assignee")
        return ResolutionOutput(
            suggested_action="REFRAME",
            reframed_title="Deploy Elastic Search Cluster to Staging Environment [14-Day Bake Required]",
            reframed_description=(
                f"Reframed per {task['security_flag']}. Provision in Staging and enforce "
                f"mandatory 14-day soak period before AWS production cutover. Assignee: {rerouted}."
            ),
            new_assignee=rerouted,
        )
    if task.get("hr_status") in {"ON_PATERNITY_LEAVE", "ON_MATERNITY_LEAVE", "ON_LEAVE"} or task.get("capacity_flag"):
        target = task.get("rerouted_assignee")
        if target:
            return ResolutionOutput(
                suggested_action="REROUTE",
                reframed_title=f"[Rerouted -> {target}] {task.get('title', 'Task')}",
                reframed_description=(
                    f"Rerouted from {task.get('assignee')} ({task.get('hr_provenance') or task.get('capacity_provenance')}) "
                    f"to {target}."
                ),
                new_assignee=target,
            )
        return ResolutionOutput(
            suggested_action="OVERRIDE",
            override_note=f"Assignee unavailable ({task.get('hr_status')}); awaiting manager reassignment.",
        )
    if task.get("assignee_resolution_flag"):
        return ResolutionOutput(
            suggested_action="OVERRIDE",
            override_note="Assignee could not be resolved unambiguously; manager confirmation required.",
        )
    return ResolutionOutput(suggested_action="PROCEED")


def _conflict_type_and_provenance(task: dict) -> tuple[str, str]:
    if task.get("finance_flag"):
        return "BUDGET", str(task.get("finance_provenance") or "Finance CSV")
    if task.get("security_flag"):
        return "SECURITY", str(task.get("security_provenance") or "Security Policy RAG")
    if task.get("hr_status") and task["hr_status"] not in ("ACTIVE", "NOT_FOUND", None):
        return "HR", str(task.get("hr_provenance") or "HR Connector")
    if task.get("capacity_flag"):
        return "CAPACITY", str(task.get("capacity_provenance") or "Capacity Check")
    if task.get("assignee_resolution_flag"):
        return "UNRESOLVED_ASSIGNEE", "Speaker Resolution"
    return "NONE", "All firewall checks passed"


def resolution_generator_node(state: AgentState) -> dict:
    """Generate structured AIResolution proposals for all extracted tasks."""
    org_id = state.get("org_id") or "org_demo_horizon"
    meeting_id = state.get("meeting_id", "unknown")
    thread_id = state.get("thread_id", meeting_id)
    is_demo = bool(state.get("is_demo", False))
    tasks = state.get("tasks", {})

    task_updates: Dict[str, Task] = {}
    resolutions: List[AIResolution] = []

    for task_id, task in tasks.items():
        if not _has_flags(task):
            task_updates[task_id] = Task(resolution_action="PROCEED", status="READY")
            resolutions.append(
                AIResolution(
                    task_id=task_id,
                    conflict_type="NONE",
                    provenance_tag="All firewall checks passed",
                    suggested_action="PROCEED",
                    new_payload=None,
                )
            )
            continue

        context_str = (
            f"Title: {task.get('title')}\n"
            f"Assignee: {task.get('assignee')}\n"
            f"Rerouted Assignee: {task.get('rerouted_assignee')}\n"
            f"HR: {task.get('hr_status')} | {task.get('hr_provenance')}\n"
            f"Finance: {task.get('finance_flag')}\n"
            f"Security: {task.get('security_flag')}\n"
            f"Capacity: {task.get('capacity_flag')}\n"
            f"Resolution Flag: {task.get('assignee_resolution_flag')}\n"
        )
        delimited = wrap_untrusted_data("task_flags", context_str)

        res_out = structured_output(
            system_prompt=RESOLUTION_SYSTEM_PROMPT,
            user_prompt=f"Decide resolution for task {task_id}:\n{delimited}",
            schema=ResolutionOutput,
            force_demo=is_demo,
        )
        if res_out is None:
            res_out = _deterministic_resolution(task)

        conflict_type, provenance_tag = _conflict_type_and_provenance(task)
        task_updates[task_id] = Task(
            resolution_action=res_out.suggested_action,
            reframed_title=res_out.reframed_title,
            reframed_description=res_out.reframed_description or res_out.defer_reason or res_out.override_note,
            rerouted_assignee=res_out.new_assignee or task.get("rerouted_assignee"),
        )
        resolutions.append(
            AIResolution(
                task_id=task_id,
                conflict_type=conflict_type,  # type: ignore[typeddict-item]
                provenance_tag=provenance_tag,
                suggested_action=res_out.suggested_action,
                new_payload=res_out.model_dump(),
            )
        )

    save_resolutions(org_id=org_id, meeting_id=meeting_id, thread_id=thread_id, resolutions=resolutions)
    upsert_tasks(org_id=org_id, meeting_id=meeting_id, thread_id=thread_id, tasks={
        k: {**tasks.get(k, {}), **v} for k, v in task_updates.items()
    })
    write_audit_trail(
        org_id=org_id,
        meeting_id=meeting_id,
        thread_id=thread_id,
        event_type="RESOLUTIONS_PROPOSED",
        agent_node="resolution_generator_node",
        detail=f"Proposed {len(resolutions)} resolutions",
        provenance_tag="Evon 30B / Compliance Resolver",
    )

    return {
        "tasks": task_updates,
        "resolutions": resolutions,
    }
