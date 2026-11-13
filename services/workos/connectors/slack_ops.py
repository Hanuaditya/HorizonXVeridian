"""Unified Slack DM & Block Kit orchestrator for Manager alerts, review menus, and Employee 1-on-1 loops."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import get_settings
from core.evon_llm import resolve_slack_channel
from core.store import record_slack_feed_message, upsert_slack_thread

logger = logging.getLogger(__name__)


def has_real_slack_creds() -> bool:
    settings = get_settings()
    return bool(
        settings.slack_bot_token
        and "placeholder" not in settings.slack_bot_token.lower()
    )


def _load_local_team_identities() -> list[dict]:
    for cand in [Path("local.identities.json"), Path(__file__).resolve().parents[3] / "local.identities.json"]:
        if cand.exists():
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "team" in data and isinstance(data["team"], list):
                        return data["team"]
                    elif isinstance(data, list):
                        return data
            except Exception:
                pass
    return []


_LOCAL_TEAM = _load_local_team_identities()

MANAGER_SLACK_USER_ID = "U_MGR_DEMO"
EMPLOYEE_A_SLACK_USER_ID = "U_EMP_A_DEMO"
EMPLOYEE_B_SLACK_USER_ID = "U_EMP_B_DEMO"

_SLACK_USER_MAP: Dict[str, str] = {
    "manager": MANAGER_SLACK_USER_ID,
    "aarav sharma": MANAGER_SLACK_USER_ID,
    "aarav.sharma@example.com": MANAGER_SLACK_USER_ID,
    "user_clerk_manager_demo": MANAGER_SLACK_USER_ID,
    "rohan patel": EMPLOYEE_A_SLACK_USER_ID,
    "rohan.patel@example.com": EMPLOYEE_A_SLACK_USER_ID,
    "user_clerk_emp_a_demo": EMPLOYEE_A_SLACK_USER_ID,
    "employee a": EMPLOYEE_A_SLACK_USER_ID,
    "priya sen": EMPLOYEE_B_SLACK_USER_ID,
    "priya.sen@example.com": EMPLOYEE_B_SLACK_USER_ID,
    "user_clerk_emp_b_demo": EMPLOYEE_B_SLACK_USER_ID,
    "employee b": EMPLOYEE_B_SLACK_USER_ID,
    "arjun rao": "U_ARJUN_DEMO",
    "arjun.rao@example.com": "U_ARJUN_DEMO",
}

for member in _LOCAL_TEAM:
    s_id = str(member.get("slack_user_id") or member.get("slack_id") or "").strip()
    if not s_id:
        continue
    fn = str(member.get("full_name") or member.get("name") or "").strip().lower()
    em = str(member.get("email") or "").strip().lower()
    ck = str(member.get("clerk_user_id") or "").strip().lower()
    role_str = str(member.get("role") or "").strip().lower()
    if "manager" in role_str or "admin" in role_str:
        MANAGER_SLACK_USER_ID = s_id
        _SLACK_USER_MAP["manager"] = s_id
    elif "backend" in role_str or "emp_a" in ck:
        EMPLOYEE_A_SLACK_USER_ID = s_id
        _SLACK_USER_MAP["employee a"] = s_id
    elif "frontend" in role_str or "emp_b" in ck:
        EMPLOYEE_B_SLACK_USER_ID = s_id
        _SLACK_USER_MAP["employee b"] = s_id
    if fn:
        _SLACK_USER_MAP[fn] = s_id
    if em:
        _SLACK_USER_MAP[em] = s_id
    if ck:
        _SLACK_USER_MAP[ck] = s_id

_DM_CHANNEL_CACHE: Dict[str, str] = {}


def resolve_slack_user_id(
    recipient: str,
    role: str = "employee",
    org_id: Optional[str] = None,
) -> Optional[str]:
    """Map recipient name, email, clerk id, or role to Slack Member ID."""
    rec_clean = (recipient or "").strip().lower()
    if rec_clean.startswith("u0") or (rec_clean.startswith("u_") and len(rec_clean) >= 6) or (rec_clean.startswith("u") and len(rec_clean) >= 9):
        return recipient.strip()
    if role == "manager" or rec_clean in {"manager", "aarav sharma", "aarav.sharma@example.com"}:
        return MANAGER_SLACK_USER_ID
    if rec_clean in _SLACK_USER_MAP:
        return _SLACK_USER_MAP[rec_clean]
    if "rohan" in rec_clean:
        return EMPLOYEE_A_SLACK_USER_ID
    if "priya" in rec_clean:
        return EMPLOYEE_B_SLACK_USER_ID
    if org_id:
        try:
            from core.store import list_employees
            for emp in list_employees(org_id):
                fn = str(emp.get("full_name") or "").lower()
                em = str(emp.get("email") or "").lower()
                ck = str(emp.get("clerk_user_id") or "").lower()
                if (rec_clean and (rec_clean in fn or fn in rec_clean or rec_clean == em or rec_clean == ck)) and emp.get("slack_id"):
                    return str(emp["slack_id"])
        except Exception:
            pass
    return None


def open_slack_dm_channel(client: Any, slack_user_id: str) -> Optional[str]:
    """Open or retrieve a real 1-on-1 direct message (IM) channel via conversations.open."""
    if not slack_user_id:
        return None
    if slack_user_id in _DM_CHANNEL_CACHE:
        return _DM_CHANNEL_CACHE[slack_user_id]
    try:
        resp = client.conversations_open(users=slack_user_id)
        if resp.get("ok") and resp.get("channel", {}).get("id"):
            dm_channel = str(resp["channel"]["id"])
            _DM_CHANNEL_CACHE[slack_user_id] = dm_channel
            logger.info("Opened Slack DM channel '%s' for user '%s'", dm_channel, slack_user_id)
            return dm_channel
    except Exception as exc:
        logger.warning("Slack conversations_open(%s) failed: %s", slack_user_id, exc)
    return None


def send_direct_slack_dm(slack_user_id: str, text: str) -> Optional[str]:
    """Send a direct 1-on-1 Slack message to a user via conversations.open."""
    settings = get_settings()
    if not has_real_slack_creds() or settings.demo_mode or not slack_user_id:
        return f"demo_dm_ts_{int(time.time())}"
    try:
        from slack_sdk import WebClient

        client = WebClient(token=settings.slack_bot_token)
        dm_ch = open_slack_dm_channel(client, slack_user_id)
        if not dm_ch:
            return None
        res = client.chat_postMessage(channel=dm_ch, text=text)
        return str(res.get("ts") or "")
    except Exception as exc:
        logger.warning("send_direct_slack_dm(%s) failed: %s", slack_user_id, exc)
        return None


def get_slack_dm_link(slack_user_id: Optional[str] = None) -> str:
    """Generate Slack deep link URL for a user or channel."""
    team_id = os.getenv("SLACK_TEAM_ID", "").strip()
    if not slack_user_id:
        return f"https://app.slack.com/client/{team_id}" if team_id else "https://app.slack.com/client"
    dm_ch = _DM_CHANNEL_CACHE.get(slack_user_id)
    if team_id and dm_ch:
        return f"https://app.slack.com/client/{team_id}/{dm_ch}"
    if dm_ch:
        return f"https://app.slack.com/client/{dm_ch}"
    if team_id and slack_user_id:
        return f"https://app.slack.com/client/{team_id}/{slack_user_id}"
    return "https://app.slack.com/client"


def resolve_live_slack_channel(client: Any, preferred_channel: str) -> str:
    """Resolve Slack channel ID cleanly, falling back to accessible workspace channels."""
    pref_clean = (preferred_channel or "").strip().lstrip("#").lower()
    fallback_order = ["all-veridian-workos", "general", "new-channel", "social"]
    try:
        resp = client.conversations_list(
            types="public_channel",
            exclude_archived=True,
            limit=200,
        )
        channels = resp.get("channels") or []
    except Exception as exc:
        logger.warning("Slack conversations_list failed (%s); using configured '%s'", exc, preferred_channel)
        return preferred_channel

    if not channels:
        return preferred_channel

    chosen = None
    for ch in channels:
        if (ch.get("id") or "").lower() == pref_clean or (ch.get("name") or "").lower() == pref_clean:
            chosen = ch
            break

    if chosen is None:
        by_name = {(ch.get("name") or "").lower(): ch for ch in channels}
        for name in fallback_order:
            if name in by_name:
                chosen = by_name[name]
                break
        if chosen is None:
            chosen = next((ch for ch in channels if ch.get("is_member")), channels[0])

    ch_id = str(chosen.get("id") or preferred_channel)
    if chosen and not chosen.get("is_member") and not chosen.get("is_private"):
        try:
            client.conversations_join(channel=ch_id)
        except Exception as join_exc:
            logger.debug("Slack conversations_join(%s) skipped: %s", ch_id, join_exc)
    return ch_id


def post_slack_message(
    org_id: str,
    thread_id: str,
    role: str,
    recipient: str,
    text: str,
    channel_kind: str = "summary",
    blocks: Optional[List[Dict[str, Any]]] = None,
    thread_ts: Optional[str] = None,
    task_id: Optional[str] = None,
    jira_key: Optional[str] = None,
    kind: str = "message",
    metadata: Optional[Dict[str, Any]] = None,
    target_channel_id: Optional[str] = None,
) -> tuple[bool, str, str]:
    """Post message to Slack (DM/channel) and always mirror it to the thread slack_feed."""
    settings = get_settings()
    preferred = target_channel_id or resolve_slack_channel(channel_kind)

    sent = False
    resolved_channel = preferred
    ts = f"demo_ts_{kind}_{task_id or thread_id}"

    slack_uid = resolve_slack_user_id(recipient, role=role, org_id=org_id)

    if has_real_slack_creds() and not settings.demo_mode:
        try:
            from slack_sdk import WebClient

            client = WebClient(token=settings.slack_bot_token)
            if target_channel_id:
                resolved_channel = target_channel_id
            elif slack_uid:
                dm_ch = open_slack_dm_channel(client, slack_uid)
                resolved_channel = dm_ch or resolve_live_slack_channel(client, preferred)
            else:
                resolved_channel = resolve_live_slack_channel(client, preferred)

            kwargs: Dict[str, Any] = {
                "channel": resolved_channel,
                "text": text,
            }
            if blocks:
                kwargs["blocks"] = blocks
            if thread_ts and not str(thread_ts).startswith("demo_"):
                kwargs["thread_ts"] = thread_ts
            msg = client.chat_postMessage(**kwargs)
            sent = bool(msg.get("ok", True))
            ts = str(msg.get("ts") or ts)
        except Exception as exc:
            logger.warning("Slack post_slack_message failed (%s); feed mirrored locally.", exc)
    elif settings.demo_mode:
        sent = True
        if slack_uid:
            resolved_channel = f"D_{slack_uid}"

    record_slack_feed_message(
        org_id=org_id,
        thread_id=thread_id,
        role=role,
        sender="Veridian Bot",
        recipient=recipient,
        text=text,
        slack_channel=resolved_channel,
        slack_ts=ts,
        task_id=task_id,
        jira_key=jira_key,
        kind=kind,
        metadata=metadata,
    )
    return sent, resolved_channel, ts


def collect_compliance_alerts(tasks: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build structured immediate alerts for over-budget spend, security policy, and blocked APIs."""
    alerts: List[Dict[str, str]] = []
    for tid, task in (tasks or {}).items():
        if task.get("finance_flag"):
            alerts.append({
                "task_id": tid,
                "type": "BUDGET",
                "title": task.get("title") or tid,
                "message": str(task["finance_flag"]),
                "provenance": str(task.get("finance_provenance") or "Finance CSV"),
            })
        if task.get("security_flag"):
            flag_str = str(task["security_flag"])
            alert_type = "BLOCKED_API" if "SEC-POL-104" in flag_str or "api" in flag_str.lower() else "POLICY"
            alerts.append({
                "task_id": tid,
                "type": alert_type,
                "title": task.get("title") or tid,
                "message": flag_str,
                "provenance": str(task.get("security_provenance") or "Security Policy RAG"),
            })
    return alerts


