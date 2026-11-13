"""Org-scoped, role-aware unified Messages & Slack sync routes (/api/messages)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import AuthContext, require_auth
from api.sse import sse_manager
from connectors.jira_ops import add_jira_comment, transition_jira_issue_done
from connectors.slack_ops import get_slack_dm_link, has_real_slack_creds, post_slack_message, send_direct_slack_dm
from connectors.sprint_loop import (
    _deterministic_analyze_reply,
    build_default_hitl_decisions,
    extract_completion_evidence,
    process_employee_reply,
    record_slack_feed_message,
    resume_graph_a_and_sync,
    trigger_checkin_for_thread,
)
from core.store import (
    get_thread_snapshot,
    get_unread_message_counts,
    list_direct_messages,
    list_employees,
    list_slack_feed,
    list_slack_feed_for_org,
    list_thread_snapshots,
    mark_channel_read,
    record_approval,
    record_direct_message,
    save_thread_snapshot,
    update_task_status_by_id,
)

logger = logging.getLogger(__name__)
router = APIRouter()

STALE_PERSONAS = {
    "jason yavorska",
    "josh lambert",
    "aarav sharma",
    "rohan patel",
    "priya sen",
    "dov hershkovitz",
    "scott williamson",
    "amit sharma",
    "gabe weaver",
}


def _filter_and_normalize_employees(employees: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter out stale legacy demo personas and enforce the strict 4-person team roster with correct roles."""
    filtered: List[Dict[str, Any]] = []
    for emp in employees:
        fn = str(emp.get("full_name") or emp.get("name") or "").strip()
        fn_low = fn.lower()
        if fn_low in STALE_PERSONAS:
            continue
        item = dict(emp)
        item["full_name"] = fn

        # Normalize roles and statuses
        if "catchme" in fn_low:
            item["role"] = "Backend Engineer"
            item["status"] = "ACTIVE"
            item["hr_status"] = "ACTIVE"
            item["department"] = item.get("department") or "Platform Engineering"
        elif "hanu" in fn_low:
            item["role"] = "Engineering Manager"
            item["status"] = "ACTIVE"
            item["hr_status"] = "ACTIVE"
            item["department"] = item.get("department") or "Engineering Leadership"
        elif "resigo" in fn_low:
            item["role"] = "Frontend Engineer"
            item["status"] = "ACTIVE"
            item["hr_status"] = "ACTIVE"
            item["department"] = item.get("department") or "Product & Frontend Engineering"
        elif "arjun" in fn_low:
            item["role"] = "Backend Engineer"
            item["status"] = "ON_PATERNITY_LEAVE"
            item["hr_status"] = "ON_PATERNITY_LEAVE"
            item["department"] = item.get("department") or "Platform Engineering"

        filtered.append(item)

    return filtered if filtered else employees


class MessageSendRequest(BaseModel):
    text: str
    task_id: Optional[str] = None
    thread_id: Optional[str] = None


def _find_matching_employee(employees: List[Dict[str, Any]], user_id: str, email: Optional[str]) -> Optional[Dict[str, Any]]:
    uid_clean = (user_id or "").strip().lower()
    em_clean = (email or "").strip().lower()

    for emp in employees:
        ck = str(emp.get("clerk_user_id") or "").strip().lower()
        em = str(emp.get("email") or "").strip().lower()
        if ck and ck == uid_clean:
            return emp
        if em and em_clean and em == em_clean:
            return emp
    return None


