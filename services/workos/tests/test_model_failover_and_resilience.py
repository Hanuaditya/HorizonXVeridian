"""Unit tests verifying automatic LLM failover, 503 resilience, and deterministic speaker-turn extraction."""

from __future__ import annotations

import logging
import sys
import time
from types import SimpleNamespace
from typing import List

import pytest
from pydantic import BaseModel

import core.evon_llm as evon_llm
from agent.nodes.extractor import ExtractionOutput
from core.evon_llm import (
    _get_gemini_candidates,
    _is_transient_or_outage_error,
    _sanitize_reason,
    demo_extract_from_transcript,
    structured_output,
    wrap_untrusted_data,
)


class _SampleProbe(BaseModel):
    answer: str


def test_is_transient_or_outage_error():
    assert _is_transient_or_outage_error(RuntimeError("503 UNAVAILABLE: The model is overloaded. Please try again later."))
    assert _is_transient_or_outage_error(Exception("429 ResourceExhausted: Quota exceeded for quota metric"))
    assert _is_transient_or_outage_error(Exception("high demand on models, please retry"))
    assert _is_transient_or_outage_error(Exception("Server connection reset / timeout"))
    assert _is_transient_or_outage_error(None) is False
    assert _is_transient_or_outage_error(ValueError("Invalid schema validation")) is False


def test_sanitize_reason_redacts_secrets_and_emails():
    raw_error = Exception(
        "Call failed with key AIzaSyD1234567890abcdef1234567890abcde for user test.engineer@domain.com "
        "and slack token xoxb-123456-abcdef789 on host https://generativelanguage.googleapis.com"
    )
    sanitized = _sanitize_reason(raw_error)
    assert "AIzaSy" not in sanitized
    assert "xoxb-" not in sanitized
    assert "test.engineer@domain.com" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized
    assert "[REDACTED_EMAIL]" in sanitized


def test_gemini_503_failover_to_backup_model(monkeypatch, caplog):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("DEMO_FALLBACK", "false")
    monkeypatch.setenv("EVON_API_KEY", "")
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key_live_503")
    monkeypatch.setenv("LLM_EXTRACTION_MODEL", "gemini-3-flash-preview")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite")

    models_called: List[str] = []

    class _MockGemini:
        def __init__(self, model: str, **kwargs):
            self.model = model

        def invoke(self, messages):
            models_called.append(self.model)
            if self.model == "gemini-3-flash-preview":
                raise RuntimeError("503 UNAVAILABLE: The model is overloaded due to high demand. Please try again later.")
            return SimpleNamespace(content='{"answer": "failover-success-2.5-flash"}')

    fake_genai = SimpleNamespace(ChatGoogleGenerativeAI=_MockGemini)
    monkeypatch.setitem(sys.modules, "langchain_google_genai", fake_genai)

    with caplog.at_level(logging.WARNING):
        res = structured_output(
            system_prompt="Return json",
            user_prompt="Give me answer",
            schema=_SampleProbe,
        )

    assert res is not None
    assert res.answer == "failover-success-2.5-flash"
    assert "gemini-3-flash-preview" in models_called
    assert "gemini-2.5-flash" in models_called
    assert any("LLM model failover: provider=google_gemini, primary_model=gemini-3-flash-preview, fallback_model=gemini-2.5-flash" in rec.message for rec in caplog.records)


def test_all_gemini_models_503_engages_deterministic_fallback(monkeypatch, caplog):
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("DEMO_FALLBACK", "false")
    monkeypatch.setenv("EVON_API_KEY", "")
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key_live_outage")
    monkeypatch.setenv("LLM_EXTRACTION_MODEL", "gemini-3-flash-preview")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "gemini-2.5-flash")

    class _Always503Gemini:
        def __init__(self, model: str, **kwargs):
            self.model = model

        def invoke(self, messages):
            raise RuntimeError(f"503 UNAVAILABLE on {self.model}: high demand outage")

    fake_genai = SimpleNamespace(ChatGoogleGenerativeAI=_Always503Gemini)
    monkeypatch.setitem(sys.modules, "langchain_google_genai", fake_genai)

    transcript = (
        "[10:00 - Arjun Rao]: Please deploy the authentication service to staging.\n"
        "[10:02 - catchme if]: I will handle the AWS cluster provisioning.\n"
        "[10:05 - Resigo]: We decided to integrate OAuth 2.0 PKCE flow."
    )
    user_prompt = wrap_untrusted_data("transcript", transcript)

    with caplog.at_level(logging.WARNING):
        out = structured_output(
            system_prompt="Extract structured tasks",
            user_prompt=user_prompt,
            schema=ExtractionOutput,
        )

    assert out is not None
    assert isinstance(out, ExtractionOutput)
    assert len(out.tasks) >= 2
    assignees = [t.assignee for t in out.tasks]
    assert "catchme if" in assignees or "Arjun Rao" in assignees
    assert any("All Gemini candidate models exhausted" in rec.message for rec in caplog.records)
    assert any("Engaging deterministic fallback extractor for ExtractionOutput" in rec.message for rec in caplog.records)


def test_demo_fallback_flag_deterministic_speaker_turn_extraction(monkeypatch):
    monkeypatch.setenv("DEMO_FALLBACK", "true")

    transcript = (
        "[11:00 - catchme if]: Main database connection pool ko optimize kar doon ga.\n"
        "[11:05 - Resigo]: Frontend login modal par error boundary add kar dunga.\n"
        "[11:10 - Arjun Rao]: We decided to freeze sprint scope today."
    )
    user_prompt = wrap_untrusted_data("meeting_transcript", transcript)

    out = structured_output(
        system_prompt="Extract tasks",
        user_prompt=user_prompt,
        schema=ExtractionOutput,
    )

    assert out is not None
    assert isinstance(out, ExtractionOutput)
    assert len(out.tasks) >= 2
    task_titles = [t.title.lower() for t in out.tasks]
    assert any("database" in t or "optimize" in t or "pool" in t for t in task_titles)
    assert any("login" in t or "frontend" in t or "error boundary" in t for t in task_titles)
    assert len(out.key_decisions) >= 1
