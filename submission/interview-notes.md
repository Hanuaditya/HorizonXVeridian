# Horizon-Veridian: Technical Interview & Judging Prep Notes

> Concise cheat-sheet for technical questions during hackathon judging and interviews.

---

## 1. High-Level Architecture & Value Proposition

- **Question: "Why did you build this instead of using existing AI meeting summarizers?"**
  - **Answer:** Existing meeting bots (Otter, Fireflies) generate unstructured text summaries or blindly flood Jira with unverified tickets. They have zero organizational context: they don't know who is on paternity leave, they don't check security policies or cloud budgets, and they force managers to manually groom boards. Horizon-Veridian implements **closed-loop governance**: 4-way compliance firewalls, zero tickets during the call, manager approval gating, and evidence-based auto-closing upon PR/commit submission.

---

## 2. Model & Voice Infrastructure

- **Question: "What models are you using and where are they called?"**
  - **Answer:** We maintain complete model truthfulness (documented in `docs/gnani-usage.md`):
    - **Speech-to-Text:** Gnani AI Vachana **Prisma v3.0** (`services/media/pipeline/gnani_client.py`) with structured logging `[GNANI-STT]`.
    - **Text-to-Speech:** Gnani AI Vachana **Timbre v2.5** for dubbed audio playback on `/meetings/[id]`.
    - **Task Extraction & Reasoning:** Gnani AI **Evon 30B** (preferred) / Google **Gemini 3 Flash Preview** (`gemini-3-flash-preview`) with structured JSON schema output (`services/workos/core/evon_llm.py`).
    - **Semantic Policy RAG:** NVIDIA NIM **NV-EmbedQA-E5-v5** with Blake2b deterministic offline fallback (`services/workos/core/embeddings.py`).

---

## 3. Security, Reliability & Invariants

- **Question: "How do you prevent duplicate tickets if a manager double-clicks or Slack replays an event?"**
  - **Answer:** We have three distinct layers of idempotency:
    1. **Task ID & Jira Key Check:** `dispatcher_node` inspects `dispatched_tickets` and existing `jira_ticket_id`s, skipping any task already created.
    2. **Slack Deduplication Cache:** `api/routes/slack.py` tracks `trigger_id` and `action_ts` in `_SEEN_SLACK_INTERACTIVE_ACTIONS` to discard duplicate webhook deliveries immediately.
    3. **Database Constraints:** Supabase `processed_meetings` enforces a unique constraint on `(org_id, meeting_id)`.
  - All 8 invariants are proven by our test suite in `services/workos/tests/test_a4_master_invariants.py`.

- **Question: "How do you handle prompt injection in meeting transcripts?"**
  - **Answer:** All untrusted transcript and employee reply data is wrapped in structured XML delimiters via `wrap_untrusted_data()`. Furthermore, Jira project keys and Slack channels are resolved strictly from allow-listed configuration (`get_settings().jira_project_key`), never blindly accepted from LLM output.

- **Question: "How does Smart Leave Redirection work?"**
  - **Answer:** When an extraction identifies an assignee (e.g. Arjun Rao) who is on paternity leave (`lookup_hr_employee`), it does NOT mutate the task before approval. It attaches a recommendation flag. `find_best_domain_replacement()` scores active peers in the organization by matching task domain skills (`elasticsearch`, `aws`, `backend`) and picking the engineer with the lowest active task workload (e.g., Rohan Patel). Reassignment only executes post-manager approval.

---

## 4. Key Metrics & Evaluation

- **Test Suite:** 37 automated tests passing across Media (7) and WorkOS (30).
- **Hinglish Benchmark:** 100% accuracy across 12 code-mixed sprint utterances covering task extraction, assignee resolution, and compliance flags (`evals/hinglish/results.md`).
- **Pre-flight Diagnostic:** Verified end-to-end via `python scripts/demo_check.py`.
