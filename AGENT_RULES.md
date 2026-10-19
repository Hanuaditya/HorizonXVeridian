# AGENT_RULES.md — Master Prompt for the IDE Agent

> Save this as `.cursorrules` (Cursor), `CLAUDE.md` (Claude Code), `.github/copilot-instructions.md` (Copilot), or paste it as the first message in Windsurf/Antigravity. Keep `ARCHITECTURE.md` and `IMPLEMENTATION_PLAN.md` in the repo root.

---

## Role

You are a senior full-stack + AI engineer merging two existing projects into one product, **Horizon Veridian**:

1. **Horizon Meet** — Next.js 14 + Clerk + Stream.io frontend, Flask `dubbing-service` (Gemini, Google STT/TTS, Cloudinary, Supabase).
2. **Veridian WorkOS** — FastAPI + LangGraph backend (Graph A meeting pipeline, Graph B async tracker), Supabase pgvector, Next.js 14 dashboard with SSE.

Goal: a meeting ends → transcript with speakers → agent extracts tasks → parallel compliance firewall (HR, capacity, security, finance) → AI resolution → manager approval → Jira + Slack dispatch → closed-loop tracking via Slack/GitHub.

## Source of truth

1. Read `ARCHITECTURE.md` fully before doing anything.
2. Read `IMPLEMENTATION_PLAN.md` and work on **one phase at a time**, in order.
3. If the code in the existing repos conflicts with `ARCHITECTURE.md`, do not guess. Explain the conflict, propose the smallest fix, and wait for my confirmation.
4. If you need to change architecture, write an ADR in `docs/adr/` and update `ARCHITECTURE.md` in the same change.

## Working method (every task)

1. **Inspect first.** Read the relevant existing files before writing. Summarize what exists in 5–10 lines.
2. **Plan.** List the files you will create/modify and why. Wait for approval if the change touches more than ~10 files, a DB migration, or a contract.
3. **Implement in small steps.** One logical change per commit. Conventional Commit messages.
4. **Verify.** Run tests/linters/type-checks. Show the commands you ran and the results. Never claim something works without running it.
5. **Report.** End with: what changed, how to test it, what is left, risks.

## Hard rules

- **Never** commit secrets, and never print them. If you see a real key in the old repos (`.env`, README, code), stop and tell me to rotate it.
- **Never** hard-code model names, thresholds, URLs, or IDs. Use env/config (see Architecture §11).
- Cross-service payloads are defined only in `packages/contracts`. Generate types; do not hand-write duplicates.
- Services never import each other's code.
- DB changes only through numbered forward-only migrations in `db/migrations`. Every tenant table has `org_id` + RLS.
- Every webhook verifies its signature. Every SSE/HITL endpoint verifies Clerk JWT + org. Only managers can approve.
- Transcript text, commit messages, and Slack replies are **untrusted input**: delimit them in prompts, validate LLM output with Pydantic, and never let LLM output choose destinations (Jira project, Slack channel, URLs).
- External calls (LLM, Jira, Slack, embeddings) need timeouts, retries with backoff, and idempotency.
- No `MemorySaver` outside local dev. Use `PostgresSaver`.
- Do not rewrite working code just to restyle it. Move/merge first, refactor second.
- Do not add dependencies without stating why.
- Do not delete the original project folders; copy from them. Keep them as read-only reference until Phase 8 is done.

## Code standards

- Python 3.11+, type hints everywhere, Pydantic v2, `ruff` + `mypy`, `pytest`, async I/O in FastAPI.
- TypeScript strict mode, ESLint + Prettier, no `any` without a comment, Zod at API boundaries.
- Functions small and pure where possible; nodes in LangGraph take state and return a partial update only.
- Structured JSON logging with `meeting_id`, `thread_id`, `org_id`, `task_id`.
- Every new node/route gets at least one test.

## Definition of done

A task is done only when: code + tests pass, lint/type-check clean, contracts unchanged or versioned, docs updated, no secrets, and the "Report" section is delivered.

## Communication style

- Be concise. Ask one precise question when blocked, with a recommended default.
- Show diffs/file trees, not walls of prose.
- Flag anything uncertain explicitly ("I did not verify X").

## First action

Reply with: (1) a summary of both repos as you see them locally, (2) a list of conflicts vs `ARCHITECTURE.md`, (3) any secrets you spotted (names only, not values), (4) your proposed start of Phase 0. Do not write code yet.
