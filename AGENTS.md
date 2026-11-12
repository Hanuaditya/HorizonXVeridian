# AGENTS.md — Full Project Reference for AI Agents

> **Read this file first.** It is the single-document reference any AI agent, IDE assistant, or developer needs to fully understand **Horizon Veridian** — what it does, how every piece fits together, what has already been built, what the real team identities are, and what rules must never be broken.
>
> If any code conflicts with this document, **stop and ask** — do not silently diverge.

---

## 1. What Is This Project?

**Horizon Veridian** is an end-to-end AI-powered sprint governance platform that merges two original products:

| Original Product | What it does |
| :--- | :--- |
| **Horizon Meet** | Real-time video meetings (Stream.io), multilingual STT/TTS dubbing (Gnani Prisma + Timbre), AI summaries |
| **Veridian WorkOS** | Agentic task extraction, 4-way compliance firewall, manager approval gate, Jira + Slack dispatch, closed-loop Jira auto-close |

**One sentence:** A meeting ends → audio is transcribed → an AI agent extracts tasks → a parallel compliance firewall checks HR/budget/security/capacity → the manager receives a Slack review menu and approves → Jira tickets are created and employees get 1-on-1 Slack DMs → periodic check-ins track progress → completion replies auto-close Jira tickets to Done.

---

## 2. Monorepo Structure

