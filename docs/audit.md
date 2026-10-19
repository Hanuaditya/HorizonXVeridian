# docs/audit.md — Phase 0 Read-Only Audit Report

**Project:** Horizon Veridian Unified Platform  
**Audit Date:** 2026-10-19  
**Source Locations:**
- Horizon Meet: `legacy/horizon-meet/` (`dubbing-service`, `trickster-next-zoom`)
- Veridian WorkOS: `legacy/veridian/` (`backend`, `frontend`, `transcript.txt`)

---

## 1. Project File Trees (Depth 3) & Top-Level Folder Roles

### 1.1 Horizon Meet (`legacy/horizon-meet/`)

```
legacy/horizon-meet/
├── dubbing-service/                # Flask media processing microservice
│   ├── app.py                     # Monolithic pipeline (STT, translation, TTS, lipsync, recomposition, Cloudinary, Supabase)
│   ├── .gitignore                 # Python ignore patterns
│   └── temp/                      # Working directory for media processing chunks
└── trickster-next-zoom/            # Next.js 15 video conferencing web application
    ├── actions/                   # Server actions (Stream.io token generation)
    ├── app/                       # App router pages and API endpoints
    │   ├── (auth)/                # Clerk authentication route group (sign-in, sign-up)
    │   ├── (root)/                # Protected app route group
    │   │   ├── (home)/            # Dashboard, insights, personal-room, recordings, upcoming
    │   │   ├── about/             # Team / about page
    │   │   └── meeting/[id]/      # Live video room with Stream Video SDK
    │   ├── api/                   # BFF endpoints (stream-token, generate-insight, start-dubbing, delete-call)
    │   ├── meeting-summaries/     # Summary listing view
    │   └── stream-webhook/        # Webhook receiver for Stream call events
    ├── components/
    │   ├── shared/                # CallList, MeetingRoom, MeetingSetup, MeetingModal, EndCallButton, etc.
    │   └── ui/                    # Radix UI primitives (dialog, dropdown, toast, button, etc.)
    ├── constants/                 # Navigation links, avatar image list
    ├── hooks/                     # Custom hooks (useGetCalls, useGetCallById)
    ├── lib/                       # Supabase client initialization, cn utility
    ├── providers/                 # StreamClientProvider, Clerk/React providers
    ├── public/                    # Static assets (icons, images, team photos)
    ├── package.json               # Dependencies and scripts
    ├── tsconfig.json              # TypeScript configuration
    ├── tailwind.config.ts         # Tailwind CSS styling config
    └── next.config.mjs            # Next.js build configuration
```

#### Folder Roles
- **`dubbing-service/`**: Standalone Flask service listening on port 5001. Handles video download from Cloudinary/Stream, extracts audio via moviepy, executes Google Speech-to-Text with diarization, generates meeting summary/chapters via Gemini, translates transcript via external API, synthesizes voice via Google TTS, recombines audio/video, uploads dubbed video to Cloudinary, and stores metadata in Supabase `recordings` table.
- **`trickster-next-zoom/`**: Next.js 15 front-end for hosting live video meetings with Stream.io, authenticating users with Clerk, scheduling meetings, and triggering the dubbing/insights generation pipeline via HTTP POST to the Flask service.

---

### 1.2 Veridian WorkOS (`legacy/veridian/`)

