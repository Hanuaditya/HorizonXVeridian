"""Unified Jira Cloud REST v3 connector (create issue, progress comment, auto-transition to Done)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from core.config import get_settings
from core.evon_llm import resolve_jira_project_key

logger = logging.getLogger(__name__)


def has_real_jira_creds() -> bool:
    settings = get_settings()
    return bool(
        settings.jira_base_url
        and settings.jira_email
        and settings.jira_api_token
        and "yourcompany" not in settings.jira_base_url.lower()
        and "placeholder" not in settings.jira_api_token.lower()
    )


def _adf_doc(text: str) -> Dict[str, Any]:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text or "Updated by Horizon Veridian WorkOS"}],
            }
        ],
    }


def create_jira_issue(
    title: str,
    description: str,
    assignee: str,
    task_id: str,
    commit_message: Optional[str] = None,
) -> Dict[str, str]:
    """Create a Jira issue in allow-listed JIRA_PROJECT_KEY (e.g., SCRUM)."""
    settings = get_settings()
    project_key = resolve_jira_project_key()

    full_desc = description or ""
    if assignee:
        full_desc = f"Assigned Employee: {assignee}\n\n{full_desc}".strip()
    if commit_message:
        full_desc = f"{full_desc}\n\nProposed Commit Message:\n{commit_message}".strip()

    if not has_real_jira_creds():
        if settings.demo_mode:
            num = "".join(c for c in task_id if c.isdigit()) or "1"
            key = f"{project_key}-{100 + int(num)}"
            return {
                "ticket_id": key,
                "url": f"https://veridian-demo.atlassian.net/browse/{key}",
                "mode": "demo_mock",
                "jira_status": "To Do",
            }
        raise EnvironmentError("Jira credentials required when DEMO_MODE=false.")

    endpoint = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue"
    payload: Dict[str, Any] = {
        "fields": {
            "project": {"key": project_key},
            "summary": title,
            "description": _adf_doc(full_desc),
            "issuetype": {"name": "Task"},
            "labels": ["horizon-veridian", "meeting-extracted"],
        }
    }
    resp = httpx.post(
        endpoint,
        json=payload,
        auth=(settings.jira_email, settings.jira_api_token),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    key = str(data.get("key") or f"{project_key}-0")
    return {
        "ticket_id": key,
        "url": f"{settings.jira_base_url.rstrip('/')}/browse/{key}",
        "mode": "live_jira",
        "jira_status": "To Do",
    }


def add_jira_comment(ticket_id: str, comment_text: str) -> bool:
    """Append a structured progress or completion comment on a Jira ticket."""
    if not ticket_id:
        return False
    settings = get_settings()
    if not has_real_jira_creds():
        if settings.demo_mode:
            return True
        return False

    endpoint = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue/{ticket_id}/comment"
    resp = httpx.post(
        endpoint,
        json={"body": _adf_doc(comment_text)},
        auth=(settings.jira_email, settings.jira_api_token),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=15.0,
    )
    resp.raise_for_status()
    return True


def transition_jira_issue_done(
    ticket_id: str,
    completion_summary: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve the 'Done' transition ID dynamically and transition Jira issue to Done."""
    if not ticket_id:
        return {"transitioned": False, "status": "UNKNOWN", "reason": "missing ticket_id"}

    settings = get_settings()
    if not has_real_jira_creds():
        if settings.demo_mode:
            return {"transitioned": True, "status": "Done", "mode": "demo_mock"}
        return {"transitioned": False, "status": "To Do", "reason": "jira creds unset"}

    base = settings.jira_base_url.rstrip("/")
    trans_url = f"{base}/rest/api/3/issue/{ticket_id}/transitions"
    resp = httpx.get(
        trans_url,
        auth=(settings.jira_email, settings.jira_api_token),
        headers={"Accept": "application/json"},
        timeout=15.0,
    )
    resp.raise_for_status()
    transitions = resp.json().get("transitions") or []

    done_transition = next(
        (
            t
            for t in transitions
            if str(t.get("name") or "").strip().lower() in {"done", "closed", "resolved", "complete"}
            or str((t.get("to") or {}).get("statusCategory", {}).get("key") or "").lower() == "done"
        ),
        None,
    )

    transitioned = False
    if done_transition and done_transition.get("id"):
        post_resp = httpx.post(
            trans_url,
            json={"transition": {"id": str(done_transition["id"])}},
            auth=(settings.jira_email, settings.jira_api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=15.0,
        )
        post_resp.raise_for_status()
        transitioned = True
    else:
        logger.warning("No Done transition found for %s among %s", ticket_id, transitions)

    if completion_summary:
        try:
            add_jira_comment(ticket_id, completion_summary)
        except Exception as exc:
            logger.warning("Completion comment on %s failed: %s", ticket_id, exc)

    return {
        "transitioned": transitioned,
        "status": "Done" if transitioned else "To Do",
        "mode": "live_jira",
    }
