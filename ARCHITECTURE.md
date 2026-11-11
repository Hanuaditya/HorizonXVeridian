# ARCHITECTURE.md — Horizon Veridian (Unified Platform)

> Source of truth for the merged project. Any IDE agent or developer must read this file before changing code.
> If code and this document disagree, stop and ask — do not silently diverge.

---

## 1. Product Summary

**Horizon Veridian** = Horizon Meet (video meetings, transcription, dubbing, summaries) + Veridian WorkOS (agentic task extraction, compliance firewall, human approval, Jira/Slack dispatch, closed-loop tracking).

One sentence: **a meeting ends, and compliant, approved work is created and tracked automatically.**

### The two original projects

| | Horizon Meet | Veridian WorkOS |
|---|---|---|
| Role | Capture + media intelligence | Decide + execute + track |
| Frontend | Next.js 15, Clerk, Stream.io | Next.js 14, Framer Motion, SSE |
| Backend | Flask (`dubbing-service`) | FastAPI + LangGraph |
| AI | Gemini, Google STT/TTS | Gemini, Llama 3.1 70B (NIM), NV-EmbedQA-E5-v5 |
| Data | Supabase, Cloudinary | Supabase + pgvector |

### Overlap that must be resolved

| Concern | Decision |
|---|---|
| Two Next.js apps | **Merge into one** `apps/web` (Next.js 15, matching Horizon Meet; port Veridian components to Next 15) |
| Two backends | **Keep two services** (different runtime profiles), joined by a signed contract |
| Two Supabase usages | **One Supabase project**, one schema, tenant-scoped |
| Auth | **Clerk** is the only identity provider; backends verify Clerk JWTs |
| Transcription | Pluggable provider (`TRANSCRIBER`). Default sprint: **Gnani Prisma V3.0** (Hinglish/Indic diarization); WhisperX & Google STT supported as alternatives |
| TTS / Dubbing | Pluggable provider (`TTS_PROVIDER`). Default sprint: **Gnani Timbre**; Google Cloud TTS supported as fallback |
| LLM model names | **Never hard-code.** All models come from env vars (`EVON_MODEL_NAME`, `LLM_EXTRACTION_MODEL`, `LLM_REASONING_MODEL`, `EMBEDDING_MODEL`) because model versions get deprecated |

---

## 2. Repository Layout (Monorepo)

```
horizon-veridian/
├── ARCHITECTURE.md
├── IMPLEMENTATION_PLAN.md
├── AGENT_RULES.md                 # master IDE prompt (copy to .cursorrules / CLAUDE.md)
├── docker-compose.yml
├── .env.example                   # root template, no real secrets ever
├── apps/
│   └── web/                       # ONE Next.js 15 app (matching Horizon Meet)
│       ├── app/
│       │   ├── (auth)/            # Clerk sign-in / sign-up
│       │   ├── (meet)/            # Horizon Meet: lobby, room, recordings, dubbing
│       │   ├── (workos)/          # Veridian: dashboard, approvals, tracker, audit
│       │   └── api/               # thin BFF routes only (token exchange, proxying)
│       ├── components/{meet,workos,ui}/
│       └── lib/{sse.ts,api-client.ts,auth.ts}
├── services/
│   ├── media/                     # Horizon Meet backend (Flask now, FastAPI optional later)
│   │   ├── app.py
│   │   ├── pipeline/{extract_audio,transcribe,translate,tts,recompose}.py
│   │   └── publisher.py           # emits meeting-ended event to workos
│   └── workos/                    # Veridian backend (FastAPI + LangGraph)
│       ├── api/{main.py,sse.py,auth.py,routes/}
│       ├── agent/{state.py,graph_a.py,graph_b.py,nodes/}
│       ├── connectors/{sync_hr.py,sync_finance.py,sync_security.py}
│       └── integrations/{jira.py,slack.py,github.py}
├── packages/
│   └── contracts/                 # SHARED schemas (single source of truth)
│       ├── meeting_ended.schema.json
│       ├── sse_events.schema.json
│       └── generated/{ts,py}/     # generated types, never hand-edited
├── db/
│   ├── migrations/                # numbered SQL, forward-only
│   └── seed/
├── infra/                         # Dockerfiles, deploy configs, CI
└── docs/
    ├── adr/                       # architecture decision records
    └── runbooks/
```

