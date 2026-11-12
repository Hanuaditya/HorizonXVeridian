"""Phase 3 / Sprint 2 tests: Gnani Prisma STT, Timbre TTS, drift guard, publisher HMAC & schema."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from contracts.meeting_ended import MeetingEndedPayload, Participant, TranscriptSegment
from pipeline.gnani_client import GnaniVoiceEngine, _generate_demo_wav_bytes
from pipeline.recompose import assert_timestamp_drift_within_bounds
from pipeline.transcribe import get_transcriber, resolve_speaker_user_ids
from pipeline.tts import compute_bounded_speaking_rate
from publisher import compute_hmac_signature, publish_meeting_ended


def test_gnani_voice_engine_demo_mode_returns_hinglish_segments(tmp_path, monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "")
    monkeypatch.setenv("DEMO_MODE", "true")

    wav_file = tmp_path / "fixture.wav"
    wav_file.write_bytes(_generate_demo_wav_bytes(1.0))

    engine = GnaniVoiceEngine()
    raw = engine.transcribe_audio(str(wav_file))
    assert "segments" in raw
    assert len(raw["segments"]) >= 6
    combined_text = " ".join(s["text"] for s in raw["segments"])
    assert "paternity leave" in combined_text.lower()
    assert "staging" in combined_text.lower()

    audio_bytes = engine.synthesize_speech("Deploying to staging with 14-day soak", target_lang="en")
    assert audio_bytes.startswith(b"RIFF")


def test_gnani_voice_engine_live_http_mock(tmp_path, monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "gnani_live_test_key")
    monkeypatch.setenv("GNANI_TOKEN", "gnani_live_test_token")
    monkeypatch.setenv("DEMO_MODE", "false")

    wav_file = tmp_path / "sample.wav"
    wav_file.write_bytes(_generate_demo_wav_bytes(0.5))

    captured = {}

    def fake_post(url, headers=None, files=None, data=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = data
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {
                "language": "hi-en",
                "segments": [
                    {"speaker": "SPEAKER_01", "start": 0.0, "end": 3.5, "text": "Jason leave pe hai"}
                ],
            },
        )

    monkeypatch.setattr("pipeline.gnani_client.requests.post", fake_post)
    engine = GnaniVoiceEngine()
    out = engine.transcribe_audio(str(wav_file))
    assert captured["url"].endswith("/stt/v3")
    assert captured["headers"]["X-API-Key-ID"] == "gnani_live_test_key"
    assert captured["data"]["model"] == "prisma-v3.0"
    assert out["segments"][0]["text"] == "Jason leave pe hai"


def test_media_demo_simulate_route(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_TEMP_DIR", str(tmp_path / "sim_tmp"))
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    monkeypatch.setenv("GNANI_API_KEY", "")
    from app import app as media_app
    monkeypatch.setattr(
        "pipeline.dubber.publish_meeting_ended",
        lambda payload: {"status": "accepted", "thread_id": f"thr-{payload.meeting_id}"},
    )
    client = media_app.test_client()
    sim_res = client.post("/media/demo-simulate", json={"meeting_id": "sim-static-old"})
    sim_res_2 = client.post("/media/demo-simulate", json={"meeting_id": "sim-static-old"})
    assert sim_res.status_code == 202
    assert sim_res_2.status_code == 202
    d1 = sim_res.get_json()
    d2 = sim_res_2.get_json()
    assert d1["status"] == "dispatched_to_workos"
    assert d1["meeting_id"].startswith("sim-")
    assert d1["meeting_id"] != "sim-static-old"
    assert d1["meeting_id"] != d2["meeting_id"]
    assert d1["thread_id"] != d2["thread_id"]


def test_transcriber_factory_and_strict_speaker_attribution(monkeypatch):
    monkeypatch.setenv("TRANSCRIBER", "gnani_prisma")
    t = get_transcriber()
    assert t.name == "gnani_prisma"

    segs = [
        TranscriptSegment(speaker="SPEAKER_01", speaker_user_id=None, start=0.0, end=4.0, text="Deploy Elastic"),
        TranscriptSegment(speaker="SPEAKER_99", speaker_user_id=None, start=4.5, end=8.0, text="Mystery speaker"),
    ]
    participants = [
        Participant(clerk_user_id="user_dov", display_name="Dov Hershkovitz", email="dov@veridian.local"),
    ]
    resolved = resolve_speaker_user_ids(
        segs,
        participants=participants,
        speaker_hints={"SPEAKER_01": "Dov"},
    )
    assert resolved[0].speaker_user_id == "user_dov"
    # Unknown speaker MUST stay None (never guessed)
    assert resolved[1].speaker_user_id is None


def test_timestamp_drift_guard_and_speaking_rate():
    rate = compute_bounded_speaking_rate(word_count=20, target_duration_sec=10.0)
    assert 0.70 <= rate <= 1.45

    assert assert_timestamp_drift_within_bounds(30.0, 30.8) == pytest.approx(0.8)
    with pytest.raises(ValueError, match="Timestamp drift exceeded"):
        assert_timestamp_drift_within_bounds(30.0, 35.0)


def test_publisher_hmac_signature_retries_and_dead_letter(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_DEAD_LETTER_DIR", str(tmp_path / "dl"))
    secret = "test_hmac_secret_123"
    payload = MeetingEndedPayload(
        meeting_id="mtg_test_001",
        org_id="org_demo_horizon",
        title="Sprint Sync",
        started_at="2026-11-11T10:00:00Z",
        ended_at="2026-11-11T10:05:00Z",
        language="hi-en",
        participants=[
            Participant(clerk_user_id="user_dov", display_name="Dov", email="dov@veridian.local")
        ],
        transcript=[
            TranscriptSegment(speaker="SPEAKER_01", speaker_user_id="user_dov", start=0.0, end=5.0, text="Jason leave pe hai")
        ],
        summary="Test summary",
        recording_url="demo://video.mp4",
    )

    seen_headers = []
    attempts = {"count": 0}

    def flaky_post(url, data=None, headers=None, timeout=None):
        attempts["count"] += 1
        seen_headers.append((data, headers))
        if attempts["count"] == 1:
            return SimpleNamespace(status_code=503, text="Temporary unavailable", json=lambda: {})
        return SimpleNamespace(status_code=202, text='{"thread_id":"thr_1"}', json=lambda: {"thread_id": "thr_1"})

    monkeypatch.setattr("publisher.requests.post", flaky_post)
    ack = publish_meeting_ended(payload, workos_url="http://localhost:8000", shared_secret=secret, backoff_base=0.01)
    assert ack["thread_id"] == "thr_1"
    assert attempts["count"] == 2

    raw_body, hdrs = seen_headers[-1]
    assert hdrs["Idempotency-Key"] == "mtg_test_001"
    expected_sig = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    assert hdrs["X-Signature"] == expected_sig
    assert abs(time.time() - float(hdrs["X-Timestamp"])) < 15

    # Verify dead-letter file on exhausted retries
    def always_fail(*_args, **_kwargs):
        raise ConnectionError("WorkOS offline")

    monkeypatch.setattr("publisher.requests.post", always_fail)
    with pytest.raises(RuntimeError, match="Failed to deliver meeting.ended"):
        publish_meeting_ended(payload, workos_url="http://localhost:8000", shared_secret=secret, max_retries=2, backoff_base=0.01)

    dl_files = list((tmp_path / "dl").glob("*.json"))
    assert len(dl_files) == 1
    dl_data = json.loads(dl_files[0].read_text(encoding="utf-8"))
    assert dl_data["meeting_id"] == "mtg_test_001"


def test_flask_media_routes_async_and_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("MEDIA_TEMP_DIR", str(tmp_path / "media_tmp"))
    monkeypatch.setenv("GNANI_API_KEY", "")

    from app import app as media_app

    # Prevent real network call to WorkOS during media unit test
    monkeypatch.setattr(
        "pipeline.dubber.publish_meeting_ended",
        lambda payload: {"status": "accepted", "thread_id": f"thr-{payload.meeting_id}"},
    )

    client = media_app.test_client()
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json()["transcriber"] == "gnani_prisma"

    dub_res = client.post("/api/start-dubbing", json={"videoUrl": "demo://sample_hinglish.mp4"})
    assert dub_res.status_code == 200
    dub_json = dub_res.get_json()
    assert dub_json["dubbed_url"].startswith("demo://cloudinary/dubbed/")
    assert len(dub_json["segments"]) >= 6
    assert dub_json["workos_ack"]["status"] == "accepted"

    async_res = client.post("/media/jobs", json={"recording_url": "demo://sample.mp4", "org_id": "org_alpha"})
    assert async_res.status_code == 202
    job_id = async_res.get_json()["job_id"]

    # Poll until completed
    for _ in range(30):
        poll = client.get(f"/media/jobs/{job_id}").get_json()
        if poll["status"] in ("COMPLETED", "FAILED"):
            break
        time.sleep(0.05)
    assert poll["status"] == "COMPLETED"
    assert poll["org_id"] == "org_alpha"

