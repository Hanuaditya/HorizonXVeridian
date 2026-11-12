"""End-to-end live integration smoke test for Horizon Veridian x Gnani AI.

Validates (with ZERO static DEMO_MODE shortcuts on LLM/STT/TTS):
  1. Gnani Timbre (timbre-v2.5): synthesizes Hinglish prompt into valid RIFF WAV bytes.
  2. Gnani Prisma v3.0 (prisma-v3.0): transcribes the synthesized WAV back to non-empty text.
  3. WorkOS LangGraph + Gemini + Supabase: runs Graph A extraction and 4-way firewall
     (HR, Finance, Security, Capacity) against live Gemini & live Supabase policy/HR tables.
  4. Optional --dispatch: dispatches 1 live Jira ticket (SCRUM) and Slack post (Veridian WorkOS).

Never prints API keys or raw secrets.

Usage:
    python -u scripts/test_live_e2e.py
    python -u scripts/test_live_e2e.py --org-id org_demo_horizon --dispatch
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
import uuid
import wave
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
MEDIA_ROOT = REPO_ROOT / "services" / "media"
WORKOS_ROOT = REPO_ROOT / "services" / "workos"

load_dotenv(REPO_ROOT / ".env", override=False)

# Enforce live mode during the smoke script regardless of shell defaults
os.environ["DEMO_MODE"] = "false"


def _log(msg: str) -> None:
    print(msg, flush=True)


def _step_1_2_gnani_voice_roundtrip() -> str:
    sys.path.insert(0, str(MEDIA_ROOT))
    from pipeline.gnani_client import GnaniVoiceEngine

    hinglish_sentence = (
        "Alex, staging deploy kar do by Friday, production mat bhejna. Jason leave par hai."
    )
    engine = GnaniVoiceEngine()

    _log("[1/3] Gnani Timbre TTS (timbre-v2.5) -> starting...")
    t0 = time.perf_counter()
    wav_bytes = engine.synthesize_speech(
        text=hinglish_sentence,
        target_lang="hi",
        force_demo=False,
    )
    tts_elapsed = time.perf_counter() - t0

    assert isinstance(wav_bytes, (bytes, bytearray)) and len(wav_bytes) > 1000, "Empty TTS output"
    assert wav_bytes[:4] == b"RIFF", "TTS output must start with RIFF WAV header"

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        duration_sec = wf.getnframes() / float(wf.getframerate() or 1)
    assert duration_sec > 0.5, f"Expected non-zero audio duration, got {duration_sec:.2f}s"
    _log(f"[1/3] Gnani Timbre TTS (timbre-v2.5) -> OK in {tts_elapsed:.2f}s ({len(wav_bytes)} bytes, {duration_sec:.2f}s WAV)")

    temp_dir = REPO_ROOT / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    probe_wav = temp_dir / f"live_e2e_{uuid.uuid4().hex[:8]}.wav"
    probe_wav.write_bytes(wav_bytes)

    try:
        _log("[2/3] Gnani Prisma STT (prisma-v3.0) -> starting...")
        t1 = time.perf_counter()
        stt_json = engine.transcribe_audio(
            str(probe_wav),
            language_code="en-IN",
            force_demo=False,
        )
        stt_elapsed = time.perf_counter() - t1

        transcript = str(stt_json.get("transcript") or "").strip()
        if not transcript and stt_json.get("segments"):
            transcript = " ".join(
                str(seg.get("text") or "") for seg in stt_json["segments"]
            ).strip()
        assert transcript, f"Empty Prisma STT transcript response: {stt_json}"
        _log(f"[2/3] Gnani Prisma STT (prisma-v3.0) -> OK in {stt_elapsed:.2f}s ({len(transcript)} chars): {transcript}")
        return transcript
    finally:
        if str(MEDIA_ROOT) in sys.path:
            sys.path.remove(str(MEDIA_ROOT))
        try:
            probe_wav.unlink(missing_ok=True)
        except Exception:
            pass


def _step_3_workos_firewall(transcribed_line: str, org_id: str, do_dispatch: bool) -> None:
    sys.path.insert(0, str(WORKOS_ROOT))
    from langgraph.checkpoint.memory import MemorySaver
    from agent.graph_a import build_graph_a
    from agent.nodes.dispatcher import dispatcher_node
    from core.config import get_settings

    settings = get_settings()
    assert not settings.demo_mode, "DEMO_MODE must be false for live E2E verification"
    assert settings.gemini_api_key or settings.evon_api_key, "Live LLM key required"

    _log(
        f"[3/3] WorkOS LangGraph + Gemini ({settings.llm_extraction_model}) + Supabase Firewall "
        f"(org_id={org_id}) -> starting..."
    )
    t0 = time.perf_counter()

    enriched_transcript = (
        f"[00:00 - Dov Hershkovitz]: {transcribed_line}\n"
        "[00:15 - Dov Hershkovitz]: Arjun Rao, deploy the Elastic search cluster "
        "directly to AWS production by Thursday.\n"
        "[00:30 - Scott Williamson]: Reminder that SEC-POL-089 requires 14 days staging bake "
        "time first, and the enterprise cluster costs Rs 2.5 Lakhs per month."
    )

    graph = build_graph_a(checkpointer=MemorySaver())
    meeting_id = f"live-e2e-{uuid.uuid4().hex[:8]}"
    thread_id = f"thr-{meeting_id}"
    config = {"configurable": {"thread_id": thread_id}}

    out = graph.invoke(
        {
            "org_id": org_id,
            "meeting_id": meeting_id,
            "thread_id": thread_id,
            "title": "Live E2E Hinglish Verification",
            "transcript": enriched_transcript,
            "is_demo": False,
            "tasks": {},
            "key_decisions": [],
            "meeting_context": {},
            "resolutions": [],
            "dispatched_tickets": [],
            "manager_approved": False,
            "turn_count": 0,
        },
        config=config,
    )
    graph_elapsed = time.perf_counter() - t0

    tasks = out.get("tasks") or {}
    resolutions = out.get("resolutions") or []
    assert tasks, "Live Gemini extractor returned 0 tasks"
    assert any(
        (t.get("hr_status") and t.get("hr_status") != "ACTIVE")
        or bool(t.get("security_flag"))
        or bool(t.get("finance_flag"))
        for t in tasks.values()
    ), f"Expected live Supabase firewall flags on extracted tasks, got: {tasks}"

    _log(
        f"[3/3] WorkOS LangGraph + Gemini + Supabase Firewall -> OK in {graph_elapsed:.2f}s "
        f"({len(tasks)} task(s), {len(resolutions)} firewall resolution(s))"
    )
    for tid, t in tasks.items():
        _log(
            f"      - {tid}: {t.get('title')} | assignee={t.get('assignee')} | "
            f"hr={t.get('hr_status')} | fin={bool(t.get('finance_flag'))} | sec={bool(t.get('security_flag'))}"
        )

    if not do_dispatch:
        _log("[OPT] Live Jira/Slack dispatch skipped (pass --dispatch to test live ticket creation).")
        return

    _log("[OPT] Testing live Jira (SCRUM) + Slack (Veridian WorkOS) dispatch for 1 task...")
    t_disp = time.perf_counter()
    first_tid = next(iter(tasks.keys()))
    first_task = dict(tasks[first_tid])
    first_task["title"] = f"[Live E2E Smoke] {first_task.get('reframed_title') or first_task.get('title')}"
    first_task.pop("jira_ticket_id", None)
    first_task["status"] = "APPROVED"

    res = dispatcher_node(
        {
            "org_id": org_id,
            "meeting_id": meeting_id,
            "thread_id": thread_id,
            "tasks": {first_tid: first_task},
            "dispatched_tickets": [],
            "approver_user_id": "live_e2e_verifier",
        }
    )
    dispatched = res.get("dispatched_tickets") or []
    assert dispatched, f"Dispatch failed: {res.get('tasks')}"
    ticket = dispatched[0]
    assert ticket.get("mode") == "live_jira", f"Expected live_jira mode, got {ticket}"
    assert ticket.get("slack_sent") is True, f"Expected slack_sent=True, got {ticket}"
    _log(
        f"[OPT] Live Dispatch -> OK in {time.perf_counter() - t_disp:.2f}s "
        f"(Jira {ticket['jira_key']}: {ticket['jira_url']})"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live Horizon Veridian x Gnani AI E2E check.")
    parser.add_argument("--org-id", default="org_demo_horizon", help="Supabase org_id to query")
    parser.add_argument(
        "--dispatch",
        action="store_true",
        help="Also create 1 real Jira issue in SCRUM and send 1 Slack notification",
    )
    args = parser.parse_args()

    t_start = time.perf_counter()
    _log("Horizon Veridian Live E2E Pipeline Smoke Test")
    _log("=" * 64)
    transcript = _step_1_2_gnani_voice_roundtrip()
    _step_3_workos_firewall(transcript, org_id=args.org_id, do_dispatch=args.dispatch)
    _log("=" * 64)
    _log(f"ALL LIVE E2E CHECKS PASSED in {time.perf_counter() - t_start:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
