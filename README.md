# Horizon Veridian

[![CI](https://github.com/Hanuaditya/HorizonXVeridian/actions/workflows/ci.yml/badge.svg)](https://github.com/Hanuaditya/HorizonXVeridian/actions/workflows/ci.yml)

> **Horizon Veridian** unites real-time AI-powered video meetings, multilingual dubbing, and automated post-meeting workflow execution into a single, cohesive platform.

---

## Architecture Overview

Horizon Veridian is organized as a clean polyglot monorepo:

```
horizon-veridian/
â”œâ”€â”€ apps/
â”‚   â””â”€â”€ web/                 # Next.js 15 frontend (Clerk auth, Stream video, WorkOS approval inbox)
â”œâ”€â”€ services/
â”‚   â”œâ”€â”€ media/               # Python Flask microservice (diarization, dubbing, STT/TTS)
â”‚   â””â”€â”€ workos/              # Python FastAPI microservice (LangGraph task extraction, compliance, dispatch)
â”œâ”€â”€ packages/
â”‚   â””â”€â”€ contracts/           # Cross-service JSON schemas and typed TypeScript/Python generators
â”œâ”€â”€ legacy/                  # Archived reference codebases (horizon-meet, veridian)
â”œâ”€â”€ docker-compose.yml       # Local container orchestration
â””â”€â”€ .env.example             # Monorepo environment configuration template
```

For full system architecture, state machines, and ADRs, see [`ARCHITECTURE.md`](./ARCHITECTURE.md).  
For the step-by-step phased roadmap, see [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md).  
For engineering principles and constraints, see [`AGENT_RULES.md`](./AGENT_RULES.md).

---

## Prerequisites

- **Node.js**: v20 or v22
- **Python**: 3.12+
- **Docker & Docker Compose** (optional for containerized workflow)
- **Git**

---

## Quickstart

### 1. Configure Environment
Copy the environment template and populate your local API keys:
```bash
cp .env.example .env
```

### 2. Install Dependencies

**Web Application (Next.js 15):**
```bash
cd apps/web
npm install
cd ../..
```

**Media Service (Flask):**
```bash
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .venv\Scripts\activate
pip install -r services/media/requirements.txt
```

**WorkOS Service (FastAPI / LangGraph):**
```bash
pip install -r services/workos/requirements.txt
```

---

## Running Locally

You can run each service independently during development:

| Service | Directory | Command | Port | Health URL |
| :--- | :--- | :--- | :--- | :--- |
| **Web UI** | `apps/web` | `npm run dev` | `3000` | `http://localhost:3000` |
| **Media Service** | `services/media` | `python app.py` | `5001` | `http://localhost:5001/health` |
| **WorkOS Service** | `services/workos` | `uvicorn api.main:app --port 8000 --reload` | `8000` | `http://localhost:8000/health` |

Alternatively, run the complete stack with Docker Compose:
```bash
docker compose up --build
```

---

## Monorepo Tooling & Contracts

Contracts between services are strictly typed using JSON Schemas under `packages/contracts/`.

- **Seed HR, Finance CSV & Security Policies (`db/seed/`):**
  ```bash
  npm run seed
  ```
- **Run Service Tests (Media & WorkOS):**
  ```bash
  pytest services/media/tests -v
  pytest services/workos/tests -v
  ```
- **Check contracts freshness (CI check):**
  ```bash
  npm run contracts:check
  ```
- **Regenerate TypeScript & Pydantic models from schemas:**
  ```bash
  npm run contracts:generate
  ```
- **Type-check & lint frontend:**
  ```bash
  npm run type-check
  npm run lint
  ```
- **Build frontend:**
  ```bash
  npm run build
  ```

### Unified Web Routes
- `/workos`: Live Gnani Evon 30B × Veridian WorkOS Compliance Hub & HITL Approval Center
- `/meetings` & `/meetings/[id]`: Unified Meeting Hub & Detail Dossier (Gnani Prisma STT + Timbre Dubbing + Tasks)
- `/admin`: Clerk ↔ Slack ↔ Jira Identity Mappings, Config Thresholds & Connector Sync
- `/`, `/upcoming`, `/previous`, `/recordings`, `/insights`, `/personal-room`: Horizon Meet Rooms & Recordings

---

## Hinglish NLP & Compliance Firewall Evaluation

Horizon-Veridian includes a dedicated Hinglish evaluation benchmark testing code-mixed English/Hindi sprint utterances across task extraction, identity resolution, and 4-way compliance firewalls (budget, leave, and blocked APIs).

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

## License
Proprietary & Confidential. All rights reserved.
