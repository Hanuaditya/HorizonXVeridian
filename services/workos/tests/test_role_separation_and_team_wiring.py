"""Tests for Role-Based UI Separation (org:member 403 protection), Jira accountId lookup,
individual Slack DM routing (U_MGR_DEMO, U_EMP_A_DEMO, U_EMP_B_DEMO), and Smart Leave auto-close.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.auth import mint_demo_jwt
from api.main import app
from connectors.jira_ops import create_jira_issue, lookup_jira_account_id
from connectors.slack_ops import (
    EMPLOYEE_A_SLACK_USER_ID,
    EMPLOYEE_B_SLACK_USER_ID,
    MANAGER_SLACK_USER_ID,
    post_employee_assignment_dm,
    post_slack_message,
    resolve_slack_user_id,
)
from core.store import (
    find_best_domain_replacement,
    get_local_store,
    save_thread_snapshot,
    upsert_employee_mapping,
)


@pytest.fixture(autouse=True)
def reset_store_and_env(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("SHARED_HMAC_SECRET", "dev-demo-secret")
    get_local_store().reset(seed_default_org=True)


def test_org_member_403_protection():
    """Verify non-admin users (org:member) are forbidden (403) from approving or triggering check-ins."""
    client = TestClient(app)
    tid = "test-thr-rbac-403"

    save_thread_snapshot(
        thread_id=tid,
        org_id="org_demo_horizon",
        snapshot={
            "meeting_id": "mtg-rbac",
            "title": "RBAC Test",
            "phase": "HITL",
            "tasks": {"t1": {"task_id": "t1", "status": "PENDING"}},
            "dispatched_tickets": [],
        },
    )

    member_jwt = mint_demo_jwt("user_member_1", "org_demo_horizon", "org:member")
    headers_member = {"Authorization": f"Bearer {member_jwt}"}

    # 1. Member calling /threads/{tid}/checkin -> 403 Forbidden
    res_chk = client.post(f"/api/threads/{tid}/checkin", headers=headers_member)
    assert res_chk.status_code == 403
    assert "Manager role required" in res_chk.json()["detail"]

    # 2. Member calling /threads/{tid}/approve -> 403 Forbidden
    res_app = client.post(f"/api/threads/{tid}/approve", json={}, headers=headers_member)
    assert res_app.status_code == 403
    assert "Manager role required" in res_app.json()["detail"]

    # 3. Member calling /api/hitl-resume -> 403 Forbidden
    res_hitl = client.post(
        "/api/hitl-resume",
        json={"thread_id": tid, "hitl_decisions": {"t1": "PROCEED"}},
        headers=headers_member,
    )
    assert res_hitl.status_code == 403
    assert "Manager role required" in res_hitl.json()["detail"]

    # 4. Manager (org:admin) is authorized and does not receive 403
    admin_jwt = mint_demo_jwt("user_admin_1", "org_demo_horizon", "org:admin")
    headers_admin = {"Authorization": f"Bearer {admin_jwt}"}

    res_admin_chk = client.post(f"/api/threads/{tid}/checkin", headers=headers_admin)
    assert res_admin_chk.status_code != 403


def test_jira_email_to_account_id_lookup(monkeypatch):
    """Verify Jira accountId resolution via /rest/api/3/user/search and assignee binding."""
    import connectors.jira_ops as jops

    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("JIRA_BASE_URL", "https://example-veridian.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "bot@veridian.local")
    monkeypatch.setenv("JIRA_API_TOKEN", "test_jira_token")

    captured_requests = []

    def mock_jira_get(url, **kwargs):
        captured_requests.append(("GET", url, kwargs))
        if "/user/search" in url:
            query = kwargs.get("params", {}).get("query", "")
            return SimpleNamespace(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: [{"accountId": f"acc_{query.split('@')[0]}", "displayName": query}],
            )
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None, json=lambda: {})

    def mock_jira_post(url, **kwargs):
        captured_requests.append(("POST", url, kwargs.get("json")))
        return SimpleNamespace(
            status_code=201,
            raise_for_status=lambda: None,
            json=lambda: {"key": "SCRUM-501", "id": "10501"},
        )

    monkeypatch.setattr(jops.httpx, "get", mock_jira_get)
    monkeypatch.setattr(jops.httpx, "post", mock_jira_post)

    # 1. Lookup accountId directly
    acc_id = lookup_jira_account_id("rohan.patel@example.com")
    assert acc_id == "acc_ifcatchme34"
    assert any("/rest/api/3/user/search" in r[1] for r in captured_requests)

    # 2. Create Jira issue for catchme if -> payload must contain fields.assignee = {"accountId": ...}
    res = create_jira_issue(
        title="Deploy Elastic cluster",
        description="Task extracted from meeting",
        assignee="catchme if",
        task_id="t1",
        commit_message="feat(infra): deploy elastic",
        assignee_email="rohan.patel@example.com",
    )
    assert res["ticket_id"] == "SCRUM-501"
    post_call = next(r for r in captured_requests if r[0] == "POST")
    posted_payload = post_call[2]
    assert posted_payload["fields"]["assignee"] == {"accountId": "acc_ifcatchme34"}


def test_individual_slack_dm_routing(monkeypatch):
    """Verify distinct Slack DM routing to Manager, Employee A, and Employee B."""
    import connectors.slack_ops as s_ops

    # 1. Verify user ID resolver maps to exact Slack IDs
    assert resolve_slack_user_id("Manager", role="manager") == MANAGER_SLACK_USER_ID
    assert resolve_slack_user_id("Hanu Aditya", role="manager") == MANAGER_SLACK_USER_ID
    assert resolve_slack_user_id("catchme if", role="employee") == EMPLOYEE_A_SLACK_USER_ID
    assert resolve_slack_user_id("rohan.patel@example.com", role="employee") == EMPLOYEE_A_SLACK_USER_ID
    assert resolve_slack_user_id("Resigo", role="employee") == EMPLOYEE_B_SLACK_USER_ID
    assert resolve_slack_user_id("priya.sen@example.com", role="employee") == EMPLOYEE_B_SLACK_USER_ID

    # 2. In live mode with mock WebClient, verify conversations_open is called per user
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-real-token")

    fake_client = MagicMock()
    fake_client.conversations_open.side_effect = lambda users: {
        "ok": True,
        "channel": {"id": f"D_FOR_{users}"},
    }
    fake_client.chat_postMessage.return_value = {"ok": True, "ts": "1700000001.001"}

    monkeypatch.setattr(s_ops, "_DM_CHANNEL_CACHE", {})
    monkeypatch.setattr("slack_sdk.WebClient", lambda token: fake_client)

    # Manager review menu / alert
    ok, ch_mgr, _ = post_slack_message(
        org_id="org_demo_horizon",
        thread_id="thr-slack-test",
        role="manager",
        recipient="Manager",
        text="Review menu",
    )
    assert ok is True
    assert ch_mgr == f"D_FOR_{MANAGER_SLACK_USER_ID}"

    # Employee A 1-on-1 DM
    ok_a, ch_a, _ = post_employee_assignment_dm(
        org_id="org_demo_horizon",
        thread_id="thr-slack-test",
        task_id="t1",
        assignee="catchme if",
        jira_key="SCRUM-10",
        jira_url="https://demo.atlassian.net/browse/SCRUM-10",
        task_title="Backend deployment",
        commit_message="feat: deploy",
        quote="Deploy elastic",
    )
    assert ok_a is True
    assert ch_a == f"D_FOR_{EMPLOYEE_A_SLACK_USER_ID}"

    # Employee B 1-on-1 DM
    ok_b, ch_b, _ = post_employee_assignment_dm(
        org_id="org_demo_horizon",
        thread_id="thr-slack-test",
        task_id="t2",
        assignee="Resigo",
        jira_key="SCRUM-11",
        jira_url="https://demo.atlassian.net/browse/SCRUM-11",
        task_title="Frontend auth checkout",
        commit_message="feat: auth",
        quote="React auth flow",
    )
    assert ok_b is True
    assert ch_b == f"D_FOR_{EMPLOYEE_B_SLACK_USER_ID}"


def test_smart_leave_redirection_recommends_catchme_if():
    """Verify Smart Leave Redirection recommends 'catchme if' when Jason is on leave."""
    upsert_employee_mapping(
        org_id="org_demo_horizon",
        full_name="catchme if",
        clerk_user_id="user_clerk_emp_a_demo",
        slack_id="U_EMP_A_DEMO",
        email="rohan.patel@example.com",
        domain_skills=["elasticsearch", "aws", "backend", "infra", "kubernetes"],
        active_task_count=1,
    )
    upsert_employee_mapping(
        org_id="org_demo_horizon",
        full_name="Josh Lambert",
        domain_skills=["elasticsearch", "aws", "backend", "infra", "kubernetes"],
        active_task_count=3,
    )
    upsert_employee_mapping(
        org_id="org_demo_horizon",
        full_name="Resigo",
        clerk_user_id="user_clerk_emp_b_demo",
        slack_id="U_EMP_B_DEMO",
        email="priya.sen@example.com",
        domain_skills=["frontend", "auth", "oauth", "ui", "api"],
        active_task_count=2,
    )

    # Arjun Rao has backend/elasticsearch task while on leave
    replacement = find_best_domain_replacement(
        org_id="org_demo_horizon",
        task_text="Deploy Elastic search cluster directly to AWS production",
        resource_type="compute",
        exclude_name="Arjun Rao",
    )
    assert replacement is not None
    assert replacement["full_name"] == "catchme if"
    assert "elasticsearch" in replacement.get("matched_skills", []) or "aws" in replacement.get("matched_skills", [])
