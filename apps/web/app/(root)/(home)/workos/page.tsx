'use client';

import React, { useEffect, useState } from 'react';
import { useAppAuth } from '@/providers/AuthBridge';
import { useAgentStream, useHITLResume } from '@/lib/sse';
import type { WorkOSAuditEntry, WorkOSThreadState } from '@/lib/workos-types';
import WorkflowHeader from '@/components/workos/WorkflowHeader';
import MeetingOverview from '@/components/workos/MeetingOverview';
import DecisionsMade from '@/components/workos/DecisionsMade';
import ApprovalsPanel from '@/components/workos/ApprovalsPanel';
import ProgressTracker from '@/components/workos/ProgressTracker';

const GOLDEN_HINGLISH_TRANSCRIPT = `[00:00 - Dov]: Team, welcome. We have three main items today.
[00:15 - Dov]: First, Jason, please deploy the Elastic search cluster directly to production by Thursday.
[00:30 - Amit]: Par Dov bhai, Jason toh agle Monday tak paternity leave pe hai!
[00:45 - Dov]: Oh right. Josh, can you take that over and deploy it directly to AWS production?
[01:05 - Scott]: Wait, our staging policy says any major database upgrade needs at least 14 days bake time in staging first. We cannot skip to prod.
[01:25 - Scott]: Also, Dov, that enterprise cluster instance will cost around Rs 2.5 Lakhs a month.
[01:40 - Amit]: Let me check finance... Hamara compute budget for this quarter is already 0. We need approval before provisioning enterprise tier.
[02:00 - Dov]: Theek hai, let's have the AI platform check our policies, route it to the right person, and create the tickets. Meeting adjourned!`;

export default function WorkOSHubPage() {
  const { isManager, orgId } = useAppAuth();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [recentThreads, setRecentThreads] = useState<WorkOSThreadState[]>([]);
  const [transcript, setTranscript] = useState<string>(GOLDEN_HINGLISH_TRANSCRIPT);
  const [meetingTitle, setMeetingTitle] = useState<string>('Q4 Hinglish Sprint Sync (Gnani Demo)');
  const [submitting, setSubmitting] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [auditEntries, setAuditEntries] = useState<WorkOSAuditEntry[]>([]);

  const { agentState, phase, steps, streamError } = useAgentStream(threadId);
  const { resume, resuming, resumeError } = useHITLResume();

  useEffect(() => {
    const loadRecent = async () => {
      try {
        const res = await fetch('/api/workos/threads');
        if (res.ok) {
          const data = await res.json();
          setRecentThreads(data.threads || []);
        }
      } catch {
        // Offline tolerance when WorkOS API is stopped
      }
    };
    loadRecent();
  }, [phase]);

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

  const handleReset = () => {
    setThreadId(null);
    setAuditEntries([]);
    setSubmitError(null);
  };

  return (
    <section className="flex flex-col gap-6 text-white">
      <WorkflowHeader
        phase={phase}
        meetingId={agentState.meeting_id}
        threadId={threadId}
        steps={steps}
        simulating={simulating}
        onRunSimulation={handleRunSimulation}
        onReset={threadId ? handleReset : undefined}
      />

      {!threadId && (
        <div className="rounded-xl border border-white/10 bg-dark-1 p-6 shadow-lg">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold text-white">
                Custom Transcript Runner & Golden Hinglish Scenario
              </h2>
              <p className="mt-1 text-xs text-white/60">
                Click <span className="font-semibold text-purple-300">▶ Run Hinglish Demo Simulation</span>{' '}
                above to trigger the full Media (5001) → Signed `meeting.ended` → WorkOS (8000) SSE
                pipeline, or submit custom text below.
              </p>
            </div>
            <button
              type="button"
              disabled={submitting || !transcript.trim()}
              onClick={handleRunPipeline}
              className="rounded-lg bg-blue-1 px-5 py-2.5 text-sm font-bold text-white transition hover:bg-blue-600 disabled:opacity-50"
            >
              {submitting ? 'Starting Graph A...' : 'Run Transcript Directly'}
            </button>
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
    </section>
  );
}