def _get_latest_thread(org_id: str, requested_tid: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if requested_tid:
        snap = get_thread_snapshot(requested_tid)
        if snap and snap.get("org_id") == org_id:
            return snap
    recent = list_thread_snapshots(org_id)
    return recent[0] if recent else None


def _resolve_user_display_name(emp: Optional[Dict[str, Any]], fallback: str) -> str:
    if emp and emp.get("full_name"):
        return str(emp["full_name"])
    return fallback


@router.get("/messages/unread")
async def get_unread_counts_endpoint(
    auth: AuthContext = Depends(require_auth),
) -> Dict[str, Any]:
    """Return total and per-channel unread message counts for the authenticated user."""
    is_manager = auth.role == "org:admin"
    employees = _filter_and_normalize_employees(list_employees(auth.org_id))
    current_emp = _find_matching_employee(employees, auth.user_id, auth.email)
    emp_name = current_emp.get("full_name") if current_emp else None

    counts = get_unread_message_counts(
        org_id=auth.org_id,
        user_id=auth.user_id,
        is_manager=is_manager,
        user_name=emp_name,
        user_email=auth.email,
    )
    return counts


@router.get("/messages/threads")
async def list_message_threads(
    auth: AuthContext = Depends(require_auth),
) -> Dict[str, Any]:
    """Return role-scoped conversation list (Veridian Bot + DMs) for the authenticated Clerk user."""
    is_manager = auth.role == "org:admin"
    employees = _filter_and_normalize_employees(list_employees(auth.org_id))
    current_emp = _find_matching_employee(employees, auth.user_id, auth.email)
    current_name: str = _resolve_user_display_name(current_emp, "Manager" if is_manager else "Employee")

    latest_snap = _get_latest_thread(auth.org_id)
    tasks_map = (latest_snap or {}).get("tasks") or {}
    dispatched_list = (latest_snap or {}).get("dispatched_tickets") or []

    unread_info = get_unread_message_counts(
        org_id=auth.org_id,
        user_id=auth.user_id,
        is_manager=is_manager,
        user_name=current_name,
        user_email=auth.email,
    )
    by_channel = unread_info.get("by_channel", {})

    is_sprint_approved = bool(
        latest_snap
        and (latest_snap.get("manager_approved") is True or latest_snap.get("phase") == "COMPLETE")
        and dispatched_list
    )

    def _find_emp_ticket(emp: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not is_sprint_approved:
            return None

        name_low = str(emp.get("full_name") or "").lower()
        for d in dispatched_list:
            a = str(d.get("assignee") or "").lower()
            if (name_low and name_low in a) or (a and a in name_low):
                j_key = d.get("jira_key") or d.get("jira_ticket_id")
                if not j_key:
                    continue
                tid = d.get("task_id")
                live_task = tasks_map.get(tid) if tid else None
                status_val = (live_task or {}).get("jira_status") or d.get("jira_status") or "To Do"
                pct_val = (live_task or {}).get("progress_pct") if live_task and "progress_pct" in live_task else d.get("progress_pct")
                return {
                    "key": str(j_key),
                    "title": (live_task or {}).get("reframed_title") or (live_task or {}).get("title") or d.get("title") or "Sprint Action Item",
                    "status": status_val,
                    "progress_pct": int(pct_val or 0),
                    "jira_url": d.get("jira_url"),
                    "task_id": tid,
                }
        return None

    threads: List[Dict[str, Any]] = []

    # 1. Veridian Bot (always first)
    bot_deep_link = get_slack_dm_link()
    threads.append({
        "channel_key": "veridian-bot",
        "title": "Veridian Bot",
        "subtitle": "Sprint Governance & Compliance Engine" if is_manager else "Personal Sprint Assistant",
        "role": "bot",
        "badge": "Verified Bot",
        "unread_count": by_channel.get("veridian-bot", 0),
        "slack_deep_link": bot_deep_link,
        "active_ticket": _find_emp_ticket(current_emp) if not is_manager and current_emp else None,
    })

    manager_emp = next((e for e in employees if "manager" in str(e.get("role") or "").lower()), None)
    if not manager_emp and employees:
        manager_emp = employees[0]

    if is_manager:
        # Manager sees 1-on-1 channels with team members
        for emp in employees:
            if current_emp and emp.get("id") == current_emp.get("id"):
                continue
            if emp.get("clerk_user_id") and emp.get("clerk_user_id") == auth.user_id:
                continue
            if "manager" in str(emp.get("role") or "").lower() and "hanu" in str(emp.get("full_name") or "").lower():
                continue
            emp_key = f"emp:{emp.get('id') or emp['full_name'].lower().replace(' ', '_')}"
            slack_uid = emp.get("slack_id") or emp.get("slack_user_id")
            ticket = _find_emp_ticket(emp)
            emp_hr = emp.get("hr_status") or emp.get("status") or "ACTIVE"
            is_on_leave = "leave" in emp_hr.lower()
            threads.append({
                "channel_key": emp_key,
                "title": emp["full_name"],
                "subtitle": emp.get("role") or "Engineer",
                "role": "employee",
                "hr_status": emp_hr,
                "status": "ON_LEAVE" if is_on_leave else (ticket.get("status") if ticket else "IDLE"),
                "ticket_key": ticket.get("key") if ticket else None,
                "progress_pct": ticket.get("progress_pct", 0) if ticket else 0,
                "department": emp.get("department") or "Engineering",
                "slack_user_id": slack_uid,
                "slack_deep_link": get_slack_dm_link(slack_uid),
                "jira_account_id": emp.get("jira_account_id"),
                "unread_count": by_channel.get(emp_key, 0),
                "active_ticket": ticket,
                "member": {
                    "id": emp.get("id"),
                    "name": emp["full_name"],
                    "email": emp.get("email"),
                    "role": emp.get("role"),
                    "hr_status": emp_hr,
                    "domain_skills": emp.get("domain_skills", []),
                },
            })
    else:
        # Employee sees channel with Manager
        if manager_emp:
            mgr_key = f"mgr:{manager_emp.get('id') or 'manager'}"
            mgr_slack_uid = manager_emp.get("slack_id")
            threads.append({
                "channel_key": mgr_key,
                "title": manager_emp["full_name"],
                "subtitle": manager_emp.get("role") or "Engineering Manager",
                "role": "manager",
                "hr_status": "ACTIVE",
                "status": "ACTIVE",
                "ticket_key": None,
                "progress_pct": 0,
                "slack_user_id": mgr_slack_uid,
                "slack_deep_link": get_slack_dm_link(mgr_slack_uid),
                "unread_count": by_channel.get(mgr_key, 0),
                "member": {
                    "name": manager_emp["full_name"],
                    "email": manager_emp.get("email"),
                    "role": manager_emp.get("role") or "Engineering Manager",
                    "hr_status": "ACTIVE",
                },
            })
        # Employee sees peer channels with other teammates
        for peer in employees:
            if current_emp and peer.get("id") == current_emp.get("id"):
                continue
            if manager_emp and peer.get("id") == manager_emp.get("id"):
                continue
            peer_key = f"peer:{peer.get('id') or peer['full_name'].lower().replace(' ', '_')}"
            peer_slack_uid = peer.get("slack_id")
            ticket = _find_emp_ticket(peer)
            peer_hr = peer.get("hr_status") or peer.get("status") or "ACTIVE"
            peer_on_leave = "leave" in peer_hr.lower()
            threads.append({
                "channel_key": peer_key,
                "title": peer["full_name"],
                "subtitle": peer.get("role") or "Engineer",
                "role": "peer",
                "hr_status": peer_hr,
                "status": "ON_LEAVE" if peer_on_leave else (ticket.get("status") if ticket else "IDLE"),
                "ticket_key": ticket.get("key") if ticket else None,
                "progress_pct": ticket.get("progress_pct", 0) if ticket else 0,
                "slack_user_id": peer_slack_uid,
                "slack_deep_link": get_slack_dm_link(peer_slack_uid),
                "unread_count": by_channel.get(peer_key, 0),
                "active_ticket": ticket,
                "member": {
                    "id": peer.get("id"),
                    "name": peer["full_name"],
                    "email": peer.get("email"),
                    "role": peer.get("role"),
                    "hr_status": peer_hr,
                },
            })

    return {
        "org_id": auth.org_id,
        "is_manager": is_manager,
        "user_id": auth.user_id,
        "current_user_name": current_name,
        "threads": threads,
        "active_thread_id": latest_snap.get("thread_id") if latest_snap else None,
    }


@router.get("/messages/{channel_key}")
async def get_channel_messages(
    channel_key: str,
    thread_id: Optional[str] = None,
    auth: AuthContext = Depends(require_auth),
) -> Dict[str, Any]:
    """Fetch chronological message stream for a channel and mark it read."""
    is_manager = auth.role == "org:admin"
    employees = _filter_and_normalize_employees(list_employees(auth.org_id))
    current_emp = _find_matching_employee(employees, auth.user_id, auth.email)
    current_name: str = _resolve_user_display_name(current_emp, "Manager" if is_manager else "Employee")

    mark_channel_read(auth.org_id, auth.user_id, channel_key)

    messages: List[Dict[str, Any]] = []
    slack_deep_link = "https://app.slack.com/client"

    if channel_key == "veridian-bot":
        feed = list_slack_feed_for_org(auth.org_id)
        if not feed and thread_id:
            snap = get_thread_snapshot(thread_id)
            feed = list((snap or {}).get("slack_feed") or [])

        name_low = current_name.lower()
        email_low = (auth.email or "").lower()

        for m in feed:
            kind = m.get("kind")
            role = m.get("role")
            rcp = str(m.get("recipient") or "")
            snd = str(m.get("sender") or "")

            if is_manager:
                # Manager sees governance alerts, review menus, progress digests, blocker escalations, and bot command responses
                # Exclude individual employee 1-on-1 checkin prompts and assignments
                if kind in {"checkin", "assignment"} and rcp not in {"Manager", "All"}:
                    continue
                if kind == "employee_reply":
                    # Employee replies are summarized into progress digests or blocker escalations for the manager
                    continue

                if (
                    role == "manager"
                    or kind in {
                        "alert",
                        "compliance_alert",
                        "review_menu",
                        "progress_digest",
                        "blocker_escalation",
                        "closure",
                        "closure_confirmation",
                        "completion_review",
                        "rework_request",
                        "manager_command",
                        "bot_command_response",
                    }
                    or (role == "bot" and rcp in {"Manager", "All", current_name})
                    or rcp in {"Manager", "All"}
                    or (m.get("metadata") or {}).get("recipient_id") in {"manager:veridian-bot", auth.user_id}
                ):
                    messages.append(m)
            else:
                # Employee sees ONLY their 1-on-1 check-ins, assignments, and replies
                if kind in {"review_menu", "compliance_alert", "blocker_escalation", "progress_digest"}:
                    continue
                rcp_low = rcp.lower()
                snd_low = snd.lower()
                if (
                    (name_low and (name_low in rcp_low or name_low in snd_low))
                    or (email_low and email_low in rcp_low)
                    or (rcp_low == "all")
                ):
                    messages.append(m)

        slack_deep_link = get_slack_dm_link(current_emp.get("slack_id") if current_emp else None)

    else:
        # Direct message channel (emp:..., mgr:..., peer:...)
        raw_dm = list_direct_messages(auth.org_id, channel_key)
        messages.extend(raw_dm)

        # Lookup recipient's Slack ID for deep link
        target_slack_id = None
        for emp in employees:
            emp_key_token = emp.get("id") or emp["full_name"].lower().replace(" ", "_")
            if emp_key_token in channel_key:
                target_slack_id = emp.get("slack_id")
                break
        slack_deep_link = get_slack_dm_link(target_slack_id)

    return {
        "channel_key": channel_key,
        "messages": messages,
        "slack_deep_link": slack_deep_link,
        "count": len(messages),
    }


@router.post("/messages/{channel_key}")
async def send_channel_message(
    channel_key: str,
    body: MessageSendRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_auth),
) -> Dict[str, Any]:
    """Send a message to Veridian Bot or a teammate, syncing with Slack and Jira execution."""
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message text is required.")

    text_clean = body.text.strip()
    is_manager = auth.role == "org:admin"
    employees = _filter_and_normalize_employees(list_employees(auth.org_id))
    current_emp = _find_matching_employee(employees, auth.user_id, auth.email)
    current_name: str = _resolve_user_display_name(current_emp, "Manager" if is_manager else "Employee")

    latest_snap = _get_latest_thread(auth.org_id, body.thread_id)
    target_thread_id = (latest_snap or {}).get("thread_id") or body.thread_id or "live-sprint-sync"

    if channel_key == "veridian-bot":
        if not is_manager:
            # Employee messaging Veridian Bot: Instant response pipeline (<300ms)
            target_task_id = body.task_id
            tasks_map = dict((latest_snap or {}).get("tasks") or {})
            if not target_task_id and latest_snap:
                name_low = current_name.lower()
                for tid, t in tasks_map.items():
                    a = str(t.get("rerouted_assignee") or t.get("assignee") or "").lower()
                    if name_low in a or a in name_low:
                        target_task_id = tid
                        break
                if not target_task_id and tasks_map:
                    target_task_id = next(iter(tasks_map.keys()))

            if not target_task_id:
                target_task_id = "t1"

            task = dict(tasks_map.get(target_task_id) or {})
            task_title = str(task.get("reframed_title") or task.get("title") or "Sprint Task")
            jira_key = str(task.get("jira_ticket_id") or task.get("jira_key") or target_task_id)

            # 1. Instant deterministic parsing (zero LLM wait)
            analysis = _deterministic_analyze_reply(text_clean, task_title)
            evidence = extract_completion_evidence(text_clean)

            # 2. Formulate immediate messages
            if analysis.intent == "COMPLETED":
                bot_emp_reply = f"Completed! Your task '{task_title}' ({jira_key}) is marked complete in Jira and your manager has been notified."
                mgr_summary_text = (
                    f"*[Task Completed]* `{jira_key}` ({task_title}) for *{current_name}* has been marked 100% complete.\n"
                    f"• *Update:* \"{text_clean}\"\n"
                    f"• *Status:* Jira ticket closed automatically."
                )
                new_status = "DONE"
                new_progress = 100
                new_jira_status = "Done"
            elif analysis.intent == "BLOCKED":
                bot_emp_reply = f"Logged blocker on {jira_key} ({task_title}): '{analysis.blockers or text_clean}'. Your manager has been escalated."
                mgr_summary_text = (
                    f"*[URGENT BLOCKER ESCALATION]* `{jira_key}` (@{current_name}):\n"
                    f"• *Task:* {task_title}\n"
                    f"• *Blocker:* {analysis.blockers or text_clean}"
                )
                new_status = "BLOCKED"
                new_progress = analysis.progress_pct
                new_jira_status = "Blocked"
            else:
                bot_emp_reply = f"Got it! Logged {analysis.progress_pct}% progress on {jira_key} ({task_title}) and notified your manager."
                mgr_summary_text = (
                    f"*[Progress Digest]* `{jira_key}` (@{current_name}): *{analysis.progress_pct}% complete*\n"
                    f"• *Completed:* {analysis.completed_milestones or text_clean}\n"
                    f"• *Blockers:* {analysis.blockers or 'None'}"
                )
                new_status = "DISPATCHED"
                new_progress = analysis.progress_pct
                new_jira_status = task.get("jira_status") or "In Progress"

            # 3. Persist ALL 3 records immediately
            # Record 1: Outgoing employee message in Employee's veridian-bot thread
            record_slack_feed_message(
                org_id=auth.org_id,
                thread_id=target_thread_id,
                role="employee",
                sender=current_name,
                recipient="Veridian Bot",
                text=text_clean,
                kind="employee_reply",
                task_id=target_task_id,
                jira_key=jira_key,
            )

            # Record 2: Veridian Bot's immediate reply to Employee
            record_slack_feed_message(
                org_id=auth.org_id,
                thread_id=target_thread_id,
                role="bot",
                sender="Veridian Bot",
                recipient=current_name,
                text=bot_emp_reply,
                kind="bot_reply",
                task_id=target_task_id,
                jira_key=jira_key,
            )

            # Record 3: Executive Summary Card for Manager
            summary_kind = "closure" if analysis.intent == "COMPLETED" else ("blocker_escalation" if analysis.intent == "BLOCKED" else "progress_digest")
            record_slack_feed_message(
                org_id=auth.org_id,
                thread_id=target_thread_id,
                role="manager",
                sender="Veridian Bot",
                recipient="Manager",
                text=mgr_summary_text,
                kind=summary_kind,
                task_id=target_task_id,
                jira_key=jira_key,
                metadata={
                    "progress_pct": new_progress,
                    "assignee": current_name,
                    "task_title": task_title,
                    "blockers": analysis.blockers,
                    "recipient_id": "manager:veridian-bot",
                },
            )

            # 4. Update task state in memory & DB
            task["status"] = new_status
            task["progress_pct"] = new_progress
            task["jira_status"] = new_jira_status
            task["completed_milestones"] = analysis.completed_milestones
            task["blockers"] = analysis.blockers
            tasks_map[target_task_id] = task

            dispatched_list = [dict(d) for d in ((latest_snap or {}).get("dispatched_tickets") or [])]
            for dt in dispatched_list:
                if dt.get("task_id") == target_task_id:
                    dt["progress_pct"] = new_progress
                    dt["jira_status"] = new_jira_status

            update_task_status_by_id(
                org_id=auth.org_id,
                task_id=target_task_id,
                status=new_status,
                jira_key=jira_key,
            )

            save_thread_snapshot(
                thread_id=target_thread_id,
                org_id=auth.org_id,
                snapshot={
                    **(latest_snap or {}),
                    "tasks": tasks_map,
                    "dispatched_tickets": dispatched_list,
                    "slack_feed": list_slack_feed(org_id=auth.org_id, thread_id=target_thread_id),
                },
            )

            # 5. Push SSE update
            await sse_manager.push_event(
                target_thread_id,
                "tracker_update",
                {
                    "source": "web_messages",
                    "task_id": target_task_id,
                    "jira_key": jira_key,
                    "intent": analysis.intent,
                    "progress_pct": new_progress,
                    "tasks": tasks_map,
                    "dispatched_tickets": dispatched_list,
                    "slack_feed": list_slack_feed(org_id=auth.org_id, thread_id=target_thread_id),
                },
                org_id=auth.org_id,
            )

            # 6. Run background Jira & Slack async sync
            def _bg_sync():
                try:
                    if analysis.intent == "COMPLETED":
                        transition_jira_issue_done(jira_key, f"Completed by {current_name}: {text_clean}")
                    else:
                        add_jira_comment(jira_key, f"Progress update ({new_progress}%) from {current_name}: {text_clean}")
                except Exception as sync_exc:
                    logger.warning("Background Jira sync error: %s", sync_exc)

                try:
                    if has_real_slack_creds():
                        post_slack_message(
                            org_id=auth.org_id,
                            thread_id=target_thread_id,
                            role="employee",
                            recipient="Veridian Bot",
                            text=f"[{current_name} via Veridian Messages on {jira_key}]: {text_clean}",
                            task_id=target_task_id,
                            jira_key=jira_key,
                        )
                except Exception as slack_exc:
                    logger.warning("Background Slack post error: %s", slack_exc)

            background_tasks.add_task(_bg_sync)

            return {
                "status": "processed",
                "channel_key": channel_key,
                "role": "employee",
                "intent": analysis.intent,
                "progress_pct": new_progress,
                "bot_reply": bot_emp_reply,
            }
        else:
            # Manager messaging Veridian Bot: Natural language command interface!
            cmd_low = text_clean.lower()

            record_slack_feed_message(
                org_id=auth.org_id,
                thread_id=target_thread_id,
                role="manager",
                sender=current_name,
                recipient="Veridian Bot",
                text=text_clean,
                kind="manager_command",
            )

            bot_reply = ""
            if any(k in cmd_low for k in ("check in", "check-in", "checkin", "ping", "trigger check")):
                checkin_res = await trigger_checkin_for_thread(auth.org_id, target_thread_id)
                cnt = len(checkin_res.get("checkins_sent", []))
                bot_reply = f"Initiated 1-on-1 sprint interval check-ins ({cnt} employee DMs sent via Slack)."
            elif any(k in cmd_low for k in ("approve", "approve all", "proceed", "lgtm", "create tickets")):
                snap = get_thread_snapshot(target_thread_id)
                if snap and snap.get("phase") == "HITL":
                    decisions = build_default_hitl_decisions(snap)
                    approver = f"clerk:{auth.user_id}"
                    record_approval(auth.org_id, target_thread_id, snap.get("meeting_id") or target_thread_id, decisions, approver)
                    await resume_graph_a_and_sync(target_thread_id, auth.org_id, approver, decisions)
                    bot_reply = "Approved all sprint governance gates. Provisioned Jira tickets and dispatched employee Slack DMs."
                else:
                    bot_reply = "Sprint tickets have already been approved and dispatched to Jira."
            elif any(k in cmd_low for k in ("status", "progress", "how much has", "sprint status", "summary", "how is")):
                # Live sprint status query
                snap = latest_snap or get_thread_snapshot(target_thread_id) or {}
                tasks = snap.get("tasks") or {}
                target_person = None
                for emp in employees:
                    if emp["full_name"].lower() in cmd_low or (emp.get("id") and emp["id"].lower() in cmd_low):
                        target_person = emp
                        break

                if target_person:
                    p_name = target_person["full_name"]
                    p_tasks = [
                        t for t in tasks.values()
                        if p_name.lower() in str(t.get("rerouted_assignee") or t.get("assignee") or "").lower()
                    ]
                    if p_tasks:
                        lines = [f"*Sprint Status for {p_name}:*"]
                        for t in p_tasks:
                            jkey = t.get("jira_ticket_id") or t.get("jira_key") or "TICKET"
                            ttitle = t.get("reframed_title") or t.get("title") or t.get("task_id")
                            pct = t.get("progress_pct", 0)
                            st = t.get("status", "OPEN")
                            blk = t.get("blockers") or "None"
                            lines.append(f"• `{jkey}` ({ttitle}): *{pct}% complete* (`{st}`)")
                            if blk and blk != "None":
                                lines.append(f"  > Blocker: {blk}")
                        bot_reply = "\n".join(lines)
                    else:
                        bot_reply = f"No active sprint tasks currently assigned to {p_name}."
                else:
                    if tasks:
                        lines = ["*Current Sprint Progress Summary:*"]
                        for tid, t in tasks.items():
                            assignee = t.get("rerouted_assignee") or t.get("assignee") or "Unassigned"
                            jkey = t.get("jira_ticket_id") or t.get("jira_key") or tid
                            ttitle = t.get("reframed_title") or t.get("title") or tid
                            pct = t.get("progress_pct", 0)
                            st = t.get("status", "OPEN")
                            blk = t.get("blockers") or "None"
                            lines.append(f"• `{jkey}` (*{assignee}*): *{pct}%* (`{st}`) — {ttitle}")
                            if blk and blk != "None":
                                lines.append(f"  > Blocker: {blk}")
                        bot_reply = "\n".join(lines)
                    else:
                        bot_reply = "No active sprint tasks found for the current sprint."
            elif any(k in cmd_low for k in ("rule", "policy", "policies", "sec-pol", "budget", "leave", "compliance")):
                bot_reply = (
                    "*Veridian Sprint Governance & Engineering Policies:*\n\n"
                    "• *SEC-POL-089 (Staging Bake Requirement):* All production deployments require a minimum 14-day staging bake. "
                    "Zero-day deployments to production are strictly blocked by the Veridian Governance Firewall.\n\n"
                    "• *SEC-POL-104 (Third-Party API Deprecation):* Unvetted or deprecated third-party APIs "
                    "(e.g. deprecated auth libraries or legacy SDKs) are prohibited without Architecture Review Board (ARB) sign-off.\n\n"
                    "• *Q4 Infrastructure Budget Cap ($5,000):* Any infrastructure, cluster provisioning, or external tooling exceeding "
                    "$5,000 triggers an immediate financial compliance alert and requires Manager review.\n\n"
                    "• *HR Leave Auto-Redirection:* Engineers on active leave (e.g. paternity leave) are automatically protected "
                    "from task assignments; the system auto-reroutes tasks to qualified active peers based on domain skill matching."
                )
            else:
                bot_reply = (
                    f"Command acknowledged: '{text_clean}'.\n"
                    "Veridian Governance Firewall active. You can ask:\n"
                    "• *Sprint status:* 'How much has catchme if finished?' or 'Give me the sprint status'\n"
                    "• *Company rules:* 'Explain SEC-POL-089 and SEC-POL-104' or 'What are the budget & leave rules?'\n"
                    "• *Actions:* 'Check in with team now' or 'Approve sprint tickets'"
                )

            record_slack_feed_message(
                org_id=auth.org_id,
                thread_id=target_thread_id,
                role="bot",
                sender="Veridian Bot",
                recipient=current_name,
                text=bot_reply,
                kind="bot_command_response",
            )

            await sse_manager.push_event(
                target_thread_id,
                "tracker_update",
                {"text": bot_reply, "channel_key": channel_key, "source": "bot_command_response"},
                org_id=auth.org_id,
            )

            return {
                "status": "command_executed",
                "channel_key": channel_key,
                "bot_response": bot_reply,
            }

    else:
        # Direct 1-on-1 Message Channel
        recipient_emp = None
        for emp in employees:
            emp_key_token = str(emp.get("id") or emp["full_name"].lower().replace(" ", "_"))
            if emp_key_token in channel_key:
                recipient_emp = emp
                break
        if not recipient_emp and employees:
            recipient_emp = employees[0]

        rec_name: str = str((recipient_emp or {}).get("full_name") or "Teammate")
        rec_id: str = str((recipient_emp or {}).get("id") or "emp_unknown")
        rec_slack_id = recipient_emp.get("slack_id") if recipient_emp else None

        slack_ts = None
        if rec_slack_id and has_real_slack_creds():
            slack_ts = send_direct_slack_dm(rec_slack_id, f"[{current_name} via Veridian Messages]: {text_clean}")

        msg = record_direct_message(
            org_id=auth.org_id,
            channel_key=channel_key,
            sender_id=auth.user_id,
            sender_name=current_name,
            recipient_id=rec_id,
            recipient_name=rec_name,
            text=text_clean,
            slack_ts=slack_ts,
            slack_channel=channel_key,
        )

        await sse_manager.push_event(
            target_thread_id,
            "tracker_update",
            {"channel_key": channel_key, "message": msg, "source": "direct_message"},
            org_id=auth.org_id,
        )

        return {
            "status": "sent",
            "channel_key": channel_key,
            "message": msg,
            "slack_ts": slack_ts,
        }
