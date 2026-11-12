'use client';

import React from 'react';
import type { StepItem } from '@/lib/sse';
import type { WorkOSPhase } from '@/lib/workos-types';

interface WorkflowHeaderProps {
  phase: WorkOSPhase;
  meetingId?: string | null;
  threadId?: string | null;
  steps: StepItem[];
  simulating?: boolean;
  onRunSimulation?: () => void;
  onReset?: () => void;
}

const PHASE_BADGE: Record<WorkOSPhase, { label: string; cls: string }> = {
  IDLE: { label: 'Ready', cls: 'bg-white/10 text-white/70 border-white/15' },
  INGESTING: { label: 'Ingesting Transcript', cls: 'bg-blue-500/20 text-blue-300 border-blue-400/30' },
  EXTRACTING: { label: 'Evon 30B Extracting', cls: 'bg-purple-500/20 text-purple-300 border-purple-400/30' },
  FIREWALL: { label: '4-Way Firewall Active', cls: 'bg-purple-500/20 text-purple-300 border-purple-400/30' },
  RESOLVING: { label: 'Generating Fixes', cls: 'bg-purple-500/20 text-purple-300 border-purple-400/30' },
  HITL: { label: 'Awaiting Manager HITL', cls: 'bg-amber-500/20 text-amber-300 border-amber-400/40' },
  DISPATCHING: { label: 'Dispatching Jira + Slack', cls: 'bg-blue-500/20 text-blue-300 border-blue-400/30' },
  COMPLETE: { label: 'Dispatched & Synced', cls: 'bg-emerald-500/20 text-emerald-300 border-emerald-400/30' },
  ERROR: { label: 'Pipeline Error', cls: 'bg-red-500/20 text-red-300 border-red-400/30' },
};

export default function WorkflowHeader({
  phase,
  meetingId,
  threadId,
  steps,
  simulating = false,
  onRunSimulation,
  onReset,
}: WorkflowHeaderProps) {
  const badge = PHASE_BADGE[phase] ?? PHASE_BADGE.IDLE;

  return (
    <div className="rounded-xl border border-white/10 bg-dark-1 p-5 text-white shadow-lg">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-purple-500 to-blue-600 font-bold text-white shadow">
            W
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-xl font-bold tracking-tight">Gnani × Veridian Work Hub</h1>
              <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${badge.cls}`}>
                {badge.label}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-white/50">
              {meetingId ? `Meeting: ${meetingId}` : 'Ready for Media -> WorkOS Hinglish Demo'}
              {threadId ? ` · Thread: ${threadId}` : ''}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {onRunSimulation && (
            <button
              type="button"
              disabled={simulating}
              onClick={onRunSimulation}
              className="rounded-lg bg-gradient-to-r from-purple-600 to-blue-1 px-4 py-2 text-xs font-bold text-white shadow transition hover:opacity-95 disabled:opacity-50"
            >
              {simulating ? 'Sending Media -> WorkOS...' : '▶ Run Hinglish Demo Simulation'}
            </button>
          )}
          {onReset && (
            <button
              type="button"
              onClick={onReset}
              className="rounded-lg border border-white/15 bg-dark-3 px-3.5 py-2 text-xs font-medium text-white/80 transition hover:bg-white/10"
            >
              Reset
            </button>
          )}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {steps.map((s) => {
          const styleMap = {
            done: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
            active: 'border-amber-400/50 bg-amber-500/15 text-amber-200 ring-1 ring-amber-400/20',
            error: 'border-red-500/40 bg-red-500/15 text-red-200',
            idle: 'border-white/10 bg-dark-2/70 text-white/50',
          };
          return (
            <div key={s.id} className={`rounded-lg border px-3 py-2 ${styleMap[s.status]}`}>
              <p className="truncate text-xs font-semibold">{s.label}</p>
              <p className="mt-0.5 truncate text-[10px] opacity-75">{s.sublabel}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
