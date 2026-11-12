"""Audio extraction and video download helpers."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import requests

from config import get_media_settings
from pipeline.gnani_client import _generate_demo_wav_bytes

logger = logging.getLogger(__name__)


def download_video(url: str, output_path: str) -> str:
    """Download video from HTTP URL (or create local fixture stub in demo:// URLs)."""
    settings = get_media_settings()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if url.startswith("demo://") or (settings.demo_mode and not url.startswith(("http://", "https://"))):
        Path(output_path).write_bytes(b"DEMO_VIDEO_FIXTURE")
        return output_path

    if url.startswith("file://"):
        local_src = Path(url[7:].lstrip("/"))
        Path(output_path).write_bytes(local_src.read_bytes())
        return output_path

    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    with open(output_path, "wb") as handle:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                handle.write(chunk)
    return output_path


def extract_audio(video_path: str, audio_path: str) -> tuple[str, float]:
    """Extract audio track to audio_path and return (audio_path, duration_seconds)."""
    settings = get_media_settings()
    Path(audio_path).parent.mkdir(parents=True, exist_ok=True)

    if video_path.endswith(".wav"):
        Path(audio_path).write_bytes(Path(video_path).read_bytes())
        return audio_path, 30.0

    # Handle demo stub or local test fixtures cleanly
    raw_head = Path(video_path).read_bytes()[:18] if Path(video_path).exists() else b""
    if raw_head.startswith(b"DEMO_VIDEO_FIXTURE"):
        wav_bytes = _generate_demo_wav_bytes(duration_sec=30.0)
        Path(audio_path).write_bytes(wav_bytes)
        return audio_path, 30.0

    try:
        from moviepy.editor import VideoFileClip  # type: ignore

        clip = VideoFileClip(video_path)
        duration = float(clip.duration or 0.0)
        if clip.audio is None:
            clip.close()
            raise RuntimeError(f"Video '{video_path}' has no audio track.")
        clip.audio.write_audiofile(audio_path, verbose=False, logger=None)
        clip.close()
        return audio_path, duration
    except ImportError as exc:
        if settings.demo_mode:
            logger.warning("moviepy not installed; using synthetic demo WAV in DEMO_MODE.")
            wav_bytes = _generate_demo_wav_bytes(duration_sec=30.0)
            Path(audio_path).write_bytes(wav_bytes)
            return audio_path, 30.0
        raise RuntimeError(
            "moviepy is required for audio extraction when not running with WAV/DEMO_MODE."
        ) from exc

