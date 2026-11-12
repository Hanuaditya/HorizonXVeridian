# Horizon-Veridian: 60-Second Live Demo Script & Walkthrough

> **Theme:** Zero Tickets During Meeting → Manager Slack Approval Gate → Individual 1-on-1 DMs → Evidence-Based Auto-Close.

---

## 1. Setup & Pre-Flight Check (T - 2 minutes)

Run the pre-flight verification script in your terminal to ensure ports, Slack bot, Jira project, and Supabase are green:
```bash
python scripts/demo_check.py
```
Expected output: `ALL DEMO READINESS CHECKS COMPLETED SUCCESSFULLY!`

Make sure your local servers are running:
```bash
npm run live
```
- Port `3000`: Next.js Web App (`http://localhost:3000/workos`)
- Port `5001`: Media Service (Gnani Prisma STT & Timbre TTS)
- Port `8000`: WorkOS Service (LangGraph Sprint Governance Orchestrator)

---

## 2. 60-Second Demo Video Timeline

| Timestamp | Visual Screen | Speaker Dialogue / Action |
| :--- | :--- | :--- |
| **00:00 - 00:10** | Split View on `/workos` showing **Manager Command Center** on the left and **Employee Bot Console** on the right. | *"Welcome to Horizon-Veridian. Traditional meeting bots spam Jira tickets mid-call, polluting backlogs. Watch our 6-stage sprint governance loop in action."* |
| **00:10 - 00:20** | Click **"Run Full Sprint Demo"** (or finish audio meeting). Progress bar stages from Extractor to Firewall. | *"As our Hinglish meeting ends, Gnani Prisma STT transcribes the dialogue. Notice: **ZERO** Jira tickets are created during the call, respecting engineering focus."* |
| **00:20 - 00:30** | Switch to Slack window. Veridian Bot delivers the Block Kit **Review Menu** to the Manager. | *"The Manager receives an executive review DM in Slack. Arjun is detected on paternity leave, so the system recommends smart rerouting to Rohan, who has the lowest active workload."* |
| **00:30 - 00:40** | Manager clicks **"Approve & Create Tickets"** button in Slack. | *"The Manager approves. Only now does Veridian create real Jira tickets in the SCRUM project, and dispatches individual 1-on-1 assignment DMs to each engineer."* |
| **00:40 - 00:50** | Employee B (Priya / Resigo) replies in Slack DM: `"OAuth dashboard completed — PR https://github.com/example/repo/pull/42"` | *"Later, Employee B replies with verifiable PR evidence in their Slack thread. The Evon NLP engine detects intent=COMPLETED and verifies the PR URL."* |
| **00:50 - 01:00** | Jira board automatically transitions `SCRUM-X` to **Done**; confirmation DM pops up in Slack; Manager sees audit log. | *"Without any manual board grooming, the Jira ticket auto-closes to Done with an immutable audit trail. That is closed-loop sprint governance with Horizon-Veridian."* |

---

## 3. Contingency Plans & Zero-Failure Fallbacks

| Scenario | Immediate Fallback |
| :--- | :--- |
| **Slack API Rate Limit (429)** | The sprint loop automatically backs off per-channel (`_CHANNEL_BACKOFF`). Alternatively, reply `"approve"` or click **Approve** directly inside the web UI at `http://localhost:3000/workos`. |
| **Jira Cloud Delay or Downtime** | If Jira Cloud is unreachable or credentials are unset, the system gracefully falls back to mock tickets (`SCRUM-101`) without breaking UI execution. |
| **Network or Wi-Fi Interruption** | Click the orange **"Replay Recorded Demo Fixture"** banner on `/workos` to instantly load `demo/fixtures/sprint_replay_fixture.json` and showcase the complete 6-stage flow without live internet calls. |
| **Missing Evidence on Completion** | If the employee replies `"Finished the work!"` without a commit/PR URL, the ticket moves to `In Review` and sends an interactive **Confirm Done** card to the Manager. |

---

## 4. Test & Evaluation Verification Commands

- Run all invariant & unit tests (37 tests across media & workos):
  ```bash
  pytest services/media/tests -v
  pytest services/workos/tests -v
  ```
- Run Hinglish 12-sample evaluation suite:
  ```bash
  python scripts/run_eval.py
  ```
- Check schema contract freshness:
  ```bash
  npm run contracts:check
  ```
