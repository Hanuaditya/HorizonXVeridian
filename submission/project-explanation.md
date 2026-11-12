# Horizon-Veridian: Project Overview & Engineering Deep-Dive

## 1. What Problem Does Horizon-Veridian Solve?
Engineering teams waste hours every week in post-meeting overhead: taking messy notes, creating Jira tickets, assigning tasks, and following up on Slack. Traditional "meeting AI bots" make things worse by auto-generating dozens of low-quality tickets mid-call, polluting backlogs, ignoring company security policies, and assigning work to engineers who are on leave.

**Horizon-Veridian** is a closed-loop Sprint Governance platform that unites real-time video meetings, multilingual speech processing, and autonomous workflow execution with strict human-in-the-loop (HITL) manager oversight.

---

## 2. The 6-Stage Sprint Governance Architecture

```
[Meeting Audio / Transcript]
           │
           ▼
[Stage 1: Gnani Prisma STT & Ingestion]
  → Transcribes conversational Hinglish with speaker attribution
           │
           ▼
[Stage 2: 4-Way Compliance Firewall (LangGraph)]
  → Evaluates Budget, Leave (HR), Security Policies & Blocked APIs (SEC-POL-104)
  → Smart Leave Redirection: Re-routes absent teammate's tasks to lowest-workload peer
           │
           ▼
[Stage 3: Zero-Ticket Manager Review Menu (Slack DM)]
  → ZERO Jira tickets exist before approval!
  → Delivers interactive Block Kit approval card to Engineering Manager
           │
           ▼
[Stage 4: Manager Approval Gate & Isolation Dispatch]
  → Creates validated Jira issues in SCRUM project
  → Dispatches individual 1-on-1 Slack DMs to each assigned engineer
           │
           ▼
[Stage 5: Scheduled & On-Demand Status Check-In Loop]
  → Periodic Slack DMs checking progress %, milestones, and blockers
           │
           ▼
[Stage 6: Evidence-Based Jira Auto-Close Loop]
  → PR URL / Commit Hash present? → Auto-transitions Jira ticket to Done (actor=system)
  → No evidence? → Moves to In Review & sends Confirm/Reject card to Manager (actor=manager)
```

---

## 3. Technology Stack & Model Truthfulness

- **Speech-to-Text (STT):** Gnani AI Vachana **Prisma v3.0** (`GNANI_PRISMA_MODEL`)
- **Text-to-Speech & Dubbing (TTS):** Gnani AI Vachana **Timbre v2.5** (`GNANI_TIMBRE_MODEL`)
- **Reasoning & Task Extraction:** Gnani AI **Evon 30B** (`EVON_MODEL_NAME`) / Google **Gemini 3 Flash Preview** (`gemini-3-flash-preview`)
- **Semantic Policy RAG:** NVIDIA NIM **NV-EmbedQA-E5-v5** with Blake2b deterministic offline fallback
- **State Orchestration:** Python 3.12, **LangGraph** (multi-tenant state machine with checkpointing), FastAPI, Flask
- **Frontend:** Next.js 15.5.6 (React 19, Tailwind CSS, TypeScript, Clerk RBAC)
- **Database:** Supabase PostgreSQL with `pgvector` and Row Level Security (RLS)
- **External Integrations:** Slack Cloud Block Kit, Jira Cloud REST API v3
