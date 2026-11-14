"""Org-scoped, role-aware unified Messages & Slack sync routes (/api/messages)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import AuthContext, require_auth
from api.sse import sse_manager
from connectors.jira_ops import (
    add_jira_comment,
    delete_jira_issue,
    transition_jira_issue_done,
    transition_jira_issue_in_progress,
    update_jira_issue_summary,
)
from connectors.slack_ops import get_slack_dm_link, has_real_slack_creds, post_slack_message, send_direct_slack_dm
from connectors.sprint_loop import (
    _deterministic_analyze_reply,
    build_default_hitl_decisions,
    dispatch_stage_2_checkin,
    extract_completion_evidence,
    notify_manager_employee_update,
    process_employee_reply,
    record_slack_feed_message,
    resume_graph_a_and_sync,
    trigger_checkin_for_thread,
)
from core.identifiers import (
    canonical_employee_key,
    clean_task_title,
    get_all_manager_keys,
    is_manager_identity,
    resolve_veridian_thread_id,
)
from core.thread_store import (
    DEMO_BOT_THREADS,
    append_demo_bot_message,
    cancel_pending_checkin_timers,
    get_demo_bot_messages,
    get_demo_bucket,
    register_checkin_timer,
    reset_demo_bot_threads,
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

    # Ensure canonical 4 members exist
    has_catchme = any("catchme" in str(e.get("full_name", "")).lower() for e in filtered)
    has_resigo = any("resigo" in str(e.get("full_name", "")).lower() for e in filtered)
    has_hanu = any("hanu" in str(e.get("full_name", "")).lower() for e in filtered)
    has_arjun = any("arjun" in str(e.get("full_name", "")).lower() for e in filtered)

    if not has_catchme:
        filtered.append({
            "id": "emp_catchme_if",
            "clerk_user_id": "user_demo_catchme",
            "full_name": "catchme if",
            "email": "catchme@veridian.io",
            "role": "Backend Engineer",
            "status": "ACTIVE",
            "hr_status": "ACTIVE",
            "department": "Platform Engineering",
            "slack_id": "U_CATCHME_IF",
        })
    if not has_resigo:
        filtered.append({
            "id": "emp_resigo",
            "clerk_user_id": "user_demo_resigo",
            "full_name": "Resigo",
            "email": "resigo@veridian.io",
            "role": "Frontend Engineer",
            "status": "ACTIVE",
            "hr_status": "ACTIVE",
            "department": "Product & Frontend Engineering",
            "slack_id": "U_RESIGO",
        })
    if not has_hanu:
        filtered.append({
            "id": "emp_hanu_aditya",
            "clerk_user_id": "user_demo_hanu",
            "full_name": "Hanu Aditya",
            "email": "hanu@veridian.io",
            "role": "Engineering Manager",
            "status": "ACTIVE",
            "hr_status": "ACTIVE",
            "department": "Engineering Leadership",
            "slack_id": "U_HANU_ADITYA",
        })
    if not has_arjun:
        filtered.append({
            "id": "emp_arjun_rao",
            "clerk_user_id": "user_demo_arjun",
            "full_name": "Arjun Rao",
            "email": "arjun.rao@example.com",
            "role": "Backend Engineer",
            "status": "ON_PATERNITY_LEAVE",
            "hr_status": "ON_PATERNITY_LEAVE",
            "department": "Platform Engineering",
            "slack_id": "U_ARJUN_RAO",
        })

    return filtered


class MessageSendRequest(BaseModel):
    text: str
    task_id: Optional[str] = None
    thread_id: Optional[str] = None
    client_msg_id: Optional[str] = None


_PROCESSED_CLIENT_MSGS: Dict[str, tuple[float, Dict[str, Any]]] = {}


def _clean_task_title(title: str) -> str:
    return clean_task_title(title)


def _find_matching_employee(employees: List[Dict[str, Any]], user_id: str, email: Optional[str]) -> Optional[Dict[str, Any]]:
    uid_clean = (user_id or "").strip().lower()
    em_clean = (email or "").strip().lower()
    uid_key = canonical_employee_key(user_id) if user_id else ""

    for emp in employees:
        ck = str(emp.get("clerk_user_id") or "").strip().lower()
        em = str(emp.get("email") or "").strip().lower()
        fn = str(emp.get("full_name") or "")
        emp_key = canonical_employee_key(fn) if fn else ""
        if ck and (ck == uid_clean or (uid_key and canonical_employee_key(ck) == uid_key)):
            return emp
        if em and em_clean and em == em_clean:
            return emp
        if uid_key and emp_key and uid_key == emp_key:
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
            emp_name = str(emp.get("full_name") or "Employee")
            emp_role = str(emp.get("role") or "").lower()
            if "manager" in emp_role and "hanu" in emp_name.lower():
                continue
            eid = str(emp.get("id") or "")
            emp_key = f"emp:{eid or emp_name.lower().replace(' ', '_')}"
            slack_uid = emp.get("slack_id") or emp.get("slack_user_id")
            ticket = _find_emp_ticket(emp)
            emp_hr = str(emp.get("hr_status") or emp.get("status") or "ACTIVE")
            is_on_leave = "leave" in emp_hr.lower()
            threads.append({
                "channel_key": emp_key,
                "title": emp_name,
                "subtitle": str(emp.get("role") or "Engineer"),
                "role": "employee",
                "hr_status": emp_hr,
                "status": "ON_LEAVE" if is_on_leave else (ticket.get("status") if ticket else "IDLE"),
                "ticket_key": ticket.get("key") if ticket else None,
                "progress_pct": ticket.get("progress_pct", 0) if ticket else 0,
                "department": str(emp.get("department") or "Engineering"),
                "slack_user_id": slack_uid,
                "slack_deep_link": get_slack_dm_link(slack_uid),
                "jira_account_id": emp.get("jira_account_id"),
                "unread_count": by_channel.get(emp_key, 0),
                "active_ticket": ticket,
                "member": {
                    "id": emp.get("id"),
                    "name": emp_name,
                    "email": emp.get("email"),
                    "role": emp.get("role"),
                    "hr_status": emp_hr,
                    "domain_skills": emp.get("domain_skills", []),
                },
            })
    else:
        # Employee sees channel with Manager
        if manager_emp:
            mgr_name = str(manager_emp.get("full_name") or "Engineering Manager")
            mgr_key = f"mgr:{manager_emp.get('id') or 'manager'}"
            mgr_slack_uid = manager_emp.get("slack_id")
            threads.append({
                "channel_key": mgr_key,
                "title": mgr_name,
                "subtitle": str(manager_emp.get("role") or "Engineering Manager"),
                "role": "manager",
                "hr_status": "ACTIVE",
                "status": "ACTIVE",
                "ticket_key": None,
                "progress_pct": 0,
                "slack_user_id": mgr_slack_uid,
                "slack_deep_link": get_slack_dm_link(mgr_slack_uid),
                "unread_count": by_channel.get(mgr_key, 0),
                "member": {
                    "name": mgr_name,
                    "email": manager_emp.get("email"),
                    "role": str(manager_emp.get("role") or "Engineering Manager"),
                    "hr_status": "ACTIVE",
                },
            })
        # Employee sees peer channels with other teammates
        for peer in employees:
            if current_emp and peer.get("id") == current_emp.get("id"):
                continue
            if manager_emp and peer.get("id") == manager_emp.get("id"):
                continue
            peer_name = str(peer.get("full_name") or "Teammate")
            pid = str(peer.get("id") or "")
            peer_key = f"peer:{pid or peer_name.lower().replace(' ', '_')}"
            peer_slack_uid = peer.get("slack_id")
            ticket = _find_emp_ticket(peer)
            peer_hr = str(peer.get("hr_status") or peer.get("status") or "ACTIVE")
            peer_on_leave = "leave" in peer_hr.lower()
            threads.append({
                "channel_key": peer_key,
                "title": peer_name,
                "subtitle": str(peer.get("role") or "Engineer"),
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
                    "name": peer_name,
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
        bucket = get_demo_bucket(auth, current_name)
        vbot_thread = f"veridian-bot:{bucket}"

        # Authoritative in-memory demo messages
        messages = list(get_demo_bot_messages(bucket))
        seen_ids: set = {m.get("id") for m in messages if m.get("id")}
        seen_sigs: set = {
            (m.get("kind"), m.get("task_id"), (m.get("text") or "").strip()[:80])
            for m in messages
        }

        # Also pull from store thread_id if seeded
        for m in list_slack_feed(org_id=auth.org_id, thread_id=vbot_thread):
            if m.get("id") in seen_ids:
                continue
            sig = (m.get("kind"), m.get("task_id"), (m.get("text") or "").strip()[:80])
            if sig in seen_sigs:
                continue
            messages.append(m)
            seen_ids.add(m.get("id"))
            seen_sigs.add(sig)

        # Also merge from all org messages (e.g. seeded with meeting thread_id or legacy routes)
        feed_all = list_slack_feed_for_org(auth.org_id)
        if not feed_all and thread_id:
            snap = get_thread_snapshot(thread_id)
            feed_all = list((snap or {}).get("slack_feed") or [])

        if is_manager:
            employees_list = _filter_and_normalize_employees(list_employees(auth.org_id))
            all_mgr_keys = get_all_manager_keys(employees_list)
            all_mgr_keys_low = {k.lower() for k in all_mgr_keys} | {
                "manager",
                "hanu_aditya",
                "hanuma_aditya",
                "hanu aditya",
                "hanuma aditya",
                current_name.lower(),
                auth.user_id.lower(),
            }
            for m in feed_all:
                if m.get("id") in seen_ids:
                    continue
                sig = (m.get("kind"), m.get("task_id"), (m.get("text") or "").strip()[:80])
                if sig in seen_sigs:
                    continue
                kind = m.get("kind")
                rcp = str(m.get("recipient") or "")
                rcp_low = rcp.lower()
                role = m.get("role")
                if kind in {"checkin", "assignment"} and rcp not in {"Manager", "All"} and rcp_low not in all_mgr_keys_low:
                    continue
                if kind == "employee_reply":
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
                    or (role == "bot" and rcp_low in all_mgr_keys_low | {current_name.lower(), "all"})
                    or rcp_low in all_mgr_keys_low | {"all"}
                    or (m.get("metadata") or {}).get("recipient_id") in {"manager:veridian-bot", auth.user_id}
                    or (m.get("metadata") or {}).get("type") == "employee_summary"
                ):
                    messages.append(m)
                    seen_ids.add(m.get("id"))
                    seen_sigs.add(sig)
        else:
            name_low = current_name.lower()
            email_low = (auth.email or "").lower()
            emp_key = canonical_employee_key(current_name) if current_name else ""
            for m in feed_all:
                if m.get("id") in seen_ids:
                    continue
                sig = (m.get("kind"), m.get("task_id"), (m.get("text") or "").strip()[:80])
                if sig in seen_sigs:
                    continue
                kind = m.get("kind")
                if kind in {
                    "review_menu",
                    "compliance_alert",
                    "blocker_escalation",
                    "progress_digest",
                    "manager_command",
                    "bot_command_response",
                }:
                    continue
                if kind in {"closure", "closure_confirmation"} and m.get("recipient") == "Manager":
                    continue
                rcp = str(m.get("recipient") or "")
                snd = str(m.get("sender") or "")
                rcp_low = rcp.lower()
                snd_low = snd.lower()
                rcp_key = canonical_employee_key(rcp) if rcp else ""
                snd_key = canonical_employee_key(snd) if snd else ""
                if (
                    (emp_key and (emp_key == rcp_key or emp_key == snd_key))
                    or (name_low and (name_low in rcp_low or name_low in snd_low))
                    or (email_low and email_low in rcp_low)
                    or (rcp_low == "all")
                ):
                    messages.append(m)
                    seen_ids.add(m.get("id"))
                    seen_sigs.add(sig)

        messages.sort(key=lambda x: str(x.get("created_at") or ""))

        slack_deep_link = get_slack_dm_link(current_emp.get("slack_id") if current_emp else None)

    else:
        # Direct message channel (emp:..., mgr:..., peer:...)
        raw_dm = list_direct_messages(auth.org_id, channel_key)
        messages.extend(raw_dm)

        # Lookup recipient's Slack ID for deep link
        target_slack_id = None
        for emp in employees:
            efn = str(emp.get("full_name") or "")
            eid = str(emp.get("id") or "")
            emp_key_token = eid or efn.lower().replace(" ", "_")
            if emp_key_token and emp_key_token in channel_key:
                target_slack_id = emp.get("slack_id")
                break
        slack_deep_link = get_slack_dm_link(target_slack_id)

    return {
        "channel_key": channel_key,
        "messages": messages,
        "slack_deep_link": slack_deep_link,
        "count": len(messages),
    }


async def handle_employee_bot_reply(
    bucket: str,
    emp_name: str,
    text: str,
    background_tasks: BackgroundTasks,
    task_id: Optional[str] = None,
    client_msg_id: Optional[str] = None,
    org_id: str = "org_demo_horizon",
    target_thread_id: str = "live-sprint-sync",
) -> Dict[str, Any]:
    """Instant (<20ms) handler for employee bot replies with auto manager summary and live Jira sync."""
    latest_snap = _get_latest_thread(org_id, target_thread_id)
    tasks_map = dict((latest_snap or {}).get("tasks") or {})
    target_task_id = task_id
    if not target_task_id:
        for tid, t in tasks_map.items():
            a = canonical_employee_key(str(t.get("rerouted_assignee") or t.get("assignee") or ""))
            if a == bucket:
                target_task_id = tid
                break
    if not target_task_id and tasks_map:
        target_task_id = next(iter(tasks_map.keys()))
    if not target_task_id:
        target_task_id = "t1"

    task = dict(tasks_map.get(target_task_id) or {})
    raw_title = str(task.get("reframed_title") or task.get("title") or "Sprint Task")
    clean_title = clean_task_title(raw_title)
    jira_key = str(task.get("jira_ticket_id") or task.get("jira_key") or ("SCRUM-21" if bucket == "catchme_if" else "SCRUM-22"))

    # 1. Append Employee Message Immediately
    append_demo_bot_message(
        bucket=bucket,
        role="employee",
        sender=emp_name,
        recipient="Veridian Bot",
        text=text,
        kind="employee_reply",
        task_id=target_task_id,
        jira_key=jira_key,
        client_msg_id=client_msg_id,
    )
    record_slack_feed_message(
        org_id=org_id,
        thread_id=f"veridian-bot:{bucket}",
        role="employee",
        sender=emp_name,
        recipient="Veridian Bot",
        text=text,
        kind="employee_reply",
        task_id=target_task_id,
        jira_key=jira_key,
        client_msg_id=client_msg_id,
    )

    analysis = _deterministic_analyze_reply(text, clean_title)

    if analysis.intent == "COMPLETED":
        new_status = "DONE"
        new_progress = 100
        new_jira_status = "Done"
        bot_emp_reply = f"Completed! Your task '{clean_title}' ({jira_key}) is marked 100% DONE, closed in Jira, and your manager has been notified."
        mgr_summary_text = (
            f"[Task Completed - @{emp_name}] {emp_name} finished 100% of {jira_key} ({clean_title}): \"{text}\". "
            f"The Jira ticket has been automatically closed."
        )
        task["checkin_stage"] = 3
        task["awaiting_employee_reply"] = False

        def _bg_jira_completed():
            try:
                add_jira_comment(jira_key, f"[Veridian Bot] Completed by {emp_name}: {text}")
                transition_jira_issue_done(jira_key, f"Completed by {emp_name}: {text}")
                delete_jira_issue(jira_key)
            except Exception as exc:
                logger.warning("Background Jira completion failed: %s", exc)

        background_tasks.add_task(_bg_jira_completed)

    elif analysis.intent == "BLOCKED":
        new_status = "BLOCKED"
        new_progress = analysis.progress_pct if analysis.progress_pct > 0 else 25
        new_jira_status = "Blocked"
        bot_emp_reply = f"Blocker logged on {jira_key} ({clean_title}). I have flagged your Jira ticket and alerted your manager immediately."
        mgr_summary_text = (
            f"[Blocker Alert - @{emp_name}] {emp_name} reported a blocker on {jira_key} ({clean_title}): \"{text}\"."
        )

        def _bg_jira_blocked():
            try:
                add_jira_comment(jira_key, f"[Veridian Bot URGENT BLOCKER] {emp_name} is blocked: {text}")
                update_jira_issue_summary(jira_key, f"[BLOCKED] {clean_title}")
            except Exception as exc:
                logger.warning("Background Jira blocker update failed: %s", exc)

        background_tasks.add_task(_bg_jira_blocked)

    else:
        new_status = "IN_PROGRESS"
        new_progress = analysis.progress_pct if analysis.progress_pct > 0 else 60
        new_jira_status = "In Progress"
        bot_emp_reply = (
            f"Got it, {emp_name}! Logged {new_progress}% progress on {jira_key} ({clean_title}), "
            f"updated your Jira ticket to In Progress ({new_progress}%), and sent an automatic summary to your manager."
        )
        mgr_summary_text = (
            f"[Auto Summary - @{emp_name}] [Progress Digest] {emp_name} has reported {new_progress}% completed ({new_progress}% complete) of {jira_key} ({clean_title}): \"{text}\". "
            f"Jira ticket updated to In Progress ({new_progress}%)."
        )
        task["awaiting_employee_reply"] = False

        def _bg_jira_progress():
            try:
                transition_jira_issue_in_progress(jira_key)
                update_jira_issue_summary(jira_key, f"[{new_progress}%] {clean_title}")
                add_jira_comment(jira_key, f"[Veridian Bot] {emp_name} reported {new_progress}% progress: {text}")
            except Exception as exc:
                logger.warning("Background Jira progress update failed: %s", exc)

        background_tasks.add_task(_bg_jira_progress)

        # Sequential Stage 2 Follow-Up 5 seconds after employee replies to Stage 1
        async def _delayed_stage_2():
            try:
                await asyncio.sleep(5)
                s = get_thread_snapshot(target_thread_id) or {}
                m = dict(s.get("tasks") or {})
                t_live = dict(m.get(target_task_id) or {})
                if t_live.get("status") != "DONE" and int(t_live.get("checkin_stage") or 0) < 2:
                    t_live["checkin_stage"] = 2
                    t_live["awaiting_employee_reply"] = True
                    m[target_task_id] = t_live
                    save_thread_snapshot(target_thread_id, org_id, {**s, "tasks": m})
                    s2_msg = (
                        f"Hi {emp_name}, wrapping up for the day — once you finish {clean_title} ({jira_key}), "
                        "please share your PR link or click 'Completed + PR' so I can close your Jira ticket."
                    )
                    append_demo_bot_message(
                        bucket=bucket,
                        role="bot",
                        sender="Veridian Bot",
                        recipient=emp_name,
                        text=s2_msg,
                        kind="checkin",
                        task_id=target_task_id,
                        jira_key=jira_key,
                        metadata={"checkin_stage": 2, "assignee": emp_name},
                    )
                    record_slack_feed_message(
                        org_id=org_id,
                        thread_id=f"veridian-bot:{bucket}",
                        role="bot",
                        sender="Veridian Bot",
                        recipient=emp_name,
                        text=s2_msg,
                        kind="checkin",
                        task_id=target_task_id,
                        jira_key=jira_key,
                        metadata={"checkin_stage": 2, "assignee": emp_name},
                    )
                    await sse_manager.push_event(target_thread_id, "tracker_update", {"tasks": m}, org_id=org_id)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.debug("Delayed stage 2 error: %s", exc)

        register_checkin_timer(asyncio.create_task(_delayed_stage_2()))

    # Append Veridian Bot reply to employee
    append_demo_bot_message(
        bucket=bucket,
        role="bot",
        sender="Veridian Bot",
        recipient=emp_name,
        text=bot_emp_reply,
        kind="bot_reply",
        task_id=target_task_id,
        jira_key=jira_key,
    )
    record_slack_feed_message(
        org_id=org_id,
        thread_id=f"veridian-bot:{bucket}",
        role="bot",
        sender="Veridian Bot",
        recipient=emp_name,
        text=bot_emp_reply,
        kind="bot_reply",
        task_id=target_task_id,
        jira_key=jira_key,
    )

    # Append Manager Automatic Summary Card
    append_demo_bot_message(
        bucket="manager",
        role="manager",
        sender="Veridian Bot",
        recipient="manager",
        text=mgr_summary_text,
        kind="progress_digest" if new_status != "BLOCKED" else "blocker_escalation",
        task_id=target_task_id,
        jira_key=jira_key,
        metadata={"employee": emp_name, "type": "employee_summary", "progress_pct": new_progress},
    )
    record_slack_feed_message(
        org_id=org_id,
        thread_id="veridian-bot:manager",
        role="manager",
        sender="Veridian Bot",
        recipient="manager",
        text=mgr_summary_text,
        kind="progress_digest" if new_status != "BLOCKED" else "blocker_escalation",
        task_id=target_task_id,
        jira_key=jira_key,
        metadata={"employee": emp_name, "type": "employee_summary", "progress_pct": new_progress},
    )

    # Update in-memory state
    task["status"] = new_status
    task["progress_pct"] = new_progress
    task["jira_status"] = new_jira_status
    task["replied"] = True
    task["last_update_text"] = text
    tasks_map[target_task_id] = task

    dispatched_list = [dict(d) for d in ((latest_snap or {}).get("dispatched_tickets") or [])]
    for dt in dispatched_list:
        if dt.get("task_id") == target_task_id or dt.get("jira_key") == jira_key:
            dt["progress_pct"] = new_progress
            dt["jira_status"] = new_jira_status
            dt["status"] = new_status

    save_thread_snapshot(
        thread_id=target_thread_id,
        org_id=org_id,
        snapshot={
            **(latest_snap or {}),
            "tasks": tasks_map,
            "dispatched_tickets": dispatched_list,
        },
    )

    update_task_status_by_id(
        org_id=org_id,
        task_id=target_task_id,
        status=new_status,
        jira_key=jira_key,
    )

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
        },
        org_id=org_id,
    )

    res_data = {
        "ok": True,
        "status": "processed",
        "channel_key": "veridian-bot",
        "role": "employee",
        "intent": analysis.intent,
        "progress_pct": new_progress,
        "bot_reply": bot_emp_reply,
        "messages": get_demo_bot_messages(bucket),
    }
    if client_msg_id:
        _PROCESSED_CLIENT_MSGS[client_msg_id] = (time.time(), res_data)
    return res_data


async def handle_manager_bot_command(
    manager_name: str,
    text: str,
    background_tasks: BackgroundTasks,
    client_msg_id: Optional[str] = None,
    org_id: str = "org_demo_horizon",
    target_thread_id: str = "live-sprint-sync",
) -> Dict[str, Any]:
    """Instant (<20ms) handler for Manager sprint status and natural language commands."""
    cmd_low = text.lower()

    # Append Manager message to DEMO_BOT_THREADS["manager"]
    append_demo_bot_message(
        bucket="manager",
        role="manager",
        sender=manager_name,
        recipient="Veridian Bot",
        text=text,
        kind="manager_command",
        client_msg_id=client_msg_id,
    )
    record_slack_feed_message(
        org_id=org_id,
        thread_id="veridian-bot:manager",
        role="manager",
        sender=manager_name,
        recipient="Veridian Bot",
        text=text,
        kind="manager_command",
        client_msg_id=client_msg_id,
    )

    latest_snap = _get_latest_thread(org_id, target_thread_id) or {}
    tasks = dict(latest_snap.get("tasks") or {})
    if not tasks:
        for s in list_thread_snapshots(org_id):
            if s.get("tasks"):
                tasks = dict(s["tasks"])
                break

    bot_reply = ""
    if any(k in cmd_low for k in ("check in", "check-in", "checkin", "ping", "trigger check")):
        try:
            await trigger_checkin_for_thread(org_id, target_thread_id)
        except Exception as exc:
            logger.debug("trigger_checkin_for_thread on manager command: %s", exc)
        bot_reply = "Sent Stage 1 progress check-ins to active engineers (catchme if, Resigo). Initiated 1-on-1 sprint interval check-ins."

    elif any(k in cmd_low for k in ("approve", "approve all", "proceed", "lgtm", "create tickets")):
        snap = get_thread_snapshot(target_thread_id)
        if snap and snap.get("phase") == "HITL":
            decisions = build_default_hitl_decisions(snap)
            approver = "clerk:manager"
            record_approval(org_id, target_thread_id, snap.get("meeting_id") or target_thread_id, decisions, approver)
            await resume_graph_a_and_sync(target_thread_id, org_id, approver, decisions)
            bot_reply = "Approved all sprint governance gates. Provisioned Jira tickets and dispatched employee Slack DMs."
        else:
            bot_reply = "Sprint tickets have already been approved and dispatched to Jira."

    elif any(k in cmd_low for k in ("status", "progress", "how much has", "sprint status", "summary", "how is", "report")):
        lines = ["*Live Sprint Status Report:*"]
        for emp_target in ("catchme if", "Resigo"):
            target_t = next((t for t in tasks.values() if emp_target.lower() in str(t.get("rerouted_assignee") or t.get("assignee") or "").lower()), None)
            jkey = (target_t or {}).get("jira_ticket_id") or (target_t or {}).get("jira_key") or ("SCRUM-21" if "catchme" in emp_target.lower() else "SCRUM-22")
            raw_t = (target_t or {}).get("reframed_title") or (target_t or {}).get("title") or ("Deploy Elasticsearch cluster to AWS production" if "catchme" in emp_target.lower() else "Build OAuth login dashboard")
            clean_t = clean_task_title(str(raw_t))
            replied = bool((target_t or {}).get("replied", False))
            st = str((target_t or {}).get("status") or "TO DO").upper()
            pct = int((target_t or {}).get("progress_pct") or 0)
            last_u = str((target_t or {}).get("last_update_text") or "")
            if not replied and st != "DONE" and pct == 0:
                lines.append(f"- {emp_target} ({jkey} — {clean_t}): 0% completed [Jira: TO DO] — No reply received from {emp_target} yet.")
            elif st == "DONE" or pct == 100:
                lines.append(f"- {emp_target} ({jkey} — {clean_t}): 100% completed [Jira: DONE / CLOSED] — \"{last_u or 'Completed'}\"")
            elif st == "BLOCKED":
                lines.append(f"- {emp_target} ({jkey} — {clean_t}): {pct}% completed [Jira: BLOCKED] — \"{last_u or 'Blocker reported'}\"")
            else:
                lines.append(f"- {emp_target} ({jkey} — {clean_t}): {pct}% completed [Jira: IN PROGRESS] — \"{last_u or 'In progress'}\"")
        lines.append("- Arjun Rao: On Paternity Leave (Task automatically reassigned to catchme if).")
        bot_reply = "\n".join(lines)

    elif any(k in cmd_low for k in ("rule", "policy", "policies", "sec-pol", "budget", "leave", "compliance", "explain")):
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
            f"Command acknowledged: '{text}'.\n"
            "Veridian Governance Firewall active. You can ask:\n"
            "• *Sprint status:* 'Give me the sprint status summary' or 'Sprint status'\n"
            "• *Company rules:* 'Explain policies' or 'Explain SEC-POL-089 and SEC-POL-104'\n"
            "• *Actions:* 'Check in now' or 'Approve sprint tickets'"
        )

    # Append bot response to DEMO_BOT_THREADS["manager"]
    append_demo_bot_message(
        bucket="manager",
        role="bot",
        sender="Veridian Bot",
        recipient=manager_name,
        text=bot_reply,
        kind="bot_command_response",
    )
    record_slack_feed_message(
        org_id=org_id,
        thread_id="veridian-bot:manager",
        role="bot",
        sender="Veridian Bot",
        recipient=manager_name,
        text=bot_reply,
        kind="bot_command_response",
    )

    await sse_manager.push_event(
        target_thread_id,
        "tracker_update",
        {"text": bot_reply, "channel_key": "veridian-bot", "source": "bot_command_response"},
        org_id=org_id,
    )

    res_data = {
        "ok": True,
        "status": "command_executed",
        "channel_key": "veridian-bot",
        "bot_response": bot_reply,
        "messages": get_demo_bot_messages("manager"),
    }
    if client_msg_id:
        _PROCESSED_CLIENT_MSGS[client_msg_id] = (time.time(), res_data)
    return res_data


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

    now_ts = time.time()
    stale_keys = [k for k, (ts, _) in _PROCESSED_CLIENT_MSGS.items() if now_ts - ts > 60.0]
    for k in stale_keys:
        _PROCESSED_CLIENT_MSGS.pop(k, None)

    if body.client_msg_id and body.client_msg_id in _PROCESSED_CLIENT_MSGS:
        logger.info("send_channel_message: duplicate client_msg_id '%s' received, returning cached response.", body.client_msg_id)
        return _PROCESSED_CLIENT_MSGS[body.client_msg_id][1]

    text_clean = body.text.strip()
    is_manager = auth.role == "org:admin"
    employees = _filter_and_normalize_employees(list_employees(auth.org_id))
    current_emp = _find_matching_employee(employees, auth.user_id, auth.email)
    current_name: str = _resolve_user_display_name(current_emp, "Manager" if is_manager else "Employee")

    latest_snap = _get_latest_thread(auth.org_id, body.thread_id)
    target_thread_id = (latest_snap or {}).get("thread_id") or body.thread_id or "live-sprint-sync"

    if channel_key == "veridian-bot":
        bucket = get_demo_bucket(auth, current_name)
        if bucket in ("catchme_if", "resigo"):
            return await handle_employee_bot_reply(
                bucket=bucket,
                emp_name=current_name,
                text=text_clean,
                background_tasks=background_tasks,
                task_id=body.task_id,
                client_msg_id=body.client_msg_id,
                org_id=auth.org_id,
                target_thread_id=target_thread_id,
            )
        else:
            return await handle_manager_bot_command(
                manager_name=current_name,
                text=text_clean,
                background_tasks=background_tasks,
                client_msg_id=body.client_msg_id,
                org_id=auth.org_id,
                target_thread_id=target_thread_id,
            )

    else:
        # Direct 1-on-1 Message Channel
        recipient_emp = None
        for emp in employees:
            efn = str(emp.get("full_name") or "")
            eid = str(emp.get("id") or "")
            emp_key_token = eid or efn.lower().replace(" ", "_")
            if emp_key_token and emp_key_token in channel_key:
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
            client_msg_id=body.client_msg_id,
        )

        await sse_manager.push_event(
            target_thread_id,
            "tracker_update",
            {"channel_key": channel_key, "message": msg, "source": "direct_message"},
            org_id=auth.org_id,
        )

        res_data = {
            "status": "sent",
            "channel_key": channel_key,
            "message": msg,
            "slack_ts": slack_ts,
        }
        if body.client_msg_id:
            _PROCESSED_CLIENT_MSGS[body.client_msg_id] = (time.time(), res_data)
        return res_data
