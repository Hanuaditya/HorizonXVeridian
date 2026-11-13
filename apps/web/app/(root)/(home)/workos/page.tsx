'use client';

import React, { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { OrgOnboardingGuard, useAppAuth } from '@/providers/AuthBridge';
import { useAgentStream, useHITLResume } from '@/lib/sse';
import type { WorkOSAuditEntry, WorkOSDispatchedTicket, WorkOSTask, WorkOSThreadState } from '@/lib/workos-types';
import WorkflowHeader from '@/components/workos/WorkflowHeader';
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileAudio,
  FolderGit2,
  HelpCircle,
  MessageSquare,
  Mic,
  Play,
  RefreshCw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Ticket,
  UploadCloud,
  User,
  Users,
  X,
  Zap,
} from 'lucide-react';
import { cn } from '@/lib/utils';

const GOLDEN_HINGLISH_TRANSCRIPT = `[00:00 - Dov]: Team, welcome. We have three main items today.
[00:15 - Dov]: First, Arjun, please deploy the Elastic search cluster directly to production by Thursday.
[00:30 - Amit]: Par Dov bhai, Arjun toh agle Monday tak paternity leave pe hai!
[00:45 - Dov]: Oh right. Josh, can you take that over and deploy it directly to AWS production?
[01:05 - Scott]: Wait, our staging policy says any major database upgrade needs at least 14 days bake time in staging first. We cannot skip to prod.
[01:25 - Scott]: Also, Dov, that enterprise cluster instance will cost around Rs 2.5 Lakhs a month.
[01:40 - Amit]: Let me check finance... Hamara compute budget for this quarter is already 0. We need approval before provisioning enterprise tier.
[02:00 - Dov]: Theek hai, let's have the AI platform check our policies, route it to the right person, and create the tickets. Meeting adjourned!`;

const FULL_SPRINT_DEMO_TRANSCRIPT = `[00:00 - Aarav Sharma]: Team, let's review our sprint commitments for Rohan Patel and Priya Sen.
[00:12 - Aarav Sharma]: First, Arjun Rao, please deploy the Elastic search cluster directly to AWS production by Friday.
[00:25 - Rohan Patel]: Arjun is currently on paternity leave! Also that AWS enterprise Elasticsearch cluster will cost Rs 2.5 Lakhs a month while our compute budget remaining is 0 INR.
[00:42 - Priya Sen]: Furthermore, SEC-POL-089 prohibits deploying directly to AWS production without a 14-day staging bake period.
[00:58 - Aarav Sharma]: Got it. Second task: Priya Sen, please integrate the unsupported Legacy v1 Payment API directly into our React auth checkout flow by Thursday.
[01:15 - Rohan Patel]: Flagging that — SEC-POL-104 explicitly blocks integrating unsupported or unapproved third-party APIs into production without security sign-off.
[01:30 - Aarav Sharma]: Understood. Veridian Bot, send me immediate compliance alerts, suggest an available domain expert with the lowest workload to replace Arjun, and send me the review menu. Do not create any Jira tickets until I approve.`;

export default function WorkOSHubPage() {
  return (
    <OrgOnboardingGuard pageName="Sprint Governance Workspace">
      <WorkOSContent />
    </OrgOnboardingGuard>
  );
}

