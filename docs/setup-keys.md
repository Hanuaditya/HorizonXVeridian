# Environment Variables & Secrets Setup Guide

This document lists every environment variable required by **Horizon Veridian**, where to obtain/configure it, and which implementation phase requires it. 

> [!CAUTION]
> **Never commit real credentials or the `.env` file to version control.** Store your actual credentials in `C:\dev\horizon-veridian\.env` (which is excluded by `.gitignore`).

---

## 1. Core & Architecture

| Variable Name | Required By | Phase | Where to Obtain / Notes |
| :--- | :--- | :--- | :--- |
| `APP_ENV` | All | 1 | Set to `development` or `production`. |
| `DEMO_MODE` | All | 1–5 | Set to `true` to use deterministic local fallbacks when vendor API keys (Gnani/Jira/Slack/Supabase) are unset in development. |
| `SHARED_HMAC_SECRET` | Media, WorkOS | 1, 3 | A 64-character random hex string for signing service-to-service HTTP requests (`python -c "import secrets; print(secrets.token_hex(32))"`). |
| `FRONTEND_URL` | Web, WorkOS | 1 | Base URL of the web frontend (default: `http://localhost:3000`). |
| `MEDIA_URL` | Web, WorkOS | 1 | URL of the media microservice (default: `http://localhost:5001`). |
| `WORKOS_URL` | Web, Media | 1 | URL of the WorkOS microservice (default: `http://localhost:8000`). |

---

## 2. Authentication & Tenancy (Clerk)

| Variable Name | Required By | Phase | Where to Obtain / Notes |
| :--- | :--- | :--- | :--- |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Web | 1, 2 | **Clerk Dashboard** → API Keys → Publishable key (`pk_test_...` or `pk_live_...`). |
| `CLERK_SECRET_KEY` | Web, WorkOS | 1, 2 | **Clerk Dashboard** → API Keys → Secret key (`sk_test_...` or `sk_live_...`). |
| `CLERK_JWKS_URL` | WorkOS | 2 | **Clerk Dashboard** → API Keys → Show JWT Public Key / JWKS URL (`https://<your-subdomain>.clerk.accounts.dev/.well-known/jwks.json`). Used for local token verification in FastAPI. |

*Clerk Configuration:*
- Enable **Organizations** in Clerk Dashboard (Configure → Organization Settings).
- Create roles: Manager (`org:admin`) and Member (`org:member`).
- Create a test organization with at least one manager and one regular member user.

---

## 3. Database & pgvector (Supabase)

| Variable Name | Required By | Phase | Where to Obtain / Notes |
| :--- | :--- | :--- | :--- |
| `NEXT_PUBLIC_SUPABASE_URL` | Web | 1, 2 | **Supabase Project Settings** → API → Project URL (`https://<project-ref>.supabase.co`). |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Web | 1, 2 | **Supabase Project Settings** → API → `anon` public key. |
| `SUPABASE_SERVICE_ROLE_KEY` | WorkOS, Media | 2 | **Supabase Project Settings** → API → `service_role` key (secret, bypasses RLS for backend service operations). |
| `DATABASE_URL` | WorkOS, Migrations | 2 | **Supabase Project Settings** → Database → Connection string (URI mode, e.g. `postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres` or port 6543 session mode). |

*Supabase Configuration:*
- In Supabase Dashboard, navigate to **Database** → **Extensions** and toggle **vector** (`pgvector`) to enabled.

---

## 4. Video & Audio Conferencing (Stream.io)

| Variable Name | Required By | Phase | Where to Obtain / Notes |
| :--- | :--- | :--- | :--- |
| `NEXT_PUBLIC_STREAM_API_KEY` | Web | 1 | **Stream Dashboard** → Video & Audio App → API Key. |
| `STREAM_API_KEY` | Web | 1 | Same as public key; used in Next.js Server Actions. |
| `STREAM_API_SECRET` | Web | 1 | **Stream Dashboard** → Video & Audio App → Secret. |

---

## 5. Gnani AI & Reasoning Models