Rules:
- `packages/contracts` is the **only** place where cross-service payload shapes are defined. TS and Python types are generated from it.
- Services never import each other's code. They communicate via HTTP + contracts only.
- No secrets in git. `.env` files are git-ignored; only `.env.example` is committed. If any real key was ever committed in either old repo, **rotate it** before merging.

---

## 3. System Context

```
 Browser (Next.js, Clerk)
   │  video call via Stream.io                     ┌───────────────┐
   │                                               │  Cloudinary   │
   ▼                                               └──────▲────────┘
┌────────────────────────┐   recording URL    ┌──────────┴────────┐
│ apps/web  (Meet UI +   │──────────────────► │  services/media   │
│ WorkOS dashboard)      │                    │  WhisperX · TTS   │
└───────▲────────────────┘                    │  dubbing · summary│
        │ SSE (JWT)                           └──────────┬────────┘
        │                                                │ signed POST
        │                                                │ /api/meeting-ended
┌───────┴──────────────────────────────────────────────▼─────────┐
│                     services/workos (FastAPI)                   │
│   Graph A (meeting→tasks→firewall→HITL→dispatch)                │
│   Graph B (Slack/GitHub → intent → Jira close/escalate)         │
└───────┬──────────────┬───────────────┬────────────────┬────────┘
        ▼              ▼               ▼                ▼
   Supabase+pgvector   Jira            Slack            GitHub
```

---

## 4. End-to-End Flow

### Phase 1 — Capture & Media (`services/media`)
1. Meeting ends in Stream.io; recording lands in Cloudinary (or storage bucket). Web app calls `POST /media/jobs` with `meeting_id`, `recording_url`.
2. Pipeline: audio extraction → **WhisperX transcription + speaker diarization** → optional translation → TTS → video recomposition with timestamp alignment (drift guard).
3. Gemini generates the human-readable summary (existing Horizon Meet feature).
4. Media service stores artifacts and emits **`meeting.ended`** (see §6) to workos.

### Phase 2 — Ingestion & Extraction (Graph A start)
5. `POST /api/meeting-ended` (HMAC-signed). `ingest_node` does the idempotency check on `meeting_id`.
6. `extractor_node` extracts action items: title, assignee, deadline, parameters, plus decisions and meeting context.
7. **Speaker → employee resolution** (new, essential): diarization labels (`SPEAKER_01`) are mapped to real people via Clerk participant list → `employees` table. Unresolved assignees are flagged `UNRESOLVED_ASSIGNEE` and go to HITL, never guessed.

### Phase 3 — Parallel Compliance Firewall (fan-out)
| Node | Check | Source | Trigger |
|---|---|---|---|
| `hr_checker` | Assignee on leave/PTO | `hr_employees` | status in leave set |
| `capacity_checker` | Live workload | Jira API | open tickets / story points over `CAPACITY_LIMIT` |
| `security_checker` | Policy semantic match | `security_policies` pgvector | cosine similarity ≥ `SECURITY_THRESHOLD` (default 0.50) |
| `finance_checker` | Unapproved spend | `finance_budgets` pgvector | similarity ≥ `FINANCE_THRESHOLD` (default 0.50) |

Thresholds are env/config values, not literals. Embeddings are 1024-dim; the DB column dimension and `EMBEDDING_MODEL` must match (enforced by a startup check).

### Phase 4 — Fan-in & Resolution
8. `merge_node` combines results through `update_tasks_reducer` (field-level, non-None overwrite, race-safe).
9. `capacity_checker` over-threshold → `auto_router_node` (lowest-load active employee).
10. `resolution_generator_node` proposes per task: `PROCEED | REFRAME | REROUTE | DEFER | OVERRIDE`.

### Phase 5 — Human-in-the-Loop
11. If any task is not `PROCEED`, `hitl_interrupt_node` pauses via the **checkpointer**.
12. SSE streams `hitl_ready` to the manager dashboard. Manager Approve/Override → `POST /api/hitl-resume` → `Command(resume=…)` with `thread_id`.
13. **Checkpointer: `MemorySaver` only in local dev; `PostgresSaver` (Supabase) from Phase 4 of the plan onward.** A restart must not lose a pending approval.

### Phase 6 — Dispatch
14. `dispatcher_node` creates Jira tickets and sends Slack DMs. Must be idempotent (store `task_id → jira_key`; retries never duplicate tickets).

