# Horizon-Veridian Engineering Roadmap

> Post-hackathon architecture enhancements and upcoming production milestones.

---

## Phase 1: Near-Term Enhancements (Q4 2026)

- [ ] **Postgres Checkpointer for LangGraph:**
  - Transition LangGraph state persistence from `MemorySaver` / file snapshot caching to `AsyncPostgresSaver` backed by Supabase `pgvector` connection pooling.
  - Enables horizontal scaling of the WorkOS worker nodes without distributed memory lock contention.
- [ ] **Streaming STT WebSockets:**
  - Connect client-side microphone streams directly to Gnani Prisma v3.0 via bidirectional WebSockets for live in-meeting captioning (<200ms latency).
- [ ] **Bi-Directional Jira & Linear Sync:**
  - Add native webhook listeners for Jira Cloud issue transitions so manual drag-and-drop on Jira boards immediately syncs status back to WorkOS and Slack threads.
  - Add Linear and GitHub Projects issue trackers alongside Jira `SCRUM`.

---

## Phase 2: Autonomous Sprint Optimization (Q1 2027)

- [ ] **Predictive Capacity Planning:**
  - Correlate past employee velocity and Git commit complexity with sprint commitments to automatically flag sprint over-commitments before the meeting ends.
- [ ] **Automated PR Code Review Agent:**
  - When an employee provides a PR URL in Slack, trigger an automated AI code review check against team style guides and security policies before prompting the Manager to confirm.
- [ ] **Multi-Dialect Indian Language Support:**
  - Expand beyond Hinglish to support Tamil-English (Tanglish), Telugu-English, and Kannada-English meeting transcription and task extraction powered by Gnani Prisma.

---

## Phase 3: Enterprise Compliance & Audit (Q2 2027)

- [ ] **SOC2 Type II Immutable Audit Logging:**
  - Hash-chain audit trail records with cryptographic timestamps in an append-only ledger.
- [ ] **Self-Hosted Enterprise Deployment:**
  - Single-command Helm chart for on-premise Kubernetes clusters with air-gapped LLM/voice inference.