| Variable Name | Required By | Phase | Where to Obtain / Notes |
| :--- | :--- | :--- | :--- |
| `GNANI_API_KEY` | Media | 3 | **Gnani AI Portal** (`app.gnani.ai`) → API key for Prisma V3.0 STT & Timbre TTS. |
| `GNANI_TOKEN` | Media | 3 | **Gnani AI Portal** (`app.gnani.ai`) → Access token header. |
| `GNANI_STT_ENDPOINT` | Media | 3 | Gnani Prisma STT endpoint (default: `https://api.gnani.ai/speech-to-text/v3`). |
| `GNANI_TTS_ENDPOINT` | Media | 3 | Gnani Timbre TTS endpoint (default: `https://api.gnani.ai/text-to-speech/v1`). |
| `GNANI_PRISMA_MODEL` | Media | 3 | Code-mixed STT model identifier (default: `Gnani Prisma V3.0`). |
| `GNANI_TIMBRE_VOICE` | Media | 3 | Timbre voice profile (default: `indic-male-default`). |
| `TRANSCRIBER` | Media | 3 | Transcription provider selector: `gnani_prisma`, `whisperx`, or `google_stt`. |
| `TTS_PROVIDER` | Media | 3 | TTS provider selector: `gnani_timbre` or `google_tts`. |
| `EVON_MODEL_NAME` | WorkOS | 4 | Sovereign Indic reasoning model (default: `gnani-ai/evon-30b`). |
| `EVON_API_BASE` | WorkOS | 4 | OpenAI-compatible inference base URL (Hugging Face / vLLM). |
| `EVON_API_KEY` | WorkOS | 4 | Hugging Face or vLLM API token (`HF_TOKEN`). |
| `GEMINI_API_KEY` | Media, WorkOS | 1, 3, 4 | **Google AI Studio** (https://aistudio.google.com/) → Get API key. |
| `NVIDIA_API_KEY` | WorkOS | 2, 4 | **NVIDIA Build** (https://build.nvidia.com/) → API key for Llama 3.1 & NV-Embed (optional fallback). |
| `NVIDIA_BASE_URL` | WorkOS | 2, 4 | NVIDIA NIM endpoint (default: `https://integrate.api.nvidia.com/v1`). |
| `LLM_EXTRACTION_MODEL` | WorkOS | 3 | Name of model for task extraction (default: `gemini-2.0-flash`). |
| `LLM_REASONING_MODEL` | WorkOS | 4 | Name of model for compliance resolution (default: `meta/llama-3.1-70b-instruct`). |
| `EMBEDDING_MODEL` | WorkOS | 2, 4 | Embedding model name (default: `nvidia/nv-embedqa-e5-v5`). |
| `EMBEDDING_DIM` | WorkOS, DB | 2 | Vector dimension integer (default: `1024`). Must match DB vector columns. |

---

## 6. Media Dubbing & Diarization (Horizon Services)

| Variable Name | Required By | Phase | Where to Obtain / Notes |
| :--- | :--- | :--- | :--- |
| `CLOUDINARY_CLOUD_NAME` | Media | 1, 3 | **Cloudinary Dashboard** → Cloud name for hosting dubbed video outputs. |
| `CLOUDINARY_API_KEY` | Media | 1, 3 | **Cloudinary Dashboard** → API Key. |
| `CLOUDINARY_API_SECRET` | Media | 1, 3 | **Cloudinary Dashboard** → API Secret. |
| `HF_TOKEN` | Media | 3 | **Hugging Face** user access token (required for pyannote speaker diarization models). |
| `GOOGLE_APPLICATION_CREDENTIALS` | Media | 3 | Path to Google Cloud Service Account JSON for Speech-to-Text and Text-to-Speech APIs. |

---

## 7. Compliance Thresholds & Workload Limits

| Variable Name | Required By | Phase | Where to Obtain / Notes |
| :--- | :--- | :--- | :--- |
| `SECURITY_THRESHOLD` | WorkOS | 4 | Cosine similarity threshold for security policy matching (default: `0.50`). |
| `FINANCE_THRESHOLD` | WorkOS | 4 | Cosine similarity threshold for budget overrun matching (default: `0.50`). |
| `COMMIT_MATCH_THRESHOLD`| WorkOS | 6 | Cosine similarity threshold for GitHub commit matching (default: `0.75`). |
| `COMMIT_MATCH_MARGIN` | WorkOS | 6 | Margin required above second-best match to avoid ambiguity (default: `0.15`). |
| `CAPACITY_LIMIT` | WorkOS | 4 | Max open Jira issues/points before flagging workload capacity (default: `10`). |
| `CAPACITY_NEW_HIRE_LIMIT`| WorkOS | 4 | Max issues for employees onboarded within 30 days (default: `2`). |

---

## 8. Integrations & Closed Loop (Jira, Slack, GitHub)

| Variable Name | Required By | Phase | Where to Obtain / Notes |
| :--- | :--- | :--- | :--- |
| `JIRA_BASE_URL` | WorkOS | 5 | Atlassian instance URL (`https://yourcompany.atlassian.net`). |
| `JIRA_EMAIL` | WorkOS | 5 | Email of the Atlassian user/service account creating tickets. |
| `JIRA_API_TOKEN` | WorkOS | 5 | Atlassian Account Settings → Security → Create API token. |
| `JIRA_PROJECT_KEY` | WorkOS | 5 | Jira project key (e.g. `VER` or `HOR`). |
| `SLACK_BOT_TOKEN` | WorkOS | 5, 6 | **Slack API Dashboard** → OAuth & Permissions → Bot User OAuth Token (`xoxb-...`). |
| `SLACK_SIGNING_SECRET` | WorkOS | 6 | **Slack API Dashboard** → Basic Information → Signing Secret. (Must reject requests if missing). |
| `SLACK_MANAGER_CHANNEL`| WorkOS | 5, 6 | Slack channel ID or name for escalations and review notifications (e.g. `#product-team`). |
| `GITHUB_WEBHOOK_SECRET` | WorkOS | 6 | Secret configured in GitHub repository Webhook settings. (Must reject requests if missing). |
