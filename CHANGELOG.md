# Changelog

All notable changes to the Horizon-Veridian project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-13 - Hackathon & Gnani Internship Release

### Added
- **6-Stage Closed-Loop Sprint Governance Orchestrator:**
  - Stage 1: End-of-Meeting Ingestion & Multi-Tenant LangGraph Graph A state machine.
  - Stage 2: 4-Way Compliance Firewall (Budget, Leave, Security Policies, and SEC-POL-104 Blocked APIs).
  - Stage 3: Zero Tickets During Meeting — Enforced Manager Review Menu in Slack DM.
  - Stage 4: Manager Approval Gate (Slack Block Kit buttons & Web UI) dispatching isolated Jira issues to the `SCRUM` project and 1-on-1 Slack DMs to engineers.
  - Stage 5: Scheduled & fast-forward 1-on-1 employee status check-in DMs with rate-limit backoff.
  - Stage 6: Evidence-based auto-close loop — auto-transitions Jira tickets to `Done` upon PR URL or commit hash; routes non-evidence replies to `In Review` with a Manager confirmation card.
- **Model Auditing & Honesty:**
  - Created `docs/gnani-usage.md` detailing every runtime model: Gnani Prisma v3.0 STT, Gnani Timbre v2.5 TTS, Gnani Evon 30B / Gemini 3 reasoning, and NV-EmbedQA-E5-v5 embeddings.
  - Added structured log lines `[GNANI-STT]` and `[GNANI-TTS]` in `services/media/pipeline/gnani_client.py`.
- **Privacy & Security Hardening:**
  - Scrubbed real personal identities from repository history and working tree using `git-filter-repo`.
  - Added `local.identities.json` (gitignored) for zero-leak local team wiring with real Slack/Clerk credentials.
  - Slack interactivity deduplication via `_SEEN_SLACK_INTERACTIVE_ACTIONS` and 3-second acknowledgement window.
  - Strict Slack v0 HMAC-SHA256 and GitHub webhook HMAC-SHA256 signature verification.
- **Master Invariant Test Suite:**
  - Added 8 required invariant tests in `services/workos/tests/test_a4_master_invariants.py` verifying zero tickets pre-approval, double-click idempotency, replay deduplication, 403 RBAC, and prompt injection immunity.
- **Hinglish Evaluation Suite:**
  - Added 12 synthetic Hinglish sprint utterances in `evals/hinglish/dataset.json`.
  - Added `scripts/run_eval.py` generating `evals/hinglish/results.md` achieving 100% across action extraction, assignee resolution, and compliance flagging.
- **Demo Readiness & Submission Kit:**
  - Added `scripts/demo_check.py` pre-flight diagnostic utility testing ports, Supabase, Slack, Jira, and keys.
  - Added `docs/DEMO_SCRIPT.md` with 60-second video choreography.
  - Added `demo/fixtures/sprint_replay_fixture.json` and UI fallback banner for network-resilient judging.
  - Created `submission/` kit with LinkedIn post, X/Twitter thread, project explanation, and technical interview notes.

### Changed
- Replaced outdated WhisperX reference in `ARCHITECTURE.md` with Gnani Prisma v3.0.
- Normalized GitHub Actions CI workflow to Node 24 compatible action tags and workspace lockfile flags (`--workspaces=false`).
- Replaced Jason Yavorska persona with Arjun Rao across all committed seed files.
