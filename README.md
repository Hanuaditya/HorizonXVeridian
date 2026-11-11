# Horizon Veridian

[![CI](https://github.com/horizon-veridian/horizon-veridian/actions/workflows/ci.yml/badge.svg)](https://github.com/horizon-veridian/horizon-veridian/actions/workflows/ci.yml)

> **Horizon Veridian** unites real-time AI-powered video meetings, multilingual dubbing, and automated post-meeting workflow execution into a single, cohesive platform.

---

## Architecture Overview

Horizon Veridian is organized as a clean polyglot monorepo:

```
horizon-veridian/
├── apps/
│   └── web/                 # Next.js 15 frontend (Clerk auth, Stream video, WorkOS approval inbox)
├── services/
│   ├── media/               # Python Flask microservice (diarization, dubbing, STT/TTS)
│   └── workos/              # Python FastAPI microservice (LangGraph task extraction, compliance, dispatch)
├── packages/
│   └── contracts/           # Cross-service JSON schemas and typed TypeScript/Python generators
├── legacy/                  # Archived reference codebases (horizon-meet, veridian)
├── docker-compose.yml       # Local container orchestration
└── .env.example             # Monorepo environment configuration template
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

## License
Proprietary & Confidential. All rights reserved.
