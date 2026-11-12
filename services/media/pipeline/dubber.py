"""End-to-end media dubbing & intelligence orchestrator using Gnani Prisma + Timbre."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import get_media_settings
from contracts.meeting_ended import MeetingEndedPayload, Participant
from pipeline.extract_audio import download_video, extract_audio
from pipeline.recompose import create_final_video, upload_to_cloudinary
from pipeline.summarizer import generate_summary_and_chapters
from pipeline.transcribe import get_transcriber, resolve_speaker_user_ids
from pipeline.translate import translate_segments
from pipeline.tts import synthesize_dubbed_track
from publisher import publish_meeting_ended

logger = logging.getLogger(__name__)


def _persist_to_supabase_if_configured(
    org_id: str,
    meeting_id: str,
    original_video_url: str,
    dubbed_url: str,
    summary: str,
    chapters: List[Dict[str, Any]],
) -> None:
    settings = get_media_settings()
    if not (
        settings.supabase_url
        and settings.supabase_key
        and "your-project" not in settings.supabase_url
        and "placeholder" not in settings.supabase_key
    ):
        return
    try:
        from supabase import create_client

        sb = create_client(settings.supabase_url, settings.supabase_key)
        sb.table("recordings").insert({
            "org_id": org_id,
            "meeting_id": meeting_id,
            "original_video_url": original_video_url,
            "dubbed_video_url": dubbed_url,
            "summary": summary,
            "chapters": chapters,
        }).execute()
    except Exception as exc:
        logger.warning("Supabase persistence skipped/failed (non-fatal in demo): %s", exc)


def process_media_job(
    job_id: str,
    meeting_id: str,
    org_id: str,
    video_url: str,
    title: str = "Horizon Veridian Meeting",
    target_lang: str = "en",
    language_hint: str = "auto-detect",
    participants: Optional[List[Dict[str, str]]] = None,
    speaker_map: Optional[Dict[str, str]] = None,
    generate_dub: bool = True,
    emit_meeting_ended: bool = True,
) -> Dict[str, Any]:
    """Run audio extraction, diarized transcription, optional dubbing, summary, and WorkOS publish."""
    settings = get_media_settings()
    work_dir = Path(settings.temp_dir) / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()

    raw_video = str(work_dir / "input.mp4")
    audio_path = str(work_dir / "audio.wav")

    is_demo_url = video_url.startswith("demo://")
    download_video(video_url, raw_video)
    _, duration_sec = extract_audio(raw_video, audio_path)

    transcriber = get_transcriber()
    try:
        t_res = transcriber.transcribe(audio_path, language_hint=language_hint, force_demo=is_demo_url)
    except TypeError:
        t_res = transcriber.transcribe(audio_path, language_hint=language_hint)

    participant_objs = [Participant(**p) for p in (participants or [])]
    attributed_segments = resolve_speaker_user_ids(
        t_res.segments,
        participants=participant_objs,
        speaker_map=speaker_map,
        speaker_hints=t_res.speaker_hints,
    )

    summary, chapters = generate_summary_and_chapters(
        attributed_segments,
        force_demo=is_demo_url,
    )

    dubbed_url = ""
    if generate_dub and attributed_segments:
        translated = translate_segments(attributed_segments, t_res.language, target_lang=target_lang)
        dubbed_audio = str(work_dir / "dubbed.wav")
        synthesize_dubbed_track(
            attributed_segments,
            translated,
            video_duration=max(duration_sec, 10.0),
            output_audio_path=dubbed_audio,
            target_lang=target_lang,
            force_demo=is_demo_url,
        )
        final_video = str(work_dir / "final_dubbed.mp4")
        create_final_video(raw_video, dubbed_audio, final_video, expected_duration=duration_sec)
        dubbed_url = upload_to_cloudinary(final_video, job_id=job_id)

    ended_at = datetime.now(timezone.utc).isoformat()
    _persist_to_supabase_if_configured(
        org_id=org_id,
        meeting_id=meeting_id,
        original_video_url=video_url,
        dubbed_url=dubbed_url,
        summary=summary,
        chapters=chapters,
    )

    payload = MeetingEndedPayload(
        meeting_id=meeting_id,
        org_id=org_id,
        title=title,
        started_at=started_at,
        ended_at=ended_at,
        language=t_res.language,
        participants=participant_objs,
        transcript=attributed_segments,
        summary=summary,
        recording_url=dubbed_url or video_url,
    )

    workos_ack = None
    if emit_meeting_ended:
        try:
            workos_ack = publish_meeting_ended(payload)
        except Exception as exc:
            logger.warning("WorkOS meeting.ended delivery failed/dead-lettered: %s", exc)
            workos_ack = {"status": "dead_lettered", "error": str(exc)}

    return {
        "job_id": job_id,
        "meeting_id": meeting_id,
        "org_id": org_id,
        "provider": t_res.provider,
        "language": t_res.language,
        "dubbed_url": dubbed_url,
        "summary": summary,
        "chapters": chapters,
        "segments": [s.model_dump(mode="json") for s in attributed_segments],
        "meeting_ended_payload": payload.model_dump(mode="json"),
        "workos_ack": workos_ack,
    }