```
legacy/veridian/
├── README.md                      # Comprehensive architectural documentation (24 KB)
├── transcript.txt                 # Golden fixture transcript from GitLab product meeting (~38 KB)
├── .gitignore                     # Gitignore rules
├── backend/                       # FastAPI + LangGraph orchestration service
│   ├── agent/                     # LangGraph workflow definitions and LLM wrappers
│   │   ├── nodes/                 # 18 graph nodes (Graph A, Graph B, and utility nodes)
│   │   ├── graph_a.py             # Graph A StateGraph (synchronous meeting ingestion to HITL dispatch)
│   │   ├── graph_b.py             # Graph B StateGraph (closed-loop Slack/GitHub tracking)
│   │   ├── llm_client.py          # Centralized OpenAI-compatible client for NVIDIA NIM
│   │   ├── state.py               # Pydantic schemas and AgentState TypedDict with reducers
│   │   ├── graph.py               # [DEAD CODE] 0-byte stub
│   │   └── tools.py               # [DEAD CODE] 0-byte stub
│   ├── api/                       # FastAPI REST & SSE endpoints
│   │   ├── routes/                # meeting.py, hitl.py, slack.py, github.py
│   │   ├── main.py                # FastAPI app initialization, CORS, SSE endpoint
│   │   └── sse.py                 # Asyncio queue manager for Server-Sent Events
│   ├── connectors/                # Enterprise data source sync scripts
│   │   ├── sync_hr.py             # ETL from bamboohr_db.json into hr_employees table
│   │   ├── sync_finance.py        # ETL from Google Sheets into finance_budgets pgvector
│   │   └── sync_security.py       # ETL from security_policy.pdf into security_policies pgvector
│   ├── data/                      # Local data sources for connectors
│   │   ├── bamboohr_db.json       # Mock HR database of employee records
│   │   └── security_policy.pdf    # Corporate security policy PDF for RAG embedding
│   ├── mock_servers/              # Mock server stubs
│   │   └── bamboohr_server.py     # [DEAD CODE] 28-byte placeholder stub
│   ├── supabase_agent_migration.sql # SQL migration script for vector RPCs and agent tables
│   ├── requirements.txt           # Python package requirements
│   └── .env.example               # Backend environment variables template
└── frontend/                      # Next.js 14 dashboard application
    ├── app/                       # App router
    │   ├── api/transcript/        # Route to read local transcript.txt
    │   ├── page.jsx               # Dashboard root with AutoLoader and 4 panels
    │   ├── globals.css            # Dark mode styles, glassmorphism tokens
    │   └── layout.jsx             # Root HTML layout
    ├── components/
    │   ├── v2/                    # Production UI: WorkflowHeader, MeetingOverview, DecisionsMade, ApprovalsPanel, ProgressTracker
    │   ├── cards/                 # Legacy UI: CommandCenterCard, DecisionsCard, TLDRCard
    │   ├── ui/                    # ZenModeBanner
    │   ├── AgentStepsPanel.jsx    # Step execution visualization panel
    │   ├── TopNav.jsx             # Top navigation bar
    │   └── TrackerAuditPanel.jsx  # Audit log viewer
    ├── lib/                       # Client utilities
    │   ├── sse.js                 # React hooks useAgentStream and useHITLResume
    │   └── utils.js               # CSS helpers and formatters
    ├── package.json               # Frontend dependencies (Next 14, Framer Motion)
    ├── package-lock.json          # Dependency lockfile
    ├── next.config.js             # Next.js config
    ├── tailwind.config.js         # Tailwind config
    └── postcss.config.js          # PostCSS config
```

#### Folder Roles
- **`backend/`**: FastAPI service (port 8000) orchestrating LangGraph workflows. Graph A ingests raw meeting transcripts, extracts action items and decisions using LLM structured output, runs a parallel compliance firewall (HR leave, Jira workload capacity, Security pgvector semantic search, Finance pgvector budget search), proposes resolutions (REFRAME, REROUTE, DEFER, OVERRIDE, PROCEED), pauses for human approval (HITL), and dispatches tickets to Jira and notifications to Slack. Graph B handles webhook callbacks from Slack replies and GitHub commits to update tickets.
- **`frontend/`**: Next.js 14 single-page application demonstrating the Veridian WorkOS flow with an `AutoLoader` that pulls `transcript.txt` and feeds FastAPI, rendering real-time SSE progress across meeting overview, decisions, firewall approvals, and ticket dispatch tracking.

---

## 2. Environment Variables Inventory (Names Only)

### Horizon Meet — `dubbing-service`
| Variable Name | Purpose |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key for meeting summaries and chapter generation |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary account cloud name |
| `CLOUDINARY_API_KEY` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase service key (used for inserting recording records) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to Google Cloud Service Account JSON for Speech-to-Text & Text-to-Speech |

