"""Horizon Veridian Media Service (Flask): Gnani Prisma V3.0 STT, Timbre TTS & MeetingEnded Publisher."""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

_MEDIA_ROOT = str(Path(__file__).resolve().parent)
if _MEDIA_ROOT not in sys.path:
    sys.path.insert(0, _MEDIA_ROOT)

from flask import Flask, jsonify, request
from flask_cors import CORS

from config import get_media_settings
from jobs import job_manager
from pipeline.dubber import process_media_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

app = Flask(__name__)
CORS(app)


@app.route("/health", methods=["GET"])
@app.route("/api/health", methods=["GET"])
def health():
    settings = get_media_settings()
    return jsonify({
        "status": "healthy",
        "service": "media",
        "transcriber": settings.transcriber,
        "tts_provider": settings.tts_provider,
        "prisma_model": settings.gnani_prisma_model,
        "demo_mode": settings.demo_mode,
    }), 200


@app.route("/media/jobs", methods=["POST"])
def create_media_job():
    body = request.get_json(silent=True) or {}
    video_url = body.get("recording_url") or body.get("videoUrl") or body.get("video_url")
    if not video_url:
        return jsonify({"error": "recording_url (or videoUrl) is required."}), 400

    job = job_manager.submit_job({
        "meeting_id": body.get("meeting_id") or str(uuid.uuid4()),
        "org_id": body.get("org_id") or "org_demo_horizon",
        "video_url": video_url,
        "title": body.get("title") or "Horizon Veridian Meeting",
        "target_lang": body.get("target_lang", "en"),
        "language_hint": body.get("language_hint", "auto-detect"),
        "participants": body.get("participants") or [],
        "speaker_map": body.get("speaker_map") or {},
        "generate_dub": body.get("generate_dub", True),
        "emit_meeting_ended": body.get("emit_meeting_ended", True),
    })
    return jsonify(job), 202


@app.route("/media/jobs/<job_id>", methods=["GET"])
def poll_media_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        return jsonify({"error": f"Media job '{job_id}' not found."}), 404
    return jsonify(job), 200


@app.route("/api/generate-insight", methods=["POST"])
def generate_insight_route():
    """Backward-compatible synchronous insight generation endpoint for apps/web."""
    body = request.get_json(silent=True) or {}
    video_url = body.get("videoUrl") or body.get("recording_url")
    if not video_url:
        return jsonify({"error": "URL required"}), 400
    try:
        res = process_media_job(
            job_id=str(uuid.uuid4()),
            meeting_id=body.get("meeting_id") or str(uuid.uuid4()),
            org_id=body.get("org_id") or "org_demo_horizon",
            video_url=video_url,
            title=body.get("title") or "Horizon Meeting Insight",
            generate_dub=False,
            emit_meeting_ended=bool(body.get("emit_meeting_ended", True)),
        )
        return jsonify({
            "message": "Insight generated",
            "meeting_id": res["meeting_id"],
            "summary": res["summary"],
            "chapters": res["chapters"],
            "segments": res["segments"],
            "workos_ack": res["workos_ack"],
        }), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/start-dubbing", methods=["POST"])
def start_dubbing_route():
    """Backward-compatible synchronous dubbing endpoint using Gnani Prisma + Timbre."""
    body = request.get_json(silent=True) or {}
    video_url = body.get("videoUrl") or body.get("recording_url")
    if not video_url:
        return jsonify({"error": "URL required"}), 400
    try:
        res = process_media_job(
            job_id=str(uuid.uuid4()),
            meeting_id=body.get("meeting_id") or str(uuid.uuid4()),
            org_id=body.get("org_id") or "org_demo_horizon",
            video_url=video_url,
            title=body.get("title") or "Horizon Dubbed Meeting",
            target_lang=body.get("target_lang", "en"),
            generate_dub=True,
            emit_meeting_ended=bool(body.get("emit_meeting_ended", True)),
        )
        return jsonify({
            "message": "Dubbing complete!",
            "meeting_id": res["meeting_id"],
            "dubbed_url": res["dubbed_url"],
            "summary": res["summary"],
            "chapters": res["chapters"],
            "segments": res["segments"],
            "workos_ack": res["workos_ack"],
        }), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    settings = get_media_settings()
    app.run(host="0.0.0.0", port=settings.media_port, debug=(settings.app_env == "development"))