### Phase 7 — Closed Loop (Graph B)
15. **Slack webhook**: reply → intent classification `COMPLETE | PARTIAL | BLOCKED | AMBIGUOUS`. `BLOCKED` → flag Jira ticket + escalate to manager. `turn_count >= 2` → stop clarifying and escalate (anti-loop guardrail).
16. **GitHub webhook**: commit message embedded → pgvector match against open ticket vectors (`semantic_matcher`) → if similarity ≥ `COMMIT_MATCH_THRESHOLD` and unambiguous, transition ticket to Done. Ambiguous or multiple matches → ask assignee via Slack, never auto-close.
17. Every transition writes to `audit_trail`.

> Note: the original docs described Graph B two ways (intent-parser vs semantic-matcher). The unified design uses **both**: Slack events go through intent parsing; GitHub events go through semantic matching, and both feed the same `ticket_resolver`.

---

## 5. Data Model (single Supabase project)

All tenant tables carry `org_id` and have **Row Level Security** enabled.

| Table | Origin | Purpose |
|---|---|---|
| `organizations`, `members` | new | Clerk org/user mapping |
| `meetings` | Horizon | id, org_id, stream_call_id, recording_url, status, summary |
| `transcripts` | Horizon | meeting_id, segments JSONB `[{speaker, start, end, text}]`, language |
| `dubbing_jobs` | Horizon | meeting_id, target_lang, status, output_url |
| `employees` | Veridian | clerk_user_id, email, slack_id, jira_account_id, active, capacity_cache |
| `hr_employees` | Veridian | leave status from HR connector |
| `finance_budgets` | Veridian | category, amount, `embedding vector(1024)` |
| `security_policies` | Veridian | chunk text, policy_id, `embedding vector(1024)` |
| `processed_meetings` | Veridian | idempotency keys |
| `tasks` | new | persisted task state: assignee, status, flags, jira_key, vector |
| `resolutions`, `approvals` | new | AI proposals and manager decisions (who/when) |
| `audit_trail` | Veridian | append-only, with `provenance_tag` |
| `slack_threads` | new | ticket ↔ Slack thread, `turn_count` |

Migrations are numbered, forward-only, and reviewed. Never edit an applied migration.

---

## 6. Contracts (packages/contracts)

### 6.1 `meeting.ended` — media → workos
`POST {WORKOS_URL}/api/meeting-ended`

Headers: `X-Signature: sha256=<HMAC(body, SHARED_SECRET)>`, `X-Timestamp` (reject if older than 5 min), `Idempotency-Key: <meeting_id>`.

```json
{
  "meeting_id": "uuid",
  "org_id": "string",
  "title": "string",
  "started_at": "ISO-8601",
  "ended_at": "ISO-8601",
  "language": "en",
  "participants": [{ "clerk_user_id": "string", "display_name": "string", "email": "string" }],
  "transcript": [{ "speaker": "SPEAKER_01", "speaker_user_id": "string|null", "start": 0.0, "end": 4.2, "text": "string" }],
  "summary": "string|null",
  "recording_url": "string|null"
}
```
Response: `202 { "thread_id": "string" }`.

### 6.2 SSE events — workos → web
Envelope `{ "event_type": "...", "payload": {...} }`.
Events: `processing_started · resolution_ready · hitl_ready · dispatched · tracker_update · complete · error`.
`tracker_update` is new (Graph B progress, so the dashboard shows closure live).

### 6.3 Public API (workos)
| Method | Path | Auth |
|---|---|---|
| POST | `/api/meeting-ended` | HMAC (service-to-service) |
| GET | `/api/stream/{thread_id}` | Clerk JWT, org-scoped |
| POST | `/api/hitl-resume` | Clerk JWT, **role = manager** |
| POST | `/api/slack-webhook` | Slack signing secret |
| POST | `/api/github-webhook` | GitHub `X-Hub-Signature-256` |
| GET | `/api/health` | none |

---

## 7. Security Requirements (non-negotiable)

1. Verify Slack signing secret and GitHub HMAC on every webhook, constant-time compare.
2. HMAC + timestamp on media→workos calls (replay protection).
3. Clerk JWT verification in FastAPI (JWKS), org check on every SSE and HITL call. `thread_id` alone is never authorization.
4. Only users with manager role can approve; record approver in `approvals`.
5. Prompt-injection hygiene: transcript text and commit messages are **untrusted data**. They are passed to LLMs as delimited data, LLM output is schema-validated (Pydantic), and LLM output can never directly choose a Jira project, Slack channel, or URL.
6. Secrets only via env/secret manager. Rotate anything previously committed.
7. Log redaction for tokens, emails, transcript bodies at INFO level.
8. RLS on all tenant tables; service role key only in backends, never in the browser.

