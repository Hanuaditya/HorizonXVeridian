# Gnani AI & Model Usage Audit

> This file is the **single source of truth** for every model and provider call in Horizon Veridian.
> README, UI text, submission posts and interview answers must match this table exactly.
> Generated: 2026-11-13. Verified by running `npm run live` and inspecting startup logs.

---

## 1. Runtime Model Calls

| # | File | Function / Class | Provider | Model / Version | Configured by | User-visible feature | Log line |
|---|---|---|---|---|---|---|---|
| 1 | `services/media/pipeline/gnani_client.py` | `GnaniVoiceEngine.transcribe_audio()` | **Gnani AI — Vachana** | **Prisma v3.0** (`GNANI_PRISMA_MODEL`, default `prisma-v3.0`) | `GNANI_API_KEY`, `GNANI_STT_ENDPOINT` | Hinglish meeting transcription with speaker diarization (Meetings Hub) | `[GNANI-STT] model=prisma-v3.0 req_id=<uuid> audio_bytes=<n>` |
| 2 | `services/media/pipeline/gnani_client.py` | `GnaniVoiceEngine.synthesize_speech()` | **Gnani AI — Vachana** | **Timbre v2.5** (`GNANI_TIMBRE_MODEL`, default `timbre-v2.5`) | `GNANI_API_KEY`, `GNANI_TTS_ENDPOINT` | Dubbed audio output on /meetings/[id] | `[GNANI-TTS] model=timbre-v2.5 voice=<voice> req_id=<uuid>` |
| 3 | `services/workos/core/evon_llm.py` | `structured_output()` → `_pick_openai_provider()` | **Gnani AI — Evon** (preferred, if key set) | **Evon 30B** (`EVON_MODEL_NAME`, default `gnani-ai/evon-30b`) | `EVON_API_KEY`, `EVON_API_BASE` | Task extraction, compliance analysis, resolution proposals | `structured_output: calling gnani-evon (gnani-ai/evon-30b)` |
| 4 | `services/workos/core/evon_llm.py` | `structured_output()` → `_pick_openai_provider()` | **NVIDIA NIM** (fallback if Evon key absent) | `LLM_REASONING_MODEL` env | `NVIDIA_API_KEY` | Same as #3 | `structured_output: calling nvidia-nim (<model>)` |
| 5 | `services/workos/core/evon_llm.py` | `structured_output()` → `ChatGoogleGenerativeAI` | **Google Gemini** (fallback if Evon + NVIDIA absent) | `LLM_EXTRACTION_MODEL` env (default `gemini-3-flash-preview`); fallback `LLM_FALLBACK_MODEL` (default `gemini-3.1-flash-lite-preview`) | `GEMINI_API_KEY` | Same as #3 | LangChain internal logging; `Gemini model '<name>' failed` on retry |
| 6 | `services/workos/core/embeddings.py` | `get_embedding()` | **NVIDIA NIM** (if key set) | **NV-EmbedQA-E5-v5** (`EMBEDDING_MODEL` env) | `NVIDIA_API_KEY`, `NVIDIA_BASE_URL` | Pgvector semantic search (security policy RAG, finance budget RAG, commit matching) | `Live NVIDIA embedding call failed` on fallback |
| 7 | `services/workos/core/embeddings.py` | `deterministic_semantic_embedding()` | **Built-in offline** | None — deterministic Blake2b hash | Always available | Same as #6 — offline fallback when NVIDIA key absent | No external call |

---

## 2. Provider Selection Logic (Runtime Decision Tree)