def send_immediate_compliance_alert(
    org_id: str,
    thread_id: str,
    meeting_id: str,
    tasks: Dict[str, Any],
) -> List[Dict[str, str]]:
    """Immediately DM the Manager if budget, policy, or blocked-API violations are detected."""
    alerts = collect_compliance_alerts(tasks)
    if not alerts:
        return []

    bullet_lines = [
        f"• *[{a['type']}]* (`{a['task_id']}` — {a['title']}): {a['message']}"
        for a in alerts
    ]
    alert_text = (
        f"*[IMMEDIATE COMPLIANCE ALERT]* · Meeting `{meeting_id}` triggered "
        f"{len(alerts)} compliance violation(s):\n" + "\n".join(bullet_lines)
    )
    post_slack_message(
        org_id=org_id,
        thread_id=thread_id,
        role="manager",
        recipient="Manager",
        text=alert_text,
        channel_kind="manager",
        kind="compliance_alert",
        metadata={"alerts": alerts},
    )
    return alerts


def send_manager_review_menu(
    org_id: str,
    thread_id: str,
    meeting_id: str,
    title: str,
    tasks: Dict[str, Any],
    resolutions: List[Dict[str, Any]],
) -> tuple[bool, str, str]:
    """Send Slack Block Kit review menu DM to Manager before any Jira tickets are created."""
    settings = get_settings()
    approve_url = f"{settings.frontend_url.rstrip('/')}/workos?thread={thread_id}&action=approve"
    res_map = {r["task_id"]: r for r in (resolutions or []) if r.get("task_id")}

    summary_lines: List[str] = [
        f"*[MANAGER REVIEW MENU]* Sprint Governance Summary for *{title or meeting_id}* (`{len(tasks)}` task(s) — zero Jira tickets created yet):"
    ]
    blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Sprint Governance Review: {str(title or meeting_id)[:70]}"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Review extracted tasks, proposed commit messages, compliance flags, and leave-redirection recommendations. *No Jira tickets have been created yet.*",
            },
        },
        {"type": "divider"},
    ]

    for tid, t in (tasks or {}).items():
        res = res_map.get(tid) or {}
        action = res.get("suggested_action") or t.get("resolution_action") or "PROCEED"
        task_title = t.get("reframed_title") or t.get("title") or tid
        desc = t.get("reframed_description") or t.get("transcript_quote") or "Extracted from sprint discussion."
        commit_msg = t.get("proposed_commit_message") or f"chore(sprint): {str(task_title).lower()[:60]}"
        assignee = t.get("assignee") or "UNASSIGNED"
        leave_rec = t.get("leave_recommendation")

        flags: List[str] = []
        if t.get("finance_flag"):
            flags.append(f"Budget: {t['finance_flag']}")
        if t.get("security_flag"):
            flags.append(f"Policy: {t['security_flag']}")
        if t.get("hr_status") and t["hr_status"] not in {"ACTIVE", "NOT_FOUND", None}:
            flags.append(f"HR: {t['hr_status']}")

        line = (
            f"• *`{tid}` — {task_title}* (`{action}`)\n"
            f"  Assignee: *{assignee}* | Commit: `{commit_msg}`\n"
            f"  Details: {desc[:180]}"
        )
        if flags:
            line += "\n  Flags: " + " · ".join(flags)
        if leave_rec:
            line += f"\n  Leave Redirect: {leave_rec}"
        summary_lines.append(line)

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": line[:2900]},
        })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "style": "primary",
                "text": {"type": "plain_text", "text": "Approve & Create Tickets"},
                "action_id": "approve_sprint_tickets",
                "value": thread_id,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Open Manager Dashboard"},
                "url": approve_url,
            },
        ],
    })
    summary_lines.append(
        f"\nReply `approve` in this thread or click *Approve & Create Tickets* ({approve_url})."
    )

    text = "\n".join(summary_lines)
    ok, channel, ts = post_slack_message(
        org_id=org_id,
        thread_id=thread_id,
        role="manager",
        recipient="Manager",
        text=text,
        channel_kind="manager",
        blocks=blocks,
        kind="review_menu",
        metadata={"approve_url": approve_url, "task_count": len(tasks)},
    )
    if ts:
        upsert_slack_thread(
            org_id=org_id,
            thread_id=thread_id,
            task_id="__MANAGER_REVIEW__",
            jira_key=None,
            slack_channel=channel,
            slack_thread_ts=ts,
            assignee="Manager",
            turn_count=0,
            status="AWAITING_MANAGER_APPROVAL",
        )
    return ok, channel, ts