```
horizon-veridian/
├── AGENTS.md                           ← THIS FILE (AI agent reference)
├── ARCHITECTURE.md                     ← Full system architecture & ADRs
├── IMPLEMENTATION_PLAN.md              ← Phased roadmap (Phases 0–8)
├── AGENT_RULES.md                      ← Hard engineering rules & coding standards
├── .env.example                        ← All env var names (never real secrets)
├── .env                                ← Real secrets — NEVER commit, NEVER print
├── docker-compose.yml
├── package.json                        ← Monorepo scripts (npm run live, build, etc.)
│
├── apps/
│   └── web/                            ← Next.js 15.5.6 frontend (Clerk + Stream.io)
│       ├── app/
│       │   ├── (auth)/                 ← Clerk sign-in/sign-up pages
│       │   ├── (root)/(home)/
│       │   │   ├── workos/page.tsx     ← MAIN: role-based WorkOS Hub (Manager vs Employee)
│       │   │   ├── admin/page.tsx      ← Admin: team identity bindings, connector sync
│       │   │   ├── meetings/           ← Meeting list & detail pages
│       │   │   ├── upcoming/           ← Horizon Meet rooms
│       │   │   ├── recordings/         ← Recordings browser
│       │   │   └── ...
│       │   └── api/                    ← BFF (Backend-For-Frontend) routes only
│       │       ├── workos/
│       │       │   ├── stream/[threadId]/route.ts   ← SSE proxy to WorkOS service
│       │       │   ├── hitl-resume/route.ts          ← Manager approval relay (admin-only)
│       │       │   ├── meeting-ended/route.ts        ← Trigger meeting end
│       │       │   ├── threads/[threadId]/checkin/   ← Check-in trigger (admin-only)
│       │       │   ├── threads/[threadId]/employee-reply/  ← Employee reply relay
│       │       │   └── audit/route.ts
│       │       └── media/
│       │           ├── demo-simulate/route.ts        ← Trigger Hinglish demo simulation
│       │           └── jobs/route.ts
│       ├── components/
│       │   ├── workos/
│       │   │   ├── EmployeeBotPane.tsx   ← Employee-only personal workspace (filtered by userId)
│       │   │   └── ...
│       │   └── shared/
│       │       └── EndCallButton.tsx     ← Triggers meeting.ended on call end → redirect /workos
│       ├── providers/
│       │   ├── AuthBridge.tsx           ← Populates AppUser{userId, orgId, orgRole, email, name}
│       │   └── providers.tsx
│       └── lib/
│           ├── workos-server.ts         ← getWorkOSAuthHeader() injects userId+orgId+orgRole
│           ├── workos-types.ts          ← Shared TS types for WorkOS SSE events
│           └── env-flags.ts            ← isDemoMode() helper (server-safe, no client bundle)
│
├── services/
│   ├── media/                          ← Flask microservice (port 5001)
│   │   ├── app.py                      ← Flask app: /health, /media/jobs, /media/demo-simulate
│   │   ├── pipeline/
│   │   │   ├── gnani_client.py         ← Gnani Prisma v3.0 STT + Timbre v2.5 TTS (timeout=20s)
│   │   │   ├── transcribe.py           ← Speaker diarization + transcript stitching
│   │   │   ├── tts.py                  ← Text-to-speech pipeline
│   │   │   ├── extract_audio.py        ← FFmpeg audio extraction
│   │   │   ├── translate.py            ← Google Translate (optional)
│   │   │   └── recompose.py            ← Re-compose audio+video with drift guard
│   │   ├── publisher.py                ← HMAC-signed POST meeting.ended → WorkOS
│   │   ├── jobs.py                     ← Background job queue (non-blocking)
│   │   └── config.py
│   │
│   └── workos/                         ← FastAPI + LangGraph microservice (port 8000)
│       ├── api/
│       │   ├── main.py                 ← FastAPI app entrypoint, lifespan, /health
│       │   ├── auth.py                 ← Clerk JWT verification, require_manager()
│       │   ├── sse.py                  ← SSE streaming endpoint
│       │   └── routes/
│       │       ├── threads.py          ← /threads, /threads/{id}/approve (admin-only), /checkin
│       │       └── ...
│       ├── agent/
│       │   ├── graph_a.py              ← LangGraph Graph A: ingest→extract→firewall→HITL→dispatch
│       │   ├── graph_b.py              ← LangGraph Graph B: Slack/GitHub→intent→auto-close
│       │   ├── state.py                ← Shared AgentState Pydantic model
│       │   ├── checkpointer.py         ← PostgresSaver (Supabase) for HITL persistence
│       │   └── nodes/
│       │       ├── dispatcher.py       ← Creates Jira tickets + posts employee DMs (idempotent)
│       │       └── ...
│       ├── connectors/
│       │   ├── slack_ops.py            ← Slack DM orchestrator (see §8 for full detail)
│       │   ├── jira_ops.py             ← Jira ticket CRUD + accountId lookup by email
│       │   ├── sprint_loop.py          ← Scheduled check-ins + reply→auto-close loop
│       │   ├── sync_hr.py              ← Supabase hr_employees sync
│       │   ├── sync_finance.py         ← Supabase finance_budgets sync
│       │   └── sync_security.py        ← Supabase security_policies sync
│       ├── core/
│       │   ├── config.py               ← Settings (pydantic-settings, reads .env)
│       │   ├── evon_llm.py             ← LLM router: Gnani Evon 30B → NVIDIA NIM → Gemini
│       │   ├── store.py                ← Supabase CRUD helpers, vector search, leave replacement
│       │   └── embeddings.py           ← 1024-dim embedding generation (NV-EmbedQA-E5-v5)
│       └── tests/
│           ├── test_phase2_auth_rls_seed.py         ← Auth, RLS, seed correctness (8 tests)
│           ├── test_phase4_and_graph_b.py            ← Graph A/B firewall, dispatch (6 tests)
│           ├── test_role_separation_and_team_wiring.py  ← 403 guard, Slack routing, leave redirect (4 tests)
│           └── test_sprint_orchestrator.py           ← Manager approval gate, check-in loop (3 tests)
│
├── packages/
│   └── contracts/                      ← SINGLE SOURCE OF TRUTH for cross-service payloads
│       ├── meeting_ended.schema.json   ← Schema: media → workos event
│       ├── sse_events.schema.json      ← Schema: workos → web SSE events
│       └── generated/
│           ├── ts/                     ← Auto-generated TypeScript types (never hand-edit)
│           └── py/                     ← Auto-generated Pydantic models (never hand-edit)
│
├── db/
│   ├── migrations/                     ← Forward-only numbered SQL migrations
│   │   ├── 001_enable_pgvector_and_auth_helpers.sql
│   │   ├── 002_core_tenancy_and_horizon_media.sql
│   │   ├── 003_workos_firewall_and_pgvector.sql
│   │   └── 004_sprint_orchestrator_skills_and_checkins.sql
│   └── seed/
│       ├── hr_employees.json           ← Demo HR data (6 employees, used by unit tests)
│       ├── finance_budgets.csv         ← Budget categories with amounts
│       ├── security_policy.md          ← Policy text source
│       └── seed_data.sql               ← Includes SEC-POL-089, SEC-POL-104 policy rows
│
└── scripts/
    ├── seed_live_supabase.py           ← Seeds REAL org with 3-person team + leave teammate
    ├── verify_keys.py                  ← Checks all API keys are valid before running
    ├── test_live_e2e.py                ← End-to-end live smoke test with per-step timing
    └── run_demo.mjs / run_demo.sh      ← Legacy demo launchers
```

