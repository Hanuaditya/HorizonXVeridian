"""Video/audio recomposition with timestamp-drift guard and Cloudinary upload."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from config import get_media_settings

logger = logging.getLogger(__name__)


def assert_timestamp_drift_within_bounds(
    source_duration_sec: float,
    dubbed_duration_sec: float,
    max_drift_ratio: float = 0.05,
    max_drift_abs_sec: float = 1.5,
) -> float:
    """Guard against audio-video desync; returns absolute drift in seconds."""
    if source_duration_sec <= 0:
        return 0.0
    drift = abs(float(dubbed_duration_sec) - float(source_duration_sec))
    allowed = max(max_drift_abs_sec, float(source_duration_sec) * max_drift_ratio)
    if drift > allowed:
        raise ValueError(
            f"Timestamp drift exceeded guard: drift={drift:.2f}s > allowed={allowed:.2f}s "
            f"(source={source_duration_sec:.2f}s, dubbed={dubbed_duration_sec:.2f}s)"
        )
    return drift


def create_final_video(
    video_path: str,
    audio_path: str,
    output_video_path: str,
    expected_duration: Optional[float] = None,
) -> str:
    """Merge recomposed audio onto original video track with drift verification."""
    settings = get_media_settings()
    Path(output_video_path).parent.mkdir(parents=True, exist_ok=True)

    raw_head = Path(video_path).read_bytes()[:18] if Path(video_path).exists() else b""
    if raw_head.startswith(b"DEMO_VIDEO_FIXTURE"):
        Path(output_video_path).write_bytes(b"DEMO_DUBBED_VIDEO_FIXTURE")
        return output_video_path

    try:
        from moviepy.editor import AudioFileClip, VideoFileClip  # type: ignore

        v_clip = VideoFileClip(video_path)
        a_clip = AudioFileClip(audio_path)
        src_dur = float(expected_duration or v_clip.duration or 0.0)
        dub_dur = float(a_clip.duration or src_dur)
        assert_timestamp_drift_within_bounds(src_dur, dub_dur)

        if src_dur > 0 and dub_dur > src_dur:
            a_clip = a_clip.subclip(0, src_dur)

        final_clip = v_clip.set_audio(a_clip)
        final_clip.write_videofile(
            output_video_path,
            codec="libx264",
            audio_codec="aac",
            verbose=False,
            logger=None,
        )
        v_clip.close()
        a_clip.close()
        final_clip.close()
        return output_video_path
    except ImportError:
        if settings.demo_mode:
            Path(output_video_path).write_bytes(b"DEMO_DUBBED_VIDEO_FIXTURE")
            return output_video_path
        raise


def upload_to_cloudinary(file_path: str, job_id: str) -> str:
    """Upload dubbed video to Cloudinary, or return local URL in DEMO_MODE when unset."""
    settings = get_media_settings()
    has_creds = (
        settings.cloudinary_cloud_name
        and settings.cloudinary_api_key
        and settings.cloudinary_api_secret
        and "placeholder" not in settings.cloudinary_cloud_name.lower()
    )
    if not has_creds or Path(file_path).read_bytes()[:20].startswith(b"DEMO_DUBBED_VIDEO"):
        if settings.demo_mode:
            return f"demo://cloudinary/dubbed/{job_id}.mp4"
        raise EnvironmentError("Cloudinary credentials are required when DEMO_MODE=false.")

    import cloudinary  # type: ignore
    import cloudinary.uploader  # type: ignore

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
    )
    result = cloudinary.uploader.upload(file_path, resource_type="video")
    return str(result["secure_url"])
