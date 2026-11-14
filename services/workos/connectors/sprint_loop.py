"""Closed-loop sprint governance coordinator: Manager approvals, interval check-ins, Slack poller, and Jira auto-close."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import re
import time
from typing import Any, Dict, List, Literal, Optional, cast

from langgraph.types import Command
from pydantic import BaseModel, Field

from agent.graph_a import get_graph_a
from agent.nodes.dispatcher import dispatcher_node
from api.sse import sse_manager
from connectors.jira_ops import add_jira_comment, transition_jira_issue_done
from connectors.slack_ops import (
    has_real_slack_creds,
    post_closure_confirmation_dms,
    post_employee_checkin_dm,
    post_manager_blocker_escalation_dm,
    post_manager_progress_digest,
    post_manager_review_request_dm,
    post_slack_message,
)
from core.config import get_settings
from core.evon_llm import structured_output, wrap_untrusted_data
from core.identifiers import canonical_employee_key, clean_task_title, resolve_veridian_thread_id
from core.store import (
    get_thread_snapshot,
    list_open_slack_threads_all,
    list_slack_feed,
    list_thread_snapshots,
    record_approval,
    record_slack_feed_message,
    save_thread_snapshot,
    update_task_status_by_id,
    upsert_slack_thread,
    write_audit_trail,
)

logger = logging.getLogger(__name__)

_SEEN_SLACK_TS: set[tuple[str, str]] = set()
_LAST_CHANNEL_CHECK_TS: Dict[str, str] = {}
_CHANNEL_BACKOFF: Dict[str, float] = {}

_PR_URL_REGEX = re.compile(r"https?://(?:www\.)?(?:github\.com|gitlab\.com)/[^\s]+/pull/\d+", re.IGNORECASE)
_COMMIT_HASH_REGEX = re.compile(r"\b([0-9a-f]{7,40})\b", re.IGNORECASE)


def extract_completion_evidence(text: str) -> Optional[Dict[str, str]]:
    """Detect presence of PR URL or Git commit hash as verifiable evidence."""
    if not text:
        return None
    pr_match = _PR_URL_REGEX.search(text)
    if pr_match:
        return {"type": "pr_url", "value": pr_match.group(0)}
    for m in _COMMIT_HASH_REGEX.finditer(text):
        cand = m.group(1)
        if any(c in "abcdefABCDEF" for c in cand) or len(cand) >= 8:
            return {"type": "commit_hash", "value": cand}
    return None


class CheckinReplyAnalysis(BaseModel):
    intent: Literal["COMPLETED", "IN_PROGRESS", "BLOCKED"]
    progress_pct: int = Field(ge=0, le=100)
    completed_milestones: str
    blockers: str = Field(default="None")
    commit_summary: str = Field(default="")


CHECKIN_ANALYSIS_PROMPT = """Analyze an employee's Slack status update on an assigned sprint task.
Classify strictly into:
- COMPLETED: work is finished, done, completed, deployed, pushed, merged, or ready to close
- BLOCKED: stuck, waiting on dependency/access, error, cannot proceed
- IN_PROGRESS: partial progress reported without full completion
Extract progress_pct (0-100), concise completed_milestones, blockers ('None' if none), and a clean commit_summary."""


def _deterministic_analyze_reply(reply_text: str, task_title: str) -> CheckinReplyAnalysis:
    low = (reply_text or "").lower()
    pct_match = re.search(r"(\d{1,3})\s*%", low)
    has_sub_100_pct = bool(pct_match and int(pct_match.group(1)) < 100)
    is_done = not has_sub_100_pct and any(
        w in low
        for w in (
            "completed",
            "complete",
            "is done",
            "finished",
            "pushed",
            "merged",
            "deployed to staging",
            "all done",
            "ho gaya",
            "kar diya",
        )
    ) and not any(w in low for w in ("not completed", "not done", "almost done"))
    is_blocked = any(w in low for w in ("blocked", "stuck", "error", "denied", "failed", "waiting on"))
    if is_done:
        return CheckinReplyAnalysis(
            intent="COMPLETED",
            progress_pct=100,
            completed_milestones=reply_text.strip()[:240],
            blockers="None",
            commit_summary=f"feat(sprint): completed {task_title[:56]}",
        )
    if is_blocked:
        pct = int(pct_match.group(1)) if pct_match else 25
        return CheckinReplyAnalysis(
            intent="BLOCKED",
            progress_pct=min(99, pct),
            completed_milestones=reply_text.strip()[:200],
            blockers=reply_text.strip()[:200],
            commit_summary=f"wip(blocked): {task_title[:56]}",
        )
    pct = int(pct_match.group(1)) if pct_match else 60
    return CheckinReplyAnalysis(
        intent="IN_PROGRESS",
        progress_pct=max(5, min(95, pct)),
        completed_milestones=reply_text.strip()[:240],
        blockers="None",
        commit_summary=f"wip(sprint): {pct}% progress on {task_title[:50]}",
    )


def analyze_employee_reply(reply_text: str, task_title: str, is_demo: bool = False) -> CheckinReplyAnalysis:
    """Use evon_llm (Gemini 3 / Evon 30B) in live mode or deterministic classifier in DEMO_MODE."""
    settings = get_settings()
    delimited = wrap_untrusted_data("employee_status_reply", reply_text)
    parsed = structured_output(
        system_prompt=CHECKIN_ANALYSIS_PROMPT,
        user_prompt=f"Task Title: {task_title}\n\n{delimited}",
        schema=CheckinReplyAnalysis,
        temperature=0.1,
        force_demo=is_demo or settings.demo_mode,
    )
    if parsed is not None:
        return parsed
    return _deterministic_analyze_reply(reply_text, task_title)


def build_default_hitl_decisions(snap: Dict[str, Any]) -> Dict[str, str]:
    tasks = snap.get("tasks") or {}
    resolutions = {r["task_id"]: r for r in (snap.get("resolutions") or []) if r.get("task_id")}
    decisions: Dict[str, str] = {}
    for tid, task in tasks.items():
        suggested = (resolutions.get(tid) or {}).get("suggested_action") or task.get("resolution_action") or "PROCEED"
        if suggested == "PROCEED" and task.get("rerouted_assignee"):
            suggested = "REROUTE"
        decisions[tid] = str(suggested)
    return decisions


async def resume_graph_a_and_sync(
    thread_id: str,
    org_id: str,
    approver_user_id: str,
    hitl_decisions: Dict[str, str],
) -> Dict[str, Any]:
    """Resume Graph A off the event loop, schedule interval check-ins, and emit SSE updates."""
    config = {"configurable": {"thread_id": thread_id}}
    settings = get_settings()
    try:
        result: Any = None
        try:
            graph = get_graph_a()
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    graph.invoke,
                    Command(resume={"decisions": hitl_decisions, "approver_user_id": approver_user_id}),
                    config,
                ),
                timeout=6.0,
            )
        except Exception as graph_err:
            logger.warning(
                "Graph A resume failed or no paused checkpoint found (%s). Running direct dispatcher fallback...",
                graph_err,
            )
            # Direct dispatcher fallback using current snapshot
            existing_snap = get_thread_snapshot(thread_id) or {}
            tasks_map = dict(existing_snap.get("tasks") or {})
            for tid, dec in hitl_decisions.items():
                if tid in tasks_map:
                    t = dict(tasks_map[tid])
                    if dec == "DEFER":
                        t["status"] = "DEFERRED"
                    elif dec in ("PROCEED", "REROUTE"):
                        t["status"] = "READY"
                        if dec == "REROUTE" and not t.get("rerouted_assignee") and t.get("proposed_assignee"):
                            t["rerouted_assignee"] = t["proposed_assignee"]
                    tasks_map[tid] = t

            fallback_state: Dict[str, Any] = {
                "org_id": org_id,
                "meeting_id": existing_snap.get("meeting_id") or thread_id,
                "thread_id": thread_id,
                "tasks": tasks_map,
                "dispatched_tickets": existing_snap.get("dispatched_tickets", []),
                "approver_user_id": approver_user_id,
            }
            dispatch_out = await asyncio.to_thread(dispatcher_node, cast(Any, fallback_state))
            for tid, upd in (dispatch_out.get("tasks") or {}).items():
                if tid in tasks_map:
                    tasks_map[tid] = {**tasks_map[tid], **dict(upd)}
                else:
                    tasks_map[tid] = dict(upd)

            result = {
                **existing_snap,
                "tasks": tasks_map,
                "dispatched_tickets": dispatch_out.get("dispatched_tickets", []),
                "meeting_id": existing_snap.get("meeting_id") or thread_id,
            }

        res_dict: Dict[str, Any] = result if isinstance(result, dict) else {}
        dispatched = res_dict.get("dispatched_tickets", [])
        tasks_out = res_dict.get("tasks", {})
        meeting_id = res_dict.get("meeting_id", thread_id)
        existing_snap = get_thread_snapshot(thread_id) or {}
        next_checkin = time.time() + max(10, settings.checkin_interval_seconds)

        save_thread_snapshot(
            thread_id=thread_id,
            org_id=org_id,
            snapshot={
                "meeting_id": meeting_id,
                "title": res_dict.get("title") or existing_snap.get("title"),
                "phase": "COMPLETE",
                "tasks": tasks_out,
                "resolutions": res_dict.get("resolutions", []) or existing_snap.get("resolutions", []),
                "key_decisions": res_dict.get("key_decisions", []) or existing_snap.get("key_decisions", []),
                "meeting_context": res_dict.get("meeting_context", {}) or existing_snap.get("meeting_context", {}),
                "immediate_alerts": res_dict.get("immediate_alerts", []) or existing_snap.get("immediate_alerts", []),
                "dispatched_tickets": dispatched,
                "approver_user_id": approver_user_id,
                "manager_approved": True,
                "next_checkin_at": next_checkin,
                "slack_feed": list_slack_feed(org_id=org_id, thread_id=thread_id),
            },
        )

        # Close the manager review menu thread cleanly
        for st in list_open_slack_threads_all():
            if st.get("org_id") == org_id and st.get("thread_id") == thread_id and st.get("task_id") == "__MANAGER_REVIEW__":
                upsert_slack_thread(
                    org_id=org_id,
                    thread_id=thread_id,
                    task_id="__MANAGER_REVIEW__",
                    jira_key=None,
                    slack_channel=st["slack_channel"],
                    slack_thread_ts=st["slack_thread_ts"],
                    assignee="Manager",
                    turn_count=1,
                    status="DONE",
                )

        await sse_manager.push_event(
            thread_id,
            "dispatched",
            {
                "meeting_id": meeting_id,
                "approved_by": approver_user_id,
                "dispatched_tickets": dispatched,
                "tasks": tasks_out,
                "slack_feed": list_slack_feed(org_id=org_id, thread_id=thread_id),
                "message": f"{len(dispatched)} ticket(s) approved and dispatched.",
            },
            org_id=org_id,
        )
        await sse_manager.push_complete(thread_id, org_id=org_id)

        try:
            asyncio.create_task(_auto_checkin_scheduler(org_id, thread_id))
        except Exception as sched_exc:
            logger.warning("Failed to spawn _auto_checkin_scheduler: %s", sched_exc)

        return {"status": "dispatched", "dispatched_tickets": dispatched}
    except Exception as exc:
        logger.error("resume_graph_a_and_sync failed: %s", exc, exc_info=True)
        await sse_manager.push_error(thread_id, str(exc), org_id=org_id)
        raise


async def _auto_checkin_scheduler(org_id: str, thread_id: str) -> None:
    """Schedule automatic demo cadence check-ins: #1 after 20s, #2 after 30s more."""
    try:
        await asyncio.sleep(20)
        logger.info("Auto-checkin scheduler: triggering Check-In #1 for %s in org %s", thread_id, org_id)
        await trigger_checkin_for_thread(org_id=org_id, thread_id=thread_id)

        await asyncio.sleep(30)
        snap = get_thread_snapshot(thread_id) or {}
        tasks = snap.get("tasks") or {}
        has_open = any(t.get("status") != "DONE" for t in tasks.values())
        if has_open:
            logger.info("Auto-checkin scheduler: triggering Check-In #2 for %s in org %s", thread_id, org_id)
            await trigger_checkin_for_thread(org_id=org_id, thread_id=thread_id)
    except Exception as exc:
        logger.warning("Auto-checkin scheduler task failed for %s: %s", thread_id, exc)