---

## 3. Live Services & Ports

| Service | Port | Health URL | Framework | Start Command |
| :--- | :--- | :--- | :--- | :--- |
| **Web UI** | 3000 | `http://localhost:3000` | Next.js 15.5.6 | `npm run dev` (from `apps/web`) |
| **Media Service** | 5001 | `http://localhost:5001/health` | Flask | `python app.py` (from `services/media`) |
| **WorkOS Service** | 8000 | `http://localhost:8000/health` | FastAPI + LangGraph | `uvicorn api.main:app --port 8000 --reload` |

**Start all 3 at once:**
```bash
npm run live          # from repo root — runs concurrently
```

---

## 4. The 7-Stage End-to-End Flow

```
┌────────────────────────────────────────────────────────────────────────┐
│  1. MEETING CAPTURE                                                    │
│  Stream.io video call ends → EndCallButton → POST /api/media/jobs      │
│  Gnani Prisma v3.0 STT transcribes (Hinglish/Indic diarization)        │
│  Gnani Timbre v2.5 TTS + recompose dubbed audio                        │
│  Gemini generates summary                                              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HMAC-signed POST meeting.ended
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  2. INGEST & EXTRACT  (Graph A — node: ingest_node + extractor_node)   │
│  Idempotency check on meeting_id                                       │
│  LLM extracts tasks: title, assignee, deadline, transcript_quote       │
│  Speaker labels (SPEAKER_01) → resolved to real people via Clerk list  │
│  Unresolved assignees → HITL, never guessed                            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                      ┌─────────────┼─────────────┐
                      ▼             ▼              ▼              ▼
┌────────────────┐ ┌──────────┐ ┌───────────┐ ┌───────────────────────┐
│  3a. HR CHECK  │ │ 3b. CAP. │ │ 3c. SECUR │ │  3d. FINANCE CHECK    │
│  hr_employees  │ │ Jira API │ │ pgvector  │ │  finance_budgets       │
│  ON_LEAVE etc  │ │ open tix │ │ ≥ 0.50 ≡  │ │  pgvector ≥ 0.50 ≡   │
└───────┬────────┘ └────┬─────┘ └─────┬─────┘ └──────────┬────────────┘
        └───────────────┴─────────────┴──────────────────┘
                                    │ merge_node (field-level reducer)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  4. RESOLUTION (resolution_generator_node)                             │
│  Per-task: PROCEED | REFRAME | REROUTE | DEFER | OVERRIDE              │
│  Smart Leave Redirect: ON_LEAVE assignee → lowest-workload domain match│
│  Immediate compliance alert DM sent to Manager BEFORE review menu      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  5. MANAGER APPROVAL GATE  (hitl_interrupt_node → Slack Block Kit)     │
│  Zero Jira tickets created yet.                                        │
│  Slack DM to Manager U_MGR_DEMO: Block Kit Review Menu with            │
│  each task title, description, proposed commit message, flags          │
│  "Approve & Create Tickets" button (action_id: approve_sprint_tickets) │
│  OR click URL http://localhost:3000/workos?thread=<id>&action=approve  │
│  OR reply "approve" in DM thread                                       │
│  → POST /api/threads/{thread_id}/approve  (admin role required)        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Manager approves
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  6. DISPATCH  (dispatcher_node)                                        │
│  For each approved task:                                               │
│  - Lookup Jira accountId: GET /rest/api/3/user/search?query={email}    │
│  - Create Jira ticket in SCRUM project, assign accountId               │
│  - Post 1-on-1 Slack DM to assignee (U_EMP_A_DEMO or U_EMP_B_DEMO)     │
│  - Post Approval confirmation DM to Manager U_MGR_DEMO                 │
│  Idempotent: task_id → jira_key stored; retries never duplicate        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│  7. CLOSED-LOOP TRACKING  (Graph B + sprint_loop)                      │
│  sprint_loop.py polls Slack DM channels every 2.5s                     │
│  Employee reply → intent: COMPLETE|PARTIAL|BLOCKED|AMBIGUOUS           │
│  COMPLETE + "done"/"finished"/"merged" → auto-close Jira to Done        │
│  BLOCKED → escalate to Manager, flag Jira                              │
│  turn_count ≥ 2 → stop clarifying, escalate (anti-loop guard)          │
│  GitHub webhook: commit message → pgvector match → auto-close if clear │
│  Every transition → audit_trail                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Team Identities & Fictional Personas

In public repository code, documentation, and automated tests, **clean fictional personas** are used. Live production bindings for real user accounts are loaded dynamically from gitignored `local.identities.json` or environment variables without ever hardcoding personal data into git.

| Persona | Role | Clerk User ID | Slack Member ID | Email | Domain Skills |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Aarav Sharma** | Engineering Manager (`org:admin`) | `user_clerk_manager_demo` | `U_MGR_DEMO` | `aarav.sharma@example.com` | management, architecture, security, infra |
| **Rohan Patel** | Senior Backend Engineer (`org:member`) | `user_clerk_emp_a_demo` | `U_EMP_A_DEMO` | `rohan.patel@example.com` | elasticsearch, aws, backend, infra, kubernetes (1 active task) |
| **Priya Sen** | Product & Frontend Engineer (`org:member`) | `user_clerk_emp_b_demo` | `U_EMP_B_DEMO` | `priya.sen@example.com` | frontend, auth, oauth, ui, api (2 active tasks) |
| **Arjun Rao** | Backend Engineer — `ON_PATERNITY_LEAVE` | `user_demo_arjun` | `U_ARJUN_DEMO` | `arjun.rao@example.com` | elasticsearch, aws, backend → triggers Smart Leave Redirect to **Rohan Patel** |

### Role-Based UI on `/workos`

| Clerk `orgRole` | What They See |
| :--- | :--- |
| `org:admin` (Aarav Sharma) | **Manager Command Center**: Review menu, compliance alerts, leave-redirect card, full team Jira status, Run Check-In Now button, Manager Slack DM feed |
| `org:member` (Rohan Patel / Priya Sen) | **Personal Employee Workspace**: Only their own tasks and tickets, only their own 1-on-1 Veridian Bot DM thread — Manager controls hidden |

### API Access Control
| Endpoint | Who can call |
| :--- | :--- |
| `POST /api/threads/{id}/approve` | `org:admin` only → 403 Forbidden for members |
| `POST /api/threads/{id}/checkin` | `org:admin` only → 403 Forbidden for members |
| `POST /api/hitl-resume` | `org:admin` only → 403 Forbidden for members |

---

## 6. Data Model (Supabase, single project)

All tables carry `org_id` + Row Level Security (RLS). Never bypass RLS with service role key from browser.

| Table | Key Columns | Purpose |
| :--- | :--- | :--- |
| `organizations` | `org_id`, `clerk_org_id`, `name` | Clerk org mapping |
| `employees` | `clerk_user_id`, `email`, `slack_id`, `jira_account_id`, `full_name`, `job_title`, `domain_skills jsonb`, `active_task_count` | People directory + leave status |
| `hr_employees` | `full_name`, `email`, `hr_status` (`ACTIVE`/`ON_PATERNITY_LEAVE`/etc.) | HR leave status source of truth |
| `finance_budgets` | `category`, `amount`, `remaining`, `embedding vector(1024)` | Budget compliance (pgvector RAG) |
| `security_policies` | `policy_id`, `chunk_text`, `embedding vector(1024)` | Policy compliance (pgvector RAG). Includes SEC-POL-089 (14-day staging) and SEC-POL-104 (blocked/unsupported third-party APIs) |
| `tasks` | `task_id`, `thread_id`, `org_id`, `assignee`, `title`, `jira_key`, `status`, various flags | Persisted task state through the pipeline |
| `processed_meetings` | `meeting_id`, `org_id` | Idempotency keys — prevents double-processing |
| `slack_threads` | `task_id`, `slack_channel`, `slack_thread_ts`, `turn_count`, `status` | Slack → Jira closed-loop tracking |
| `audit_trail` | `thread_id`, `task_id`, `action`, `actor`, `provenance_tag`, `created_at` | Append-only immutable audit log |
| `approvals` | `thread_id`, `approver_clerk_id`, `approved_at`, `method` | Manager decision record |
| `slack_feed` | `thread_id`, `org_id`, `role`, `sender`, `recipient`, `text`, `kind` | Mirrored Slack messages for UI display |

---

## 7. Contracts (packages/contracts) — Never Break These

### `meeting.ended` — media → workos
```
POST {WORKOS_URL}/api/meeting-ended
Headers:
  X-Signature: sha256=<HMAC(body, SHARED_SECRET)>
  X-Timestamp: <unix-epoch>  (rejected if >5 min old)
  Idempotency-Key: <meeting_id>
