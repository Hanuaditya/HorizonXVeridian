'use client';

import React, { useEffect, useState } from 'react';
import { OrgOnboardingGuard, useAppAuth } from '@/providers/AuthBridge';
import { useAgentStream, useHITLResume } from '@/lib/sse';
import type { WorkOSAuditEntry, WorkOSThreadState } from '@/lib/workos-types';
import WorkflowHeader from '@/components/workos/WorkflowHeader';
import MeetingOverview from '@/components/workos/MeetingOverview';
import DecisionsMade from '@/components/workos/DecisionsMade';
import ApprovalsPanel from '@/components/workos/ApprovalsPanel';
import ProgressTracker from '@/components/workos/ProgressTracker';
import ManagerCommandPane from '@/components/workos/ManagerCommandPane';
import EmployeeBotPane from '@/components/workos/EmployeeBotPane';

const GOLDEN_HINGLISH_TRANSCRIPT = `[00:00 - Dov]: Team, welcome. We have three main items today.
[00:15 - Dov]: First, Jason, please deploy the Elastic search cluster directly to production by Thursday.
[00:30 - Amit]: Par Dov bhai, Jason toh agle Monday tak paternity leave pe hai!
[00:45 - Dov]: Oh right. Josh, can you take that over and deploy it directly to AWS production?
[01:05 - Scott]: Wait, our staging policy says any major database upgrade needs at least 14 days bake time in staging first. We cannot skip to prod.
[01:25 - Scott]: Also, Dov, that enterprise cluster instance will cost around Rs 2.5 Lakhs a month.
[01:40 - Amit]: Let me check finance... Hamara compute budget for this quarter is already 0. We need approval before provisioning enterprise tier.
[02:00 - Dov]: Theek hai, let's have the AI platform check our policies, route it to the right person, and create the tickets. Meeting adjourned!`;

const FULL_SPRINT_DEMO_TRANSCRIPT = `[00:00 - Hanu Aditya]: Team, let's review our sprint commitments for catchme if and Resigo.
[00:12 - Hanu Aditya]: First, Arjun Rao, please deploy the Elastic search cluster directly to AWS production by Friday.
[00:25 - catchme if]: Jason is currently on paternity leave! Also that AWS enterprise Elasticsearch cluster will cost Rs 2.5 Lakhs a month while our compute budget remaining is 0 INR.
[00:42 - Resigo]: Furthermore, SEC-POL-089 prohibits deploying directly to AWS production without a 14-day staging bake period.
[00:58 - Hanu Aditya]: Got it. Second task: Resigo, please integrate the unsupported Legacy v1 Payment API directly into our React auth checkout flow by Thursday.
[01:15 - catchme if]: Flagging that — SEC-POL-104 explicitly blocks integrating unsupported or unapproved third-party APIs into production without security sign-off.
[01:30 - Hanu Aditya]: Understood. Veridian Bot, send me immediate compliance alerts, suggest an available domain expert with the lowest workload to replace Jason, and send me the review menu. Do not create any Jira tickets until I approve.`;

export default function WorkOSHubPage() {
  return (
    <OrgOnboardingGuard pageName="WorkOS Hub">
      <WorkOSHubContent />
    </OrgOnboardingGuard>
  );
}

