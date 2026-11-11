# Sprint Report: Sprints 1–4 (Phases 2–5 + Webhook Guardrails)

- **Date:** 2026-11-11
- **Branch:** `master`
- **Scope:** Implemented full offline-runnable & API-ready Horizon Veridian × Gnani AI stack (`db/`, `services/media/`, `services/workos/`, `apps/web/`) pending live vendor API credentials.

## Summary of Changes

1. **Architecture & Config Alignment (`docs/adr/0001-gnani-sovereign-ai-pivot.md`)**
   - Documented Gnani Prisma V3.0 (STT + diarization), Gnani Timbre (TTS), Gnani Evon 30B (reasoning), and `DEMO_MODE` deterministic local fallbacks while maintaining config-driven model names (`ARCHITECTURE.md` ADR-6) and `EMBEDDING_DIM=1024`.

2. **Unified Database, RLS, Seed & Auth (`db/`, `services/workos/`)**
   - Forward-only migrations `001`–`003`: `vector` extension, `current_org_id()`/`current_user_id()`/`current_org_role()` Clerk JWT helpers, Horizon tables + trigger-synced backward-compatible `recordings` table, WorkOS firewall/task/audit tables, HNSW `vector(1024)` indexes, and RLS on all tenant tables.
   - Offline deterministic 1024-dim semantic embedder (`services/workos/core/embeddings.py`) + seed CSV/JSON/MD data (`db/seed/seed_cli.py`, `db/seed/seed_data.sql`) + org-aware HR/Finance CSV/Security connectors.
   - Clerk JWKS JWT authentication (`services/workos/api/auth.py`) with `require_manager` role check and dev HMAC demo tokens when `CLERK_JWKS_URL` is unset in `development` + `DEMO_MODE`.

3. **Media Service (`services/media/`)**
   - Modular `pipeline/` implementing pluggable `Transcriber` (`GnaniPrismaTranscriber`, `WhisperXTranscriber`, `GoogleSTTTranscriber`), `GnaniVoiceEngine`, `resolve_speaker_user_ids` (strict `null` on unknown), bounded async `MediaJobManager` (`POST /media/jobs`, `GET /media/jobs/<id>`), timestamp-drift guard, Gemini config-driven summarizer, and HMAC-SHA256 `publisher.py` with retries & dead-lettering.

4. **WorkOS Service & Graph A/B (`services/workos/`)**
   - LangGraph Graph A (`ingest` -> `extractor` -> `resolve_assignees` -> 4-way parallel firewall -> `auto_router` -> `merge` -> `resolution_generator` -> `hitl_interrupt` -> `state_update` -> `dispatcher`) using thread-safe `SQLitePersistentSaver` / `PostgresSaver`.
   - Graph B closed loop (`intent_parser`, `semantic_matcher`, `ticket_resolver`, `escalation`) enforcing `turn_count >= 2` anti-loop escalation, commit similarity + margin checks, and strict rejection when `SLACK_SIGNING_SECRET` or `GITHUB_WEBHOOK_SECRET` is missing.
   - Authenticated org-scoped SSE with `Last-Event-ID` replay & REST `/api/threads/{id}/state` fallback.

5. **Unified Frontend (`apps/web/`)**
   - Added BFF routes under `apps/web/app/api/workos/` & `apps/web/app/api/media/jobs/`.
   - Added `/workos` (Live Work Hub + Manager HITL Panel + Firewall Badges + Audit Log), `/meetings` & `/meetings/[id]` (Original vs Dubbed player + Prisma diarized transcript), `/admin` (Employee Clerk/Slack/Jira mapping & connector sync), and Clerk `<OrganizationSwitcher />`.

## Remaining Work When Keys Arrive
- Paste live Supabase, Clerk, Stream.io, Gnani AI (`GNANI_API_KEY`, `GNANI_TOKEN`), HuggingFace/Evon (`EVON_API_KEY`), Jira, and Slack credentials into `C:\dev\horizon-veridian\.env`.
- Apply `db/migrations/001`–`003` and `db/seed/seed_data.sql` to live Supabase.
- Run Playwright E2E and golden-transcript eval calibration against `evals/` (Phase 7/8).