Body: { meeting_id, org_id, title, started_at, ended_at, language,
        participants[{clerk_user_id, display_name, email}],
        transcript[{speaker, speaker_user_id, start, end, text}],
        summary, recording_url }
Response: 202 { thread_id }
```

### SSE Events — workos → web
```
Envelope: { event_type, payload }
Events: processing_started | resolution_ready | hitl_ready | dispatched |
        tracker_update | complete | error
```

> **Never hand-edit generated files in `packages/contracts/generated/`.** Only edit the `.schema.json` files, then run `npm run contracts:generate`.

---

## 8. Key Files & What They Do

### `services/workos/core/evon_llm.py`
LLM Router with 3-tier fallback:
1. **Gnani Evon 30B** (`EVON_API_KEY`, `EVON_API_BASE`) — preferred, OpenAI-compatible, timeout=30s
2. **NVIDIA NIM** (`NVIDIA_API_KEY`) — fallback, OpenAI-compatible
3. **Google Gemini** (`GEMINI_API_KEY`) — final fallback, `thinking_budget=0`, timeout=25s

Security: all untrusted transcript/commit/Slack text is wrapped in `<untrusted_data>` blocks. LLM output is Pydantic-validated. LLM output can NEVER choose Jira project keys, Slack channels, or URLs.

### `services/workos/connectors/slack_ops.py`
- `resolve_slack_user_id(recipient, role, org_id)` — maps name/email/clerk_id to real Slack Member ID
- `open_slack_dm_channel(client, slack_user_id)` — opens 1-on-1 DM via `conversations.open`, cached
- `post_slack_message(...)` — routes to individual DM or channel, mirrors to `slack_feed` table
- `send_immediate_compliance_alert(...)` — DMs Manager BEFORE review menu if budget/policy/SEC-POL-104 hit
- `send_manager_review_menu(...)` — Block Kit DM to Manager with Approve button, zero tickets created yet
- `post_employee_assignment_dm(...)` — 1-on-1 DM to assignee after Manager approves
- `post_employee_checkin_dm(...)` — periodic status check to assignee
- `post_manager_progress_digest(...)` — progress summary to Manager
- `post_closure_confirmation_dms(...)` — both employee and Manager notified on Done

### `services/workos/connectors/jira_ops.py`
- `lookup_jira_account_id(email)` — calls `GET /rest/api/3/user/search?query={email}`, caches result
- `create_jira_issue(org_id, task)` — creates ticket in `SCRUM` project, sets `assignee.accountId`

### `services/workos/core/store.py`
- `find_best_domain_replacement(org_id, domain_skills)` — finds lowest `active_task_count` employee matching skills; explicitly excludes leadership (`Engineering Manager`, VP roles)
- `upsert_employee_mapping(...)` — persists `domain_skills`, `active_task_count`, `status`

### `apps/web/app/(root)/(home)/workos/page.tsx`
- Reads `orgRole` from Clerk auth
- `isAdmin = orgRole === "org:admin"` → renders `ManagerCommandPane` or `EmployeeBotPane`
- `FULL_SPRINT_DEMO_TRANSCRIPT` preset references Aarav Sharma, Rohan Patel, Priya Sen, Arjun Rao (paternity leave)

### `apps/web/providers/AuthBridge.tsx`
- Populates `AppUser { userId, orgId, orgRole, email, name }` from Clerk
- `email` added to interface so Employee filtering works correctly

### `scripts/seed_live_supabase.py`
- Run with `--org-id <clerk_org_id> --force` to upsert all 4 team members
- Idempotent via `upsert` on `email`; `--force` clears and re-seeds HR/budget/policy data
- Returns JSON summary confirming all bindings and row counts

---

## 9. Environment Variables (names only — real values in `.env`)

```bash
# Mode
DEMO_MODE=false                    # true = deterministic golden transcript, no real API calls
NEXT_PUBLIC_DEMO_MODE=false