async def trigger_checkin_for_thread(org_id: str, thread_id: str) -> Dict[str, Any]:
    """Send Stage-1 check-in DMs to each assigned employee for open tickets not yet started.

    State machine:
      checkin_stage == 0 → send Stage 1, set checkin_stage=1, awaiting_employee_reply=True
      checkin_stage == 1 and awaiting_employee_reply == True → skip (never double-send)
      checkin_stage >= 2 → skip (already in Stage 2 or completed)
    """
    snap = get_thread_snapshot(thread_id)
    if not snap or snap.get("org_id") != org_id:
        raise KeyError(f"Thread '{thread_id}' not found for org '{org_id}'.")

    tasks = dict(snap.get("tasks") or {})
    open_threads = {
        r["task_id"]: r
        for r in list_open_slack_threads_all()
        if r.get("org_id") == org_id and r.get("thread_id") == thread_id
    }

    slack_feed_msgs = list_slack_feed(org_id=org_id, thread_id=thread_id)
    sent_items: List[Dict[str, Any]] = []
    tasks_updated: Dict[str, Any] = {}

    for tid, task in tasks.items():
        task = dict(task)
        if task.get("status") == "DONE":
            continue
        if task.get("status") not in {"DISPATCHED", "OPEN", "BLOCKED"}:
            continue
        jira_key = task.get("jira_ticket_id") or task.get("jira_key")
        if not jira_key:
            continue

        checkin_stage = int(task.get("checkin_stage") or 0)
        awaiting_reply = bool(task.get("awaiting_employee_reply", False))

        # State-machine guard: skip if already awaiting employee reply (stage 1)
        if checkin_stage == 1 and awaiting_reply:
            logger.info(
                "trigger_checkin_for_thread: task %s is in stage 1 awaiting reply — skipping duplicate send.",
                tid,
            )
            continue
        # Skip if already at stage 2+
        if checkin_stage >= 2:
            logger.info(
                "trigger_checkin_for_thread: task %s already at stage %d — skipping.",
                tid, checkin_stage,
            )
            continue

        assignee = str(task.get("rerouted_assignee") or task.get("assignee") or "Engineer")
        raw_title = str(task.get("reframed_title") or task.get("title") or tid)
        title = raw_title
        if "elastic" in raw_title.lower():
            title = "Deploy Elasticsearch cluster to AWS production"
        elif "oauth" in raw_title.lower() or "auth" in raw_title.lower():
            title = "Build OAuth login dashboard"
        st = open_threads.get(tid) or {}

        prior_checkins = sum(
            1 for m in slack_feed_msgs
            if m.get("task_id") == tid and m.get("kind") == "checkin"
        )
        round_num = prior_checkins + 1

        # Rapid duplicate trigger guard (<10s)
        recent_checkin = False
        for m in reversed(slack_feed_msgs):
            if m.get("task_id") == tid and m.get("kind") == "checkin":
                ca = m.get("created_at")
                if ca:
                    try:
                        dt = datetime.fromisoformat(str(ca).replace("Z", "+00:00"))
                        if (datetime.now(timezone.utc) - dt).total_seconds() < 10.0:
                            recent_checkin = True
                    except Exception:
                        pass
                break
        if recent_checkin:
            logger.info("trigger_checkin_for_thread: checkin for task %s sent <10s ago, skipping duplicate.", tid)
            continue

        # Post Stage 1 checkin DM to employee
        ok, ch, ts = post_employee_checkin_dm(
            org_id=org_id,
            thread_id=thread_id,
            task_id=tid,
            assignee=assignee,
            jira_key=str(jira_key),
            task_title=title,
            channel_id=st.get("slack_channel"),
            thread_ts=st.get("slack_thread_ts"),
            checkin_round=round_num,
            domain_context=str(task.get("domain") or ""),
        )

        # Update task state machine fields
        task["checkin_stage"] = 1
        task["awaiting_employee_reply"] = True
        tasks_updated[tid] = task

        sent_items.append({
            "task_id": tid,
            "jira_key": jira_key,
            "assignee": assignee,
            "sent": ok,
            "slack_channel": ch,
            "slack_ts": ts,
            "checkin_stage": 1,
        })

    # Persist updated task states
    merged_tasks = dict(tasks)
    merged_tasks.update(tasks_updated)

    settings = get_settings()
    save_thread_snapshot(
        thread_id=thread_id,
        org_id=org_id,
        snapshot={
            **snap,
            "tasks": merged_tasks,
            "next_checkin_at": time.time() + max(10, settings.checkin_interval_seconds),
            "slack_feed": list_slack_feed(org_id=org_id, thread_id=thread_id),
        },
    )

    if sent_items:
        write_audit_trail(
            org_id=org_id,
            meeting_id=str(snap.get("meeting_id") or thread_id),
            thread_id=thread_id,
            event_type="CHECKIN_SENT",
            agent_node="sprint_checkin_scheduler",
            detail=f"Sent Stage-1 check-in DMs to {len(sent_items)} assignee(s).",
            provenance_tag="Interval Sprint Check-In Loop",
        )
        await sse_manager.push_event(
            thread_id,
            "tracker_update",
            {
                "source": "checkin_scheduler",
                "sent_checkins": sent_items,
                "tasks": merged_tasks,
                "dispatched_tickets": snap.get("dispatched_tickets", []),
                "slack_feed": list_slack_feed(org_id=org_id, thread_id=thread_id),
            },
            org_id=org_id,
        )

    return {"thread_id": thread_id, "checkins_sent": sent_items}


