# ADR-0001: Sovereign Indic Speech & Reasoning Pivot (Gnani AI Ecosystem)

- **Status:** Accepted
- **Date:** 2026-11-11
- **Context:** The Great Indian AI Internship Challenge (Gnani AI) & Horizon Veridian integration sprint.

## Context & Problem Statement

The baseline architecture relied exclusively on:
1. Google STT (`TRANSCRIBER=google_stt`) / WhisperX, which underperforms on Indian enterprise English accents and intra-sentence code-mixed *Hinglish* (e.g., *"Yaar, Jason leave pe hai, to Elastic production deployment Josh karega"*).
2. Google Cloud TTS for dubbing, which lacks natural Indic voice prosody.
3. US-hosted NVIDIA NIM Llama 3.1 70B (`LLM_REASONING_MODEL`), without a sovereign Indian AI model option.
4. Hard external API dependencies blocking local end-to-end verification before all vendor credentials are provisioned.

## Decision

1. **Pluggable Gnani AI Providers (Config-Driven, Zero Hardcoded Literals):**
   - **STT + Diarization (`services/media`):** Add `GnaniPrismaTranscriber` calling `GNANI_STT_ENDPOINT` with `GNANI_PRISMA_MODEL` behind the `Transcriber` interface alongside `WhisperXTranscriber` and `GoogleSTTTranscriber`, selected via `TRANSCRIBER` (defaulting to `gnani_prisma` for the sprint).
   - **TTS (`services/media`):** Add `GnaniTimbreSynthesizer` calling `GNANI_TTS_ENDPOINT` with `GNANI_TIMBRE_VOICE` alongside Google TTS, selected via `TTS_PROVIDER` (defaulting to `gnani_timbre`).
   - **LLM Reasoning & Extraction (`services/workos`):** Add `EvonLLMClient` (`EVON_MODEL_NAME`, `EVON_API_BASE`, `EVON_API_KEY` / `HF_TOKEN`) into the config-driven LLM router alongside `ChatGoogleGenerativeAI` (`LLM_EXTRACTION_MODEL`) and NVIDIA NIM (`LLM_REASONING_MODEL`).
2. **Deterministic Offline Embedding & `DEMO_MODE` Support:**
   - Maintain `EMBEDDING_DIM=1024` across all `pgvector` HNSW indexes and startup checks (`ARCHITECTURE.md` §4/§5).
   - Add an offline deterministic 1024-dim semantic feature embedder when `DEMO_MODE=true` or when `NVIDIA_API_KEY` is unset, plus local SQLite/in-memory state store fallback and Jira/Slack mock dispatch receipts when `DEMO_MODE=true` and third-party tokens are missing.
   - Zero security weakening: webhook routes (`/api/slack-webhook`, `/api/github-webhook`, `/api/meeting-ended`) MUST STILL reject requests when secrets are missing.

## Consequences

- **Positive:** Immediate offline end-to-end execution of the Hinglish golden demo flow and test suite before live credentials are inserted; seamless drop-in upgrade to live Gnani Prisma V3.0, Timbre, Evon 30B, Supabase pgvector, Clerk, Jira, and Slack once keys are added to `.env`.
- **Negative / Risks:** Two code paths exist inside provider wrappers (`live` vs `DEMO_MODE` fallback); mitigated by strict contract validation (`packages/contracts`) and automated tests for both mocked HTTP clients and deterministic demo execution.
