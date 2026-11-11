"""Environment-driven configuration for services/media."""

from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class MediaSettings:
    app_env: str
    demo_mode: bool
    media_port: int
    workos_url: str
    shared_hmac_secret: str

    # Providers (never hardcoded)
    transcriber: str
    tts_provider: str
    whisperx_model: str

    # Gnani AI
    gnani_api_key: str
    gnani_token: str
    gnani_stt_endpoint: str
    gnani_tts_endpoint: str
    gnani_prisma_model: str
    gnani_timbre_voice: str

    # Gemini / Summaries
    gemini_api_key: str
    llm_extraction_model: str
    llm_fallback_model: str

    # Storage / DB
    cloudinary_cloud_name: str
    cloudinary_api_key: str
    cloudinary_api_secret: str
    supabase_url: str
    supabase_key: str
    temp_dir: str
    dead_letter_dir: str


def get_media_settings() -> MediaSettings:
    supa_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or ""
    ).strip()
    return MediaSettings(
        app_env=os.getenv("APP_ENV", "development").strip(),
        demo_mode=_as_bool(os.getenv("DEMO_MODE"), default=True),
        media_port=int(os.getenv("MEDIA_PORT", "5001")),
        workos_url=os.getenv("WORKOS_URL", "http://localhost:8000").strip(),
        shared_hmac_secret=os.getenv("SHARED_HMAC_SECRET", "").strip(),
        transcriber=os.getenv("TRANSCRIBER", "gnani_prisma").strip().lower(),
        tts_provider=os.getenv("TTS_PROVIDER", "gnani_timbre").strip().lower(),
        whisperx_model=os.getenv("WHISPERX_MODEL", "small").strip(),
        gnani_api_key=os.getenv("GNANI_API_KEY", "").strip(),
        gnani_token=os.getenv("GNANI_TOKEN", "").strip(),
        gnani_stt_endpoint=os.getenv("GNANI_STT_ENDPOINT", "https://api.gnani.ai/speech-to-text/v3").strip(),
        gnani_tts_endpoint=os.getenv("GNANI_TTS_ENDPOINT", "https://api.gnani.ai/text-to-speech/v1").strip(),
        gnani_prisma_model=os.getenv("GNANI_PRISMA_MODEL", "Gnani Prisma V3.0").strip(),
        gnani_timbre_voice=os.getenv("GNANI_TIMBRE_VOICE", "indic-male-default").strip(),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        llm_extraction_model=os.getenv("LLM_EXTRACTION_MODEL", "gemini-2.0-flash").strip(),
        llm_fallback_model=os.getenv("LLM_FALLBACK_MODEL", "gemini-1.5-flash").strip(),
        cloudinary_cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", "").strip(),
        cloudinary_api_key=os.getenv("CLOUDINARY_API_KEY", "").strip(),
        cloudinary_api_secret=os.getenv("CLOUDINARY_API_SECRET", "").strip(),
        supabase_url=os.getenv("SUPABASE_URL", "").strip(),
        supabase_key=supa_key,
        temp_dir=os.getenv("MEDIA_TEMP_DIR", "temp").strip(),
        dead_letter_dir=os.getenv("MEDIA_DEAD_LETTER_DIR", "services/media/.dead_letters").strip(),
    )