### Horizon Meet — `trickster-next-zoom`
| Variable Name | Purpose |
|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk frontend public key |
| `CLERK_SECRET_KEY` | Clerk backend secret key |
| `NEXT_PUBLIC_STREAM_API_KEY` | Stream.io frontend public API key |
| `STREAM_API_KEY` | Stream.io backend API key |
| `STREAM_API_SECRET` | Stream.io backend API secret |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase public URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anonymous public key |
| `NEXT_PUBLIC_BASE_URL` | App base URL for generating meeting invite links |
| `PYTHON_SERVICE_URL` | URL to Flask dubbing service (defaults to `http://localhost:5001`) |

### Veridian WorkOS — `backend`
| Variable Name | Purpose |
|---|---|
| `NVIDIA_API_KEY` | NVIDIA NIM API key for LLM and embeddings |
| `NVIDIA_BASE_URL` | NVIDIA NIM endpoint URL (default: `https://integrate.api.nvidia.com/v1`) |
| `GOOGLE_API_KEY` | Google Gemini API key (read in `extractor.py` for `ChatGoogleGenerativeAI`) |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Supabase service role key (backend database operations) |
| `JIRA_URL` | Atlassian Jira cloud base URL |
| `JIRA_EMAIL` | Jira service account email |
| `JIRA_API_TOKEN` | Jira API token |
| `JIRA_PROJECT_KEY` | Default Jira project key (default: `VER`) |
| `SLACK_BOT_TOKEN` | Slack Bot OAuth token (`xoxb-...`) |
| `SLACK_SIGNING_SECRET` | Slack request signing secret |
| `SLACK_MANAGER_CHANNEL` | Slack channel for escalations (default: `#product-team`) |
| `SLACK_MANAGER_HANDLE` | Slack handle for manager notifications (default: `@manager`) |
| `SLACK_SUMMARY_CHANNEL` | Slack channel for final summary dispatch |
| `GITHUB_WEBHOOK_SECRET` | Secret for verifying GitHub HMAC-SHA256 webhooks |
| `BAMBOOHR_BASE_URL` | BambooHR mock server base URL |
| `GOOGLE_SHEETS_CREDENTIALS_FILE` | Google service account JSON for finance sync |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | Google Spreadsheet ID for finance budgets |
| `APP_SECRET_KEY` | Secret key for application auth/sessions |
| `FRONTEND_URL` | Allowed origin for CORS (default: `http://localhost:3000`) |
| `LANGCHAIN_TRACING_V2` | LangSmith tracing toggle |
| `LANGCHAIN_API_KEY` | LangSmith API key |
| `LANGCHAIN_PROJECT` | LangSmith project name |

### Veridian WorkOS — `frontend`
- No explicit `process.env` references in code. Endpoints (`http://localhost:8000/api/...`) are currently hardcoded in `page.jsx` and `lib/sse.js`.

---

## 3. External Services & SDKs (Lockfile Versions)