def post_employee_assignment_dm(
    org_id: str,
    thread_id: str,
    task_id: str,
    assignee: str,
    jira_key: str,
    jira_url: str,
    task_title: str,
    commit_message: str,
    quote: str,
) -> tuple[bool, str, str]:
    """Send 1-on-1 task assignment DM to approved assignee after ticket creation."""
    text = (
        f"*[1-on-1 Task Assignment — @{assignee}]*\n"
        f"Your sprint ticket *{jira_key}* ({jira_url}) has been approved and created:\n"
        f"• *Task:* {task_title}\n"
        f"• *Proposed Commit:* `{commit_message}`\n"
        f"> \"{quote}\""
    )
    ok, channel, ts = post_slack_message(
        org_id=org_id,
        thread_id=thread_id,
        role="employee",
        recipient=assignee,
        text=text,
        channel_kind="summary",
        task_id=task_id,
        jira_key=jira_key,
        kind="assignment",
    )
    return ok, channel, ts


def post_employee_checkin_dm(
    org_id: str,
    thread_id: str,
    task_id: str,
    assignee: str,
    jira_key: str,
    task_title: str,
    channel_id: Optional[str] = None,
    thread_ts: Optional[str] = None,
) -> tuple[bool, str, str]:
    """Send scheduled 1-on-1 check-in question to an assigned employee."""
    text = (
        f"Hi {assignee}, status check on `{jira_key}` ({task_title}): "
        "what is your progress %, what have you completed so far, and are there any blockers?"
    )
    return post_slack_message(
        org_id=org_id,
        thread_id=thread_id,
        role="employee",
        recipient=assignee,
        text=text,
        channel_kind="summary",
        thread_ts=thread_ts,
        target_channel_id=channel_id,
        task_id=task_id,
        jira_key=jira_key,
        kind="checkin",
    )


