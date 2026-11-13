"""Unit tests for the dedicated Messages workspace (/api/messages) & Slack synchronization."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.auth import mint_demo_jwt
from api.main import app
from core.store import (
    get_local_store,
    record_direct_message,
    record_slack_feed_message,
    save_thread_snapshot,
)


@pytest.fixture(autouse=True)
def reset_store_and_env(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("SHARED_HMAC_SECRET", "dev-demo-secret")
    get_local_store().reset(seed_default_org=True)


def test_messages_threads_manager_perspective():
    client = TestClient(app)
    mgr_token = mint_demo_jwt(
        user_id="user_mgr_test",
        org_id="org_demo_horizon",
        role="org:admin",
    )

    res = client.get("/api/messages/threads", headers={"Authorization": f"Bearer {mgr_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["is_manager"] is True
    threads = data["threads"]
    assert len(threads) >= 1

    # First channel is always veridian-bot
    assert threads[0]["channel_key"] == "veridian-bot"
    assert threads[0]["role"] == "bot"

    # Manager sees employee direct channels
    emp_channels = [t for t in threads if t["channel_key"].startswith("emp:")]
    assert len(emp_channels) >= 1
    for emp_ch in emp_channels:
        assert emp_ch["role"] == "employee"
        assert "slack_deep_link" in emp_ch


def test_messages_threads_employee_perspective():
    client = TestClient(app)
    emp_token = mint_demo_jwt(
        user_id="user_emp_test",
        org_id="org_demo_horizon",
        role="org:member",
    )

    res = client.get("/api/messages/threads", headers={"Authorization": f"Bearer {emp_token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["is_manager"] is False
    threads = data["threads"]
    assert len(threads) >= 1

    # Employee sees veridian-bot and manager
    assert threads[0]["channel_key"] == "veridian-bot"
    mgr_channel = next((t for t in threads if t["channel_key"].startswith("mgr:")), None)
    assert mgr_channel is not None
    assert mgr_channel["role"] == "manager"


def test_messages_channel_feed_and_unread_flow():
    client = TestClient(app)
    mgr_token = mint_demo_jwt(
        user_id="user_mgr_unread",
        org_id="org_demo_horizon",
        role="org:admin",
    )

    # Record a governance alert message
    record_slack_feed_message(
        org_id="org_demo_horizon",
        thread_id="thr-test-feed",
        role="manager",
        sender="Veridian Bot",
        recipient="Manager",
        text="[ALERT] Budget exceeded by ₹2.5 Lakhs",
        kind="alert",
    )

    # Check unread count
    unread_res = client.get("/api/messages/unread", headers={"Authorization": f"Bearer {mgr_token}"})
    assert unread_res.status_code == 200
    unread_data = unread_res.json()
    assert unread_data["unread_total"] >= 1
    assert unread_data["by_channel"].get("veridian-bot", 0) >= 1

    # Read channel messages
    ch_res = client.get("/api/messages/veridian-bot", headers={"Authorization": f"Bearer {mgr_token}"})
    assert ch_res.status_code == 200
    ch_data = ch_res.json()
    assert ch_data["count"] >= 1
    assert any("[ALERT]" in m["text"] for m in ch_data["messages"])

    # Unread count should now be 0 for veridian-bot
    unread_after = client.get("/api/messages/unread", headers={"Authorization": f"Bearer {mgr_token}"}).json()
    assert unread_after["by_channel"].get("veridian-bot", 0) == 0


def test_messages_post_manager_command_executes_action():
    client = TestClient(app)
    mgr_token = mint_demo_jwt(
        user_id="user_mgr_cmd",
        org_id="org_demo_horizon",
        role="org:admin",
    )

    # Save active sprint thread snapshot
    save_thread_snapshot(
        thread_id="thr-sprint-cmd",
        org_id="org_demo_horizon",
        snapshot={
            "meeting_id": "mtg-cmd",
            "phase": "COMPLETE",
            "tasks": {
                "t1": {"task_id": "t1", "assignee": "Rohan Patel", "status": "DISPATCHED", "jira_ticket_id": "VER-101"}
            },
            "dispatched_tickets": [
                {"task_id": "t1", "assignee": "Rohan Patel", "jira_status": "To Do", "jira_key": "VER-101"}
            ],
        },
    )

    post_res = client.post(
        "/api/messages/veridian-bot",
        headers={"Authorization": f"Bearer {mgr_token}"},
        json={"text": "Trigger scheduled check-in now", "thread_id": "thr-sprint-cmd"},
    )
    assert post_res.status_code == 200
    post_data = post_res.json()
    assert post_data["status"] == "command_executed"
    assert "Initiated 1-on-1 sprint interval check-ins" in post_data["bot_response"]


def test_messages_post_direct_message_records_stream():
    client = TestClient(app)
    mgr_token = mint_demo_jwt(
        user_id="user_mgr_dm",
        org_id="org_demo_horizon",
        role="org:admin",
    )

    dm_res = client.post(
        "/api/messages/emp:rohan_patel",
        headers={"Authorization": f"Bearer {mgr_token}"},
        json={"text": "Please make sure integration tests run on staging."},
    )
    assert dm_res.status_code == 200
    dm_data = dm_res.json()
    assert dm_data["status"] == "sent"
    assert dm_data["message"]["text"] == "Please make sure integration tests run on staging."

    # Read back direct channel
    fetch_res = client.get("/api/messages/emp:rohan_patel", headers={"Authorization": f"Bearer {mgr_token}"})
    assert fetch_res.status_code == 200
    fetch_data = fetch_res.json()
    assert len(fetch_data["messages"]) >= 1
    assert any("integration tests" in m["text"] for m in fetch_data["messages"])
