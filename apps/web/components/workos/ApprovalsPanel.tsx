'use client';

import React, { useMemo, useState } from 'react';
import type { WorkOSPhase, WorkOSResolution, WorkOSTask } from '@/lib/workos-types';

interface ApprovalsPanelProps {
  tasks: Record<string, WorkOSTask>;
  resolutions: WorkOSResolution[];
  phase: WorkOSPhase;
  threadId: string | null;
  isManager: boolean;
  resuming: boolean;
  resumeError: string | null;
  onResume: (threadId: string, decisions: Record<string, string>) => Promise<unknown>;
}

const ACTIONS: Array<{ value: string; label: string }> = [
  { value: 'REFRAME', label: 'Reframe' },
  { value: 'REROUTE', label: 'Reroute' },
  { value: 'DEFER', label: 'Defer' },
  { value: 'OVERRIDE', label: 'Override' },
  { value: 'PROCEED', label: 'Proceed' },
];

export default function ApprovalsPanel({
  tasks,
  resolutions,
  phase,
  threadId,
  isManager,
  resuming,
  resumeError,
  onResume,
}: ApprovalsPanelProps) {
  const [overrides, setOverrides] = useState<Record<string, string>>({});

  const taskList = useMemo(() => Object.values(tasks || {}), [tasks]);
  const resMap = useMemo(() => {
    const map: Record<string, WorkOSResolution> = {};
    (resolutions || []).forEach((r) => {
      map[r.task_id] = r;
    });
    return map;
  }, [resolutions]);

  const flaggedTasks = taskList.filter((t) => {
    const suggested = resMap[t.task_id]?.suggested_action ?? t.resolution_action ?? 'PROCEED';
    return suggested !== 'PROCEED';
  });

  const isHITL = phase === 'HITL';
  const isDone = phase === 'COMPLETE' || phase === 'DISPATCHING';

  const handleApproveAllSuggested = async () => {
    if (!threadId) return;
    const decisions: Record<string, string> = {};
    taskList.forEach((t) => {
      decisions[t.task_id] =
        overrides[t.task_id] ?? resMap[t.task_id]?.suggested_action ?? 'PROCEED';
    });
    await onResume(threadId, decisions);
  };

  return (
    <div
      className={`flex h-full flex-col rounded-xl border bg-dark-1 p-5 text-white transition ${
        isHITL ? 'border-amber-400/50 ring-1 ring-amber-400/20' : 'border-white/10'
      }`}
    >
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-md border border-amber-400/40 bg-amber-500/20 text-xs font-bold text-amber-300">
            3
          </span>
          <h2 className="text-xs font-semibold uppercase tracking-widest text-white/70">
            Manager HITL Approvals
          </h2>
        </div>
        {isHITL && (
          <span className="flex items-center gap-1.5 text-[11px] font-medium text-amber-300">
            <span className="h-2 w-2 animate-pulse rounded-full bg-amber-400" />
            Action Required
          </span>
        )}
      </div>

      <div className="flex-1 space-y-2.5 overflow-y-auto pr-1">
        {flaggedTasks.length === 0 ? (
          <div className="flex h-full items-center justify-center py-8 text-center text-sm text-white/35">
            {taskList.length > 0
              ? 'No policy violations detected — tasks proceeded automatically.'
              : 'Compliance remediations will pause here for manager sign-off.'}
          </div>
        ) : (
          flaggedTasks.map((task) => {
            const res = resMap[task.task_id];
            const suggested = res?.suggested_action ?? task.resolution_action ?? 'PROCEED';
            const selected = overrides[task.task_id] ?? suggested;

            return (
              <div
                key={task.task_id}
                className="rounded-lg border border-amber-500/25 bg-dark-2 p-3 text-xs"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-semibold text-white">
                      {task.reframed_title ?? task.title}
                    </p>
                    {task.reframed_description && (
                      <p className="mt-1 text-[11px] text-white/65">{task.reframed_description}</p>
                    )}
                  </div>
                  <span className="rounded bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-300">
                    AI: {suggested}
                  </span>
                </div>

                {isHITL && !isDone && (
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {ACTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        type="button"
                        disabled={!isManager || resuming}
                        onClick={() =>
                          setOverrides((prev) => ({ ...prev, [task.task_id]: opt.value }))
                        }
                        className={`rounded border px-2 py-1 text-[10px] font-semibold transition ${
                          selected === opt.value
                            ? 'border-blue-1 bg-blue-1 text-white'
                            : 'border-white/15 bg-dark-3 text-white/70 hover:bg-white/10'
                        } disabled:cursor-not-allowed disabled:opacity-45`}
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
      </div>

      <div className="mt-4 border-t border-white/10 pt-3">
        {!isManager && isHITL && (
          <p className="mb-2 rounded border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-[11px] text-red-300">
            Read-only: Only organization managers (`org:admin`) can approve or override HITL items.
          </p>
        )}
        {resumeError && (
          <p className="mb-2 rounded border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-[11px] text-red-300">
            {resumeError}
          </p>
        )}
        <button
          type="button"
          disabled={!isHITL || !isManager || resuming || !threadId}
          onClick={handleApproveAllSuggested}
          className="w-full rounded-lg bg-blue-1 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {resuming
            ? 'Dispatching Approved Actions...'
            : isDone
              ? 'Approved & Dispatched'
              : 'Approve Suggested Fixes & Dispatch'}
        </button>
      </div>
    </div>
  );
}
