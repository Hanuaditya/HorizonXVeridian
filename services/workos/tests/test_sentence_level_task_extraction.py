"""Unit tests for sentence-level task extraction & governance firewall in _build_deterministic_hitl_fallback."""

from __future__ import annotations

import pytest

from api.routes.meeting import _build_deterministic_hitl_fallback


ENGLISH_MULTI_TASK_TRANSCRIPT = (
    "[00:00 - Hanu Aditya]: Good morning team. Quick sprint standup today.\n"
    "[00:15 - Hanu Aditya]: Arjun Rao, please deploy Elasticsearch cluster to AWS production by Thursday. Also Resigo, please build the OAuth login dashboard by Friday.\n"
    "[00:30 - catchme if]: Arjun is on paternity leave until next Monday, but I will cover for him.\n"
    "[00:45 - Hanu Aditya]: Great, let us route the AWS Elasticsearch deployment to catchme if.\n"
    "[01:00 - Resigo]: Got it, starting on the OAuth login dashboard right away.\n"
    "[01:15 - Hanu Aditya]: Team, please note we cannot connect Legacy v1 External API as it is unapproved and exceeds our Q4 compute budget.\n"
    "[01:30 - Resigo]: Sounds good.\n"
    "[01:45 - Hanu Aditya]: Perfect. Thanks everyone."
)

HINGLISH_MULTI_TASK_TRANSCRIPT = (
    "[00:00 - Hanu Aditya]: Good morning team. Quick sprint standup start karte hain.\n"
    "[00:15 - Hanu Aditya]: Arjun, deploy Elasticsearch cluster to AWS production by Thursday. Resigo, tum Thursday tak OAuth login dashboard build kar dena.\n"
    "[00:30 - catchme if]: Arjun toh paternity leave pe hai, main cover kar leta hoon.\n"
    "[00:45 - Hanu Aditya]: Great, let us route the AWS Elasticsearch deployment to catchme if.\n"
    "[01:00 - Resigo]: Got it, starting on the OAuth login dashboard right away.\n"
    "[01:15 - Hanu Aditya]: Aur haan, Legacy v1 External API connect mat karna because it exceeds Q4 compute budget and violates SEC-POL-104.\n"
    "[01:30 - Resigo]: Sounds good.\n"
    "[01:45 - Hanu Aditya]: Perfect. Thanks everyone."
)


def test_english_multi_task_speaker_turn_extraction():
    """Verify sentence-level extraction on English transcript with multi-task turns."""
    hitl_state = _build_deterministic_hitl_fallback(ENGLISH_MULTI_TASK_TRANSCRIPT)
    tasks = hitl_state["tasks"]

    # Exactly 3 clean deduplicated tasks
    assert "t1" in tasks
    assert "t2" in tasks
    assert "t3" in tasks
    assert len(tasks) == 3

    # Task 1: Leave redirection (Arjun Rao -> catchme if)
    t1 = tasks["t1"]
    assert t1["title"] == "Deploy Elasticsearch cluster to AWS production"
    assert t1["assignee"] == "catchme if"
    assert t1.get("original_assignee") == "Arjun Rao"
    assert t1.get("decision") == "REROUTE"
    assert t1.get("flag_badge") == "Smart Leave Redirection: catchme if"

    # Task 2: Second employee task (Resigo)
    t2 = tasks["t2"]
    assert t2["title"] == "Build OAuth login dashboard"
    assert t2["assignee"] == "Resigo"
    assert t2.get("decision") == "PROCEED"

    # Task 3: Policy & Budget firewall (Legacy v1 External API)
    t3 = tasks["t3"]
    assert t3["title"] == "Connect Legacy v1 External API"
    assert t3.get("decision") == "DEFER"
    assert t3.get("flag_badge") == "SEC-POL-104 • Finance: Over Budget"

    # Policy / Leave Flags counter in summary metrics reflects count >= 2
    summary = hitl_state.get("summary_metrics") or {}
    flags_count = (
        summary.get("policy_leave_flags")
        or summary.get("policy_flags_count")
        or hitl_state.get("policy_leave_flags")
        or hitl_state.get("policy_flags_count")
        or 0
    )
    assert flags_count >= 2


def test_hinglish_multi_task_speaker_turn_extraction():
    """Verify sentence-level extraction on Hinglish transcript with multi-task turns."""
    hitl_state = _build_deterministic_hitl_fallback(HINGLISH_MULTI_TASK_TRANSCRIPT)
    tasks = hitl_state["tasks"]

    # Exactly 3 clean deduplicated tasks
    assert "t1" in tasks
    assert "t2" in tasks
    assert "t3" in tasks
    assert len(tasks) == 3

    # Task 1: Leave redirection (Arjun Rao -> catchme if)
    t1 = tasks["t1"]
    assert t1["title"] == "Deploy Elasticsearch cluster to AWS production"
    assert t1["assignee"] == "catchme if"
    assert t1.get("original_assignee") == "Arjun Rao"
    assert t1.get("decision") == "REROUTE"
    assert t1.get("flag_badge") == "Smart Leave Redirection: catchme if"

    # Task 2: Second employee task (Resigo)
    t2 = tasks["t2"]
    assert t2["title"] == "Build OAuth login dashboard"
    assert t2["assignee"] == "Resigo"
    assert t2.get("decision") == "PROCEED"

    # Task 3: Policy & Budget firewall (Legacy v1 External API)
    t3 = tasks["t3"]
    assert t3["title"] == "Connect Legacy v1 External API"
    assert t3.get("decision") == "DEFER"
    assert t3.get("flag_badge") == "SEC-POL-104 • Finance: Over Budget"

    # Policy / Leave Flags counter in summary metrics reflects count >= 2
    summary = hitl_state.get("summary_metrics") or {}
    flags_count = (
        summary.get("policy_leave_flags")
        or summary.get("policy_flags_count")
        or hitl_state.get("policy_leave_flags")
        or hitl_state.get("policy_flags_count")
        or 0
    )
    assert flags_count >= 2


def test_dict_initial_state_and_verbatim_quotes():
    """Verify dictionary initial_state and verbatim quotes from transcript."""
    payload = {
        "meeting_id": "mtg-dict-001",
        "thread_id": "thr-dict-001",
        "org_id": "org_demo_horizon",
        "transcript": ENGLISH_MULTI_TASK_TRANSCRIPT,
    }
    hitl_state = _build_deterministic_hitl_fallback(payload)
    tasks = hitl_state["tasks"]
    for tid, t in tasks.items():
        q = t.get("transcript_quote")
        assert q, f"Task {tid} missing transcript quote"
        assert q in ENGLISH_MULTI_TASK_TRANSCRIPT, f"Quote '{q}' not found verbatim in input transcript"