def post_manager_progress_digest(
    org_id: str,
    thread_id: str,
    assignee: str,
    jira_key: str,
    task_id: str,
    progress_pct: int,
    completed_milestones: str,
    blockers: str,
) -> tuple[bool, str, str]:
    """Send executive Progress Digest DM to Manager."""
    text = (
        f"*[Progress Digest]* `{jira_key}` (@{assignee}): *{progress_pct}% complete*\n"
        f"• *Completed:* {completed_milestones}\n"
        f"• *Blockers:* {blockers or 'None'}"
    )
    return post_slack_message(
        org_id=org_id,
        thread_id=thread_id,
        role="manager",
        recipient="Manager",
        text=text,
        channel_kind="manager",
        task_id=task_id,
        jira_key=jira_key,
        kind="progress_digest",
        metadata={"progress_pct": progress_pct, "blockers": blockers},
    )


def post_manager_review_request_dm(
    org_id: str,
    thread_id: str,
    assignee: str,
    jira_key: str,
    jira_url: str,
    task_id: str,
    reply_text: str,
    commit_summary: str,
) -> tuple[bool, str, str]:
    """Notify Manager that employee claimed task completion without commit/PR evidence, providing review buttons."""
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*[Completion Review Requested]*\n"
                    f"*{assignee}* claimed completion on `{jira_key}` without direct commit hash or PR URL evidence.\n"
                    f"• *Status:* Moved to `In Review`\n"
                    f"• *Update:* \"{reply_text}\"\n"
                    f"• *Summary:* `{commit_summary}`\n"
                    f"Please review and confirm closure or request rework:"
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Confirm Done"},
                    "style": "primary",
                    "action_id": "confirm_task_done",
                    "value": f"{thread_id}:{task_id}",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Request Rework"},
                    "style": "danger",
                    "action_id": "reject_task_done",
                    "value": f"{thread_id}:{task_id}",
                },
            ],
        },
    ]
    fallback_text = f"[Completion Review] {assignee} claims {jira_key} done. Action required: Confirm Done or Request Rework."
    return post_slack_message(
        org_id=org_id,
        thread_id=thread_id,
        role="manager",
        recipient="Manager",
        text=fallback_text,
        blocks=blocks,
        channel_kind="manager",
        task_id=task_id,
        jira_key=jira_key,
        kind="completion_review",
        metadata={"task_id": task_id, "status": "IN_REVIEW"},
    )


