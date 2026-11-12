'use client';

import React, { useMemo, useState } from 'react';
import type {
  WorkOSComplianceAlert,
  WorkOSDispatchedTicket,
  WorkOSPhase,
  WorkOSResolution,
  WorkOSSlackMessage,
  WorkOSTask,
} from '@/lib/workos-types';

interface ManagerCommandPaneProps {
  threadId: string | null;
  phase: WorkOSPhase;
  tasks: Record<string, WorkOSTask>;
  resolutions: WorkOSResolution[];
  alerts: WorkOSComplianceAlert[];
  dispatchedTickets: WorkOSDispatchedTicket[];
  slackFeed: WorkOSSlackMessage[];
  approverUserId?: string | null;
  isManager: boolean;
  resuming: boolean;
  resumeError: string | null;
  checkingIn: boolean;
  onApproveAll: (threadId: string, decisions: Record<string, string>) => Promise<unknown>;
  onTriggerCheckin: () => Promise<void>;
}

const ACTION_OPTIONS = [
  { value: 'REROUTE', label: 'Reroute' },
  { value: 'REFRAME', label: 'Reframe' },
  { value: 'DEFER', label: 'Defer' },
  { value: 'PROCEED', label: 'Proceed' },
];

export default function ManagerCommandPane({
  threadId,
  phase,
  tasks,
  resolutions,
  alerts,
  dispatchedTickets,
  slackFeed,
  approverUserId,
  isManager,
  resuming,
  resumeError,
  checkingIn,
  onApproveAll,
  onTriggerCheckin,
}: ManagerCommandPaneProps) {
  const [overrides, setOverrides] = useState<Record<string, string>>({});

  const taskList = useMemo(() => Object.values(tasks || {}), [tasks]);
  const resMap = useMemo(() => {
    const m: Record<string, WorkOSResolution> = {};
    (resolutions || []).forEach((r) => {
      m[r.task_id] = r;
    });
    return m;
  }, [resolutions]);

  const managerFeed = useMemo(
    () => (slackFeed || []).filter((m) => m.role === 'manager'),
    [slackFeed]
  );

  const isHITL = phase === 'HITL';
  const hasOpenTickets = dispatchedTickets.some(
    (t) => (t.jira_status || 'To Do').toLowerCase() !== 'done'
  );

  const handleApproveClick = async () => {
    if (!threadId) return;
    const decisions: Record<string, string> = {};
    taskList.forEach((t) => {
      const suggested = resMap[t.task_id]?.suggested_action ?? t.resolution_action ?? 'PROCEED';
      decisions[t.task_id] = overrides[t.task_id] ?? suggested;
    });
    await onApproveAll(threadId, decisions);
  };

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-amber-400/25 bg-dark-1 p-5 text-white shadow-lg">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3">
        <div>
          <span className="rounded bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300">
            Left Pane · Manager Command & Slack DM View
          </span>
          <h2 className="mt-1 text-base font-bold text-white">
            Manager Review Gate, Alerts & Live Jira Board
          </h2>
        </div>
        <span className="rounded-full border border-white/15 bg-dark-2 px-3 py-1 font-mono text-[11px] text-white/75">
          {dispatchedTickets.length === 0
            ? '0 Jira Tickets Created'
            : `${dispatchedTickets.length} Jira Ticket(s)`}
        </span>
      </div>

      {alerts.length > 0 && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3.5">
          <p className="text-xs font-bold uppercase tracking-wider text-red-300">
            Immediate Compliance & Blocked-API Manager Alerts ({alerts.length})
          </p>
          <div className="mt-2 space-y-1.5">
            {alerts.map((a, idx) => (
              <div key={`${a.task_id}-${idx}`} className="text-xs text-red-100">
                <span className="mr-1.5 rounded bg-red-500/30 px-1.5 py-0.5 font-mono text-[10px] font-bold">
                  {a.type}
                </span>
                <span className="font-semibold">{a.title}:</span> {a.message}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2.5">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-white/60">
            {isHITL
              ? 'End-of-Meeting Review Menu (Zero Tickets Until Approved)'
              : 'Approved Tasks & Smart Leave Redirections'}
          </h3>
          {isHITL && (
            <button
              type="button"
              disabled={!isManager || resuming || !threadId}
              onClick={handleApproveClick}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow transition hover:bg-emerald-500 disabled:opacity-50"
            >
              {resuming ? 'Creating Jira Tickets...' : 'Approve & Create Tickets'}
            </button>
          )}
        </div>

        {taskList.length === 0 ? (
          <div className="rounded-lg border border-white/10 bg-dark-2 p-4 text-xs text-white/45">
            Run a sprint transcript or demo preset to populate proposed Jira summaries, commit
            messages, policy flags, and leave redirection suggestions.
          </div>
        ) : (
          taskList.map((task) => {
            const suggested =
              resMap[task.task_id]?.suggested_action ?? task.resolution_action ?? 'PROCEED';
            const selected = overrides[task.task_id] ?? suggested;
            return (
              <div
                key={task.task_id}
                className="rounded-lg border border-white/10 bg-dark-2 p-3 text-xs"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="font-semibold text-white">
                      {task.reframed_title ?? task.title}
                    </p>
                    <p className="mt-0.5 text-[11px] text-white/65">
                      Assignee:{' '}
                      <span className="font-semibold text-sky-200">{task.assignee}</span>
                      {task.rerouted_assignee && task.rerouted_assignee !== task.assignee && (
                        <span className="text-amber-300">
                          {' '}
                          → Suggested: <strong>{task.rerouted_assignee}</strong>
                        </span>
                      )}
                    </p>
                    {task.proposed_commit_message && (
                      <p className="mt-1 font-mono text-[10px] text-purple-300">
                        Commit: {task.proposed_commit_message}
                      </p>
                    )}
                  </div>
                  <span className="rounded bg-white/10 px-2 py-0.5 font-mono text-[10px] text-white/80">
                    {selected}
                  </span>
                </div>

                {task.leave_recommendation && (
                  <div className="mt-2 rounded border border-amber-400/30 bg-amber-500/10 p-2 text-[11px] text-amber-200">
                    {task.leave_recommendation}
                  </div>
                )}

                {isHITL && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {ACTION_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() =>
                          setOverrides((prev) => ({ ...prev, [task.task_id]: opt.value }))
                        }
                        className={`rounded px-2 py-0.5 text-[10px] font-semibold transition ${
                          selected === opt.value
                            ? 'bg-blue-1 text-white'
                            : 'bg-dark-3 text-white/60 hover:text-white'
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}

        {resumeError && (
          <p className="rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
            {resumeError}
          </p>
        )}
      </div>

      {dispatchedTickets.length > 0 && (
        <div className="space-y-2 border-t border-white/10 pt-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-emerald-300">
                Live Jira SCRUM Tickets ({approverUserId ? `Approved by ${approverUserId}` : 'Dispatched'})
              </h3>
            </div>
            {hasOpenTickets && (
              <button
                type="button"
                disabled={checkingIn}
                onClick={onTriggerCheckin}
                className="rounded-lg border border-purple-400/40 bg-purple-600/30 px-3 py-1.5 text-[11px] font-bold text-purple-100 transition hover:bg-purple-600/50 disabled:opacity-50"
              >
                {checkingIn ? 'Sending Check-In DMs...' : 'Run Scheduled Check-In Now'}
              </button>
            )}
          </div>

          <div className="space-y-2">
            {dispatchedTickets.map((dt) => {
              const linkedTask = tasks[dt.task_id] || {};
              const jiraStatus = linkedTask.jira_status || dt.jira_status || 'To Do';
              const isDone = jiraStatus.toLowerCase() === 'done' || linkedTask.status === 'DONE';
              const pct = linkedTask.progress_pct ?? dt.progress_pct ?? (isDone ? 100 : 0);
              return (
                <div
                  key={dt.jira_key}
                  className={`rounded-lg border p-3 text-xs ${
                    isDone
                      ? 'border-emerald-500/40 bg-emerald-500/10'
                      : 'border-white/10 bg-dark-2'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <a
                      href={dt.jira_url}
                      target="_blank"
                      rel="noreferrer"
                      className="font-mono text-xs font-bold text-sky-300 hover:underline"
                    >
                      {dt.jira_key}
                    </a>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-white/65">{pct}%</span>
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase ${
                          isDone
                            ? 'bg-emerald-500/30 text-emerald-200'
                            : 'bg-blue-500/25 text-blue-200'
                        }`}
                      >
                        {isDone ? 'DONE' : jiraStatus.toUpperCase()}
                      </span>
                    </div>
                  </div>
                  <p className="mt-1 font-medium text-white">{dt.title}</p>
                  <p className="mt-0.5 text-[11px] text-white/60">Assignee: {dt.assignee}</p>
                  {(linkedTask.commit_summary || dt.commit_summary) && (
                    <p className="mt-1 font-mono text-[10px] text-emerald-300">
                      Closed Commit: {linkedTask.commit_summary || dt.commit_summary}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="border-t border-white/10 pt-3">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-white/60">
          Manager Slack DM Feed ({managerFeed.length})
        </h3>
        <div className="max-h-60 space-y-2 overflow-y-auto pr-1">
          {managerFeed.length === 0 ? (
            <p className="text-xs text-white/40">
              Manager Slack DMs (alerts, review menu, progress digests, closure notices) appear here.
            </p>
          ) : (
            managerFeed.map((m) => (
              <div
                key={m.id}
                className="rounded-lg border border-white/10 bg-dark-2 p-2.5 text-[11px] text-white/85"
              >
                <div className="mb-1 flex items-center justify-between text-[10px] text-white/50">
                  <span className="font-semibold text-purple-300">
                    {m.sender} → Manager ({m.kind || 'dm'})
                  </span>
                  <span>{m.created_at ? new Date(m.created_at).toLocaleTimeString() : ''}</span>
                </div>
                <pre className="whitespace-pre-wrap font-sans text-[11px] leading-relaxed">
                  {m.text}
                </pre>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

