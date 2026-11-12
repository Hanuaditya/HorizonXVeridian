"""Gnani AI Voice Engine: Prisma V3.0 (STT + Diarization) and Timbre (TTS)."""

from __future__ import annotations

import io
import logging
import math
import struct
import wave
from typing import Any, Dict, List, Optional

import requests

from config import get_media_settings

logger = logging.getLogger(__name__)


def _has_real_key(key: str) -> bool:
    return bool(key and "placeholder" not in key.lower())


def _generate_demo_wav_bytes(duration_sec: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Synthesize a valid mono 16kHz PCM WAV clip for offline DEMO_MODE."""
    num_samples = max(1, int(duration_sec * sample_rate))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(num_samples):
            val = int(1200 * math.sin(2.0 * math.pi * 220.0 * i / sample_rate))
            frames.extend(struct.pack("<h", val))
        wf.writeframes(bytes(frames))
    return buf.getvalue()


def _demo_prisma_response() -> Dict[str, Any]:
    """Deterministic Hinglish code-mixed diarized output matching Challenge golden script."""
    return {
        "model": "Gnani Prisma V3.0 (DEMO_MODE)",
        "language": "hi-en",
        "segments": [
            {
                "speaker": "SPEAKER_01",
                "speaker_hint": "Dov",
                "start": 0.0,
                "end": 12.0,
                "text": "Team, welcome. We have three main items today.",
            },
            {
                "speaker": "SPEAKER_01",
                "speaker_hint": "Dov",
                "start": 12.5,
                "end": 28.0,
                "text": "First, Jason, please deploy the Elastic search cluster directly to production by Thursday.",
            },
            {
                "speaker": "SPEAKER_02",
                "speaker_hint": "Amit",
                "start": 28.5,
                "end": 42.0,
                "text": "Par Dov bhai, Jason toh agle Monday tak paternity leave pe hai!",
            },
            {
                "speaker": "SPEAKER_01",
                "speaker_hint": "Dov",
                "start": 42.5,
                "end": 62.0,
                "text": "Oh right. Josh, can you take that over and deploy it directly to AWS production?",
            },
            {
                "speaker": "SPEAKER_03",
                "speaker_hint": "Scott",
                "start": 62.5,
                "end": 82.0,
                "text": "Wait, our staging policy says any major database upgrade needs at least 14 days bake time in staging first. We cannot skip to prod.",
            },
            {
                "speaker": "SPEAKER_03",
                "speaker_hint": "Scott",
                "start": 82.5,
                "end": 98.0,
                "text": "Also, Dov, that enterprise cluster instance will cost around Rs 2.5 Lakhs a month.",
            },
            {
                "speaker": "SPEAKER_02",
                "speaker_hint": "Amit",
                "start": 98.5,
                "end": 116.0,
                "text": "Let me check finance... Hamara compute budget for this quarter is already 0. We need approval before provisioning enterprise tier.",
            },
            {
                "speaker": "SPEAKER_01",
                "speaker_hint": "Dov",
                "start": 116.5,
                "end": 128.0,
                "text": "Theek hai, let's have the AI platform check our policies, route it to the right person, and create the tickets. Meeting adjourned!",
            },
        ],
    }


_SUPPORTED_VACHANA_LANGS = {
    "as-IN", "bn-IN", "en-IN", "gu-IN", "hi-IN", "indic-auto",
    "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN",
}


def _normalize_stt_language_code(lang: str) -> str:
    val = (lang or "").strip()
    if val in _SUPPORTED_VACHANA_LANGS:
        return val
    low = val.lower()
    if low in {"", "auto", "auto-detect", "indic-auto"}:
        return "indic-auto"
    if low in {"hi-en", "hinglish", "en", "en-in"}:
        return "en-IN"
    if low in {"hi", "hi-in"}:
        return "hi-IN"
    return "indic-auto"


def _pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 48000) -> bytes:
    """Wrap raw 16-bit mono signed PCM (returned by Gnani Timbre) in a RIFF WAV header."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


class GnaniVoiceEngine:
    """Wrapper over Gnani Prisma V3.0 STT and Gnani Timbre TTS APIs."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        token: Optional[str] = None,
        stt_endpoint: Optional[str] = None,
        tts_endpoint: Optional[str] = None,
        prisma_model: Optional[str] = None,
        timbre_model: Optional[str] = None,
    ) -> None:
        settings = get_media_settings()
        self.api_key = (api_key if api_key is not None else settings.gnani_api_key).strip()
        self.token = (token if token is not None else settings.gnani_token).strip()
        self.stt_endpoint = (stt_endpoint or settings.gnani_stt_endpoint).rstrip("/")
        self.tts_endpoint = (tts_endpoint or settings.gnani_tts_endpoint).rstrip("/")
        self.prisma_model = prisma_model or settings.gnani_prisma_model
        self.timbre_model = timbre_model or settings.gnani_timbre_model
        self.demo_mode = settings.demo_mode

        self.headers: Dict[str, str] = {}
        if self.api_key:
            self.headers["X-API-Key-ID"] = self.api_key
            self.headers["x-api-key"] = self.api_key
        if self.token and "placeholder" not in self.token.lower():
            self.headers["Authorization"] = f"Bearer {self.token}"

    def transcribe_audio(
        self,
        audio_file_path: str,
        language_code: str = "auto-detect",
        force_demo: bool = False,
    ) -> Dict[str, Any]:
        """Transcribe audio with Gnani Vachana Prisma V3.0 STT + speaker diarization."""
        if force_demo or not _has_real_key(self.api_key):
            if force_demo or self.demo_mode:
                logger.info("GnaniVoiceEngine: using deterministic Hinglish DEMO_MODE STT fixture.")
                return _demo_prisma_response()
            raise EnvironmentError("GNANI_API_KEY is required when DEMO_MODE=false.")

        with open(audio_file_path, "rb") as audio:
            files = {"audio_file": audio}
            data = {
                "model": self.prisma_model,
                "language_code": _normalize_stt_language_code(language_code),
            }
            response = requests.post(
                self.stt_endpoint,
                headers=self.headers,
                files=files,
                data=data,
                timeout=20.0,
            )
            response.raise_for_status()
            payload = response.json()
            if "segments" not in payload and payload.get("transcript"):
                payload["segments"] = [
                    {
                        "speaker": "SPEAKER_01",
                        "start": 0.0,
                        "end": 5.0,
                        "text": str(payload["transcript"]).strip(),
                    }
                ]
            return payload

    def synthesize_speech(
        self,
        text: str,
        target_lang: str = "hi",
        voice: Optional[str] = None,
        speed: float = 1.0,
        force_demo: bool = False,
    ) -> bytes:
        """Synthesize speech using Gnani Vachana Timbre TTS."""
        settings = get_media_settings()
        chosen_voice = voice or settings.gnani_timbre_voice

        if force_demo or not _has_real_key(self.api_key):
            if force_demo or self.demo_mode:
                est_duration = max(0.5, min(6.0, len(text.split()) * 0.25))
                return _generate_demo_wav_bytes(duration_sec=est_duration)
            raise EnvironmentError("GNANI_API_KEY is required when DEMO_MODE=false.")

        payload = {
            "model": self.timbre_model,
            "text": text,
            "language": target_lang,
            "voice": chosen_voice,
            "speed": speed,
        }
        response = requests.post(
            self.tts_endpoint,
            headers=self.headers,
            json=payload,
            timeout=20.0,
        )
        response.raise_for_status()
        audio_bytes = response.content
        if audio_bytes and not audio_bytes.startswith((b"RIFF", b"ID3", b"fLaC", b"OggS")):
            return _pcm_to_wav_bytes(audio_bytes, sample_rate=48000)
        return audio_bytes

