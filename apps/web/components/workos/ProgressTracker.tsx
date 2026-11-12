'use client';

import React from 'react';
import type {
  WorkOSAuditEntry,
  WorkOSDispatchedTicket,
  WorkOSPhase,
} from '@/lib/workos-types';

interface ProgressTrackerProps {
  dispatchedTickets: WorkOSDispatchedTicket[];
  phase: WorkOSPhase;
  approverUserId?: string | null;
  auditEntries?: WorkOSAuditEntry[];
}

export default function ProgressTracker({
  dispatchedTickets,
  phase,
  approverUserId,
  auditEntries = [],
}: ProgressTrackerProps) {
  return (
    <div className="flex h-full flex-col rounded-xl border border-white/10 bg-dark-1 p-5 text-white">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-md border border-emerald-400/40 bg-emerald-500/20 text-xs font-bold text-emerald-300">
            4
          </span>
          <h2 className="text-xs font-semibold uppercase tracking-widest text-white/70">
            Jira Dispatch & Closed Loop
          </h2>
        </div>
        {approverUserId && (
          <span className="font-mono text-[10px] text-emerald-300">
            Approved by {approverUserId}
          </span>
        )}
      </div>

      <div className="flex-1 space-y-2.5 overflow-y-auto pr-1">
        {dispatchedTickets.length === 0 ? (
          <div className="flex h-full items-center justify-center py-8 text-center text-sm text-white/35">
            {phase === 'DISPATCHING'
              ? 'Creating Jira issues and notifying assignees on Slack...'
              : 'Approved Jira tickets and Slack receipts will appear here.'}
          </div>
        ) : (
          dispatchedTickets.map((t) => (
            <div
              key={t.jira_key}
              className="rounded-lg border border-emerald-500/25 bg-dark-2 p-3 text-xs"
            >
              <div className="flex items-center justify-between gap-2">
                <a
                  href={t.jira_url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-mono text-xs font-bold text-emerald-300 hover:underline"
                >
                  {t.jira_key}
                </a>
                <div className="flex items-center gap-1.5">
                  {t.slack_sent && (
                    <span className="rounded bg-purple-500/20 px-2 py-0.5 text-[10px] text-purple-200">
                      Slack DM Sent
                    </span>
                  )}
                  <span className="rounded bg-white/10 px-2 py-0.5 text-[10px] text-white/70">
                    {t.mode || 'dispatched'}
                  </span>
                </div>
              </div>
              <p className="mt-1 font-medium text-white">{t.title}</p>
              <p className="mt-0.5 text-[11px] text-white/55">Assignee: {t.assignee}</p>
            </div>
          ))
        )}

        {auditEntries.length > 0 && (
          <div className="mt-3 border-t border-white/10 pt-3">
            <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-white/45">
              Immutable Audit Log
            </p>
            <div className="space-y-1">
              {auditEntries.slice(0, 6).map((a, i) => (
                <div key={a.id || i} className="flex items-center justify-between gap-2 text-[10px] text-white/60">
                  <span className="truncate font-mono text-sky-1">{a.event_type}</span>
                  <span className="truncate opacity-75">{a.provenance_tag}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