def notify_manager_employee_update(
    org_id: str,
    thread_id: str,
    employee_name: str,
    task: Dict[str, Any],
    update_text: str,
    source: str = "WorkOS Messages",
    intent: Optional[str] = None,
    progress_pct: Optional[int] = None,
    blockers: Optional[str] = None,
    jira_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Auto-push executive summary to Manager's veridian-bot thread and Slack DM."""
    tid = task.get("task_id") or "t1"
    jkey = jira_key or str(task.get("jira_ticket_id") or task.get("jira_key") or tid)
    raw_title = str(task.get("reframed_title") or task.get("title") or "Sprint Task")
    clean_title = clean_task_title(raw_title)

    if intent is None:
        analysis = analyze_employee_reply(update_text, clean_title, False)
        intent = analysis.intent
        if progress_pct is None:
            progress_pct = analysis.progress_pct
        if blockers is None:
            blockers = analysis.blockers

    pct = 100 if intent == "COMPLETED" else (progress_pct if progress_pct is not None else 0)

    if intent == "COMPLETED":
        summary_kind = "closure"
        prefix = f"[Task Completed — @{employee_name}]"
        mgr_text = (
            f"*{prefix}* [Task Completed] `{jkey}`: *{employee_name}* finished '{clean_title}'. "
            f"Jira ticket closed."
        )
    elif intent == "BLOCKED":
        summary_kind = "blocker_escalation"
        prefix = f"[Blocker Alert — @{employee_name}]"
        mgr_text = (
            f"*{prefix}* [URGENT BLOCKER ESCALATION] `{jkey}` (@{employee_name}):\n"
            f"• *Task:* {clean_title}\n"
            f"• *Blocker:* {blockers or update_text}"
        )
    else:
        summary_kind = "progress_digest"
        concise = update_text.strip().replace("\n", " ")[:140]
        src_tag = "Slack DM Summary" if "slack" in source.lower() else "WorkOS Messages Summary"
        prefix = f"[{src_tag} — @{employee_name}]"
        mgr_text = (
            f"*{prefix}* [Progress Digest] `{jkey}` (@{employee_name}): *{pct}% complete*\n"
            f"• *Task:* {clean_title}\n"
            f"• *Update:* \"{concise}\""
        )

    # In-App Manager Feed (stored under recipient="manager" so it reaches all manager keys)
    msg = record_slack_feed_message(
        org_id=org_id,
        thread_id="veridian-bot:manager",
        role="manager",
        sender="Veridian Bot",
        recipient="manager",
        text=mgr_text,
        kind=summary_kind,
        task_id=tid,
        jira_key=jkey,
        metadata={
            "type": "employee_summary",
            "employee": employee_name,
            "source": source,
            "progress_pct": pct,
            "task_title": clean_title,
            "blockers": blockers,
            "recipient_id": "manager:veridian-bot",
        },
    )

    # Also post to Manager via Slack DM if real credentials available
    try:
        if has_real_slack_creds():
            post_slack_message(
                org_id=org_id,
                thread_id=thread_id,
                role="manager",
                recipient="Manager",
                text=mgr_text,
                channel_kind="manager",
                task_id=tid,
                jira_key=jkey,
                kind=summary_kind,
                metadata={"source": source, "recipient_id": "manager:veridian-bot"},
            )
    except Exception as exc:
        logger.debug("notify_manager_employee_update: Slack DM post skipped: %s", exc)

    return msg


async def dispatch_stage_2_checkin(
    org_id: str,
    thread_id: str,
    task_id: str,
    assignee: str,
    jira_key: str,
    task_title: str,
    progress_pct: int = 0,
    delay_seconds: float = 2.5,
) -> None:
    """Send Stage 2 check-in question after employee reply and short delay."""
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)

    snap = get_thread_snapshot(thread_id)
    if not snap:
        return
    tasks_map = dict(snap.get("tasks") or {})
    task = dict(tasks_map.get(task_id) or {})

    # Guard: do not send Stage 2 if task is already completed (100% / DONE)
    if task.get("status") == "DONE" or int(task.get("checkin_stage") or 0) >= 3:
        logger.info("dispatch_stage_2_checkin: task %s is already DONE/stage 3 — skipping Stage 2.", task_id)
        return

    clean_title = clean_task_title(task_title or str(task.get("reframed_title") or task.get("title") or task_id))
    stage2_text = (
        f"Hi {assignee}, wrapping up for the day — did you finish {clean_title} ({jira_key}), "
        f"or is anything blocking you? Please share your latest progress % and any commit hashes or PR links."
    )

    emp_thread_key = canonical_employee_key(assignee)
    emp_vbot_thread = f"veridian-bot:{emp_thread_key}"
    record_slack_feed_message(
        org_id=org_id,
        thread_id=emp_vbot_thread,  # <-- route to employee's vbot thread
        role="bot",
        sender="Veridian Bot",
        recipient=emp_thread_key,
        text=stage2_text,
        kind="checkin",
        task_id=task_id,
        jira_key=jira_key,
        metadata={"checkin_stage": 2, "assignee": assignee},
    )
    # Also record to meeting thread so snapshot slack_feed stays consistent
    record_slack_feed_message(
        org_id=org_id,
        thread_id=thread_id,
        role="bot",
        sender="Veridian Bot",
        recipient=emp_thread_key,
        text=stage2_text,
        kind="checkin",
        task_id=task_id,
        jira_key=jira_key,
        metadata={"checkin_stage": 2, "assignee": assignee},
    )

    task["checkin_stage"] = 2
    task["awaiting_employee_reply"] = True
    tasks_map[task_id] = task

    save_thread_snapshot(
        thread_id=thread_id,
        org_id=org_id,
        snapshot={
            **snap,
            "tasks": tasks_map,
            "slack_feed": list_slack_feed(org_id=org_id, thread_id=thread_id),
        },
    )

    await sse_manager.push_event(
        thread_id,
        "tracker_update",
        {
            "source": "stage_2_checkin",
            "task_id": task_id,
            "jira_key": jira_key,
            "progress_pct": progress_pct,
            "tasks": tasks_map,
            "slack_feed": list_slack_feed(org_id=org_id, thread_id=thread_id),
        },
        org_id=org_id,
    )


