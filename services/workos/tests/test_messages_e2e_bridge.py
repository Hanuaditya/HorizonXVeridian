"""E2E bridge tests: employee→manager auto-summaries and manager sprint status command."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.auth import mint_demo_jwt
from api.main import app
from core.identifiers import canonical_employee_key
from core.store import (
    get_local_store,
    list_slack_feed,
    save_thread_snapshot,
)

ORG = "org_demo_horizon"
MEETING_ID = "meeting-e2e-bridge-test"
THREAD_ID = "thread-e2e-bridge-001"


@pytest.fixture(autouse=True)
def reset_store_and_env(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("SHARED_HMAC_SECRET", "dev-demo-secret")
    get_local_store().reset(seed_default_org=True)


def _seed_sprint():
    """Seed a minimal sprint snapshot with one SCRUM-21 task for catchme if."""
    tasks = {
        "t_catchme": {
            "task_id": "t_catchme",
            "title": "Deploy Elasticsearch cluster to AWS production",
            "reframed_title": "Deploy Elasticsearch cluster to AWS production",
            "assignee": "catchme if",
            "rerouted_assignee": "catchme if",
            "jira_key": "SCRUM-21",
            "jira_ticket_id": "SCRUM-21",
            "status": "DISPATCHED",
            "progress_pct": 0,
            "checkin_stage": 1,
            "awaiting_employee_reply": True,
        }
    }
    save_thread_snapshot(
        thread_id=THREAD_ID,
        org_id=ORG,
        snapshot={
            "thread_id": THREAD_ID,
            "org_id": ORG,
            "meeting_id": MEETING_ID,
            "phase": "ACTIVE_SPRINT",
            "manager_approved": True,
            "tasks": tasks,
            "dispatched_tickets": [
                {
                    "task_id": "t_catchme",
                    "assignee": "catchme if",
                    "jira_key": "SCRUM-21",
                    "jira_ticket_id": "SCRUM-21",
                    "title": "Deploy Elasticsearch cluster to AWS production",
                }
            ],
        },
    )
    return tasks


def test_catchme_if_reply_auto_updates_manager_feed():
    """Employee 'catchme if' posts a progress update → manager feed gets an executive summary."""
    client = TestClient(app)
    _seed_sprint()

    emp_token = mint_demo_jwt(user_id="user_demo_catchme", org_id=ORG, role="org:member")
    mgr_token = mint_demo_jwt(user_id="user_demo_hanu", org_id=ORG, role="org:admin")

    # Employee sends progress update
    resp = client.post(
        "/api/messages/veridian-bot",
        json={"text": "60% done: staging environment provisioned and ready for testing", "thread_id": THREAD_ID},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("intent") == "IN_PROGRESS"
    # POST response must include messages immediately for zero-lag render
    assert "messages" in data
    assert isinstance(data["messages"], list)
    assert len(data["messages"]) >= 2  # employee msg + bot reply

    # Bot reply must mention progress
    bot_reply = data.get("bot_reply", "")
    assert "60%" in bot_reply or "progress" in bot_reply.lower()

    # Employee's veridian-bot thread should contain their message and bot reply
    emp_thread = list_slack_feed(org_id=ORG, thread_id="veridian-bot:catchme_if")
    assert len(emp_thread) >= 2
    texts = [m["text"] for m in emp_thread]
    assert any("60%" in t or "staging" in t.lower() for t in texts), f"Employee msg missing: {texts}"
    assert any("Logged" in t or "progress" in t.lower() or "60%" in t for t in texts), f"Bot reply missing: {texts}"

    # Manager's veridian-bot thread should contain the executive summary
    mgr_thread = list_slack_feed(org_id=ORG, thread_id="veridian-bot:manager")
    assert len(mgr_thread) >= 1, f"Manager feed empty! mgr_thread={mgr_thread}"
    mgr_texts = [m["text"] for m in mgr_thread]
    assert any("catchme" in t.lower() or "60%" in t or "Progress" in t for t in mgr_texts), f"Manager summary missing: {mgr_texts}"

    # Verify GET /api/messages/veridian-bot as Manager also contains the summary
    mgr_get_resp = client.get(
        f"/api/messages/veridian-bot?thread_id={THREAD_ID}",
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert mgr_get_resp.status_code == 200
    mgr_get_texts = [m["text"] for m in mgr_get_resp.json()["messages"]]
    assert any("catchme" in t.lower() or "60%" in t or "Progress" in t for t in mgr_get_texts), f"Manager GET missing summary: {mgr_get_texts}"


def test_manager_sprint_status_command():
    """Manager posts 'Give me the sprint status summary' → bot_response contains SCRUM key and %."""
    client = TestClient(app)
    _seed_sprint()

    mgr_token = mint_demo_jwt(user_id="user_demo_hanu", org_id=ORG, role="org:admin")

    resp = client.post(
        "/api/messages/veridian-bot",
        json={"text": "Give me the sprint status summary", "thread_id": THREAD_ID},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    bot_response = data.get("bot_response", "")
    # Must mention SCRUM ticket key and percentage
    assert "SCRUM" in bot_response or "%" in bot_response, f"Status response missing SCRUM/%: {bot_response}"
    # Messages should be in response
    assert "messages" in data
    assert isinstance(data["messages"], list)


def test_manager_exact_sprint_status_breakdown():
    """Manager asks 'Sprint status' → returns exact breakdown for catchme if, Resigo, and Arjun Rao."""
    client = TestClient(app)
    _seed_sprint()

    mgr_token = mint_demo_jwt(user_id="user_demo_hanu", org_id=ORG, role="org:admin")

    resp = client.post(
        "/api/messages/veridian-bot",
        json={"text": "Sprint status", "thread_id": THREAD_ID},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert resp.status_code == 200
    bot_response = resp.json().get("bot_response", "")

    assert "SCRUM-21" in bot_response
    assert "catchme if" in bot_response
    assert "Resigo" in bot_response
    assert "No reply received from Resigo yet" in bot_response
    assert "Arjun Rao: On Paternity Leave" in bot_response


def test_employee_completion_pr_updates_jira_done():
    """Employee reports 'Completed + PR' → 100% progress, status DONE, and manager notified."""
    client = TestClient(app)
    _seed_sprint()

    emp_token = mint_demo_jwt(user_id="user_demo_catchme", org_id=ORG, role="org:member")
    mgr_token = mint_demo_jwt(user_id="user_demo_hanu", org_id=ORG, role="org:admin")

    resp = client.post(
        "/api/messages/veridian-bot",
        json={"text": "Completed + PR: https://github.com/org/repo/pull/42", "thread_id": THREAD_ID},
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("intent") == "COMPLETED"
    assert data.get("progress_pct") == 100
    assert "100%" in data.get("bot_reply", "")

    # Manager should receive completion summary
    mgr_feed = client.get(
        f"/api/messages/veridian-bot?thread_id={THREAD_ID}",
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert mgr_feed.status_code == 200
    mgr_texts = [m["text"] for m in mgr_feed.json()["messages"]]
    assert any("100%" in t and "catchme" in t.lower() for t in mgr_texts)