| Service / SDK | Project | Specified Version | Lockfile Version | Notes |
|---|---|---|---|---|
| **Next.js** | Horizon Meet | `^15.4.7` | `15.4.7` | Incompatible with Veridian's Next 14 |
| **Next.js** | Veridian | `14.2.0` | `14.2.0` | Architecture target is Next.js 14 |
| **React / React-DOM** | Horizon Meet | `^18` | `18.3.1` | React 18 |
| **React / React-DOM** | Veridian | `^18` | `18.2.0` | React 18 |
| **Clerk Auth** | Horizon Meet | `^6.31.3` | `6.31.3` | `@clerk/nextjs` |
| **Stream Video React SDK** | Horizon Meet | `^1.19.8` | `1.19.8` | `@stream-io/video-react-sdk` |
| **Stream Node SDK** | Horizon Meet | `^0.7.0` | `0.7.0` | `@stream-io/node-sdk` |
| **Stream Chat** | Horizon Meet | `^9.17.0` | `9.17.0` | `stream-chat` |
| **Supabase JS Client** | Horizon Meet | `^2.74.0` | `2.74.0` | `@supabase/supabase-js` |
| **Framer Motion** | Veridian | `^11.0.0` | `11.0.8` | `framer-motion` |
| **Tailwind CSS** | Horizon Meet | `^3.4.1` | `3.4.1` | `tailwindcss` |
| **Tailwind CSS** | Veridian | `^3.4.0` | `3.4.1` | `tailwindcss` |
| **LangGraph** | Veridian Backend | `>=0.2.0` | unpinned | Workflow orchestration |
| **LangChain Core/Community** | Veridian Backend | `>=0.2.0` | unpinned | LLM primitives |
| **OpenAI Python SDK** | Veridian Backend | `>=1.0.0` | unpinned | Used for NVIDIA NIM OpenAI compatibility |
| **FastAPI** | Veridian Backend | `>=0.110.0` | unpinned | Async API framework |
| **Uvicorn** | Veridian Backend | `>=0.29.0` | unpinned | ASGI server |
| **Pydantic** | Veridian Backend | `>=2.0.0` | unpinned | Data validation |
| **Supabase Python** | Veridian Backend | `>=2.0.0` | unpinned | PostgREST / RPC client |
| **Slack SDK** | Veridian Backend | `>=3.27.0` | unpinned | WebClient for DMs and alerts |
| **Jira Python** | Veridian Backend | `>=3.8.0` | unpinned | Issue creation and status transitions |
| **Google Cloud Speech** | Dubbing Service | unpinned | unpinned | Speech-to-Text with diarization |
| **Google Cloud TTS** | Dubbing Service | unpinned | unpinned | Text-to-Speech synthesis |
| **Google Generative AI** | Dubbing Service | unpinned | unpinned | Gemini summary generation |
| **Cloudinary Python** | Dubbing Service | unpinned | unpinned | Video asset upload and CDN |
| **MoviePy / PyDub** | Dubbing Service | unpinned | unpinned | Video/audio extraction and alignment |

> [!WARNING]
> `langchain-google-genai` is imported in `backend/agent/nodes/extractor.py` (`from langchain_google_genai import ChatGoogleGenerativeAI`), but is **completely missing from `requirements.txt`**. Installing `requirements.txt` on a clean environment will result in an immediate `ModuleNotFoundError`.

---

## 4. Database Schema Audit (Code-Derived)

### 4.1 Horizon Meet Schema
- **Table: `recordings`**
  - `id`: UUID (Primary Key, autogenerated)
  - `created_at`: TIMESTAMPTZ
  - `original_video_url`: TEXT (Cloudinary / Stream recording URL)
  - `dubbed_video_url`: TEXT (Cloudinary dubbed video URL, or empty string)
  - `summary`: TEXT (Gemini-generated summary paragraph)
  - `chapters`: JSONB (Array of `{ "time": "MM:SS", "title": "..." }`)

### 4.2 Veridian WorkOS Schema (from `supabase_agent_migration.sql` and code)
- **Table: `processed_meetings`**
  - `meeting_id`: TEXT (Primary Key)
  - `processed_at`: TIMESTAMPTZ
  - `task_count`: INTEGER
- **Table: `hr_employees`**
  - `id`: SERIAL PRIMARY KEY
  - `full_name`: TEXT
  - `email`: TEXT
  - `department`: TEXT
  - `job_title`: TEXT
  - `status`: TEXT (`ACTIVE`, `ON_PATERNITY_LEAVE`, `ON_MATERNITY_LEAVE`, `ON_LEAVE`, `TERMINATED`, `UNKNOWN`)
  - `last_synced_from`: TEXT
  - `synced_at`: TIMESTAMPTZ
- **Table: `employees`**
  - `id`: SERIAL PRIMARY KEY
  - `full_name`: TEXT
  - `email`: TEXT
  - `status`: TEXT (`ACTIVE`, `NEW_HIRE`, `ON_PATERNITY_LEAVE`, etc.)
  - `open_tickets`: INTEGER
  - `last_synced_from`: TEXT
  - `synced_at`: TIMESTAMPTZ
