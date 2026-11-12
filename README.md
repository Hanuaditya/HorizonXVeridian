# Horizon Veridian

[![CI](https://github.com/Hanuaditya/HorizonXVeridian/actions/workflows/ci.yml/badge.svg)](https://github.com/Hanuaditya/HorizonXVeridian/actions/workflows/ci.yml)

> **Horizon Veridian** unites real-time video meetings, multilingual speech intelligence via Gnani AI, and autonomous 6-stage sprint governance into a single, closed-loop platform with strict Human-In-The-Loop (HITL) manager oversight.

---

## ⚡ The 6-Stage Closed-Loop Sprint Governance Lifecycle

Unlike traditional meeting bots that flood Jira with unverified tasks mid-call, Horizon-Veridian guarantees engineering focus, organizational compliance, and zero backlog pollution:

```
[1. Hinglish Meeting Speech]
            │
            ▼
[2. Gnani Prisma STT Ingestion]
  → Transcribes conversational English & Hindi with speaker diarization
            │
            ▼
[3. 4-Way Compliance Firewall (LangGraph)]
  → Evaluates Cloud Budgets, HR Leave Status, Security Policies & Blocked APIs (SEC-POL-104)
  → Smart Leave Redirection: re-routes absent teammate's tasks to lowest-workload peer
            │
            ▼
[4. Zero Tickets During Meeting (Manager Approval Gate)]
  → ZERO Jira tickets exist before approval!
  → Veridian Bot delivers an interactive Block Kit Review Menu to the Engineering Manager in Slack
            │
            ▼
[5. Manager Approval & Isolated Dispatch]
  → Creates validated Jira tickets in SCRUM project
  → Dispatches individual 1-on-1 assignment DMs to engineers
            │
            ▼
[6. Status Check-Ins & Evidence-Based Jira Auto-Close]
  → Periodic Slack status check-ins tracking progress %, milestones & blockers
  → PR URL / Commit Hash present? → Auto-transitions Jira ticket to Done (actor=system)
  → No evidence? → Moves to In Review & prompts Manager to Confirm Done (actor=manager)
```

---

## 🧠 AI Model Architecture & Truthfulness Audit

Every model called by Horizon-Veridian is audited and verified against runtime logs (see [`docs/gnani-usage.md`](./docs/gnani-usage.md)):

| Role | Provider | Model | Configured In | Log Signature |
| :--- | :--- | :--- | :--- | :--- |
| **Speech-to-Text (STT)** | **Gnani AI — Vachana** | **Prisma v3.0** (`GNANI_PRISMA_MODEL`) | `services/media/pipeline/gnani_client.py` | `[GNANI-STT] model=prisma-v3.0` |
| **Text-to-Speech (TTS)** | **Gnani AI — Vachana** | **Timbre v2.5** (`GNANI_TIMBRE_MODEL`) | `services/media/pipeline/gnani_client.py` | `[GNANI-TTS] model=timbre-v2.5` |
| **Reasoning & Task Extraction** | **Gnani AI — Evon** / **Gemini** | **Evon 30B** / **Gemini 3 Flash Preview** | `services/workos/core/evon_llm.py` | `structured_output: calling ...` |
| **Semantic Policy RAG** | **NVIDIA NIM** / Offline | **NV-EmbedQA-E5-v5** / Blake2b | `services/workos/core/embeddings.py` | 1024-dim pgvector embeddings |

---

## 📊 Hinglish NLP & Compliance Firewall Evaluation

Horizon-Veridian includes a dedicated Hinglish evaluation benchmark testing code-mixed English/Hindi sprint utterances across task extraction, identity resolution, and 4-way compliance firewalls:

| Metric | Accuracy | Samples | Details |
| :--- | :--- | :--- | :--- |
| **Task Action Extraction** | **100.0%** | 12/12 | Extracts action item verbs & intent from conversational Hindi/English |
| **Assignee Resolution** | **100.0%** | 12/12 | Maps nicknames & phonetic references to verified team identities |
| **Compliance & Firewall** | **100.0%** | 12/12 | Catches budget caps, paternity leave & blocked APIs (`SEC-POL-104`) |

To run the evaluation suite locally:
```bash
python scripts/run_eval.py
```
Full evaluation report and sample-by-sample predictions are recorded in [`evals/hinglish/results.md`](./evals/hinglish/results.md).

---

## 🛡️ Reliability & Security Invariants

Verified by our automated invariant test suite (`services/workos/tests/test_a4_master_invariants.py`):
1. **Zero Tickets Pre-Approval:** No Jira ticket or assignee DM exists before explicit manager approval.
2. **Double-Approve Idempotency:** Double-clicking Approve creates exactly one ticket per task.
3. **Replay Deduplication:** Replayed Slack webhooks are deduplicated via `trigger_id` and `action_ts`.
4. **Signature Verification:** Forged or unsigned Slack and GitHub webhook calls are strictly rejected with HTTP 403.
5. **Strict RBAC:** Non-managers receive HTTP 403 on approval, check-in, and HITL endpoints; employees only view their own tickets.
6. **Prompt Injection Immunity:** Untrusted transcript overrides cannot alter Jira project keys or auto-close tickets.
7. **Leave Suggestion Integrity:** Tasks assigned to personnel on leave generate non-mutating suggestions pre-approval; rerouting executes post-approval.
8. **Unresolved Assignee Safety:** Ambiguous speaker tags escalate to the Manager rather than defaulting to a teammate.

---

## 🚀 Quickstart & Running Locally

### 1. Prerequisites
- **Node.js**: v20 or v22
- **Python**: 3.12+
- **Git**

### 2. Configure Environment
```bash
cp .env.example .env
```
*(Optional)* For testing with real Slack/Clerk identities without committing personal data, place your mappings into gitignored `local.identities.json`.

### 3. Run Pre-Flight Demo Check
```bash
python scripts/demo_check.py
```

### 4. Start Live Services
```bash
npm run live
```
- **Web UI:** `http://localhost:3000` (WorkOS Hub at `/workos`, Admin at `/admin`)
- **Media Service (Port 5001):** `http://localhost:5001/health`
- **WorkOS Service (Port 8000):** `http://localhost:8000/health`

---

## 🧪 Testing & Verification

Run the complete test suite across services (37 passing tests):
```bash
pytest services/media/tests -v
pytest services/workos/tests -v
```

Verify cross-service contract schemas:
```bash
npm run contracts:check
```

---

## 📁 Repository Map & Key Documentation

- [`docs/gnani-usage.md`](./docs/gnani-usage.md) — Single source of truth for runtime model calls & logs
- [`docs/DEMO_SCRIPT.md`](./docs/DEMO_SCRIPT.md) — 60-second video demo walkthrough & contingency plans
- [`evals/hinglish/results.md`](./evals/hinglish/results.md) — 12-sample Hinglish evaluation benchmark
- [`submission/`](./submission/) — Hackathon submission kit (Project explanation, LinkedIn, X, Interview notes)
- [`CHANGELOG.md`](./CHANGELOG.md) — Release notes and migration changelog
- [`ROADMAP.md`](./ROADMAP.md) — Post-hackathon architectural roadmap

---

## License
Proprietary & Confidential. All rights reserved.