async def process_employee_reply(
    org_id: str,
    thread_id: str,
    task_id: str,
    reply_text: str,
    source: str = "web_console",
    post_to_slack: bool = True,
    slack_channel: Optional[str] = None,
    slack_thread_ts: Optional[str] = None,
) -> Dict[str, Any]:
    """Process an employee status reply: extract progress/completion, update Jira, DM Manager."""
    snap = get_thread_snapshot(thread_id)
    if not snap or snap.get("org_id") != org_id:
        raise KeyError(f"Thread '{thread_id}' not found for org '{org_id}'.")

    tasks = {k: dict(v) for k, v in (snap.get("tasks") or {}).items()}
    task = tasks.get(task_id)
    if not task:
        raise KeyError(f"Task '{task_id}' not found in thread '{thread_id}'.")

    assignee = str(task.get("assignee") or "Employee")
    jira_key = str(task.get("jira_ticket_id") or task.get("jira_key") or "")
    jira_url = str(task.get("jira_url") or "")
    task_title = str(task.get("reframed_title") or task.get("title") or task_id)
    meeting_id = str(snap.get("meeting_id") or thread_id)

    if source == "web_console" and post_to_slack:
        post_slack_message(
            org_id=org_id,
            thread_id=thread_id,
            role="employee",
            recipient="Veridian Bot",
            text=f"[{assignee} via Employee Console on {jira_key or task_id}]: {reply_text}",
            channel_kind="summary",
            thread_ts=slack_thread_ts,
            target_channel_id=slack_channel,
            task_id=task_id,
            jira_key=jira_key or None,
            kind="employee_reply",
        )
    else:
        record_slack_feed_message(
            org_id=org_id,
            thread_id=thread_id,
            role="employee",
            sender=assignee,
            recipient="Veridian Bot",
            text=reply_text,
            slack_channel=slack_channel or "",
            slack_ts=slack_thread_ts or "",
            task_id=task_id,
            jira_key=jira_key or None,
            kind="employee_reply",
        )

    analysis = await asyncio.to_thread(analyze_employee_reply, reply_text, task_title, False)

    dispatched_list = [dict(d) for d in (snap.get("dispatched_tickets") or [])]
    evidence = extract_completion_evidence(reply_text)

    if analysis.intent == "COMPLETED" and evidence:
        commit_summary = analysis.commit_summary or f"feat(sprint): completed {task_title[:60]}"
        evidence_note = f"Evidence ({evidence['type']}): {evidence['value']}"
        jira_result = await asyncio.to_thread(
            transition_jira_issue_done,
            jira_key,
            f"Completed by {assignee} with verified evidence [{evidence_note}].\nCommit Summary: {commit_summary}\nUpdate: {reply_text}",
        )
        task["status"] = "DONE"
        task["jira_status"] = jira_result.get("status", "Done")
        task["progress_pct"] = 100
        task["checkin_stage"] = 3
        task["awaiting_employee_reply"] = False
        task["completed_milestones"] = analysis.completed_milestones
        task["blockers"] = "None"
        task["commit_summary"] = commit_summary
        task["completion_evidence"] = evidence
        tasks[task_id] = task

        notify_manager_employee_update(
            org_id=org_id,
            thread_id=thread_id,
            employee_name=assignee,
            task=task,
            update_text=reply_text,
            source="Slack DM" if "slack" in source.lower() else "WorkOS Messages",
            intent="COMPLETED",
            progress_pct=100,
            jira_key=jira_key or task_id,
        )

        for dt in dispatched_list:
            if dt.get("task_id") == task_id:
                dt["jira_status"] = task["jira_status"]
                dt["progress_pct"] = 100
                dt["commit_summary"] = commit_summary

        update_task_status_by_id(org_id=org_id, task_id=task_id, status="DONE", jira_key=jira_key or None)
        upsert_slack_thread(
            org_id=org_id,
            thread_id=thread_id,
            task_id=task_id,
            jira_key=jira_key or None,
            slack_channel=slack_channel or "summary",
            slack_thread_ts=slack_thread_ts or f"closed_{task_id}",
            assignee=assignee,
            turn_count=1,
            status="DONE",
        )
        post_closure_confirmation_dms(
            org_id=org_id,
            thread_id=thread_id,
            assignee=assignee,
            jira_key=jira_key or task_id,
            jira_url=jira_url,
            task_id=task_id,
            commit_summary=f"{commit_summary} ({evidence_note})",
        )
        write_audit_trail(
            org_id=org_id,
            meeting_id=meeting_id,
            thread_id=thread_id,
            task_id=task_id,
            event_type="TICKET_AUTO_CLOSED",
            agent_node="sprint_loop.process_employee_reply",
            detail=f"Auto-closed {jira_key} -> Done. Evidence ({evidence['type']}): {evidence['value']}. Actor: system",
            provenance_tag=f"Evidence-Based Auto-Close (actor=system, {source})",
        )
    elif analysis.intent == "COMPLETED" and not evidence:
        commit_summary = analysis.commit_summary or f"feat(sprint): completed {task_title[:60]}"
        task["status"] = "IN_REVIEW"
        task["jira_status"] = "In Review"
        task["progress_pct"] = 90
        task["completed_milestones"] = analysis.completed_milestones
        task["blockers"] = "Pending manager review (no PR/commit hash provided)"
        task["commit_summary"] = commit_summary
        tasks[task_id] = task

        for dt in dispatched_list:
            if dt.get("task_id") == task_id:
                dt["jira_status"] = "In Review"
                dt["progress_pct"] = 90
                dt["commit_summary"] = commit_summary

        if jira_key:
            try:
                await asyncio.to_thread(
                    add_jira_comment,
                    jira_key,
                    f"Completion claimed by {assignee} without direct commit/PR evidence.\nStatus moved to In Review pending Manager confirmation.\nUpdate: {reply_text}",
                )
            except Exception as exc:
                logger.warning("Jira In Review comment failed for %s: %s", jira_key, exc)

        update_task_status_by_id(org_id=org_id, task_id=task_id, status="IN_REVIEW", jira_key=jira_key or None)

        post_manager_review_request_dm(
            org_id=org_id,
            thread_id=thread_id,
            assignee=assignee,
            jira_key=jira_key or task_id,
            jira_url=jira_url,
            task_id=task_id,
            reply_text=reply_text,
            commit_summary=commit_summary,
        )
        write_audit_trail(
            org_id=org_id,
            meeting_id=meeting_id,
            thread_id=thread_id,
            task_id=task_id,
            event_type="COMPLETION_PENDING_REVIEW",
            agent_node="sprint_loop.process_employee_reply",
            detail=f"{jira_key} marked In Review (missing commit/PR evidence). Manager confirmation requested. Actor: system",
            provenance_tag=f"Non-Evidence Completion Review (actor=system, {source})",
        )
    else:
        new_status = "BLOCKED" if analysis.intent == "BLOCKED" else "DISPATCHED"
        comment_body = (
            f"Status Check-In Update ({analysis.progress_pct}%) from {assignee}:\n"
            f"- Completed: {analysis.completed_milestones}\n"
            f"- Blockers: {analysis.blockers or 'None'}"
        )
        if jira_key:
            try:
                await asyncio.to_thread(add_jira_comment, jira_key, comment_body)
            except Exception as exc:
                logger.warning("Jira progress comment failed for %s: %s", jira_key, exc)

        task["status"] = new_status
        task["progress_pct"] = analysis.progress_pct
        task["completed_milestones"] = analysis.completed_milestones
        task["blockers"] = analysis.blockers
        task["awaiting_employee_reply"] = False
        tasks[task_id] = task

        for dt in dispatched_list:
            if dt.get("task_id") == task_id:
                dt["progress_pct"] = analysis.progress_pct
                dt["jira_status"] = "Blocked" if new_status == "BLOCKED" else (dt.get("jira_status") or "To Do")

        if new_status == "BLOCKED":
            update_task_status_by_id(org_id=org_id, task_id=task_id, status="BLOCKED", jira_key=jira_key or None)
            post_manager_blocker_escalation_dm(
                org_id=org_id,
                thread_id=thread_id,
                assignee=assignee,
                jira_key=jira_key or task_id,
                task_id=task_id,
                task_title=task_title,
                blocker_text=analysis.blockers or reply_text,
            )

        post_manager_progress_digest(
            org_id=org_id,
            thread_id=thread_id,
            assignee=assignee,
            jira_key=jira_key or task_id,
            task_id=task_id,
            progress_pct=analysis.progress_pct,
            completed_milestones=analysis.completed_milestones,
            blockers=analysis.blockers,
            task_title=task_title,
        )
        notify_manager_employee_update(
            org_id=org_id,
            thread_id=thread_id,
            employee_name=assignee,
            task=task,
            update_text=reply_text,
            source="Slack DM" if "slack" in source.lower() else "WorkOS Messages",
            intent=analysis.intent,
            progress_pct=analysis.progress_pct,
            blockers=analysis.blockers,
            jira_key=jira_key or task_id,
        )
        try:
            asyncio.create_task(
                dispatch_stage_2_checkin(
                    org_id=org_id,
                    thread_id=thread_id,
                    task_id=task_id,
                    assignee=assignee,
                    jira_key=jira_key or task_id,
                    task_title=task_title,
                    progress_pct=analysis.progress_pct,
                    delay_seconds=2.5,
                )
            )
        except Exception as stage2_exc:
            logger.debug("dispatch_stage_2_checkin scheduling error: %s", stage2_exc)
        record_slack_feed_message(
            org_id=org_id,
            thread_id=thread_id,
            role="bot",
            sender="Veridian Bot",
            recipient=assignee,
            text=f"Got it! Logged {analysis.progress_pct}% progress on {jira_key or task_id} and notified your manager.",
            kind="bot_reply",
            task_id=task_id,
            jira_key=jira_key or None,
        )
        write_audit_trail(
            org_id=org_id,
            meeting_id=meeting_id,
            thread_id=thread_id,
            task_id=task_id,
            event_type="CHECKIN_PROGRESS_DIGEST",
            agent_node="sprint_loop.process_employee_reply",
            detail=f"{jira_key} {analysis.progress_pct}% ({analysis.intent})",
            provenance_tag=f"Employee Check-In ({source})",
        )

    save_thread_snapshot(
        thread_id=thread_id,
        org_id=org_id,
        snapshot={
            **snap,
            "tasks": tasks,
            "dispatched_tickets": dispatched_list,
            "slack_feed": list_slack_feed(org_id=org_id, thread_id=thread_id),
        },
    )
    await sse_manager.push_event(
        thread_id,
        "tracker_update",
        {
            "source": source,
            "task_id": task_id,
            "jira_key": jira_key,
            "intent": analysis.intent,
            "progress_pct": analysis.progress_pct,
            "jira_status": task.get("jira_status"),
            "commit_summary": task.get("commit_summary"),
            "tasks": tasks,
            "dispatched_tickets": dispatched_list,
            "slack_feed": list_slack_feed(org_id=org_id, thread_id=thread_id),
        },
        org_id=org_id,
    )

    return {
        "thread_id": thread_id,
        "task_id": task_id,
        "jira_key": jira_key,
        "analysis": analysis.model_dump(),
        "task": task,
        "dispatched_tickets": dispatched_list,
    }