- **Table: `finance_budgets`**
  - `id`: UUID PRIMARY KEY
  - `category`: TEXT
  - `budget_remaining`: NUMERIC
  - `currency`: TEXT
  - `owner`: TEXT
  - `embedding`: `vector(1024)`
- **Table: `security_policies`**
  - `id`: UUID PRIMARY KEY
  - `policy_id`: TEXT
  - `document_name`: TEXT
  - `chunk_text`: TEXT
  - `page_number`: INTEGER
  - `embedding`: `vector(1024)`
- **Table: `audit_trail`**
  - `id`: UUID PRIMARY KEY
  - `meeting_id`: TEXT
  - `event_type`: TEXT
  - `agent_node`: TEXT
  - `detail`: TEXT
  - `confidence`: FLOAT
  - `provenance`: TEXT
  - `created_at`: TIMESTAMPTZ
- **RPC Functions**:
  - `match_finance_budgets(query_embedding vector(1024), match_threshold float, match_count int)`
  - `match_security_policies(query_embedding vector(1024), match_threshold float, match_count int)`

### 4.3 Missing Tables Required by ARCHITECTURE.md §5
The following tables are specified in the architecture but do **not** exist in either legacy codebase:
1. `organizations` (tenant roots)
2. `members` (Clerk user to org mapping)
3. `meetings` (unified meeting metadata with `org_id`, `stream_call_id`, etc.)
4. `transcripts` (structured JSONB segments with speaker, start, end, text)
5. `dubbing_jobs` (async job queue state)
6. `tasks` (persisted task records, flags, Jira key, vector)
7. `resolutions` (persisted AI proposed actions)
8. `approvals` (human decision audit with approver user ID)
9. `slack_threads` (Slack thread tracking with `turn_count`)

> [!CRITICAL]
> **Zero Row Level Security (RLS)** is enabled in the legacy Veridian migration script, and **no tables contain `org_id`**. Every query in the legacy code is global.

---

## 5. Hardcoded Models, Thresholds, URLs & Ports

### 5.1 Hardcoded Model Names
| File | Line | Hardcoded Model | Target Config Variable |
|---|---|---|---|
| `dubbing-service/app.py` | 37 | `'models/gemini-2.0-flash-exp'` | `LLM_EXTRACTION_MODEL` / `GEMINI_MODEL` |
| `dubbing-service/app.py` | 184, 201 | `'models/gemini-1.5-flash'` | `GEMINI_FALLBACK_MODEL` |
| `dubbing-service/app.py` | 263 | `'en-US-WaveNet-D'`, `'en-US-WaveNet-F'` | `TTS_VOICE_MALE`, `TTS_VOICE_FEMALE` |
| `backend/agent/llm_client.py` | 34 | `"meta/llama-3.1-70b-instruct"` | `LLM_REASONING_MODEL` |
| `backend/agent/llm_client.py` | 35 | `"nvidia/nv-embedqa-e5-v5"` | `EMBEDDING_MODEL` |
| `backend/agent/nodes/extractor.py` | 199 | `"gemini-2.5-flash"` | `LLM_EXTRACTION_MODEL` |
| `backend/connectors/sync_hr.py` | 24 | `"meta/llama3-70b-instruct"` | `LLM_REASONING_MODEL` |
| `backend/connectors/sync_finance.py` | 24 | `"nvidia/nv-embedqa-e5-v5"` | `EMBEDDING_MODEL` |
| `backend/connectors/sync_security.py` | 18 | `"nvidia/nv-embedqa-e5-v5"` | `EMBEDDING_MODEL` |