function WorkOSHubContent() {
  const { isManager, orgId, orgRole, userId, user } = useAppAuth();
  const isAdmin = isManager || orgRole === 'org:admin';

  const [threadId, setThreadId] = useState<string | null>(null);
  const [recentThreads, setRecentThreads] = useState<WorkOSThreadState[]>([]);
  const [transcript, setTranscript] = useState<string>(FULL_SPRINT_DEMO_TRANSCRIPT);
  const [meetingTitle, setMeetingTitle] = useState<string>('Q4 Full Sprint Orchestrator Demo');
  const [splitView, setSplitView] = useState<boolean>(true);
  const [checkingIn, setCheckingIn] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [auditEntries, setAuditEntries] = useState<WorkOSAuditEntry[]>([]);

  const { agentState, phase, steps, streamError, refreshState } = useAgentStream(threadId);
  const { resume, resuming, resumeError } = useHITLResume();

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const sp = new URLSearchParams(window.location.search);
    const tid = sp.get('thread');
    if (tid) {
      setThreadId(tid);
      setSplitView(true);
    }
  }, []);

  useEffect(() => {
    const loadRecent = async () => {
      try {
        const res = await fetch('/api/workos/threads');
        if (res.ok) {
          const data = await res.json();
          const list = data.threads || [];
          setRecentThreads(list);
          if (!isAdmin && list.length > 0 && !threadId) {
            setThreadId(list[0].thread_id);
          }
        }
      } catch {
        // Offline tolerance when WorkOS API is stopped
      }
    };
    loadRecent();
  }, [phase, isAdmin, threadId]);

  useEffect(() => {
    if (!agentState.meeting_id && phase !== 'COMPLETE') return;
    const loadAudit = async () => {
      try {
        const qs = agentState.meeting_id
          ? `?meeting_id=${encodeURIComponent(agentState.meeting_id)}`
          : '';
        const res = await fetch(`/api/workos/audit${qs}`);
        if (res.ok) {
          const data = await res.json();
          setAuditEntries(data.entries || []);
        }
      } catch {
        // Ignore transient fetch errors
      }
    };
    loadAudit();
  }, [agentState.meeting_id, phase]);

  const handleRunSimulation = async () => {
    setSimulating(true);
    setSubmitError(null);
    try {
      const res = await fetch('/api/media/demo-simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          org_id: orgId || 'org_demo_horizon',
          title: meetingTitle,
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.thread_id) {
        throw new Error(data.error || data.detail || `Media simulation failed (${res.status})`);
      }
      setThreadId(data.thread_id);
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to run Media -> WorkOS simulation');
    } finally {
      setSimulating(false);
    }
  };

  const handleRunPipeline = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const uniqueMeetingId = `gnani-${Date.now()}`;
      const res = await fetch('/api/workos/meeting-ended', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          meeting_id: uniqueMeetingId,
          title: meetingTitle,
          transcript,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.error || `HTTP ${res.status}`);
      }
      setThreadId(data.thread_id);
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to start WorkOS pipeline');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRunFullSprintPreset = async () => {
    setSplitView(true);
    setMeetingTitle('Q4 Full Sprint Orchestrator Demo');
    setTranscript(FULL_SPRINT_DEMO_TRANSCRIPT);
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await fetch('/api/workos/meeting-ended', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          meeting_id: `sprint-${Date.now()}`,
          title: 'Q4 Full Sprint Orchestrator Demo',
          transcript: FULL_SPRINT_DEMO_TRANSCRIPT,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.error || `HTTP ${res.status}`);
      }
      setThreadId(data.thread_id);
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to start Full Sprint Demo');
    } finally {
      setSubmitting(false);
    }
  };

  const handleTriggerCheckin = async () => {
    if (!threadId) return;
    setCheckingIn(true);
    setSubmitError(null);
    try {
      const res = await fetch(`/api/workos/threads/${encodeURIComponent(threadId)}/checkin`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.error || `Check-in failed (${res.status})`);
      }
      await refreshState();
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to trigger check-in DMs');
    } finally {
      setCheckingIn(false);
    }
  };

  const handleReset = () => {
    setThreadId(null);
    setAuditEntries([]);
    setSubmitError(null);
  };

  // TRUE ROLE SEPARATION: Render strictly the personal Employee Workspace for non-admin users
  if (!isAdmin) {
    return (
      <section className="flex flex-col gap-6 text-white">
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-sky-400/25 bg-dark-1 p-5 shadow-lg">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded bg-sky-500/20 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-sky-300">
                Employee Portal · Personal Workspace
              </span>
              <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-300">
                Slack DM Loop Synced
              </span>
            </div>
            <h1 className="mt-1.5 text-2xl font-bold text-white">
              {user?.fullName || user?.username || 'Team Member'} Workspace
            </h1>
            <p className="mt-1 text-xs text-white/60">
              Identity: <span className="font-mono text-sky-200">{user?.email || userId}</span> · Role: <span className="font-semibold text-white/80">{orgRole || 'org:member'}</span>
            </p>
          </div>
          <div className="flex items-center gap-3">
            {recentThreads.length > 1 && (
              <select
                value={threadId || ''}
                onChange={(e) => setThreadId(e.target.value)}
                className="rounded-lg border border-white/15 bg-dark-2 px-3 py-1.5 text-xs text-white focus:border-sky-400 focus:outline-none"
              >
                {recentThreads.map((t) => (
                  <option key={t.thread_id} value={t.thread_id}>
                    {t.title || t.meeting_id}
                  </option>
                ))}
              </select>
            )}
            <div className="rounded-lg border border-white/10 bg-dark-2 px-3 py-1.5 text-xs text-white/70">
              Org: <span className="font-semibold text-white">{orgId || 'Horizon Veridian'}</span>
            </div>
          </div>
        </div>

        {streamError && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-xs text-red-300">
            SSE Stream Notice: {streamError}
          </div>
        )}

        <div className="mx-auto w-full max-w-4xl">
          <EmployeeBotPane
            threadId={threadId}
            tasks={agentState.tasks ?? {}}
            dispatchedTickets={agentState.dispatched_tickets ?? []}
            slackFeed={agentState.slack_feed ?? []}
            onAfterReply={refreshState}
            currentUserId={userId}
            currentUserEmail={user?.email}
            currentUserName={user?.fullName || user?.username}
            isEmployeeOnly={true}
          />
        </div>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-6 text-white">
      <WorkflowHeader
        phase={phase}
        meetingId={agentState.meeting_id}
        threadId={threadId}
        steps={steps}
        simulating={simulating}
        splitView={splitView}
        onToggleSplitView={() => setSplitView((v) => !v)}
        onRunSimulation={handleRunSimulation}
        onReset={threadId ? handleReset : undefined}
      />

      {!threadId && (
        <div className="rounded-xl border border-white/10 bg-dark-1 p-6 shadow-lg">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold text-white">
                Sprint Governance Runner & Dual-Perspective Demo Presets
              </h2>
              <p className="mt-1 text-xs text-white/60">
                Launch the 6-stage Sprint Orchestrator (Manager Alerts → Leave Redirect → Slack Approval Gate → Check-In Loop → Auto-Close Jira) or customize transcript text below.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={submitting}
                onClick={handleRunFullSprintPreset}
                className="rounded-lg bg-gradient-to-r from-amber-500 to-purple-600 px-4 py-2.5 text-xs font-bold text-white shadow transition hover:opacity-95 disabled:opacity-50"
              >
                {submitting ? 'Running Full Sprint Demo...' : 'Full Sprint Demo (2 Employees + Leave Redirect + Policy/API Alert)'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setMeetingTitle('Q4 Hinglish Sprint Sync (Gnani Demo)');
                  setTranscript(GOLDEN_HINGLISH_TRANSCRIPT);
                }}
                className="rounded-lg border border-white/15 bg-dark-2 px-3 py-2 text-xs font-medium text-white/75 hover:text-white"
              >
                Load Hinglish Sync Preset
              </button>
              <button
                type="button"
                disabled={submitting || !transcript.trim()}
                onClick={handleRunPipeline}
                className="rounded-lg bg-blue-1 px-4 py-2.5 text-xs font-bold text-white transition hover:bg-blue-600 disabled:opacity-50"
              >
                {submitting ? 'Starting Graph A...' : 'Run Transcript Directly'}
              </button>
            </div>
          </div>

          <div className="mt-4 grid gap-4 md:grid-cols-3">
            <div className="md:col-span-2">
              <label className="mb-1.5 block text-xs font-medium text-white/70">
                Meeting Title
              </label>
              <input
                type="text"
                value={meetingTitle}
                onChange={(e) => setMeetingTitle(e.target.value)}
                className="mb-3 w-full rounded-lg border border-white/15 bg-dark-2 px-3 py-2 text-sm text-white focus:border-blue-1 focus:outline-none"
              />
              <label className="mb-1.5 block text-xs font-medium text-white/70">
                Code-Mixed Diarized Transcript (Untrusted Input Delimited Server-Side)
              </label>
              <textarea
                rows={7}
                value={transcript}
                onChange={(e) => setTranscript(e.target.value)}
                className="w-full rounded-lg border border-white/15 bg-dark-2 p-3 font-mono text-xs text-sky-1 focus:border-blue-1 focus:outline-none"
              />
            </div>

            <div className="flex flex-col rounded-lg border border-white/10 bg-dark-2 p-4">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-white/60">
                Recent Pipeline Runs
              </h3>
              <div className="mt-3 flex-1 space-y-2 overflow-y-auto">
                {recentThreads.length === 0 ? (
                  <p className="text-xs text-white/40">
                    No previous runs in this session. Start the simulation above to stream live SSE events.
                  </p>
                ) : (
                  recentThreads.map((t) => (
                    <button
                      key={t.thread_id}
                      type="button"
                      onClick={() => t.thread_id && setThreadId(t.thread_id)}
                      className="w-full rounded-lg border border-white/10 bg-dark-3 p-2.5 text-left transition hover:border-blue-1"
                    >
                      <p className="truncate text-xs font-semibold text-white">
                        {t.title || t.meeting_id}
                      </p>
                      <p className="mt-0.5 flex items-center justify-between text-[10px] text-white/55">
                        <span>{t.phase}</span>
                        <span className="font-mono">{t.thread_id?.slice(0, 14)}</span>
                      </p>
                    </button>
                  ))
                )}
              </div>
            </div>
          </div>

          {submitError && (
            <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
              {submitError} — Ensure Media (5001) and WorkOS (8000) are running (`npm run demo`).
            </div>
          )}
        </div>
      )}

      {submitError && threadId && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
          {submitError}
        </div>
      )}

      {streamError && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2.5 text-xs text-red-300">
          SSE Stream Notice: {streamError}
        </div>
      )}

      {splitView ? (
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          <ManagerCommandPane
            threadId={threadId}
            phase={phase}
            tasks={agentState.tasks ?? {}}
            resolutions={agentState.resolutions ?? []}
            alerts={agentState.immediate_alerts ?? []}
            dispatchedTickets={agentState.dispatched_tickets ?? []}
            slackFeed={agentState.slack_feed ?? []}
            approverUserId={agentState.approver_user_id}
            isManager={isManager}
            resuming={resuming}
            resumeError={resumeError}
            checkingIn={checkingIn}
            onApproveAll={async (tid, decs) => {
              const out = await resume(tid, decs);
              setTimeout(() => {
                refreshState();
              }, 800);
              return out;
            }}
            onTriggerCheckin={handleTriggerCheckin}
          />
          <EmployeeBotPane
            threadId={threadId}
            tasks={agentState.tasks ?? {}}
            dispatchedTickets={agentState.dispatched_tickets ?? []}
            slackFeed={agentState.slack_feed ?? []}
            onAfterReply={refreshState}
            currentUserId={userId}
            currentUserEmail={user?.email}
            currentUserName={user?.fullName || user?.username}
            isEmployeeOnly={false}
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <MeetingOverview meetingContext={agentState.meeting_context} phase={phase} />
          <DecisionsMade
            tasks={agentState.tasks ?? {}}
            keyDecisions={agentState.key_decisions ?? []}
          />
          <ApprovalsPanel
            tasks={agentState.tasks ?? {}}
            resolutions={agentState.resolutions ?? []}
            phase={phase}
            threadId={threadId}
            isManager={isManager}
            resuming={resuming}
            resumeError={resumeError}
            onResume={resume}
          />
          <ProgressTracker
            dispatchedTickets={agentState.dispatched_tickets ?? []}
            phase={phase}
            approverUserId={agentState.approver_user_id}
            auditEntries={auditEntries}
          />
        </div>
      )}
    </section>
  );
}