# Auth
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
CLERK_SECRET_KEY
CLERK_JWKS_URL

# Stream.io (video calls)
NEXT_PUBLIC_STREAM_API_KEY
STREAM_API_SECRET

# Supabase (database)
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
NEXT_PUBLIC_SUPABASE_ANON_KEY
DATABASE_URL                       # postgres:// for PostgresSaver checkpointer

# Gnani AI (STT + TTS)
GNANI_API_KEY
GNANI_TOKEN
GNANI_STT_ENDPOINT                 # https://api.vachana.ai/...
GNANI_TTS_ENDPOINT
GNANI_PRISMA_MODEL=prisma-v3.0
GNANI_TIMBRE_VOICE=timbre-v2.5

# LLM: Gnani Evon 30B (preferred)
EVON_MODEL_NAME=gnani-ai/evon-30b
EVON_API_BASE
EVON_API_KEY

# LLM: Google Gemini (fallback)
GEMINI_API_KEY
LLM_EXTRACTION_MODEL=gemini-3-flash-preview
LLM_FALLBACK_MODEL=gemini-3.1-flash-lite-preview
LLM_REASONING_MODEL

# Embeddings
NVIDIA_API_KEY
EMBEDDING_MODEL=NV-EmbedQA-E5-v5
EMBEDDING_DIM=1024