### 5.2 Hardcoded Thresholds & Limits
| File | Line | Value | ARCHITECTURE.md Specification |
|---|---|---|---|
| `backend/agent/nodes/security_checker.py` | 24 | `SECURITY_SIMILARITY_THRESHOLD = 0.50` | `SECURITY_THRESHOLD = 0.75` |
| `backend/agent/nodes/finance_checker.py` | 26 | `FINANCE_SIMILARITY_THRESHOLD = 0.50` | `FINANCE_THRESHOLD = 0.70` |
| `backend/agent/nodes/capacity_checker.py` | 26 | `REGULAR_THRESHOLD = 10` | `CAPACITY_LIMIT = 10` (config-driven) |
| `backend/agent/nodes/capacity_checker.py` | 27 | `NEW_HIRE_THRESHOLD = 2` | `CAPACITY_NEW_HIRE_LIMIT = 2` |
| `backend/agent/nodes/semantic_matcher.py` | 33, 39 | `0.6` / `0.8` (in prompt text) | `COMMIT_MATCH_THRESHOLD` |
| `backend/agent/llm_client.py` | 36 | `EMBEDDING_DIMENSIONS = 1024` | `EMBEDDING_DIM = 1024` |
| `backend/agent/nodes/dispatcher.py` | 26 | `SLACK_CHANNEL = "#agent-firewall"` | `SLACK_DEFAULT_CHANNEL` |

### 5.3 Hardcoded URLs & Ports
| File | Line | Hardcoded URL / Port |
|---|---|---|
| `dubbing-service/app.py` | 226 | `https://api.mymemory.translated.net/get?q=...` (free web translation API) |
| `dubbing-service/app.py` | 436 | Port `5001` |
| `trickster-next-zoom/app/api/start-dubbing/route.ts` | 23 | `http://localhost:5001` |
| `trickster-next-zoom/app/api/generate-insight/route.ts` | 18 | `http://localhost:5001` |
| `veridian/backend/api/main.py` | 7 | Port `8000` |
| `veridian/backend/api/main.py` | 61-66 | CORS origins: `http://localhost:3000`, `http://localhost:3001` |
| `veridian/backend/connectors/sync_finance.py` | 19 | Spreadsheet ID: `10jz-23jHhMSXWDPqTvIUbUIahZvIv9BXTvTVMjzxkfw` |
| `veridian/frontend/app/page.jsx` | 31 | `http://localhost:8000/api/meeting-ended` |
| `veridian/frontend/lib/sse.js` | 48, 118 | `http://localhost:8000/api/stream/${threadId}`, `http://localhost:8000/api/hitl-resume` |

---

## 6. Secrets & Vulnerability Audit

1. **Git Commit History**:
   - Neither repository committed actual `.env` or `.env.local` files into Git.
2. **Hardcoded Non-Sensitive IDs in Code**:
   - `legacy/veridian/backend/connectors/sync_finance.py` (Line 19): Hardcoded Google Sheet ID `10jz-23jHhMSXWDPqTvIUbUIahZvIv9BXTvTVMjzxkfw`. Must be moved to an environment variable.
3. **Critical Security Bypass Flaws**:
   - `legacy/veridian/backend/api/routes/slack.py` (Lines 44–45): If `SLACK_SIGNING_SECRET` is unset or empty, `_verify_slack_signature` logs a warning and returns `True`, completely disabling signature verification.
   - `legacy/veridian/backend/api/routes/github.py` (Lines 38–39): If `GITHUB_WEBHOOK_SECRET` is unset or empty, `_verify_github_signature` logs a warning and returns `True`.
   - `legacy/veridian/backend/api/routes/hitl.py` (Lines 1–133): `POST /api/hitl-resume` has **no authentication or authorization check**. Anyone with network access can resume or override an agent decision without being authenticated as a manager.
   - `legacy/veridian/backend/api/main.py` (Lines 88–127): `GET /api/stream/{thread_id}` has **no authentication**. Any client can listen to internal company meeting task streams knowing or brute-forcing a thread ID.

---

## 7. Dead Code, Duplication & Architectural Conflicts