function WorkOSContent() {
  const { isManager, orgId, orgRole, userId, user } = useAppAuth();
  const isAdmin = isManager || orgRole === 'org:admin';

  const [threadId, setThreadId] = useState<string | null>(null);
  const [recentThreads, setRecentThreads] = useState<WorkOSThreadState[]>([]);
  const [transcript, setTranscript] = useState<string>(FULL_SPRINT_DEMO_TRANSCRIPT);
  const [meetingTitle, setMeetingTitle] = useState<string>('Q4 Full Sprint Orchestrator Demo');
  const [submitting, setSubmitting] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showIngestModal, setShowIngestModal] = useState(false);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [confirmingTaskId, setConfirmingTaskId] = useState<string | null>(null);
  const [rejectingTaskId, setRejectingTaskId] = useState<string | null>(null);

  const { agentState, phase, refreshState } = useAgentStream(threadId);
  const { resume, resuming, resumeError } = useHITLResume();

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const sp = new URLSearchParams(window.location.search);
    const tid = sp.get('thread');
    if (tid) setThreadId(tid);
  }, []);

  useEffect(() => {
    const loadRecent = async () => {
      try {
        const res = await fetch('/api/workos/threads');
        if (res.ok) {
          const data = await res.json();
          const list: WorkOSThreadState[] = data.threads || [];
          setRecentThreads(list);
          if (list.length > 0 && !threadId && list[0].thread_id) {
            setThreadId(list[0].thread_id);
          }
        }
      } catch {
        // Offline tolerance
      }
    };
    loadRecent();
  }, [phase, threadId]);

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
      setShowIngestModal(false);
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
      const uniqueMeetingId = `mtg-${Date.now()}`;
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
      setShowIngestModal(false);
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to start WorkOS pipeline');
    } finally {
      setSubmitting(false);
    }
  };

  const handleApproveAll = async () => {
    if (!threadId) return;
    const taskList = Object.values(agentState.tasks || {});
    const decisions: Record<string, string> = {};
    taskList.forEach((t) => {
      decisions[t.task_id] = overrides[t.task_id] ?? t.resolution_action ?? 'PROCEED';
    });
    await resume(threadId, decisions);
    setTimeout(() => {
      refreshState();
    }, 800);
  };

  const handleManagerConfirmDone = async (taskId: string) => {
    if (!threadId) return;
    setConfirmingTaskId(taskId);
    try {
      const res = await fetch(`/api/workos/threads/${encodeURIComponent(threadId)}/tasks/${encodeURIComponent(taskId)}/confirm-done`, {
        method: 'POST',
      });
      if (res.ok) {
        await refreshState();
      }
    } catch {
      // Ignore
    } finally {
      setConfirmingTaskId(null);
    }
  };

  const handleManagerRejectDone = async (taskId: string) => {
    if (!threadId) return;
    setRejectingTaskId(taskId);
    try {
      const res = await fetch(`/api/workos/threads/${encodeURIComponent(threadId)}/tasks/${encodeURIComponent(taskId)}/reject-done`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Additional test coverage required before Done closure' }),
      });
      if (res.ok) {
        await refreshState();
      }
    } catch {
      // Ignore
    } finally {
      setRejectingTaskId(null);
    }
  };

  const handleReset = () => {
    setThreadId(null);
    setSubmitError(null);
  };

  // Metrics Calculation
  const tasksList = useMemo(() => Object.values(agentState.tasks || {}), [agentState.tasks]);
  const dispatchedTickets = useMemo(() => agentState.dispatched_tickets || [], [agentState.dispatched_tickets]);
  const isApproved = dispatchedTickets.length > 0;

  const pendingReviewCount = isApproved
    ? 0
    : tasksList.filter((t) => t.status !== 'DEFERRED' && t.status !== 'CANCELLED').length;

  const policyFlagsCount = useMemo(() => {
    let count = 0;
    tasksList.forEach((t) => {
      if (t.finance_flag) count++;
      if (t.security_flag) count++;
      if (t.leave_recommendation || t.rerouted_assignee || (t.hr_status || '').toLowerCase().includes('leave')) count++;
    });
    return count;
  }, [tasksList]);

  const activeTicketsCount = dispatchedTickets.length;

  const sprintCompletionPct = useMemo(() => {
    if (dispatchedTickets.length === 0) return 0;
    const total = dispatchedTickets.reduce((acc, dt) => acc + (dt.progress_pct || 0), 0);
    return Math.round(total / dispatchedTickets.length);
  }, [dispatchedTickets]);

  // Employee-only filter: Match dynamic identity
  const employeeTasks = useMemo(() => {
    if (isAdmin) return [];
    const myName = (user?.fullName || user?.username || '').toLowerCase();
    const myEmail = (user?.email || '').toLowerCase();
    const myUid = (userId || '').toLowerCase();

    return dispatchedTickets.length > 0
      ? dispatchedTickets.filter((dt) => {
          const a = (dt.assignee || '').toLowerCase();
          if (myName && (a.includes(myName) || myName.includes(a))) return true;
          if (myEmail && a.includes(myEmail.split('@')[0])) return true;
          return false;
        })
      : tasksList.filter((t) => {
          const a = (t.rerouted_assignee || t.assignee || '').toLowerCase();
          if (myName && (a.includes(myName) || myName.includes(a))) return true;
          if (myEmail && a.includes(myEmail.split('@')[0])) return true;
          return false;
        });
  }, [isAdmin, dispatchedTickets, tasksList, user, userId]);

  return (
    <div className="flex flex-col gap-6 text-white pb-12">
      {/* 1. Header Bar */}
      <WorkflowHeader
        phase={phase}
        meetingId={agentState.meeting_id}
        threadId={threadId}
        onOpenIngestModal={() => setShowIngestModal(true)}
        onReset={threadId ? handleReset : undefined}
        isManager={isAdmin}
      />

      {/* 2. Ingest Modal / Slide-over */}
      {showIngestModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
          <div className="relative w-full max-w-2xl rounded-2xl border border-white/[0.07] bg-dark-1 p-6 shadow-2xl">
            <button
              type="button"
              onClick={() => setShowIngestModal(false)}
              className="absolute right-4 top-4 rounded-lg p-1.5 text-white/50 hover:bg-white/[0.08] hover:text-white"
            >
              <X className="size-4" />
            </button>

            <div className="flex items-center gap-2.5 mb-4">
              <div className="flex size-9 items-center justify-center rounded-xl bg-blue-600/20 text-blue-400">
                <Play className="size-4 fill-current" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Ingest Meeting Transcript</h3>
                <p className="text-xs text-white/50">Run through Gnani Prisma & Sovereign Governance</p>
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-xs font-semibold text-white/70">Meeting Title</label>
                <input
                  type="text"
                  value={meetingTitle}
                  onChange={(e) => setMeetingTitle(e.target.value)}
                  className="w-full rounded-xl border border-white/[0.07] bg-dark-3/60 px-3.5 py-2 text-xs text-white focus:border-blue-1 focus:outline-none"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-white/70">
                    Diarized Code-Mixed Transcript (Untrusted Input)
                  </label>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setMeetingTitle('Q4 Full Sprint Orchestrator Demo');
                        setTranscript(FULL_SPRINT_DEMO_TRANSCRIPT);
                      }}
                      className="text-[11px] text-blue-400 hover:underline"
                    >
                      Sprint Demo Preset
                    </button>
                    <span className="text-white/20">·</span>
                    <button
                      type="button"
                      onClick={() => {
                        setMeetingTitle('Q4 Hinglish Sync (Gnani Demo)');
                        setTranscript(GOLDEN_HINGLISH_TRANSCRIPT);
                      }}
                      className="text-[11px] text-purple-400 hover:underline"
                    >
                      Hinglish Sync Preset
                    </button>
                  </div>
                </div>
                <textarea
                  rows={8}
                  value={transcript}
                  onChange={(e) => setTranscript(e.target.value)}
                  className="w-full rounded-xl border border-white/[0.07] bg-dark-3/60 p-3 font-mono text-xs text-sky-200 focus:border-blue-1 focus:outline-none"
                />
              </div>

              <div className="flex items-center justify-between border-t border-white/[0.08] pt-4">
                <button
                  type="button"
                  disabled={simulating}
                  onClick={handleRunSimulation}
                  className="flex items-center gap-2 rounded-xl border border-purple-500/30 bg-purple-500/10 px-3.5 py-2 text-xs font-semibold text-purple-200 transition hover:bg-purple-500/20 disabled:opacity-50"
                >
                  <Mic className="size-3.5 text-purple-400" />
                  <span>{simulating ? 'Simulating Audio...' : 'Run Gnani Audio Simulation'}</span>
                </button>

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setShowIngestModal(false)}
                    className="rounded-xl border border-white/[0.1] px-4 py-2 text-xs font-medium text-white/70 hover:bg-white/[0.05]"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={submitting || !transcript.trim()}
                    onClick={handleRunPipeline}
                    className="flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow transition hover:bg-blue-500 disabled:opacity-50"
                  >
                    <span>{submitting ? 'Starting...' : 'Run Pipeline'}</span>
                    <ArrowRight className="size-3.5" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 3. Role-Based Views */}
      {isAdmin ? (
        // =========================================================================
        // MANAGER VIEW (org:admin): Sprint Governance & Execution Board
        // =========================================================================
        <div className="space-y-6">
          {/* KPI Summary Strip (4 Cards) */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <div className="rounded-2xl border border-white/[0.07] bg-dark-1 p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-white/50">Pending Review</span>
                <Clock className="size-4 text-amber-400" />
              </div>
              <p className="mt-2 font-mono text-2xl font-bold tabular-nums text-white">
                {pendingReviewCount}
              </p>
              <p className="mt-1 text-[11px] text-white/40">
                {isApproved ? 'All gates cleared' : 'Awaiting your sign-off'}
              </p>
            </div>

            <div className="rounded-2xl border border-white/[0.07] bg-dark-1 p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-white/50">Policy / Leave Flags</span>
                <ShieldAlert className="size-4 text-rose-400" />
              </div>
              <p className="mt-2 font-mono text-2xl font-bold tabular-nums text-rose-300">
                {policyFlagsCount}
              </p>
              <p className="mt-1 text-[11px] text-white/40">
                {policyFlagsCount > 0 ? 'Firewall alerts triggered' : 'All policies compliant'}
              </p>
            </div>

            <div className="rounded-2xl border border-white/[0.07] bg-dark-1 p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-white/50">Active Jira Tickets</span>
                <Ticket className="size-4 text-sky-400" />
              </div>
              <p className="mt-2 font-mono text-2xl font-bold tabular-nums text-sky-300">
                {activeTicketsCount}
              </p>
              <p className="mt-1 text-[11px] text-white/40">
                {!isApproved ? '0 tickets before approval' : 'Provisioned in Jira'}
              </p>
            </div>

            <div className="rounded-2xl border border-white/[0.07] bg-dark-1 p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-white/50">Sprint Completion</span>
                <CheckCircle2 className="size-4 text-emerald-400" />
              </div>
              <p className="mt-2 font-mono text-2xl font-bold tabular-nums text-emerald-300">
                {sprintCompletionPct}%
              </p>
              <div className="mt-2 h-1.5 w-full rounded-full bg-white/10 overflow-hidden">
                <div
                  className="h-full bg-emerald-500 transition-all duration-300"
                  style={{ width: `${sprintCompletionPct}%` }}
                />
              </div>
            </div>
          </div>

          {/* Governance Approval Queue (Pre-Approval Gate) */}
          {!isApproved && tasksList.length > 0 && (
            <div className="rounded-2xl border border-amber-500/30 bg-dark-1 p-5 shadow-xl">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.07] pb-4">
                <div className="flex items-center gap-2.5">
                  <div className="flex size-7 items-center justify-center rounded-lg bg-amber-500/20 text-amber-300">
                    <Shield className="size-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-white">Governance Approval Queue</h3>
                    <p className="text-xs text-amber-300/80">
                      Governance Gate Active — 0 Jira tickets exist until you approve.
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  disabled={resuming || !threadId}
                  onClick={handleApproveAll}
                  className="flex items-center gap-2 rounded-xl bg-amber-500 px-5 py-2.5 text-xs font-bold text-black shadow-lg transition hover:bg-amber-400 disabled:opacity-50"
                >
                  {resuming ? (
                    <RefreshCw className="size-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="size-4" />
                  )}
                  <span>Approve & Create Tickets</span>
                </button>
              </div>

              {resumeError && (
                <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 p-2.5 text-xs text-red-300">
                  Approval Error: {resumeError}
                </div>
              )}

              <div className="mt-4 space-y-3">
                {tasksList.map((task) => {
                  const isLeaveConflict = Boolean(task.leave_recommendation || task.rerouted_assignee || (task.hr_status || '').toLowerCase().includes('leave'));
                  const hasSecFlag = Boolean(task.security_flag);
                  const hasFinFlag = Boolean(task.finance_flag);
                  const currentDecision = overrides[task.task_id] ?? task.resolution_action ?? 'PROCEED';

                  return (
                    <div
                      key={task.task_id}
                      className="rounded-xl border border-white/[0.07] bg-dark-3/60 p-4 text-xs"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="flex-1 min-w-[280px]">
                          <div className="flex flex-wrap items-center gap-2 mb-1.5">
                            <span className="font-mono font-bold text-white/50">{task.task_id}</span>
                            <span className="font-semibold text-white text-sm">{task.title}</span>

                            {isLeaveConflict && (
                              <span className="rounded bg-amber-500/15 border border-amber-500/30 px-2 py-0.5 text-[10px] font-semibold text-amber-300">
                                Smart Leave Redirection: {task.rerouted_assignee || task.assignee}
                              </span>
                            )}

                            {hasSecFlag && (
                              <span className="rounded bg-rose-500/15 border border-rose-500/30 px-2 py-0.5 text-[10px] font-semibold text-rose-300">
                                {task.security_flag}
                              </span>
                            )}

                            {hasFinFlag && (
                              <span className="rounded bg-rose-500/15 border border-rose-500/30 px-2 py-0.5 text-[10px] font-semibold text-rose-300">
                                Finance: Over Budget
                              </span>
                            )}
                          </div>

                          {task.transcript_quote && (
                            <p className="mt-1 font-mono text-[11px] text-white/50 italic bg-dark-2 p-2 rounded-lg border border-white/[0.04]">
                              {`"${task.transcript_quote}"`}
                            </p>
                          )}

                          <div className="mt-2.5 flex items-center gap-2 text-[11px] text-white/60">
                            <User className="size-3.5 text-blue-400" />
                            <span>
                              Assignee:{' '}
                              <strong className="text-white">
                                {task.rerouted_assignee || task.assignee}
                              </strong>
                            </span>
                            {isLeaveConflict && (
                              <span className="text-white/40">
                                (Reassigned from {task.assignee} due to paternity/medical leave)
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Segmented Decision Control */}
                        <div className="flex rounded-lg border border-white/[0.07] bg-dark-2 p-1">
                          {['PROCEED', 'REROUTE', 'DEFER'].map((act) => (
                            <button
                              key={act}
                              type="button"
                              onClick={() => setOverrides((prev) => ({ ...prev, [task.task_id]: act }))}
                              className={cn(
                                'rounded px-2.5 py-1 text-[10px] font-semibold transition',
                                currentDecision === act
                                  ? 'bg-blue-1 text-white shadow-sm'
                                  : 'text-white/50 hover:text-white'
                              )}
                            >
                              {act}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Live Jira Sprint Board (Post-Approval) */}
          <div className="rounded-2xl border border-white/[0.07] bg-dark-1 p-5 shadow-xl">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.07] pb-4">
              <div className="flex items-center gap-2.5">
                <div className="flex size-7 items-center justify-center rounded-lg bg-sky-500/20 text-sky-300">
                  <Ticket className="size-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Live Jira Sprint Board</h3>
                  <p className="text-xs text-white/50">
                    Real-time ticket statuses, automated closure & Slack verification
                  </p>
                </div>
              </div>

              <Link
                href="/messages"
                className="flex items-center gap-1.5 rounded-xl border border-white/[0.07] bg-dark-3/70 px-3.5 py-2 text-xs font-semibold text-white/80 transition hover:bg-white/[0.08] hover:text-white"
              >
                <MessageSquare className="size-3.5 text-blue-400" />
                <span>Open in Messages Workspace →</span>
              </Link>
            </div>

            <div className="mt-4">
              {dispatchedTickets.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-8 text-center border border-dashed border-white/[0.07] rounded-xl">
                  <div className="flex size-10 items-center justify-center rounded-xl bg-white/[0.04] text-white/30 mb-2">
                    <Ticket className="size-5" />
                  </div>
                  <h4 className="text-xs font-semibold text-white/70">No tickets provisioned yet</h4>
                  <p className="mt-1 text-[11px] text-white/40 max-w-sm">
                    Review and approve the governance queue above to create live Jira tickets and notify engineers on Slack.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {dispatchedTickets.map((t) => {
                    const isDone = (t.jira_status || '').toLowerCase() === 'done';
                    const isInReview = (t.jira_status || '').toLowerCase() === 'in review';

                    return (
                      <div
                        key={t.jira_key || t.task_id}
                        className="rounded-xl border border-white/[0.07] bg-dark-3/60 p-4 text-xs transition hover:border-white/[0.15]"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <span className="font-mono text-xs font-bold text-sky-400">
                              {t.jira_key}
                            </span>
                            <span className="text-sm font-semibold text-white">{t.title}</span>
                            <span
                              className={cn(
                                'rounded px-2 py-0.5 text-[10px] font-bold uppercase',
                                isDone
                                  ? 'bg-emerald-500/20 text-emerald-300'
                                  : isInReview
                                  ? 'bg-amber-500/20 text-amber-300'
                                  : 'bg-white/10 text-white/70'
                              )}
                            >
                              {t.jira_status || 'To Do'}
                            </span>
                          </div>

                          <div className="flex items-center gap-2">
                            {t.jira_url && (
                              <a
                                href={t.jira_url}
                                target="_blank"
                                rel="noreferrer"
                                className="flex items-center gap-1 rounded-lg border border-sky-400/20 bg-sky-500/10 px-2.5 py-1 text-[11px] text-sky-300 hover:bg-sky-500/20"
                              >
                                <span>View in Jira</span>
                                <ExternalLink className="size-3" />
                              </a>
                            )}
                            <Link
                              href="/messages"
                              className="flex items-center gap-1 rounded-lg border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-[11px] text-white/70 hover:bg-white/[0.08] hover:text-white"
                            >
                              <span>Open DM →</span>
                            </Link>
                          </div>
                        </div>

                        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] pt-2.5">
                          <div className="flex items-center gap-4 text-[11px] text-white/50">
                            <span>
                              Assignee: <strong className="text-white/80">{t.assignee}</strong>
                            </span>
                            <span>·</span>
                            <span>Progress: <strong className="font-mono text-white/80">{t.progress_pct || 0}%</strong></span>
                          </div>

                          {/* Manager Review Controls for In Review items */}
                          {isInReview && (
                            <div className="flex items-center gap-2">
                              <span className="text-[11px] text-amber-300 font-medium">
                                Employee submitted completion without evidence link:
                              </span>
                              <button
                                type="button"
                                disabled={confirmingTaskId === t.task_id}
                                onClick={() => handleManagerConfirmDone(t.task_id)}
                                className="rounded-lg bg-emerald-600 px-2.5 py-1 text-[10px] font-bold text-white shadow hover:bg-emerald-500"
                              >
                                {confirmingTaskId === t.task_id ? 'Confirming...' : 'Confirm Done'}
                              </button>
                              <button
                                type="button"
                                disabled={rejectingTaskId === t.task_id}
                                onClick={() => handleManagerRejectDone(t.task_id)}
                                className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-2.5 py-1 text-[10px] font-semibold text-rose-300 hover:bg-rose-500/20"
                              >
                                {rejectingTaskId === t.task_id ? 'Rejecting...' : 'Request Rework'}
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        // =========================================================================
        // EMPLOYEE VIEW (org:member): My Sprint Workspace
        // =========================================================================
        <div className="space-y-6">
          <div className="rounded-2xl border border-sky-500/25 bg-dark-1 p-5 shadow-xl">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.07] pb-4">
              <div>
                <span className="rounded bg-sky-500/20 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-sky-300">
                  Employee Portal · My Sprint Workspace
                </span>
                <h2 className="mt-1.5 text-xl font-bold text-white">
                  {user?.fullName || user?.username || 'Team Member'}
                </h2>
                <p className="mt-0.5 text-xs text-white/60">
                  Assigned tickets and check-in updates for the current sprint
                </p>
              </div>

              <Link
                href="/messages"
                className="flex items-center gap-2 rounded-xl bg-blue-1 px-4 py-2 text-xs font-semibold text-white shadow transition hover:bg-blue-1/90"
              >
                <Bot className="size-4" />
                <span>Open Veridian Bot in Messages →</span>
              </Link>
            </div>

            <div className="mt-4">
              {employeeTasks.length === 0 ? (
                <div className="p-8 text-center border border-dashed border-white/[0.07] rounded-xl">
                  <CheckCircle2 className="size-8 mx-auto text-emerald-400/60 mb-2" />
                  <h4 className="text-sm font-semibold text-white">No active sprint tickets</h4>
                  <p className="mt-1 text-xs text-white/40 max-w-sm mx-auto">
                    You have no outstanding Jira tickets in this sprint run. If you received a Slack DM from Veridian Bot, open the Messages tab to reply.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {employeeTasks.map((task: any) => {
                    const ticketKey = task.jira_key || task.jira_ticket_id || task.task_id;
                    const isDone = (task.jira_status || task.status || '').toLowerCase() === 'done';

                    return (
                      <div
                        key={ticketKey}
                        className="rounded-xl border border-white/[0.07] bg-dark-3/60 p-4 text-xs"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2.5">
                            <span className="font-mono text-sm font-bold text-sky-300">
                              {ticketKey}
                            </span>
                            <span className="text-sm font-semibold text-white">{task.title}</span>
                            <span
                              className={cn(
                                'rounded px-2 py-0.5 text-[10px] font-bold uppercase',
                                isDone
                                  ? 'bg-emerald-500/20 text-emerald-300'
                                  : 'bg-white/10 text-white/70'
                              )}
                            >
                              {task.jira_status || task.status || 'To Do'}
                            </span>
                          </div>

                          {task.jira_url && (
                            <a
                              href={task.jira_url}
                              target="_blank"
                              rel="noreferrer"
                              className="flex items-center gap-1 rounded-lg border border-sky-400/20 bg-sky-500/10 px-2.5 py-1 text-xs text-sky-300 hover:bg-sky-500/20"
                            >
                              <span>View in Jira</span>
                              <ExternalLink className="size-3" />
                            </a>
                          )}
                        </div>

                        <div className="mt-3">
                          <div className="flex items-center justify-between text-[11px] text-white/50 mb-1">
                            <span>Completion Progress</span>
                            <span className="font-mono text-white/80">{task.progress_pct || 0}%</span>
                          </div>
                          <div className="h-2 w-full rounded-full bg-white/10 overflow-hidden">
                            <div
                              className="h-full bg-emerald-500 transition-all duration-300"
                              style={{ width: `${task.progress_pct || 0}%` }}
                            />
                          </div>
                        </div>

                        <div className="mt-3 flex items-center justify-between border-t border-white/[0.06] pt-2.5 text-[11px] text-white/50">
                          <span>
                            Resource Type: <strong className="text-white/80">{task.resource_type || 'Feature'}</strong>
                          </span>
                          <Link
                            href="/messages"
                            className="text-blue-400 hover:underline flex items-center gap-1"
                          >
                            <span>Reply to interval check-in</span>
                            <ArrowRight className="size-3" />
                          </Link>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