# Integrations
JIRA_BASE_URL
JIRA_EMAIL
JIRA_API_TOKEN
JIRA_PROJECT_KEY=SCRUM
SLACK_BOT_TOKEN
SLACK_SIGNING_SECRET
GITHUB_WEBHOOK_SECRET
SHARED_HMAC_SECRET                 # media → workos signed events

# Thresholds
SECURITY_THRESHOLD=0.50
FINANCE_THRESHOLD=0.50
COMMIT_MATCH_THRESHOLD
CAPACITY_LIMIT

# Frontend URL (for Slack approval buttons)
FRONTEND_URL=http://localhost:3000

# Observability
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY
LANGCHAIN_PROJECT=horizon-veridian
```

---

## 10. CI/CD Pipeline (`.github/workflows/ci.yml`)

Three parallel jobs run on every push to `master`/`main`:

| Job | What it checks |
| :--- | :--- |
| **Validate Contracts & Schema Drift** | `python packages/contracts/scripts/generate_contracts.py --check` — fails if generated files are stale |
| **Validate Python Services** | `pytest services/media/tests -v` (7 tests) + `pytest services/workos/tests -v` (21 tests) + `/health` checks |
| **Validate Web App (Next.js 15)** | `npm ci`, `tsc --noEmit`, `eslint`, `next build` with `DEMO_MODE=true` |

**Current CI status:** All 3 jobs pass on `master` (commit `cea1ad7`).

---

## 11. Test Suite (28 Total, All Pass)

```bash
pytest services/workos/tests -v     # 21 tests
pytest services/media/tests -v      #  7 tests
```

| File | Tests | What they cover |
| :--- | :--- | :--- |
| `test_phase2_auth_rls_seed.py` | 8 | Clerk JWT auth, RLS isolation between orgs, startup vector dimension check |
| `test_phase4_and_graph_b.py` | 6 | Graph A golden transcript firewall, HITL persistence, idempotent dispatch, prompt-injection rejection, Slack/GitHub webhook HMAC, Gemini LLM routing |
| `test_role_separation_and_team_wiring.py` | 4 | `org:member` 403 on approve/checkin, Jira email→accountId lookup, individual Slack DM routing to U_MGR_DEMO/U_EMP_A_DEMO/U_EMP_B_DEMO, Smart Leave redirecting Arjun → Rohan Patel |
| `test_sprint_orchestrator.py` | 3 | Zero tickets before manager approval, immediate compliance alert (budget+policy+SEC-POL-104), interval check-ins + natural-language auto-close |

---

## 12. Hard Rules (Never Break These)

1. **No secrets in git.** Never commit `.env`. Never print secret values in logs or responses.
2. **Never hard-code** model names, Slack user IDs (except in `slack_ops.py` REAL_TEAM constants), thresholds, Jira project keys, or Supabase URLs. All come from env/config.
3. **Cross-service payloads** are defined ONLY in `packages/contracts/`. Generated types are never hand-edited.
4. **Services never import each other's code.** Only HTTP + contracts.
5. **DB changes** only through numbered forward-only migrations in `db/migrations/`. Every tenant table has `org_id` + RLS.
6. **Every webhook** verifies its HMAC signature (Slack signing secret, GitHub `X-Hub-Signature-256`, media→workos `X-Signature`).
7. **Every SSE/HITL endpoint** verifies Clerk JWT + org membership. `thread_id` alone is never authorization.
8. **Only managers can approve.** `require_manager()` returns 403 for `org:member`. Record approver in `approvals`.
9. **Transcript text, commit messages, Slack replies** are untrusted input. Wrap in `<untrusted_data>` blocks, validate LLM output with Pydantic, never let LLM output choose destinations.
10. **External calls** (LLM, Jira, Slack, Gnani) need timeouts (Gnani: 20s, Gemini: 25s), retries with backoff, and idempotency.
11. **`find_best_domain_replacement`** explicitly excludes leadership roles (Engineering Manager, VP, etc.) from being suggested as engineering task replacements.
12. **`demo-simulate` endpoint** generates a fresh `meeting_id = f"sim-{uuid.uuid4().hex[:8]}"` on every request to prevent idempotency drops on repeat runs.

---

## 13. Quick Commands

```bash
# Start everything
npm run live