### 7.1 Dead Code & Unfinished Stubs
- `legacy/veridian/backend/agent/graph.py`: 0-byte file.
- `legacy/veridian/backend/agent/tools.py`: 0-byte file.
- `legacy/veridian/backend/agent/nodes/resolution.py`: 0-byte file (superseded by `resolution_generator.py`).
- `legacy/veridian/backend/mock_servers/bamboohr_server.py`: 28-byte file with `# TODO: bamboohr_server.py`.
- `legacy/veridian/frontend/components/cards/`: Unused older cards (`CommandCenterCard.jsx`, `DecisionsCard.jsx`, `TLDRCard.jsx`), superseded by `components/v2/`.

### 7.2 Duplicated Infrastructure
- **Two separate Next.js web applications**: Horizon (`trickster-next-zoom`, Next 15) and Veridian (`frontend`, Next 14).
- **Two Supabase instances/clients**: Horizon client in TypeScript (`lib/supabase.ts`) and Veridian in Python (`supabase` library).
- **Two AI stacks**: Horizon uses Google Gemini directly (`google-generativeai`); Veridian uses both Gemini via LangChain (`langchain-google-genai`) and NVIDIA NIM via OpenAI SDK.

### 7.3 Conflicts vs ARCHITECTURE.md

| Feature / Area | Existing Legacy Code | ARCHITECTURE.md Requirement | Conflict Severity |
|---|---|---|---|
| **Service Communication** | Media service saves directly to Supabase table `recordings`; does not call WorkOS. | Media service emits HMAC-signed `meeting.ended` POST to WorkOS API (`POST /api/meeting-ended`). | **High** |
| **Meeting Payload Contract** | WorkOS endpoint accepts plain `{ meeting_id, transcript }` string with no headers. | Strictly validated JSON Schema `meeting_ended.schema.json` with HMAC signature, timestamp, participants list, and diarized segments. | **High** |
| **Speaker-to-Employee Resolution** | Missing entirely. Graph A extractor expects raw names in text; if unassigned, sets `UNASSIGNED`. | Diarization labels (`SPEAKER_01`) mapped via Clerk participants → `employees` table. Unresolved assignees flagged `UNRESOLVED_ASSIGNEE` and sent to HITL. | **High** |
| **Checkpointer & Persistence** | Graph A uses in-memory `MemorySaver`. State is lost on process restart. Tasks and resolutions are not saved to DB tables. | `PostgresSaver` in Supabase with durable persistence to `tasks`, `resolutions`, and `approvals` tables. | **High** |
| **Multi-Tenancy & Auth** | No Clerk integration in FastAPI backend. No `org_id` on any DB table. Zero Row Level Security (RLS). | Clerk JWKS verification in FastAPI; manager role required for HITL; all tables tenant-isolated with `org_id` and RLS. | **High** |
| **GitHub Semantic Matcher (Graph B)** | Prompts LLM with all task strings in prompt context. | Uses pgvector cosine similarity over open ticket embedding vectors scoped to committer and repo mapping. | **Medium** |
| **Transcription Provider** | Google Speech-to-Text hardcoded in Flask app. | Pluggable `Transcriber` interface targeting WhisperX with diarization, with Google STT fallback. | **Medium** |
| **Frontend Framework Version** | Horizon uses Next.js 15.4.7; Veridian uses Next.js 14.2.0. | Single Next.js 14 app in `apps/web` with route groups `(auth)`, `(meet)`, and `(workos)`. | **Medium** |
| **Security Thresholds** | Security threshold is hardcoded at `0.50`; Finance threshold is `0.50`. | Config-driven: `SECURITY_THRESHOLD=0.75`, `FINANCE_THRESHOLD=0.70`. | **Medium** |

---

## 8. Summary of Audit Findings & Readiness

1. Both source projects are now mirrored and verified in `legacy/horizon-meet` and `legacy/veridian`.
2. The codebases have working core capabilities (video room and dubbing in Horizon; LangGraph compliance firewall and Slack/GitHub loop in Veridian), but differ substantially from the unified architectural contract.
3. No active secrets are committed in git.
4. The path is clear to proceed into **Phase 1: Monorepo Scaffold & Shared Contracts**.
