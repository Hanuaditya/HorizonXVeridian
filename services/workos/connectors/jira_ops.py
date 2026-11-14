"""Unified Jira Cloud REST v3 connector (create issue, progress comment, auto-transition to Done)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

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


_JIRA_ACCOUNT_ID_CACHE: Dict[str, str] = {}


def lookup_jira_account_id(
    query_str: str,
    org_id: Optional[str] = None,
) -> Optional[str]:
    """Look up Jira accountId by email or name using /rest/api/3/user/search."""
    clean = (query_str or "").strip()
    if not clean:
        return None
    if clean in _JIRA_ACCOUNT_ID_CACHE:
        return _JIRA_ACCOUNT_ID_CACHE[clean]

    settings = get_settings()
    if not has_real_jira_creds():
        if settings.demo_mode:
            mock_acc = f"demo-acc-{clean.split('@')[0].lower().replace(' ', '-')}"
            _JIRA_ACCOUNT_ID_CACHE[clean] = mock_acc
            return mock_acc
        return None

    endpoint = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/user/search"
    try:
        resp = httpx.get(
            endpoint,
            params={"query": clean},
            auth=(settings.jira_email, settings.jira_api_token),
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            users = resp.json()
            if isinstance(users, list) and len(users) > 0:
                acc_id = users[0].get("accountId")
                if acc_id:
                    _JIRA_ACCOUNT_ID_CACHE[clean] = str(acc_id)
                    logger.info("Resolved Jira accountId '%s' for '%s'", acc_id, clean)
                    return str(acc_id)
    except Exception as exc:
        logger.warning("Jira user search failed for '%s': %s", clean, exc)
    return None


def create_jira_issue(
    title: str,
    description: str,
    assignee: str,
    task_id: str,
    commit_message: Optional[str] = None,
    org_id: Optional[str] = None,
    assignee_email: Optional[str] = None,
    jira_account_id: Optional[str] = None,
) -> Dict[str, str]:
    """Create a Jira issue in allow-listed JIRA_PROJECT_KEY (e.g., SCRUM) assigned to the employee."""
    settings = get_settings()
    project_key = resolve_jira_project_key()

    full_desc = description or ""
    if assignee:
        full_desc = f"Assigned Employee: {assignee}\n\n{full_desc}".strip()
    if commit_message:
        full_desc = f"{full_desc}\n\nProposed Commit Message:\n{commit_message}".strip()

    # Resolve Jira accountId if not already provided
    resolved_acc_id = jira_account_id
    if not resolved_acc_id and assignee_email:
        resolved_acc_id = lookup_jira_account_id(assignee_email, org_id=org_id)
    if not resolved_acc_id and assignee:
        known_emails = {
            "rohan patel": "rohan.patel@example.com",
            "priya sen": "priya.sen@example.com",
            "aarav sharma": "aarav.sharma@example.com",
            "arjun rao": "arjun.rao@example.com",
        }
        try:
            from connectors.slack_ops import _LOCAL_TEAM
            for m in _LOCAL_TEAM:
                fn = str(m.get("full_name") or m.get("name") or "").lower()
                em = str(m.get("email") or "")
                if fn and em:
                    known_emails[fn] = em
        except Exception:
            pass
        cand_email = known_emails.get(assignee.lower())
        if cand_email:
            resolved_acc_id = lookup_jira_account_id(cand_email, org_id=org_id)
        if not resolved_acc_id:
            resolved_acc_id = lookup_jira_account_id(assignee, org_id=org_id)

    if not has_real_jira_creds():
        if settings.demo_mode:
            num = "".join(c for c in task_id if c.isdigit()) or "1"
            key = f"{project_key}-{100 + int(num)}"
            return {
                "ticket_id": key,
                "url": f"https://veridian-demo.atlassian.net/browse/{key}",
                "mode": "demo_mock",
                "jira_status": "To Do",
                "assignee_account_id": resolved_acc_id or "demo-acc-assignee",
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
    if resolved_acc_id:
        payload["fields"]["assignee"] = {"accountId": resolved_acc_id}

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
        "assignee_account_id": resolved_acc_id or "",
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


def transition_jira_issue_in_progress(ticket_id: str) -> Dict[str, Any]:
    """Transition Jira issue to In Progress dynamically."""
    if not ticket_id:
        return {"transitioned": False, "status": "UNKNOWN"}
    settings = get_settings()
    if not has_real_jira_creds():
        return {"transitioned": True, "status": "In Progress", "mode": "demo_mock"}

    try:
        base = settings.jira_base_url.rstrip("/")
        trans_url = f"{base}/rest/api/3/issue/{ticket_id}/transitions"
        resp = httpx.get(
            trans_url,
            auth=(settings.jira_email, settings.jira_api_token),
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        transitions = resp.json().get("transitions") or []
        inp_trans = next(
            (
                t for t in transitions
                if "in progress" in str(t.get("name") or "").lower()
                or "progress" in str(t.get("name") or "").lower()
                or str((t.get("to") or {}).get("statusCategory", {}).get("key") or "").lower() in {"indeterminate", "in_progress"}
            ),
            None,
        )
        if inp_trans and inp_trans.get("id"):
            post_resp = httpx.post(
                trans_url,
                json={"transition": {"id": str(inp_trans["id"])}},
                auth=(settings.jira_email, settings.jira_api_token),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=10.0,
            )
            post_resp.raise_for_status()
            return {"transitioned": True, "status": "In Progress", "mode": "live_jira"}
    except Exception as exc:
        logger.warning("transition_jira_issue_in_progress failed for %s: %s", ticket_id, exc)
    return {"transitioned": False, "status": "In Progress"}


def update_jira_issue_summary(ticket_id: str, new_summary: str) -> bool:
    """Update summary title of a Jira ticket (e.g. '[60%] Deploy Elasticsearch...')."""
    if not ticket_id or not new_summary:
        return False
    settings = get_settings()
    if not has_real_jira_creds():
        return True
    try:
        base = settings.jira_base_url.rstrip("/")
        url = f"{base}/rest/api/3/issue/{ticket_id}"
        resp = httpx.put(
            url,
            json={"fields": {"summary": new_summary[:255]}},
            auth=(settings.jira_email, settings.jira_api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("update_jira_issue_summary failed for %s: %s", ticket_id, exc)
        return False


def delete_jira_issue(ticket_id: str) -> bool:
    """Delete a Jira issue or mark deleted."""
    if not ticket_id:
        return False
    settings = get_settings()
    if not has_real_jira_creds():
        return True
    try:
        base = settings.jira_base_url.rstrip("/")
        url = f"{base}/rest/api/3/issue/{ticket_id}?deleteSubtasks=true"
        resp = httpx.delete(
            url,
            auth=(settings.jira_email, settings.jira_api_token),
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("delete_jira_issue failed for %s: %s", ticket_id, exc)
        return False


def purge_all_project_issues(project_key: Optional[str] = None) -> Dict[str, Any]:
    """Query Jira via JQL (project = SCRUM) and delete all existing issues in the project."""
    target_project = project_key or resolve_jira_project_key() or "SCRUM"
    logger.info("purge_all_project_issues: starting purge for Jira project '%s'", target_project)

    settings = get_settings()
    if not has_real_jira_creds():
        logger.info("purge_all_project_issues: mock credentials or demo mode; returning empty purge.")
        return {"purged": 0, "keys": [], "project": target_project, "mode": "demo"}

    base = settings.jira_base_url.rstrip("/")
    auth = (settings.jira_email, settings.jira_api_token)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    jql_query = f"project = {target_project}"

    issue_keys: List[str] = []
    next_page_token: Optional[str] = None

    try:
        # Jira Cloud REST API v3: /rest/api/3/search/jql
        while True:
            body: Dict[str, Any] = {
                "jql": jql_query,
                "fields": ["key"],
                "maxResults": 100,
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token

            resp = httpx.post(
                f"{base}/rest/api/3/search/jql",
                json=body,
                auth=auth,
                headers=headers,
                timeout=15.0,
            )

            # Fallback to legacy GET /rest/api/3/search if search/jql returns 404 or 400
            if resp.status_code in (404, 400):
                resp = httpx.get(
                    f"{base}/rest/api/3/search",
                    params={"jql": jql_query, "fields": "key", "maxResults": 100},
                    auth=auth,
                    headers={"Accept": "application/json"},
                    timeout=15.0,
                )

            if resp.status_code != 200:
                logger.warning(
                    "purge_all_project_issues: JQL query failed (%d): %s",
                    resp.status_code,
                    resp.text,
                )
                break

            data = resp.json() or {}
            issues = data.get("issues") or []
            for item in issues:
                k = item.get("key")
                if k and k not in issue_keys:
                    issue_keys.append(k)

            next_page_token = data.get("nextPageToken")
            is_last = data.get("isLast", True)
            if not issues or is_last or not next_page_token:
                break

    except Exception as exc:
        logger.warning("purge_all_project_issues: failed to query issues via JQL: %s", exc)

    deleted_keys: List[str] = []
    for k in issue_keys:
        try:
            del_resp = httpx.delete(
                f"{base}/rest/api/3/issue/{k}?deleteSubtasks=true",
                auth=auth,
                headers={"Accept": "application/json"},
                timeout=10.0,
            )
            if del_resp.status_code in (200, 204):
                deleted_keys.append(k)
                logger.info("purge_all_project_issues: successfully deleted Jira issue '%s'", k)
            else:
                logger.warning(
                    "purge_all_project_issues: failed to delete issue '%s' (%d): %s",
                    k,
                    del_resp.status_code,
                    del_resp.text,
                )
        except Exception as exc:
            logger.warning("purge_all_project_issues: error deleting issue '%s': %s", k, exc)

    logger.info(
        "purge_all_project_issues: purged %d / %d issues in project '%s'",
        len(deleted_keys),
        len(issue_keys),
        target_project,
    )
    return {
        "purged": len(deleted_keys),
        "keys": deleted_keys,
        "project": target_project,
        "mode": "live_jira",
    }



