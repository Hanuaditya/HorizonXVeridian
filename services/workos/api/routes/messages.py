"""Org-scoped, role-aware unified Messages & Slack sync routes (/api/messages)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import AuthContext, require_auth
from api.sse import sse_manager
from connectors.slack_ops import get_slack_dm_link, has_real_slack_creds, send_direct_slack_dm
from connectors.sprint_loop import (
    build_default_hitl_decisions,
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
    list_slack_feed_for_org,
    list_thread_snapshots,
    mark_channel_read,
    record_approval,
    record_direct_message,
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
    current_name = current_emp.get("full_name") if current_emp else ("Manager" if is_manager else "Employee")

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

    def _find_emp_ticket(emp: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        name_low = str(emp.get("full_name") or "").lower()
        email_low = str(emp.get("email") or "").lower()
        slack_id = str(emp.get("slack_id") or "").lower()

        for d in dispatched_list:
            a = str(d.get("assignee") or "").lower()
            if (name_low and name_low in a) or (a and a in name_low):
                return {
                    "key": d.get("jira_key") or d.get("task_id"),
                    "title": d.get("title") or "Sprint Action Item",
                    "status": d.get("jira_status") or "To Do",
                    "progress_pct": int(d.get("progress_pct") or 0),
                    "jira_url": d.get("jira_url"),
                    "task_id": d.get("task_id"),
                }
        for tid, t in tasks_map.items():
            a = str(t.get("rerouted_assignee") or t.get("assignee") or "").lower()
            if (name_low and name_low in a) or (a and a in name_low):
                return {
                    "key": t.get("jira_ticket_id") or tid,
                    "title": t.get("title") or "Sprint Action Item",
                    "status": t.get("jira_status") or t.get("status") or "To Do",
                    "progress_pct": int(t.get("progress_pct") or 0),
                    "jira_url": t.get("jira_url"),
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
            threads.append({
                "channel_key": emp_key,
                "title": emp["full_name"],
                "subtitle": emp.get("role") or "Engineer",
                "role": "employee",
                "hr_status": emp.get("hr_status") or emp.get("status") or "ACTIVE",
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
                    "hr_status": emp.get("hr_status") or "ACTIVE",
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
            threads.append({
                "channel_key": peer_key,
                "title": peer["full_name"],
                "subtitle": peer.get("role") or "Engineer",
                "role": "peer",
                "hr_status": peer.get("hr_status") or peer.get("status") or "ACTIVE",
                "slack_user_id": peer_slack_uid,
                "slack_deep_link": get_slack_dm_link(peer_slack_uid),
                "unread_count": by_channel.get(peer_key, 0),
                "active_ticket": ticket,
                "member": {
                    "id": peer.get("id"),
                    "name": peer["full_name"],
                    "email": peer.get("email"),
                    "role": peer.get("role"),
                    "hr_status": peer.get("hr_status") or "ACTIVE",
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
    current_name = current_emp.get("full_name") if current_emp else ("Manager" if is_manager else "Employee")

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
            if is_manager:
                # Manager sees governance alerts, review menus, progress digests, and bot messages
                if (
                    m.get("role") in {"manager", "bot"}
                    or m.get("recipient") in {"Manager", "All"}
                    or m.get("kind") in {"alert", "review_menu", "progress_digest", "closure_confirmation", "rework_request"}
                ):
                    messages.append(m)
            else:
                # Employee sees ONLY their 1-on-1 check-ins, assignments, and replies
                rcp = str(m.get("recipient") or "").lower()
                snd = str(m.get("sender") or "").lower()
                if (
                    (name_low and (name_low in rcp or name_low in snd))
                    or (email_low and email_low in rcp)
                    or m.get("role") == "employee"
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
    auth: AuthContext = Depends(require_auth),
) -> Dict[str, Any]:
    """Send a message to Veridian Bot or a teammate, syncing with Slack and Jira execution."""
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message text is required.")

    text_clean = body.text.strip()
    is_manager = auth.role == "org:admin"
    employees = _filter_and_normalize_employees(list_employees(auth.org_id))
    current_emp = _find_matching_employee(employees, auth.user_id, auth.email)
    current_name = current_emp.get("full_name") if current_emp else ("Manager" if is_manager else "Employee")

    latest_snap = _get_latest_thread(auth.org_id, body.thread_id)
    target_thread_id = (latest_snap or {}).get("thread_id") or body.thread_id or "live-sprint-sync"

    if channel_key == "veridian-bot":
        if not is_manager:
            # Employee messaging Veridian Bot: Route through Sprint Loop Employee Reply Pipeline!
            target_task_id = body.task_id
            if not target_task_id and latest_snap:
                # Find task assigned to this employee
                name_low = current_name.lower()
                for tid, t in (latest_snap.get("tasks") or {}).items():
                    a = str(t.get("rerouted_assignee") or t.get("assignee") or "").lower()
                    if name_low in a or a in name_low:
                        target_task_id = tid
                        break
                if not target_task_id and latest_snap.get("tasks"):
                    target_task_id = next(iter(latest_snap["tasks"].keys()))

            if not target_task_id:
                target_task_id = "t1"

            result = await process_employee_reply(
                org_id=auth.org_id,
                thread_id=target_thread_id,
                task_id=target_task_id,
                reply_text=text_clean,
                source="web_messages",
                post_to_slack=True,
            )
            return {
                "status": "processed",
                "channel_key": channel_key,
                "role": "employee",
                "result": result,
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
            if any(k in cmd_low for k in ("check in", "check-in", "checkin", "check", "ping", "status", "scheduled")):
                checkin_res = await trigger_checkin_for_thread(auth.org_id, target_thread_id)
                cnt = checkin_res.get("dispatched_checkins", 0)
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
            else:
                bot_reply = (
                    f"Command acknowledged: '{text_clean}'. "
                    "Veridian Governance Firewall active. "
                    "You can type 'Check in with team now' or 'Approve sprint tickets'."
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

        rec_name = recipient_emp["full_name"] if recipient_emp else "Teammate"
        rec_id = recipient_emp.get("id") if recipient_emp else "emp_unknown"
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