async def confirm_task_completion_by_manager(
    org_id: str,
    thread_id: str,
    task_id: str,
    actor: str = "manager",
) -> Dict[str, Any]:
    """Manager explicitly confirms task completion, auto-closing Jira ticket to Done."""
    snap = get_thread_snapshot(thread_id)
    if not snap or snap.get("org_id") != org_id:
        raise KeyError(f"Thread '{thread_id}' not found for org '{org_id}'.")
    tasks = {k: dict(v) for k, v in (snap.get("tasks") or {}).items()}
    task = tasks.get(task_id)
    if not task:
        raise KeyError(f"Task '{task_id}' not found in thread '{thread_id}'.")

    assignee = str(task.get("assignee") or "Employee")
    jira_key = str(task.get("jira_ticket_id") or task.get("jira_key") or "")
    jira_url = str(task.get("jira_url") or "")
    commit_summary = str(task.get("commit_summary") or f"feat(sprint): confirmed {task_id}")
    meeting_id = str(snap.get("meeting_id") or thread_id)

    jira_result = await asyncio.to_thread(
        transition_jira_issue_done,
        jira_key,
        f"Completion confirmed by Manager ({actor}).\nCommit Summary: {commit_summary}",
    )
    task["status"] = "DONE"
    task["jira_status"] = jira_result.get("status", "Done")
    task["progress_pct"] = 100
    task["blockers"] = "None"
    tasks[task_id] = task

    dispatched_list = [dict(d) for d in (snap.get("dispatched_tickets") or [])]
    for dt in dispatched_list:
        if dt.get("task_id") == task_id:
            dt["jira_status"] = task["jira_status"]
            dt["progress_pct"] = 100

    update_task_status_by_id(org_id=org_id, task_id=task_id, status="DONE", jira_key=jira_key or None)
    post_closure_confirmation_dms(
        org_id=org_id,
        thread_id=thread_id,
        assignee=assignee,
        jira_key=jira_key or task_id,
        jira_url=jira_url,
        task_id=task_id,
        commit_summary=f"{commit_summary} (Confirmed by Manager)",
    )
    write_audit_trail(
        org_id=org_id,
        meeting_id=meeting_id,
        thread_id=thread_id,
        task_id=task_id,
        event_type="TICKET_MANAGER_CONFIRMED_DONE",
        agent_node="sprint_loop.confirm_task_completion_by_manager",
        detail=f"Manager {actor} confirmed completion of {jira_key} -> Done.",
        provenance_tag=f"Manager-Confirmed Completion (actor={actor})",
    )
    save_thread_snapshot(
        thread_id=thread_id,
        org_id=org_id,
        snapshot={
            **snap,
            "tasks": tasks,
            "dispatched_tickets": dispatched_list,
            "slack_feed": list_slack_feed(org_id=org_id, thread_id=thread_id),
        },
    )
    await sse_manager.push_event(
        thread_id,
        "tracker_update",
        {
            "source": "manager_confirmation",
            "task_id": task_id,
            "tasks": tasks,
            "dispatched_tickets": dispatched_list,
            "slack_feed": list_slack_feed(org_id=org_id, thread_id=thread_id),
        },
        org_id=org_id,
    )
    return {"status": "confirmed_done", "task_id": task_id, "jira_key": jira_key}


