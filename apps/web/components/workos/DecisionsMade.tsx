'use client';

import React from 'react';
import type { WorkOSDecision, WorkOSTask } from '@/lib/workos-types';

interface DecisionsMadeProps {
  tasks: Record<string, WorkOSTask>;
  keyDecisions: WorkOSDecision[];
}

export default function DecisionsMade({ tasks, keyDecisions }: DecisionsMadeProps) {
  const taskList = Object.values(tasks || {});

  return (
    <div className="flex h-full flex-col rounded-xl border border-white/10 bg-dark-1 p-5 text-white">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-md border border-blue-400/40 bg-blue-500/20 text-xs font-bold text-blue-300">
            2
          </span>
          <h2 className="text-xs font-semibold uppercase tracking-widest text-white/70">
            Firewall & Extracted Work
          </h2>
        </div>
        <span className="font-mono text-[11px] text-white/40">{taskList.length} item(s)</span>
      </div>

      <div className="flex-1 space-y-2.5 overflow-y-auto pr-1">
        {taskList.length === 0 ? (
          <div className="flex h-full items-center justify-center py-8 text-center text-sm text-white/35">
            Compliance firewall results & provenance tags appear here.
          </div>
        ) : (
          taskList.map((task) => {
            const flags: Array<{ label: string; cls: string; prov?: string | null }> = [];
            if (task.hr_status && task.hr_status !== 'ACTIVE' && task.hr_status !== 'NOT_FOUND') {
              flags.push({
                label: `HR: ${task.hr_status}`,
                cls: 'bg-amber-500/15 text-amber-300 border-amber-400/30',
                prov: task.hr_provenance,
              });
            }
            if (task.security_flag) {
              flags.push({
                label: 'SECURITY POLICY',
                cls: 'bg-red-500/15 text-red-300 border-red-400/30',
                prov: task.security_provenance,
              });
            }
            if (task.finance_flag) {
              flags.push({
                label: 'FINANCE BUDGET ₹0',
                cls: 'bg-orange-500/15 text-orange-300 border-orange-400/30',
                prov: task.finance_provenance,
              });
            }
            if (task.capacity_flag) {
              flags.push({
                label: 'CAPACITY LIMIT',
                cls: 'bg-purple-500/15 text-purple-300 border-purple-400/30',
                prov: task.capacity_provenance,
              });
            }
            if (task.assignee_resolution_flag) {
              flags.push({
                label: task.assignee_resolution_flag,
                cls: 'bg-red-500/15 text-red-300 border-red-400/30',
                prov: 'Speaker Mapping -> HITL',
              });
            }

            return (
              <div
                key={task.task_id}
                className="rounded-lg border border-white/10 bg-dark-2 p-3 text-xs"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="font-semibold text-white">{task.title}</p>
                  <span className="flex-shrink-0 rounded bg-dark-3 px-2 py-0.5 text-[10px] text-sky-1">
                    {task.rerouted_assignee ? `${task.assignee} -> ${task.rerouted_assignee}` : task.assignee}
                  </span>
                </div>

                {task.transcript_quote && (
                  <p className="mt-1 italic text-[11px] text-white/50">
                    &ldquo;{task.transcript_quote}&rdquo;
                  </p>
                )}

                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {flags.length === 0 ? (
                    <span className="rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                      ALL CLEAR · PROCEED
                    </span>
                  ) : (
                    flags.map((f, idx) => (
                      <div key={idx} className="flex flex-wrap items-center gap-1.5">
                        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${f.cls}`}>
                          {f.label}
                        </span>
                        {f.prov && (
                          <span className="rounded border border-purple-400/20 bg-purple-500/10 px-1.5 py-0.5 font-mono text-[10px] text-purple-200">
                            {f.prov}
                          </span>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            );
          })
        )}

        {keyDecisions.length > 0 && (
          <div className="mt-3 border-t border-white/10 pt-3">
            <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-white/45">
              Captured Decisions
            </p>
            {keyDecisions.map((d, i) => (
              <p key={i} className="mb-1 text-[11px] text-white/75">
                • {d.decision}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
