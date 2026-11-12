"""Pluggable transcription & speaker diarization interface."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config import get_media_settings
from contracts.meeting_ended import Participant, TranscriptSegment
from pipeline.gnani_client import GnaniVoiceEngine

logger = logging.getLogger(__name__)


@dataclass
class TranscriptResult:
    segments: List[TranscriptSegment]
    language: str
    provider: str
    speaker_hints: Dict[str, str]


class Transcriber(ABC):
    """Abstract interface for speech-to-text with speaker diarization."""

    name: str

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        language_hint: str = "auto-detect",
        force_demo: bool = False,
    ) -> TranscriptResult:
        """Transcribe an audio file into diarized TranscriptSegments."""


class GnaniPrismaTranscriber(Transcriber):
    """Default sprint transcriber powered by Gnani Prisma V3.0 (Hinglish & Indic)."""

    name = "gnani_prisma"

    def __init__(self, engine: Optional[GnaniVoiceEngine] = None) -> None:
        self.engine = engine or GnaniVoiceEngine()

    def transcribe(
        self,
        audio_path: str,
        language_hint: str = "auto-detect",
        force_demo: bool = False,
    ) -> TranscriptResult:
        raw = self.engine.transcribe_audio(
            audio_path,
            language_code=language_hint,
            force_demo=force_demo,
        )
        speaker_hints: Dict[str, str] = {}
        segments: List[TranscriptSegment] = []

        raw_segments = raw.get("segments") or []
        if not raw_segments and raw.get("transcript"):
            raw_segments = [{"speaker": "SPEAKER_01", "start": 0.0, "end": 5.0, "text": raw["transcript"]}]

        for item in raw_segments:
            speaker = str(item.get("speaker") or "SPEAKER_01")
            if item.get("speaker_hint"):
                speaker_hints[speaker] = str(item["speaker_hint"])
            start = float(item.get("start", 0.0))
            end = float(item.get("end", max(start + 1.0, start)))
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            segments.append(
                TranscriptSegment(
                    speaker=speaker,
                    speaker_user_id=None,
                    start=start,
                    end=end,
                    text=text,
                )
            )

        return TranscriptResult(
            segments=segments,
            language=str(raw.get("language") or "hi-en"),
            provider=self.name,
            speaker_hints=speaker_hints,
        )


class GoogleSTTTranscriber(Transcriber):
    """Fallback transcriber using Google Cloud Speech-to-Text with speaker tags."""

    name = "google_stt"

    def transcribe(
        self,
        audio_path: str,
        language_hint: str = "hi-IN",
    ) -> TranscriptResult:
        from google.cloud import speech  # type: ignore

        client = speech.SpeechClient()
        with open(audio_path, "rb") as f:
            content = f.read()

        audio = speech.RecognitionAudio(content=content)
        encoding = (
            speech.RecognitionConfig.AudioEncoding.LINEAR16
            if audio_path.endswith(".wav")
            else speech.RecognitionConfig.AudioEncoding.MP3
        )
        config = speech.RecognitionConfig(
            encoding=encoding,
            sample_rate_hertz=16000,
            language_code=language_hint if language_hint != "auto-detect" else "hi-IN",
            enable_automatic_punctuation=True,
            diarization_config=speech.SpeakerDiarizationConfig(
                enable_speaker_diarization=True,
                min_speaker_count=1,
                max_speaker_count=6,
            ),
        )
        operation = client.long_running_recognize(config=config, audio=audio)
        response = operation.result(timeout=300)
        if not response.results:
            return TranscriptResult(segments=[], language=language_hint, provider=self.name, speaker_hints={})

        last_res = response.results[-1]
        detected_lang = getattr(last_res, "language_code", language_hint) or language_hint
        words = last_res.alternatives[0].words
        segments: List[TranscriptSegment] = []

        cur_speaker: Optional[int] = None
        cur_words: List[str] = []
        seg_start = 0.0
        seg_end = 0.0

        for w in words:
            if cur_speaker is None:
                cur_speaker = w.speaker_tag
                seg_start = w.start_time.total_seconds()
            if w.speaker_tag != cur_speaker:
                segments.append(
                    TranscriptSegment(
                        speaker=f"SPEAKER_{cur_speaker:02d}",
                        speaker_user_id=None,
                        start=seg_start,
                        end=max(seg_start, seg_end),
                        text=" ".join(cur_words).strip(),
                    )
                )
                cur_speaker = w.speaker_tag
                cur_words = []
                seg_start = w.start_time.total_seconds()
            cur_words.append(w.word)
            seg_end = w.end_time.total_seconds()

        if cur_words and cur_speaker is not None:
            segments.append(
                TranscriptSegment(
                    speaker=f"SPEAKER_{cur_speaker:02d}",
                    speaker_user_id=None,
                    start=seg_start,
                    end=max(seg_start, seg_end),
                    text=" ".join(cur_words).strip(),
                )
            )

        return TranscriptResult(
            segments=segments,
            language=detected_lang,
            provider=self.name,
            speaker_hints={},
        )


class WhisperXTranscriber(Transcriber):
    """Local/GPU WhisperX + pyannote diarization provider."""

    name = "whisperx"

    def transcribe(
        self,
        audio_path: str,
        language_hint: str = "auto-detect",
    ) -> TranscriptResult:
        import os
        import whisperx  # type: ignore

        settings = get_media_settings()
        device = os.getenv("WHISPERX_DEVICE", "cpu")
        compute_type = "int8" if device == "cpu" else "float16"
        model = whisperx.load_model(settings.whisperx_model, device, compute_type=compute_type)
        audio = whisperx.load_audio(audio_path)
        result = model.transcribe(audio, batch_size=8)
        detected_lang = result.get("language", "en")

        hf_token = os.getenv("HF_TOKEN", "").strip()
        if hf_token:
            diarize_model = whisperx.DiarizationPipeline(use_auth_token=hf_token, device=device)
            diarize_segments = diarize_model(audio)
            result = whisperx.assign_word_speakers(diarize_segments, result)

        segments: List[TranscriptSegment] = []
        for idx, seg in enumerate(result.get("segments", []), start=1):
            text = str(seg.get("text") or "").strip()
            if not text:
                continue
            segments.append(
                TranscriptSegment(
                    speaker=str(seg.get("speaker") or f"SPEAKER_{idx:02d}"),
                    speaker_user_id=None,
                    start=float(seg.get("start", 0.0)),
                    end=float(seg.get("end", 0.0)),
                    text=text,
                )
            )
        return TranscriptResult(
            segments=segments,
            language=detected_lang,
            provider=self.name,
            speaker_hints={},
        )


def get_transcriber(name: Optional[str] = None) -> Transcriber:
    """Factory reading TRANSCRIBER env var (gnani_prisma | whisperx | google_stt)."""
    settings = get_media_settings()
    choice = (name or settings.transcriber or "gnani_prisma").strip().lower()
    if choice == "gnani_prisma":
        return GnaniPrismaTranscriber()
    if choice == "whisperx":
        return WhisperXTranscriber()
    if choice == "google_stt":
        return GoogleSTTTranscriber()
    raise ValueError(f"Unsupported TRANSCRIBER '{choice}'. Expected gnani_prisma, whisperx, or google_stt.")


def resolve_speaker_user_ids(
    segments: List[TranscriptSegment],
    participants: List[Participant],
    speaker_map: Optional[Dict[str, str]] = None,
    speaker_hints: Optional[Dict[str, str]] = None,
) -> List[TranscriptSegment]:
    """Deterministically attach speaker_user_id when mapped or uniquely matched; never guess."""
    explicit_map = speaker_map or {}
    hints = speaker_hints or {}
    resolved: List[TranscriptSegment] = []

    for seg in segments:
        user_id: Optional[str] = None
        if seg.speaker in explicit_map:
            user_id = explicit_map[seg.speaker]
        elif seg.speaker in hints and participants:
            hint_name = hints[seg.speaker].strip().lower()
            matches = [
                p.clerk_user_id
                for p in participants
                if hint_name in p.display_name.lower() or p.display_name.lower().startswith(hint_name)
            ]
            # Only resolve if unambiguous single match; never guess on ties
            if len(matches) == 1:
                user_id = matches[0]

        resolved.append(
            seg.model_copy(update={"speaker_user_id": user_id})
        )

    return resolved