def post_closure_confirmation_dms(
    org_id: str,
    thread_id: str,
    assignee: str,
    jira_key: str,
    jira_url: str,
    task_id: str,
    commit_summary: str,
) -> None:
    """Notify both employee and Manager when Jira ticket is automatically closed (Done)."""
    emp_text = (
        f"Confirmed! Marked `{jira_key}` ({jira_url}) as *Done* automatically.\n"
        f"• *Commit & Completion Summary:* `{commit_summary}`"
    )
    post_slack_message(
        org_id=org_id,
        thread_id=thread_id,
        role="employee",
        recipient=assignee,
        text=emp_text,
        channel_kind="summary",
        task_id=task_id,
        jira_key=jira_key,
        kind="closure",
    )

    mgr_text = (
        f"*[Task Completed & Ticket Closed]* `{jira_key}` ({jira_url}) for *{assignee}* "
        f"has been automatically transitioned to *Done*.\n"
        f"• *Final Commit Summary:* `{commit_summary}`"
    )
    post_slack_message(
        org_id=org_id,
        thread_id=thread_id,
        role="manager",
        recipient="Manager",
        text=mgr_text,
        channel_kind="manager",
        task_id=task_id,
        jira_key=jira_key,
        kind="closure",
        metadata={"commit_summary": commit_summary, "jira_status": "Done"},
    )

