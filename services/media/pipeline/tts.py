"""Pluggable Text-to-Speech synthesis & segment timing alignment."""

from __future__ import annotations

import io
import logging
import wave
from pathlib import Path
from typing import List, Optional

from config import get_media_settings
from contracts.meeting_ended import TranscriptSegment
from pipeline.gnani_client import GnaniVoiceEngine

logger = logging.getLogger(__name__)


def compute_bounded_speaking_rate(
    word_count: int,
    target_duration_sec: float,
    base_wpm: float = 130.0,
    min_rate: float = 0.70,
    max_rate: float = 1.45,
) -> float:
    """Compute bounded speech rate to keep dubbed segment aligned with slot duration."""
    if word_count <= 0 or target_duration_sec <= 0:
        return 1.0
    required_wpm = (word_count / max(target_duration_sec, 0.5)) * 60.0
    raw_rate = required_wpm / base_wpm
    return max(min_rate, min(max_rate, round(raw_rate, 3)))


def _wav_duration_seconds(wav_bytes: bytes) -> float:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 16000
            return frames / float(rate)
    except Exception:
        return 0.0


def synthesize_dubbed_track(
    segments: List[TranscriptSegment],
    translated_texts: List[str],
    video_duration: float,
    output_audio_path: str,
    target_lang: str = "en",
) -> str:
    """Synthesize aligned dubbed audio track using Gnani Timbre or Google TTS."""
    settings = get_media_settings()
    Path(output_audio_path).parent.mkdir(parents=True, exist_ok=True)
    provider = settings.tts_provider

    engine = GnaniVoiceEngine() if provider == "gnani_timbre" else None

    try:
        from pydub import AudioSegment  # type: ignore

        final_audio = AudioSegment.silent(duration=int(max(video_duration, 1.0) * 1000))
        for idx, (seg, text) in enumerate(zip(segments, translated_texts)):
            if not text.strip():
                continue
            slot_end = segments[idx + 1].start if idx + 1 < len(segments) else max(seg.end, video_duration)
            slot_dur = max(slot_end - seg.start, 1.5)
            rate = compute_bounded_speaking_rate(len(text.split()), slot_dur)

            if provider == "gnani_timbre" and engine is not None:
                audio_bytes = engine.synthesize_speech(text=text, target_lang=target_lang, speed=rate)
                seg_audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
            else:
                from google.cloud import texttospeech  # type: ignore

                tts_client = texttospeech.TextToSpeechClient()
                voice_name = "en-US-WaveNet-D" if idx % 2 == 0 else "en-US-WaveNet-F"
                res = tts_client.synthesize_speech(
                    input=texttospeech.SynthesisInput(text=text),
                    voice=texttospeech.VoiceSelectionParams(language_code="en-US", name=voice_name),
                    audio_config=texttospeech.AudioConfig(
                        audio_encoding=texttospeech.AudioEncoding.MP3,
                        speaking_rate=rate,
                    ),
                )
                seg_audio = AudioSegment.from_mp3(io.BytesIO(res.audio_content))

            seg_audio = seg_audio[: int(slot_dur * 1000)].fade_out(80)
            final_audio = final_audio.overlay(seg_audio, position=int(seg.start * 1000))

        fmt = "wav" if output_audio_path.endswith(".wav") else "mp3"
        final_audio.export(output_audio_path, format=fmt)
        return output_audio_path

    except ImportError:
        # Pure-stdlib WAV concatenation fallback when pydub is unavailable locally
        sample_rate = 16000
        target_total_frames = int(max(video_duration, 1.0) * sample_rate)
        combined = bytearray(target_total_frames * 2)

        for idx, (seg, text) in enumerate(zip(segments, translated_texts)):
            if not text.strip():
                continue
            slot_end = segments[idx + 1].start if idx + 1 < len(segments) else max(seg.end, video_duration)
            slot_dur = max(slot_end - seg.start, 1.0)
            rate = compute_bounded_speaking_rate(len(text.split()), slot_dur)
            if engine is not None:
                wav_bytes = engine.synthesize_speech(text=text, target_lang=target_lang, speed=rate)
                with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                    pcm = wf.readframes(wf.getnframes())
                start_byte = min(len(combined), int(seg.start * sample_rate) * 2)
                max_len = min(len(pcm), int(slot_dur * sample_rate) * 2, len(combined) - start_byte)
                if max_len > 0:
                    combined[start_byte : start_byte + max_len] = pcm[:max_len]

        with wave.open(output_audio_path, "wb") as out_wf:
            out_wf.setnchannels(1)
            out_wf.setsampwidth(2)
            out_wf.setframerate(sample_rate)
            out_wf.writeframes(bytes(combined))
        return output_audio_path
