'use client'

import { useState, useMemo } from 'react'

const ACTION_OPTIONS = [
  { value: 'PROCEED',  label: 'Proceed',          cls: 'btn-green' },
  { value: 'REFRAME',  label: 'Enforce Policy',   cls: 'btn-amber' },
  { value: 'REROUTE',  label: 'Reroute',          cls: 'btn-purple' },
  { value: 'DEFER',    label: 'Defer',             cls: 'btn-ghost' },
  { value: 'OVERRIDE', label: 'Override',          cls: 'btn-danger' },
]

function hasFlag(task) {
  return !!(task?.security_flag || task?.finance_flag || task?.capacity_flag ||
    (task?.hr_status && !['ACTIVE','NOT_FOUND','QUERY_ERROR'].includes(task?.hr_status)))
}

// Section 3 — Approvals HITL (bottom-left)
export default function ApprovalsPanel({ tasks, resolutions, phase, threadId, onResume, resuming }) {
  const [decisions, setDecisions] = useState({})

  const taskList = useMemo(() => Object.values(tasks ?? {}), [tasks])
  const resMap = useMemo(() => {
    const m = {}
    ;(resolutions ?? []).forEach(r => { m[r.task_id] = r })
    return m
  }, [resolutions])

  const flaggedTasks = taskList.filter(t => hasFlag(t))
  const isHITL = phase === 'HITL'
  const isComplete = phase === 'COMPLETE' || phase === 'DISPATCHING'

  // Count how many flagged tasks still need a decision
  const pendingCount = flaggedTasks.filter(t => !decisions[t.task_id]).length
  const allApproved = pendingCount === 0 && flaggedTasks.length > 0

  const handleToggle = (taskId, action) => {
    setDecisions(prev => ({ ...prev, [taskId]: action }))
  }

  const handleExecute = () => {
    const finalDecisions = {}
    taskList.forEach(t => {
      finalDecisions[t.task_id] = decisions[t.task_id]
        ?? resMap[t.task_id]?.suggested_action
        ?? 'PROCEED'
    })
    onResume(threadId, finalDecisions)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Section header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-red-500/20 border border-red-400/30 flex items-center justify-center">
            <span className="text-[11px] font-bold text-red-400">3</span>
          </div>
          <h2 className="text-[13px] font-semibold text-white/70 uppercase tracking-widest">Approvals</h2>
        </div>
        {isHITL && (
          <span className="flex items-center gap-1.5 text-[11px] text-amber-400">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 pulse-dot" />
            Awaiting review
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto space-y-2.5">
        {!isHITL && !isComplete && flaggedTasks.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-[13px] text-white/25 text-center">Approval checkpoints will<br />appear here during HITL review</p>
          </div>
        ) : (
          flaggedTasks.map(task => {
            const suggested = resMap[task.task_id]?.suggested_action ?? 'PROCEED'
            const selected = decisions[task.task_id] ?? (isComplete ? suggested : null)
            const isApproved = !!selected

            return (
              <div key={task.task_id} className={`glass-card-alt p-3 border transition-all ${
                isApproved ? 'border-green-500/25' : isHITL ? 'border-amber-500/25 task-flagged' : 'border-white/[0.07]'
              }`}>
                {/* Task name + approval checkbox row */}
                <div className="flex items-start gap-2.5 mb-2.5">
                  {/* Approval indicator */}
                  <div className={`mt-0.5 w-4 h-4 rounded flex-shrink-0 border-2 flex items-center justify-center transition-all ${
                    isApproved || isComplete ? 'bg-green-500/20 border-green-400' : 'border-white/20'
                  }`}>
                    {(isApproved || isComplete) && (
                      <svg className="w-2.5 h-2.5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[13px] font-semibold text-white leading-tight line-clamp-2">
                      {task.reframed_title ?? task.title}
                    </p>
                    <p className="text-[11px] text-white/40 mt-0.5">
                      Suggested: <span className="text-amber-400 font-medium">{suggested}</span>
                    </p>
                  </div>
                </div>

                {/* Action selector — only shown during HITL */}
                {isHITL && !isComplete && (
                  <div className="flex flex-wrap gap-1.5">
                    {ACTION_OPTIONS.map(opt => (
                      <button
                        key={opt.value}
                        onClick={() => handleToggle(task.task_id, opt.value)}
                        className={`btn ${opt.cls} text-[11px] py-1 px-2.5 ${
                          selected === opt.value ? 'ring-1 ring-white/40 scale-[1.02]' : ''
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                )}

                {/* Show final decision if complete */}
                {isComplete && (
                  <span className="pill pill-green text-[10px]">✓ {suggested}</span>
                )}
              </div>
            )
          })
        )}

        {/* Clear tasks summary */}
        {taskList.filter(t => !hasFlag(t)).length > 0 && (
          <div className="pt-2 border-t border-white/[0.05]">
            <p className="text-[11px] text-white/30">
              + {taskList.filter(t => !hasFlag(t)).length} task(s) auto-approved (no flags)
            </p>
          </div>
        )}
      </div>

      {/* Execute Workflow button */}
      <div className={`mt-4 pt-4 border-t border-white/[0.06] ${!isHITL && !isComplete ? 'opacity-30' : ''}`}>
        {isComplete ? (
          <div className="flex items-center gap-2 justify-center py-2 text-green-400">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            <span className="text-[13px] font-medium">Workflow Dispatched</span>
          </div>
        ) : (
          <>
            <button
              onClick={handleExecute}
              disabled={!isHITL || !allApproved || resuming}
              className="btn btn-primary w-full py-3 text-[14px] font-bold justify-center"
            >
              {resuming
                ? <><span className="animate-spin mr-2">⟳</span> Dispatching…</>
                : <><span>⚡</span> Execute Workflow</>
              }
            </button>
            {isHITL && !allApproved && flaggedTasks.length > 0 && (
              <p className="text-[11px] text-amber-400/70 text-center mt-2">
                Review {pendingCount} remaining task(s) to unlock
              </p>
            )}
          </>
        )}
      </div>
    </div>
  )
}
