"""Translation helper for dubbed tracks."""

from __future__ import annotations

import logging
from typing import List

import requests

from config import get_media_settings
from contracts.meeting_ended import TranscriptSegment

logger = logging.getLogger(__name__)


def translate_segments(
    segments: List[TranscriptSegment],
    source_lang: str,
    target_lang: str = "en",
) -> List[str]:
    """Translate transcript segments to target_lang; preserves text on failure or same language."""
    settings = get_media_settings()
    src_prefix = (source_lang or "en").split("-")[0].lower()
    tgt_prefix = (target_lang or "en").split("-")[0].lower()

    if src_prefix == tgt_prefix:
        return [s.text for s in segments]

    if settings.demo_mode and src_prefix in {"hi", "en"} and tgt_prefix == "en":
        return [s.text for s in segments]

    translated: List[str] = []
    for seg in segments:
        try:
            url = (
                f"https://api.mymemory.translated.net/get"
                f"?q={requests.utils.quote(seg.text)}&langpair={src_prefix}|{tgt_prefix}"
            )
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            out = resp.json().get("responseData", {}).get("translatedText")
            translated.append(out or seg.text)
        except Exception as exc:
            logger.debug("translate_segments fallback for segment: %s", exc)
            translated.append(seg.text)
    return translated

