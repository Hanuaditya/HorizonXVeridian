'use client';

import React from 'react';
import type { WorkOSPhase } from '@/lib/workos-types';
import {
  Check,
  ChevronRight,
  Clock,
  Layers,
  Play,
  RotateCcw,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface WorkflowHeaderProps {
  phase: WorkOSPhase;
  meetingId?: string | null;
  threadId?: string | null;
  onOpenIngestModal: () => void;
  onReset?: () => void;
  isManager: boolean;
}

export default function WorkflowHeader({
  phase,
  meetingId,
  threadId,
  onOpenIngestModal,
  onReset,
  isManager,
}: WorkflowHeaderProps) {
  // 4-Step Lifecycle Indicator
  const steps = [
    {
      id: 1,
      label: 'Transcribe',
      sub: 'Gnani Prisma',
      isComplete: phase !== 'IDLE' && phase !== 'ERROR',
      isActive: phase === 'INGESTING' || phase === 'EXTRACTING',
    },
    {
      id: 2,
      label: 'Policy Audit',
      sub: '4-Way Firewall',
      isComplete: ['RESOLVING', 'HITL', 'DISPATCHING', 'COMPLETE'].includes(phase),
      isActive: phase === 'FIREWALL' || phase === 'RESOLVING',
    },
    {
      id: 3,
      label: 'Manager Gate',
      sub: 'Zero-Ticket Rule',
      isComplete: ['DISPATCHING', 'COMPLETE'].includes(phase),
      isActive: phase === 'HITL',
    },
    {
      id: 4,
      label: 'Active Sprint',
      sub: 'Jira + Slack Loop',
      isComplete: phase === 'COMPLETE',
      isActive: phase === 'DISPATCHING' || phase === 'COMPLETE',
    },
  ];

  return (
    <div className="rounded-2xl border border-white/[0.07] bg-dark-1 p-5 text-white shadow-xl">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/[0.08] pb-4">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-xl bg-blue-1/20 text-blue-1 border border-blue-1/30">
            <ShieldCheck className="size-5" />
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-lg font-bold tracking-tight text-white">
                Sprint Governance & Execution
              </h1>
              <span
                className={cn(
                  'rounded-full px-2.5 py-0.5 text-[11px] font-semibold tracking-wide border',
                  phase === 'COMPLETE'
                    ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                    : phase === 'HITL'
                    ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                    : phase === 'IDLE'
                    ? 'bg-white/[0.06] text-white/60 border-white/[0.08]'
                    : 'bg-blue-1/15 text-blue-1 border-blue-1/30'
                )}
              >
                {phase === 'HITL'
                  ? 'Awaiting Manager Review'
                  : phase === 'COMPLETE'
                  ? 'Active Sprint Synced'
                  : phase === 'IDLE'
                  ? 'Ready'
                  : `Phase: ${phase}`}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-white/45">
              {meetingId ? `Meeting: ${meetingId}` : 'Automated Sprint Governance & Jira Execution'}
              {threadId ? ` · Thread: ${threadId.slice(0, 18)}...` : ''}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {isManager && (
            <button
              type="button"
              onClick={onOpenIngestModal}
              className="flex items-center gap-2 rounded-xl bg-blue-1 px-4 py-2 text-xs font-semibold text-white shadow-md transition hover:opacity-90"
            >
              <Play className="size-3.5 fill-current" />
              <span>Ingest Meeting</span>
            </button>
          )}

          {onReset && threadId && (
            <button
              type="button"
              onClick={onReset}
              className="flex items-center gap-1.5 rounded-xl border border-white/[0.1] bg-dark-3/60 px-3 py-2 text-xs font-medium text-white/70 transition hover:bg-dark-3 hover:text-white"
            >
              <RotateCcw className="size-3.5" />
              <span>Reset</span>
            </button>
          )}
        </div>
      </div>

      {/* 4-Step Lifecycle Bar */}
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {steps.map((st, idx) => (
          <div
            key={st.id}
            className={cn(
              'flex items-center gap-3 rounded-xl border p-2.5 transition-all',
              st.isActive
                ? 'border-blue-1/40 bg-blue-1/[0.08]'
                : st.isComplete
                ? 'border-emerald-500/30 bg-emerald-500/[0.04]'
                : 'border-white/[0.06] bg-dark-3/50 opacity-60'
            )}
          >
            <div
              className={cn(
                'flex size-6 shrink-0 items-center justify-center rounded-lg text-xs font-bold',
                st.isComplete
                  ? 'bg-emerald-500 text-black'
                  : st.isActive
                  ? 'bg-blue-1 text-white'
                  : 'bg-white/10 text-white/60'
              )}
            >
              {st.isComplete ? <Check className="size-3.5 stroke-[3]" /> : st.id}
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold text-white">{st.label}</p>
              <p className="truncate text-[10px] text-white/40">{st.sub}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