# Run all tests
pytest services/workos/tests -v
pytest services/media/tests -v

# Type-check frontend
npm --prefix apps/web run type-check

# Production build
npm --prefix apps/web run build

# Check contracts freshness
python packages/contracts/scripts/generate_contracts.py --check

# Regenerate contracts
python packages/contracts/scripts/generate_contracts.py

# Seed live Supabase (3-person team)
python scripts/seed_live_supabase.py --org-id org_your_clerk_org_id --force

# Verify all API keys
python scripts/verify_keys.py

# Run E2E smoke test
python -u scripts/test_live_e2e.py
```

---

## 14. Key Pages & Routes

| URL | Who sees it | What it is |
| :--- | :--- | :--- |
| `/workos` | Manager → Command Center / Employee → Personal Workspace | **Main WorkOS Hub** — role-gated |
| `/admin` | Anyone (Clerk-authed) | Team identity editor, connector sync, threshold config |
| `/meetings` | Anyone | Meeting list with Gnani STT transcripts |
| `/meetings/[id]` | Anyone | Meeting detail: transcript, dubbing, task list |
| `/upcoming`, `/previous` | Anyone | Horizon Meet room browser |
| `/recordings` | Anyone | Recording playback |
| `/personal-room` | Anyone | Stream.io personal call room |

---

## 15. Architecture Decision Records (ADRs)

| ADR | Decision | Reason |
| :--- | :--- | :--- |
| ADR-1 | Monorepo, two backend services | Different runtimes (Flask+GPU for media, FastAPI+LangGraph for agent); one contract package |
| ADR-2 | One Next.js 15 app with route groups | Shared auth, shared layout, one deploy |
| ADR-3 | Clerk as sole IdP | Already used by Horizon Meet; avoids second auth system |
| ADR-4 | Contracts generated from JSON schema | Prevents TypeScript/Python type drift |
| ADR-5 | PostgresSaver for HITL checkpointing | Pending approvals survive service restarts |
| ADR-6 | Config-driven model names (env vars) | Model deprecations should not require code changes |
| ADR-7 | Manager approval required before any dispatch | Core trust guarantee — no auto-creation of work items |
| ADR-8 | Gnani Sovereign AI for STT/TTS | Indic language support (Hinglish diarization), data sovereignty |

---

## 16. What Is NOT In Scope (v1)

Multi-region deploy, on-prem LLM, non-Jira trackers, non-Slack messengers, mobile apps, non-Clerk auth providers. Design extension points are present but not built.

---

> **Last updated:** 2026-11-13 by Antigravity (AI agent, session `68f04738`).  
> **Git state:** `master` @ `cea1ad7` — 28 tests passing, CI green, all 3 services live.