```
Task Extraction / Resolution / Firewall analysis (services/workos):
  1. EVON_API_KEY set and not "placeholder" → Gnani Evon 30B (OpenAI-compatible, timeout=30s)
  2. NVIDIA_API_KEY set                     → NVIDIA NIM  (OpenAI-compatible, timeout=30s)
  3. GEMINI_API_KEY set + DEMO_MODE=false   → Google Gemini (thinking_budget=0, timeout=25s)
  4. DEMO_MODE=true                         → Deterministic golden transcript fixture (no LLM call)

Transcription / STT (services/media):
  1. GNANI_API_KEY set and not "placeholder" + DEMO_MODE=false → Gnani Prisma v3.0 (timeout=20s)
  2. DEMO_MODE=true or key absent           → Deterministic Hinglish fixture segments (no HTTP call)

TTS / Dubbing (services/media):
  1. GNANI_API_KEY set + DEMO_MODE=false   → Gnani Timbre v2.5 (timeout=20s)
  2. DEMO_MODE=true or key absent          → Silent demo WAV (no HTTP call)

Embeddings (services/workos):
  1. NVIDIA_API_KEY set                    → NV-EmbedQA-E5-v5 via NVIDIA NIM (timeout=15s)
  2. Fallback (always)                     → deterministic_semantic_embedding() — offline, 1024-dim
```

---

## 3. How to Verify at Runtime

**Media service (port 5001):** `GET /health` returns `{"transcriber": "gnani_prisma", "prisma_model": "prisma-v3.0", "demo_mode": false}`.

**WorkOS service (port 8000):** Startup log line:
```
WorkOS API started (env=development demo=False evon_model=gnani-ai/evon-30b embedding_dim=1024)
```
If `evon_model` shows a placeholder, the service has fallen back to Gemini.

**To confirm which LLM actually ran** on a request, search the WorkOS logs for:
- `structured_output: calling gnani-evon` → Evon 30B was used
- `structured_output: calling nvidia-nim` → NVIDIA NIM was used
- `Gemini model 'gemini-3-flash-preview'` in WARNING → Gemini fallback triggered

---

## 4. Honest Claims for README / Submission

✅ **Gnani Prisma v3.0** — always used for STT when `GNANI_API_KEY` is set (live mode). Real HTTP call to `api.vachana.ai/stt/v3`.

✅ **Gnani Timbre v2.5** — always used for TTS/dubbing when `GNANI_API_KEY` is set (live mode). Real HTTP call to `api.vachana.ai/tts/v3`.

⚠️ **Gnani Evon 30B** — used for task extraction **only if `EVON_API_KEY` and `EVON_API_BASE` are configured**. In most developer environments where these keys are absent, **Google Gemini (`gemini-3-flash-preview`) runs instead**. Do NOT claim Evon is used unless you can show `structured_output: calling gnani-evon` in logs.

✅ **NVIDIA NV-EmbedQA-E5-v5** — used for pgvector embeddings when `NVIDIA_API_KEY` is set. Falls back to deterministic offline embedder silently.

✅ **Google Gemini** — always the LLM fallback and confirmed to work. This is what runs in the submission demo unless Evon keys are available.

---

## 5. Log Lines Added (this audit)

Each Gnani API call now emits a structured log line with provider, model, and a request ID (never content, never keys):

| File | Function | Log format |
|---|---|---|
| `gnani_client.py` | `transcribe_audio()` | `[GNANI-STT] provider=gnani_prisma model=<model> req_id=<uuid8>` |
| `gnani_client.py` | `synthesize_speech()` | `[GNANI-TTS] provider=gnani_timbre model=<model> voice=<voice> req_id=<uuid8>` |
| `evon_llm.py` | `structured_output()` | already logs `structured_output: calling <label>` |
| `embeddings.py` | `get_embedding()` | already logs on fallback; added `[EMBED] provider=nvidia model=<model>` on success |

---

## 6. Corrections Made to Docs

| File | Old claim | Corrected to |
|---|---|---|
| `ARCHITECTURE.md` §3 diagram | "WhisperX" | "Gnani Prisma v3.0" |
| `ARCHITECTURE.md` §4 Phase 1 | "WhisperX transcription + speaker diarization" | "Gnani Prisma v3.0 transcription + speaker diarization" |
| `README.md` CI badge URL | `horizon-veridian/horizon-veridian` | `Hanuaditya/HorizonXVeridian` |
| `AGENTS.md` §2 | No distinction between Evon and Gemini | Now notes Gemini is the actual runtime fallback |