async def reject_task_completion_by_manager(
    org_id: str,
    thread_id: str,
    task_id: str,
    actor: str = "manager",
    reason: str = "Rework requested by Manager",
) -> Dict[str, Any]:
    """Manager rejects task completion, setting task back to DISPATCHED / In Progress."""
    snap = get_thread_snapshot(thread_id)
    if not snap or snap.get("org_id") != org_id:
        raise KeyError(f"Thread '{thread_id}' not found for org '{org_id}'.")
    tasks = {k: dict(v) for k, v in (snap.get("tasks") or {}).items()}
    task = tasks.get(task_id)
    if not task:
        raise KeyError(f"Task '{task_id}' not found in thread '{thread_id}'.")

    assignee = str(task.get("assignee") or "Employee")
    jira_key = str(task.get("jira_ticket_id") or task.get("jira_key") or "")
    meeting_id = str(snap.get("meeting_id") or thread_id)

    if jira_key:
        try:
            await asyncio.to_thread(
                add_jira_comment,
                jira_key,
                f"Completion review rejected by Manager ({actor}).\nReason: {reason}\nStatus reverted to In Progress.",
            )
        except Exception as exc:
            logger.warning("Jira rejection comment failed for %s: %s", jira_key, exc)

    task["status"] = "DISPATCHED"
    task["jira_status"] = "In Progress"
    task["progress_pct"] = 60
    task["blockers"] = reason
    tasks[task_id] = task

    dispatched_list = [dict(d) for d in (snap.get("dispatched_tickets") or [])]
    for dt in dispatched_list:
        if dt.get("task_id") == task_id:
            dt["jira_status"] = "In Progress"
            dt["progress_pct"] = 60

    update_task_status_by_id(org_id=org_id, task_id=task_id, status="DISPATCHED", jira_key=jira_key or None)

    rework_msg = f"*[Rework Requested]* `{jira_key}` needs additional work:\n• *Manager Feedback:* {reason}\nPlease update when ready."
    post_slack_message(
        org_id=org_id,
        thread_id=thread_id,
        role="employee",
        recipient=assignee,
        text=rework_msg,
        channel_kind="summary",
        task_id=task_id,
        jira_key=jira_key,
        kind="rework_request",
    )
    write_audit_trail(
        org_id=org_id,
        meeting_id=meeting_id,
        thread_id=thread_id,
        task_id=task_id,
        event_type="TICKET_COMPLETION_REJECTED",
        agent_node="sprint_loop.reject_task_completion_by_manager",
        detail=f"Manager {actor} rejected completion of {jira_key}. Reason: {reason}",
        provenance_tag=f"Manager-Rejected Completion (actor={actor})",
    )
    save_thread_snapshot(
        thread_id=thread_id,
        org_id=org_id,
        snapshot={
            **snap,
            "tasks": tasks,
            "dispatched_tickets": dispatched_list,
            "slack_feed": list_slack_feed(org_id=org_id, thread_id=thread_id),
        },
    )
    await sse_manager.push_event(
        thread_id,
        "tracker_update",
        {
            "source": "manager_rejection",
            "task_id": task_id,
            "tasks": tasks,
            "dispatched_tickets": dispatched_list,
            "slack_feed": list_slack_feed(org_id=org_id, thread_id=thread_id),
        },
        org_id=org_id,
    )
    return {"status": "rework_requested", "task_id": task_id, "jira_key": jira_key}