---

## 8. Reliability Requirements

- Idempotency: meeting ingest, Jira creation, Slack DM, webhook handling.
- Retries with backoff + timeout on every external call (Jira, Slack, LLM, embeddings). Circuit-break on repeated failure and emit `error` SSE.
- Long media jobs run in a background worker/queue (not inside a request).
- SSE: heartbeat every ~15s, `Last-Event-ID` resume, and a REST fallback `GET /api/threads/{id}/state` so a refresh never loses the screen.
- Graph B handlers return 200 to Slack within 3s and process asynchronously.

---

## 9. Observability

- LangSmith tracing for both graphs (toggle by env).
- Structured JSON logs with `meeting_id`, `thread_id`, `org_id`, `task_id` correlation fields.
- Metrics: meeting→dispatch latency, flags per firewall node, approval time, auto-close precision (manual corrections / auto-closes).

---

## 10. Testing Strategy

| Level | What |
|---|---|
| Unit | reducer, thresholds, intent classification parsing, signature verification |
| Graph | each node with fixtures; full Graph A with mocked Jira/Slack/LLM |
| Contract | JSON-schema validation of every cross-service payload in CI |
| E2E | Playwright: transcript → dashboard → approve → ticket mocked |
| Eval | golden transcripts (the GitLab demo + 5 more) with expected flags; track extraction precision/recall |

Definition of done for any task: tests pass, contract unchanged or versioned, `ARCHITECTURE.md` updated if behavior changed.

---

## 11. Environment Variables (names only)

```
# shared
APP_ENV, DEMO_MODE, SHARED_HMAC_SECRET
# gnani ai
GNANI_API_KEY, GNANI_TOKEN, GNANI_STT_ENDPOINT, GNANI_TTS_ENDPOINT, GNANI_PRISMA_MODEL, GNANI_TIMBRE_VOICE
EVON_MODEL_NAME, EVON_API_BASE, EVON_API_KEY
# clerk
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY, CLERK_SECRET_KEY, CLERK_JWKS_URL
# stream
NEXT_PUBLIC_STREAM_API_KEY, STREAM_API_SECRET
# supabase
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, NEXT_PUBLIC_SUPABASE_ANON_KEY, DATABASE_URL
# models
GEMINI_API_KEY, NVIDIA_API_KEY
LLM_EXTRACTION_MODEL, LLM_REASONING_MODEL, EMBEDDING_MODEL, EMBEDDING_DIM=1024
# thresholds
SECURITY_THRESHOLD=0.50, FINANCE_THRESHOLD=0.50, COMMIT_MATCH_THRESHOLD, COMMIT_MATCH_MARGIN, CAPACITY_LIMIT, CAPACITY_NEW_HIRE_LIMIT
# integrations
JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY
SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET
GITHUB_WEBHOOK_SECRET
# media
CLOUDINARY_*, GOOGLE_APPLICATION_CREDENTIALS, TRANSCRIBER, TTS_PROVIDER, WHISPERX_MODEL, HF_TOKEN
# observability
LANGCHAIN_TRACING_V2, LANGCHAIN_API_KEY, LANGCHAIN_PROJECT
```

---

## 12. Architecture Decision Records (summary)

| # | Decision | Reason |
|---|---|---|
| ADR-1 | Monorepo, two services | Different runtimes (GPU/media vs agent API); one contract package |
| ADR-2 | One Next.js 15 app using route groups | Shared auth, shared layout, one deploy (matches Horizon working Next 15 stack) |
| ADR-3 | Clerk as sole IdP | Already used by Horizon; avoids second auth system |
| ADR-4 | Contracts generated from JSON schema | Prevents TS/Python drift |
| ADR-5 | PostgresSaver for HITL | Pending approvals survive restarts |
| ADR-6 | Config-driven model names | Model deprecations should not require code changes |
| ADR-7 | Human approval required before any dispatch with a flag | Core trust guarantee |

---

## 13. Out of Scope (for v1)

Multi-region deploy, on-prem LLM, non-Jira trackers, mobile apps. Design extension points but do not build them.
