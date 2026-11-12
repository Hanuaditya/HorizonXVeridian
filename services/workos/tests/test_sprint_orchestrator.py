"""Tests for the 6-Stage Manager-Gated Sprint Orchestrator, Smart Leave Redirect & Auto-Close Loop."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.auth import mint_demo_jwt
from api.main import app
from core.config import get_settings
from core.store import get_local_store, list_slack_feed


def _sign_body(raw_body: bytes, secret: str) -> dict:
    ts = str(int(time.time()))
    sig = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Signature": sig,
        "X-Timestamp": ts,
    }


def _sign_slack(raw_body: bytes, secret: str, content_type: str = "application/x-www-form-urlencoded") -> dict:
    ts = str(int(time.time()))
    base = f"v0:{ts}:{raw_body.decode('utf-8')}"
    sig = "v0=" + hmac.new(secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "Content-Type": content_type,
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": sig,
    }


def test_zero_tickets_before_manager_approval_and_slack_interactivity(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "slack_interactivity_test_secret_2026")
    get_local_store().reset(seed_default_org=True)

    jira_calls = []
    monkeypatch.setattr(
        "agent.nodes.dispatcher._create_jira_issue",
        lambda **kw: jira_calls.append(kw) or {
            "ticket_id": f"SCRUM-{len(jira_calls) + 10}",
            "url": f"https://demo.atlassian.net/browse/SCRUM-{len(jira_calls) + 10}",
            "mode": "demo_mock",
            "jira_status": "To Do",
        },
    )

    client = TestClient(app)
    mgr_token = mint_demo_jwt("user_mgr_1", "org_demo_horizon", "org:admin")

    # Even clean tasks with zero flags MUST pause at HITL and create ZERO tickets until Manager approves
    payload = {
        "meeting_id": "mtg-clean-gate",
        "org_id": "org_demo_horizon",
        "title": "Clean Sprint Sync",
        "started_at": "2026-11-12T10:00:00Z",
        "ended_at": "2026-11-12T10:15:00Z",
        "language": "en",
        "participants": [
            {"clerk_user_id": "user_josh", "display_name": "Josh Lambert", "email": "josh@veridian.local"}
        ],
        "transcript": [
            {
                "speaker": "SPEAKER_01",
                "speaker_user_id": "user_josh",
                "start": 0.0,
                "end": 10.0,
                "text": "Josh will publish sprint documentation.",
            }
        ],
    }
    raw = json.dumps(payload).encode("utf-8")
    res = client.post("/api/meeting-ended", content=raw, headers=_sign_body(raw, get_settings().shared_hmac_secret))
    assert res.status_code == 202
    thread_id = res.json()["thread_id"]

    # Zero Jira tickets created before approval!
    assert jira_calls == []

    snap = client.get(f"/api/threads/{thread_id}/state", headers={"Authorization": f"Bearer {mgr_token}"}).json()
    assert snap["phase"] == "HITL"
    assert snap["dispatched_tickets"] == []

    feed = list_slack_feed("org_demo_horizon", thread_id)
    assert any(m["role"] == "manager" and m["kind"] == "review_menu" for m in feed)

    # Unsigned Slack interactivity MUST be rejected 403
    inter_payload = json.dumps({
        "type": "block_actions",
        "user": {"id": "U_MGR", "username": "scott.mgr"},
        "actions": [{"action_id": "approve_sprint_tickets", "value": thread_id}],
    })
    form_body = f"payload={inter_payload}".encode("utf-8")
    bad = client.post("/api/slack/interactivity", content=form_body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert bad.status_code == 403
    assert jira_calls == []

    # Signed Slack interactivity approves and creates tickets cleanly
    ok = client.post(
        "/api/slack/interactivity",
        content=form_body,
        headers=_sign_slack(form_body, "slack_interactivity_test_secret_2026"),
    )
    assert ok.status_code == 200
    assert len(jira_calls) >= 1

    final_snap = client.get(f"/api/threads/{thread_id}/state", headers={"Authorization": f"Bearer {mgr_token}"}).json()
    assert final_snap["phase"] == "COMPLETE"
    assert len(final_snap["dispatched_tickets"]) >= 1


def test_immediate_alerts_for_budget_policy_and_blocked_api_and_smart_leave_redirect(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    get_local_store().reset(seed_default_org=True)

    # Ensure demo_extract returns 2 tasks: Arjun (on leave, Elastic prod deploy, over budget) + Gabe (Legacy v1 blocked API)
    import agent.nodes.extractor as ext_mod
    from agent.nodes.extractor import ExtractionOutput, MeetingContext, TaskExtraction

    def _custom_extract(system_prompt, user_prompt, schema, temperature=0.1, force_demo=False):
        if schema is ExtractionOutput:
            return ExtractionOutput(
                meeting_context=MeetingContext(title="Sprint Policy & Leave Test", attendees=["Arjun Rao", "Gabe Weaver"]),
                tasks=[
                    TaskExtraction(
                        task_id="t1",
                        title="Deploy Elastic search cluster directly to AWS production costing Rs 2.5 Lakhs",
                        assignee="Arjun Rao",
                        resource_type="compute",
                        transcript_quote="Arjun deploy Elastic cluster to AWS production costing Rs 2.5 Lakhs",
                        proposed_commit_message="feat(infra): stage Elastic cluster with 14-day soak",
                    ),
                    TaskExtraction(
                        task_id="t2",
                        title="Integrate unsupported Legacy v1 Payment API third-party SDK into checkout",
                        assignee="Gabe Weaver",
                        resource_type="third_party_api",
                        transcript_quote="Integrate unsupported Legacy v1 Payment API directly",
                        proposed_commit_message="feat(api): blocked legacy payment integration pending AppSec",
                    ),
                ],
            )
        return None

    monkeypatch.setattr(ext_mod, "structured_output", _custom_extract)

    client = TestClient(app)
    mgr_token = mint_demo_jwt("user_mgr_1", "org_demo_horizon", "org:admin")

    res = client.post(
        "/api/transcript-ingest",
        json={"title": "Sprint Policy & Leave Test", "transcript": "Dummy delimited transcript"},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res.status_code == 202
    thread_id = res.json()["thread_id"]

    snap = client.get(f"/api/threads/{thread_id}/state", headers={"Authorization": f"Bearer {mgr_token}"}).json()
    assert snap["phase"] == "HITL"
    assert snap["dispatched_tickets"] == []

    # 1. Immediate alerts include BUDGET, POLICY (SEC-POL-089), and BLOCKED_API (SEC-POL-104)
    alerts = snap.get("immediate_alerts") or []
    alert_types = {a["type"] for a in alerts}
    assert "BUDGET" in alert_types
    assert "BLOCKED_API" in alert_types
    assert "SEC-POL-104" in snap["tasks"]["t2"]["security_flag"]

    # Immediate Slack DM sent to Manager BEFORE approval
    feed = list_slack_feed("org_demo_horizon", thread_id)
    assert any(m["kind"] == "compliance_alert" and m["role"] == "manager" for m in feed)

    # 2. Smart Leave Redirect suggests Josh Lambert (domain match + lowest workload = 1 active task) without auto-assigning yet
    t1 = snap["tasks"]["t1"]
    assert t1["hr_status"] == "ON_PATERNITY_LEAVE"
    assert t1["rerouted_assignee"] == "Josh Lambert"
    assert "Josh Lambert" in (t1.get("leave_recommendation") or "")
    assert "lowest workload" in (t1.get("leave_recommendation") or "").lower()
    assert t1["assignee"] == "Arjun Rao"  # Not mutated silently before approval!

    # 3. Manager approves REROUTE for t1 -> Jira ticket assigned to Josh Lambert & 1-on-1 DM sent to Josh
    res_approve = client.post(
        "/api/hitl-resume",
        json={"thread_id": thread_id, "hitl_decisions": {"t1": "REROUTE", "t2": "REFRAME"}},
        headers={"Authorization": f"Bearer {mgr_token}"},
    )
    assert res_approve.status_code == 200
    done_snap = client.get(f"/api/threads/{thread_id}/state", headers={"Authorization": f"Bearer {mgr_token}"}).json()
    t1_ticket = next(d for d in done_snap["dispatched_tickets"] if d["task_id"] == "t1")
    assert t1_ticket["assignee"] == "Josh Lambert"


def test_interval_checkins_partial_digest_and_natural_language_auto_close_jira(monkeypatch):
    from api.auth import AuthContext, require_auth

    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("JIRA_BASE_URL", "https://example-veridian.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "bot@veridian.local")
    monkeypatch.setenv("JIRA_API_TOKEN", "live_jira_token")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "")
    get_local_store().reset(seed_default_org=True)
    app.dependency_overrides[require_auth] = lambda: AuthContext(
        user_id="user_mgr_1",
        org_id="org_demo_horizon",
        role="org:admin",
        is_demo=False,
    )

    # Seed an active completed dispatch snapshot ready for check-ins
    import connectors.jira_ops as jira_ops
    jira_calls = []

    def fake_jira_get(url, **kwargs):
        jira_calls.append(("GET", url))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"transitions": [{"id": "31", "name": "Done", "to": {"statusCategory": {"key": "done"}}}]},
        )

    def fake_jira_post(url, **kwargs):
        jira_calls.append(("POST", url, kwargs.get("json")))
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"ok": True})

    monkeypatch.setattr(jira_ops.httpx, "get", fake_jira_get)
    monkeypatch.setattr(jira_ops.httpx, "post", fake_jira_post)

    # Route employee check-in analysis through deterministic mock without calling external Gemini network
    import connectors.sprint_loop as sl
    from connectors.sprint_loop import CheckinReplyAnalysis

    def fake_analyze(reply_text, task_title, is_demo=False):
        if "60%" in reply_text:
            return CheckinReplyAnalysis(
                intent="IN_PROGRESS",
                progress_pct=60,
                completed_milestones="Staging provisioned",
                blockers="None",
                commit_summary="wip(staging): 60%",
            )
        return CheckinReplyAnalysis(
            intent="COMPLETED",
            progress_pct=100,
            completed_milestones="All staging checks finished and pushed",
            blockers="None",
            commit_summary="feat(staging): completed Elastic 14-day soak & verification",
        )

    monkeypatch.setattr(sl, "analyze_employee_reply", fake_analyze)

    from core.store import save_thread_snapshot, upsert_slack_thread

    tid = "thr-checkin-e2e"
    save_thread_snapshot(
        thread_id=tid,
        org_id="org_demo_horizon",
        snapshot={
            "meeting_id": "mtg-checkin-e2e",
            "title": "Check-In Loop Test",
            "phase": "COMPLETE",
            "tasks": {
                "t1": {
                    "task_id": "t1",
                    "title": "Stage Elastic Cluster",
                    "assignee": "Josh Lambert",
                    "status": "DISPATCHED",
                    "jira_ticket_id": "SCRUM-42",
                    "jira_url": "https://example-veridian.atlassian.net/browse/SCRUM-42",
                    "jira_status": "To Do",
                }
            },
            "dispatched_tickets": [
                {
                    "task_id": "t1",
                    "title": "Stage Elastic Cluster",
                    "assignee": "Josh Lambert",
                    "jira_key": "SCRUM-42",
                    "jira_url": "https://example-veridian.atlassian.net/browse/SCRUM-42",
                    "jira_status": "To Do",
                }
            ],
        },
    )
    upsert_slack_thread(
        org_id="org_demo_horizon",
        thread_id=tid,
        task_id="t1",
        jira_key="SCRUM-42",
        slack_channel="C0CHVP9J15E",
        slack_thread_ts="1700000001.100",
        assignee="Josh Lambert",
        status="OPEN",
    )

    client = TestClient(app)
    try:
        chk = client.post(f"/api/threads/{tid}/checkin")
        assert chk.status_code == 200
        assert chk.json()["checkins_sent"][0]["jira_key"] == "SCRUM-42"

        # 2. Partial progress reply -> Jira comment + Manager Progress Digest DM
        prog = client.post(
            f"/api/threads/{tid}/employee-reply",
            json={"task_id": "t1", "reply_text": "60% done: staging environment provisioned"},
        )
        assert prog.status_code == 200
        assert prog.json()["analysis"]["intent"] == "IN_PROGRESS"
        assert any("/comment" in c[1] for c in jira_calls if c[0] == "POST")
        assert any(m["kind"] == "progress_digest" and m["role"] == "manager" for m in list_slack_feed("org_demo_horizon", tid))

        # 3. Natural-language completion reply -> auto-transition Jira SCRUM-42 -> Done + Manager closure DM
        done = client.post(
            f"/api/threads/{tid}/employee-reply",
            json={"task_id": "t1", "reply_text": "My work assigned during the meeting is completed"},
        )
        assert done.status_code == 200
        assert done.json()["task"]["jira_status"] == "Done"
        assert done.json()["task"]["status"] == "DONE"
        assert any(c[0] == "GET" and "/transitions" in c[1] for c in jira_calls)
        assert any(c[0] == "POST" and "/transitions" in c[1] and c[2]["transition"]["id"] == "31" for c in jira_calls)

        feed = list_slack_feed("org_demo_horizon", tid)
        assert any(m["kind"] == "closure" and m["role"] == "manager" for m in feed)
    finally:
        app.dependency_overrides.pop(require_auth, None)