def _match_task_from_slack_message(text: str, open_rows: List[Dict[str, Any]], user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    low = (text or "").lower()
    for row in open_rows:
        jk = str(row.get("jira_key") or "").lower()
        if jk and jk in low:
            return row
    task_rows = [r for r in open_rows if r.get("task_id") not in {"__MANAGER_REVIEW__", None}]
    if user_id:
        user_clean = user_id.strip().upper()
        from connectors.slack_ops import resolve_slack_user_id
        for r in task_rows:
            assignee_low = str(r.get("assignee") or "").lower()
            matched_uid = resolve_slack_user_id(assignee_low, org_id=r.get("org_id"))
            if matched_uid and user_clean == matched_uid.strip().upper():
                return r
    return task_rows[0] if len(task_rows) == 1 else (task_rows[-1] if task_rows else None)


async def poll_slack_and_checkins_once() -> None:
    """Poll open live Slack conversations and trigger due interval check-ins."""
    settings = get_settings()
    open_threads = list_open_slack_threads_all()

    # 1. Interval check-ins for threads with open DISPATCHED tasks
    now = time.time()
    seen_threads: set[tuple[str, str]] = set()
    for st in open_threads:
        org_id = str(st.get("org_id") or "")
        tid = str(st.get("thread_id") or "")
        if not org_id or not tid or (org_id, tid) in seen_threads:
            continue
        seen_threads.add((org_id, tid))
        snap = get_thread_snapshot(tid)
        if not snap or snap.get("phase") != "COMPLETE":
            continue
        next_due = float(snap.get("next_checkin_at") or 0)
        if next_due and now >= next_due:
            has_open = any(t.get("status") == "DISPATCHED" for t in (snap.get("tasks") or {}).values())
            if has_open:
                await trigger_checkin_for_thread(org_id, tid)

    # 2. Live Slack conversations.history polling (if bot token active and live mode)
    if settings.demo_mode or not has_real_slack_creds():
        return

    channels: Dict[str, List[Dict[str, Any]]] = {}
    for st in open_threads:
        ch = str(st.get("slack_channel") or "")
        if ch and not ch.startswith("#"):
            channels.setdefault(ch, []).append(st)

    if not channels:
        return

    from slack_sdk import WebClient

    client = WebClient(token=settings.slack_bot_token)
    for ch_id, rows in list(channels.items())[:20]:
        if now < _CHANNEL_BACKOFF.get(ch_id, 0.0):
            logger.debug("Slack poller throttled on channel %s; backing off...", ch_id)
            continue
        try:
            oldest = _LAST_CHANNEL_CHECK_TS.get(ch_id)
            kwargs: Dict[str, Any] = {"channel": ch_id, "limit": 10}
            if oldest:
                kwargs["oldest"] = oldest
            resp = await asyncio.to_thread(client.conversations_history, **kwargs)
            messages = list(reversed(resp.get("messages") or []))
            for msg in messages:
                ts = str(msg.get("ts") or "")
                if not ts:
                    continue
                _LAST_CHANNEL_CHECK_TS[ch_id] = ts
                if (ch_id, ts) in _SEEN_SLACK_TS:
                    continue
                _SEEN_SLACK_TS.add((ch_id, ts))
                if msg.get("bot_id") or msg.get("subtype") == "bot_message":
                    continue
                text = str(msg.get("text") or "").strip()
                if not text:
                    continue

                # Check if Manager replied "approve" to a paused HITL thread
                mgr_row = next((r for r in rows if r.get("task_id") == "__MANAGER_REVIEW__"), None)
                if mgr_row and text.lower() in {"approve", "approved", "lgtm", "yes", "approve all"}:
                    m_org = mgr_row["org_id"]
                    m_tid = mgr_row["thread_id"]
                    snap = get_thread_snapshot(m_tid)
                    if snap and snap.get("phase") == "HITL":
                        decisions = build_default_hitl_decisions(snap)
                        approver = f"slack:{msg.get('user') or 'manager'}"
                        record_approval(m_org, m_tid, snap.get("meeting_id") or m_tid, decisions, approver)
                        await resume_graph_a_and_sync(m_tid, m_org, approver, decisions)
                        continue

                target_row = _match_task_from_slack_message(text, rows, user_id=msg.get("user"))
                if target_row and target_row.get("task_id"):
                    await process_employee_reply(
                        org_id=target_row["org_id"],
                        thread_id=target_row["thread_id"],
                        task_id=target_row["task_id"],
                        reply_text=text,
                        source="slack",
                        post_to_slack=False,
                        slack_channel=ch_id,
                        slack_thread_ts=str(msg.get("thread_ts") or target_row.get("slack_thread_ts") or ts),
                    )
        except Exception as exc:
            err_str = str(exc).lower()
            if "ratelimited" in err_str or "429" in err_str:
                retry_after = 15.0
                _CHANNEL_BACKOFF[ch_id] = now + min(retry_after, 60.0)
                logger.warning("Slack poller rate-limited on channel %s: backing off for %ss", ch_id, retry_after)
            else:
                logger.debug("Slack poller cycle note on channel %s: %s", ch_id, exc)

