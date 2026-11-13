"""Unit tests for employee thread key unification, Stage 1 -> Reply -> Stage 2 check-in state machine,
and automatic executive summary feed for the Manager (/api/messages/veridian-bot).
"""

from __future__ import annotations

import asyncio
import pytest
from fastapi.testclient import TestClient

from api.auth import mint_demo_jwt
from api.main import app
from connectors.sprint_loop import (
    dispatch_stage_2_checkin,
    process_employee_reply,
    trigger_checkin_for_thread,
)
from core.identifiers import canonical_employee_key, is_manager_identity
from core.store import (
    get_local_store,
    get_thread_snapshot,
    record_slack_feed_message,
    save_thread_snapshot,
)


@pytest.fixture(autouse=True)
def reset_store_and_env(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("SHARED_HMAC_SECRET", "dev-demo-secret")
    get_local_store().reset(seed_default_org=True)


def test_canonical_employee_key_resolution():
    """Verify canonical slug resolution across spaces, cases, Clerk user_ids, and emails."""
    assert canonical_employee_key("catchme if") == "catchme_if"
    assert canonical_employee_key("Catchme If") == "catchme_if"
    assert canonical_employee_key("catchme_if") == "catchme_if"
    assert canonical_employee_key("user_demo_catchme") == "catchme_if"
    assert canonical_employee_key("user_catchme") == "catchme_if"
    assert canonical_employee_key("catchme@veridian.io") == "catchme_if"

    assert canonical_employee_key("Resigo") == "resigo"
    assert canonical_employee_key("resigo") == "resigo"
    assert canonical_employee_key("user_demo_resigo") == "resigo"

    assert canonical_employee_key("Arjun Rao") == "arjun_rao"
    assert canonical_employee_key("arjun_rao") == "arjun_rao"

    assert canonical_employee_key("Hanu Aditya") == "hanu_aditya"
    assert canonical_employee_key("Hanuma Aditya") == "hanu_aditya"
    assert canonical_employee_key("hanuma@veridian.io") == "hanu_aditya"

    assert is_manager_identity("Hanuma Aditya") is True
    assert is_manager_identity("Hanu Aditya") is True
    assert is_manager_identity("manager") is True
    assert is_manager_identity("catchme if") is False


def test_catchme_if_and_resigo_receive_assignment_and_checkin_messages():
    """Verify both catchme if and Resigo see their 1-on-1 Task Assignment and checkins in veridian-bot."""
    client = TestClient(app)
    emp_catchme_token = mint_demo_jwt(user_id="user_demo_catchme", org_id="org_demo_horizon", role="org:member")
    emp_resigo_token = mint_demo_jwt(user_id="user_demo_resigo", org_id="org_demo_horizon", role="org:member")

    save_thread_snapshot(
        thread_id="thr-assign-test",
        org_id="org_demo_horizon",
        snapshot={
            "meeting_id": "mtg-assign",
            "phase": "COMPLETE",
            "manager_approved": True,
            "tasks": {
                "t1": {
                    "task_id": "t1",
                    "title": "Deploy Elasticsearch cluster to AWS production",
                    "assignee": "catchme if",
                    "status": "DISPATCHED",
                    "jira_ticket_id": "SCRUM-21",
                    "checkin_stage": 0,
                    "awaiting_employee_reply": False,
                },
                "t2": {
                    "task_id": "t2",
                    "title": "Build OAuth login dashboard",
                    "assignee": "Resigo",
                    "status": "DISPATCHED",
                    "jira_ticket_id": "SCRUM-22",
                    "checkin_stage": 0,
                    "awaiting_employee_reply": False,
                },
            },
            "dispatched_tickets": [
                {"task_id": "t1", "assignee": "catchme if", "jira_key": "SCRUM-21"},
                {"task_id": "t2", "assignee": "Resigo", "jira_key": "SCRUM-22"},
            ],
        },
    )

    # Record 1-on-1 Task Assignment cards for both
    record_slack_feed_message(
        org_id="org_demo_horizon",
        thread_id="thr-assign-test",
        role="employee",
        sender="Veridian Bot",
        recipient="catchme_if",
        text="*[1-on-1 Task Assignment — @catchme if]*\nYour sprint ticket *SCRUM-21* has been approved and created.",
        kind="assignment",
        task_id="t1",
        jira_key="SCRUM-21",
    )
    record_slack_feed_message(
        org_id="org_demo_horizon",
        thread_id="thr-assign-test",
        role="employee",
        sender="Veridian Bot",
        recipient="resigo",
        text="*[1-on-1 Task Assignment — @Resigo]*\nYour sprint ticket *SCRUM-22* has been approved and created.",
        kind="assignment",
        task_id="t2",
        jira_key="SCRUM-22",
    )

    # Fetch catchme if messages
    catchme_res = client.get(
        "/api/messages/veridian-bot?thread_id=thr-assign-test",
        headers={"Authorization": f"Bearer {emp_catchme_token}"},
    )
    assert catchme_res.status_code == 200
    catchme_texts = [m["text"] for m in catchme_res.json()["messages"]]
    assert any("SCRUM-21" in t for t in catchme_texts)
    # catchme if must NOT see Resigo's assignment
    assert not any("SCRUM-22" in t for t in catchme_texts)

    # Fetch Resigo messages
    resigo_res = client.get(
        "/api/messages/veridian-bot?thread_id=thr-assign-test",
        headers={"Authorization": f"Bearer {emp_resigo_token}"},
    )
    assert resigo_res.status_code == 200
    resigo_texts = [m["text"] for m in resigo_res.json()["messages"]]
    assert any("SCRUM-22" in t for t in resigo_texts)
    # Resigo must NOT see catchme if's assignment
    assert not any("SCRUM-21" in t for t in resigo_texts)


def test_checkin_flow_stage_1_hard_blocks_stage_2_until_reply():
    """Verify Stage 1 checkin is sent only when checkin_stage == 0, and subsequent triggers are hard-blocked."""
    save_thread_snapshot(
        thread_id="thr-stage-test",
        org_id="org_demo_horizon",
        snapshot={
            "meeting_id": "mtg-stage",
            "phase": "COMPLETE",
            "manager_approved": True,
            "tasks": {
                "t1": {
                    "task_id": "t1",
                    "title": "Deploy Elasticsearch cluster to AWS production",
                    "assignee": "catchme if",
                    "status": "DISPATCHED",
                    "jira_ticket_id": "SCRUM-21",
                    "checkin_stage": 0,
                    "awaiting_employee_reply": False,
                }
            },
        },
    )

    # 1. First trigger -> Stage 1 sent
    res1 = asyncio.run(trigger_checkin_for_thread("org_demo_horizon", "thr-stage-test"))
    assert len(res1["checkins_sent"]) == 1
    assert res1["checkins_sent"][0]["checkin_stage"] == 1

    snap = get_thread_snapshot("thr-stage-test")
    task = snap["tasks"]["t1"]
    assert task["checkin_stage"] == 1
    assert task["awaiting_employee_reply"] is True

    # Verify Stage 1 text format
    feed = snap["slack_feed"]
    stage1_msgs = [m for m in feed if m.get("kind") == "checkin" and m.get("task_id") == "t1"]
    assert len(stage1_msgs) == 1
    assert "quick check-in on" in stage1_msgs[0]["text"]
    assert "SCRUM-21" in stage1_msgs[0]["text"]
    assert "What % are you at, and are there any blockers?" in stage1_msgs[0]["text"]

    # 2. Second trigger immediately after -> Hard blocked! No duplicate check-in sent
    res2 = asyncio.run(trigger_checkin_for_thread("org_demo_horizon", "thr-stage-test"))
    assert len(res2["checkins_sent"]) == 0

    # Ensure no Stage 2 message was sent prematurely
    snap2 = get_thread_snapshot("thr-stage-test")
    assert snap2["tasks"]["t1"]["checkin_stage"] == 1
    feed2 = snap2["slack_feed"]
    assert not any("wrapping up for the day" in m["text"] for m in feed2)


def test_employee_reply_triggers_stage_2_followup():
    """Verify that employee progress reply clears awaiting_employee_reply and schedules Stage 2."""
    client = TestClient(app)
    emp_token = mint_demo_jwt(user_id="user_demo_catchme", org_id="org_demo_horizon", role="org:member")

    save_thread_snapshot(
        thread_id="thr-reply-stage2",
        org_id="org_demo_horizon",
        snapshot={
            "meeting_id": "mtg-r-stage2",
            "phase": "COMPLETE",
            "manager_approved": True,
            "tasks": {
                "t1": {
                    "task_id": "t1",
                    "title": "Deploy Elasticsearch cluster to AWS production",
                    "assignee": "catchme if",
                    "status": "DISPATCHED",
                    "jira_ticket_id": "SCRUM-21",
                    "checkin_stage": 1,
                    "awaiting_employee_reply": True,
                }
            },
        },
    )

    # Employee sends 60% progress update
    res = client.post(
        "/api/messages/veridian-bot",
        headers={"Authorization": f"Bearer {emp_token}"},
        json={
            "text": "60% completed: index templates and shards configured, testing cluster health.",
            "thread_id": "thr-reply-stage2",
            "task_id": "t1",
        },
    )
    assert res.status_code == 200
    assert res.json()["progress_pct"] == 60

    snap = get_thread_snapshot("thr-reply-stage2")
    task = snap["tasks"]["t1"]
    assert task["awaiting_employee_reply"] is False
    assert task["progress_pct"] == 60

    # Manually invoke dispatch_stage_2_checkin with delay_seconds=0 to verify Stage 2 execution
    asyncio.run(dispatch_stage_2_checkin(
        org_id="org_demo_horizon",
        thread_id="thr-reply-stage2",
        task_id="t1",
        assignee="catchme if",
        jira_key="SCRUM-21",
        task_title=task["title"],
        progress_pct=60,
        delay_seconds=0,
    ))

    snap_after = get_thread_snapshot("thr-reply-stage2")
    task_after = snap_after["tasks"]["t1"]
    assert task_after["checkin_stage"] == 2
    assert task_after["awaiting_employee_reply"] is True

    stage2_msgs = [m for m in snap_after["slack_feed"] if "wrapping up for the day" in m.get("text", "")]
    assert len(stage2_msgs) == 1
    assert "SCRUM-21" in stage2_msgs[0]["text"]
    assert "did you finish Deploy Elasticsearch cluster to AWS production" in stage2_msgs[0]["text"]


def test_completed_reply_sets_stage_3_and_stops_checkins():
    """Verify that a 100% completed reply sets checkin_stage=3, status=DONE, and never dispatches Stage 2."""
    client = TestClient(app)
    emp_token = mint_demo_jwt(user_id="user_demo_catchme", org_id="org_demo_horizon", role="org:member")

    save_thread_snapshot(
        thread_id="thr-complete-test",
        org_id="org_demo_horizon",
        snapshot={
            "meeting_id": "mtg-comp",
            "phase": "COMPLETE",
            "manager_approved": True,
            "tasks": {
                "t1": {
                    "task_id": "t1",
                    "title": "Deploy Elasticsearch cluster to AWS production",
                    "assignee": "catchme if",
                    "status": "DISPATCHED",
                    "jira_ticket_id": "SCRUM-21",
                    "checkin_stage": 1,
                    "awaiting_employee_reply": True,
                    "progress_pct": 60,
                }
            },
        },
    )

    # Employee submits completion with PR
    res = client.post(
        "/api/messages/veridian-bot",
        headers={"Authorization": f"Bearer {emp_token}"},
        json={
            "text": "Completed + PR: https://github.com/veridian/infra/pull/104 - cluster deployed successfully.",
            "thread_id": "thr-complete-test",
            "task_id": "t1",
        },
    )
    assert res.status_code == 200
    assert res.json()["intent"] == "COMPLETED"
    assert res.json()["progress_pct"] == 100

    snap = get_thread_snapshot("thr-complete-test")
    task = snap["tasks"]["t1"]
    assert task["status"] == "DONE"
    assert task["progress_pct"] == 100
    assert task["checkin_stage"] == 3
    assert task["awaiting_employee_reply"] is False

    # Attempting to dispatch Stage 2 must early-exit and do nothing
    asyncio.run(dispatch_stage_2_checkin(
        org_id="org_demo_horizon",
        thread_id="thr-complete-test",
        task_id="t1",
        assignee="catchme if",
        jira_key="SCRUM-21",
        task_title=task["title"],
        progress_pct=100,
        delay_seconds=0,
    ))

    snap_after = get_thread_snapshot("thr-complete-test")
    assert not any("wrapping up for the day" in m.get("text", "") for m in snap_after["slack_feed"])


def test_slack_dm_inbound_reply_inserts_summary_for_manager():
    """Verify that an inbound Slack DM reply inserts [Slack DM Summary — @...] into Hanuma Aditya's feed."""
    client = TestClient(app)
    mgr_token = mint_demo_jwt(user_id="hanuma_aditya", org_id="org_demo_horizon", role="org:admin")

    save_thread_snapshot(
        thread_id="thr-slack-inbound",
        org_id="org_demo_horizon",
        snapshot={
            "meeting_id": "mtg-slack-inbound",
            "phase": "COMPLETE",
            "manager_approved": True,
            "tasks": {
                "t1": {
                    "task_id": "t1",
                    "title": "Deploy Elasticsearch cluster to AWS production",
                    "assignee": "catchme if",
                    "status": "DISPATCHED",
                    "jira_ticket_id": "SCRUM-21",
                    "checkin_stage": 1,
                    "awaiting_employee_reply": True,
                }
            },
        },
    )

    # Inbound Slack reply processed via process_employee_reply
    asyncio.run(process_employee_reply(
        org_id="org_demo_horizon",
        thread_id="thr-slack-inbound",
        task_id="t1",
        reply_text="60% done: cluster deployed on staging VPC, running health benchmarks.",
        source="slack",
        post_to_slack=False,
    ))

    # Hanuma Aditya (Manager) reads /api/messages/veridian-bot
    mgr_res = client.get(
        "/api/messages/veridian-bot?thread_id=thr-slack-inbound",
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert mgr_res.status_code == 200
    mgr_feed = mgr_res.json()["messages"]
    mgr_texts = [m["text"] for m in mgr_feed]

    assert any("[Slack DM Summary — @catchme if]" in t for t in mgr_texts)
    assert any("60% complete" in t for t in mgr_texts)
    assert any("SCRUM-21" in t for t in mgr_texts)


def test_in_app_reply_and_manager_sprint_status_command():
    """Verify in-app employee reply updates manager feed, and Manager sprint status command returns report."""
    client = TestClient(app)
    mgr_token = mint_demo_jwt(user_id="hanuma_aditya", org_id="org_demo_horizon", role="org:admin")
    emp_token = mint_demo_jwt(user_id="user_demo_resigo", org_id="org_demo_horizon", role="org:member")

    save_thread_snapshot(
        thread_id="thr-cmd-test",
        org_id="org_demo_horizon",
        snapshot={
            "meeting_id": "mtg-cmd",
            "phase": "COMPLETE",
            "manager_approved": True,
            "tasks": {
                "t1": {
                    "task_id": "t1",
                    "title": "Build OAuth login dashboard",
                    "assignee": "Resigo",
                    "status": "DISPATCHED",
                    "jira_ticket_id": "SCRUM-22",
                    "progress_pct": 20,
                }
            },
        },
    )

    # 1. Resigo sends in-app reply
    emp_res = client.post(
        "/api/messages/veridian-bot",
        headers={"Authorization": f"Bearer {emp_token}"},
        json={
            "text": "75% complete: PKCE login flow and callback routes implemented.",
            "thread_id": "thr-cmd-test",
            "task_id": "t1",
        },
    )
    assert emp_res.status_code == 200
    assert emp_res.json()["progress_pct"] == 75

    # 2. Verify Manager sees the executive summary card
    mgr_feed_res = client.get(
        "/api/messages/veridian-bot?thread_id=thr-cmd-test",
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert mgr_feed_res.status_code == 200
    mgr_texts = [m["text"] for m in mgr_feed_res.json()["messages"]]
    assert any("75% complete" in t for t in mgr_texts)
    assert any("SCRUM-22" in t for t in mgr_texts)

    # 3. Manager sends sprint status command
    cmd_res = client.post(
        "/api/messages/veridian-bot",
        headers={"Authorization": f"Bearer {mgr_token}"},
        json={
            "text": "Give me the sprint status summary",
            "thread_id": "thr-cmd-test",
        },
    )
    assert cmd_res.status_code == 200
    bot_reply = cmd_res.json()["bot_response"]
    assert "Live Sprint Status" in bot_reply
    assert "SCRUM-22" in bot_reply
    assert "75%" in bot_reply
