'use client'

import { useState, useMemo } from 'react'
import { getAccentColor, getPillClass, hasFlag, getConflictLabel, getInitials } from '../../lib/utils'

// ── Resolution action metadata ──────────────────────────────────────────────
const ACTION_META = {
  REFRAME:  { label: 'Enforce Policy',     cls: 'btn-amber',  icon: '⚡' },
  REROUTE:  { label: 'Reroute Task',       cls: 'btn-purple', icon: '↗' },
  DEFER:    { label: 'Defer to Q4',        cls: 'btn-ghost',  icon: '⏸' },
  OVERRIDE: { label: 'Override Guardrail', cls: 'btn-danger', icon: '⚠' },
  PROCEED:  { label: 'Proceed',            cls: 'btn-green',  icon: '✓' },
}

// ── Provenance Tag ───────────────────────────────────────────────────────────
function ProvenanceTag({ text }) {
  if (!text) return null
  return <span className="provenance">🔗 {text}</span>
}

// ── Single Task Card ─────────────────────────────────────────────────────────
function TaskCard({ task, resolution, decision, onDecisionChange, dispatched }) {
  const [showDiff, setShowDiff] = useState(false)
  const accent = getAccentColor(task)
  const conflict = getConflictLabel(task)
  const hasAFlag = hasFlag(task)
  const suggestedAction = resolution?.suggested_action ?? 'PROCEED'
  const currentDecision = decision ?? suggestedAction
  const isDispatched = !!dispatched

  // Glow class based on conflict
  const glowClass = hasAFlag
    ? (task.security_flag ? 'task-blocked' : 'task-flagged')
    : 'task-clear'

  return (
    <div className={`glass-card-alt relative overflow-hidden transition-all duration-300 ${glowClass} ${isDispatched ? 'opacity-70' : ''}`}>
      {/* Left accent bar */}
      <div className="absolute left-0 top-0 bottom-0 w-0.5 rounded-l" style={{ backgroundColor: accent }} />

      <div className="p-4 pl-5">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex items-start gap-2.5 min-w-0 flex-1">
            {/* Avatar */}
            <div
              className="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-[11px] font-bold"
              style={{ background: `${accent}22`, border: `1px solid ${accent}44`, color: accent }}
            >
              {getInitials(task.rerouted_assignee ?? task.assignee)}
            </div>
            <div className="min-w-0">
              <p className="text-[13px] font-semibold text-white leading-tight line-clamp-2">
                {task.reframed_title ?? task.title}
              </p>
              <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                <span className="text-[11px] text-white/50">
                  {task.rerouted_assignee ? (
                    <><span className="line-through text-white/30">{task.assignee}</span> → <span className="text-veridian-purple-400">{task.rerouted_assignee}</span></>
                  ) : task.assignee}
                </span>
                {conflict && <span className={`pill ${conflict === 'SECURITY' ? 'pill-red' : conflict === 'BUDGET' ? 'pill-amber' : 'pill-purple'}`}>{conflict}</span>}
              </div>
            </div>
          </div>

          {/* Status pill */}
          <div className="flex-shrink-0">
            {isDispatched
              ? <span className="pill pill-green">✓ DISPATCHED</span>
              : <span className={getPillClass(currentDecision)}>{currentDecision}</span>
            }
          </div>
        </div>

        {/* AI Reasoning / flags */}
        {hasAFlag && (
          <div className="bg-black/20 border border-white/[0.06] rounded-lg p-3 mb-3 space-y-1.5">
            {task.security_flag && (
              <div className="flex items-start gap-2">
                <span className="text-red-400 text-[12px] font-semibold flex-shrink-0">Security</span>
                <span className="text-[12px] text-white/60">{task.security_flag}</span>
              </div>
            )}
            {task.finance_flag && (
              <div className="flex items-start gap-2">
                <span className="text-amber-400 text-[12px] font-semibold flex-shrink-0">Budget</span>
                <span className="text-[12px] text-white/60">{task.finance_flag}</span>
              </div>
            )}
            {task.capacity_flag && (
              <div className="flex items-start gap-2">
                <span className="text-veridian-purple-400 text-[12px] font-semibold flex-shrink-0">Capacity</span>
                <span className="text-[12px] text-white/60">{task.capacity_flag}</span>
              </div>
            )}
            {task.hr_status && task.hr_status !== 'ACTIVE' && (
              <div className="flex items-start gap-2">
                <span className="text-amber-400 text-[12px] font-semibold flex-shrink-0">HR</span>
                <span className="text-[12px] text-white/60">{task.hr_status}</span>
              </div>
            )}
          </div>
        )}

        {/* Provenance tags */}
        <div className="flex flex-wrap gap-1.5 mb-3">
          {task.hr_provenance      && <ProvenanceTag text={task.hr_provenance} />}
          {task.finance_provenance && <ProvenanceTag text={task.finance_provenance} />}
          {task.security_provenance && <ProvenanceTag text={`${task.security_provenance} · conf ${task.security_confidence?.toFixed(2)}`} />}
          {task.capacity_provenance && <ProvenanceTag text={task.capacity_provenance} />}
        </div>

        {/* Transcript quote */}
        {task.transcript_quote && (
          <p className="text-[12px] text-white/40 italic border-l-2 border-white/10 pl-3 mb-3 leading-snug line-clamp-2">
            "{task.transcript_quote}"
          </p>
        )}

        {/* AI Resolution suggestion */}
        {hasAFlag && resolution && (
          <div className="bg-veridian-purple-800/20 border border-veridian-purple-400/15 rounded-lg p-3 mb-3">
            <p className="text-[10px] font-semibold text-veridian-purple-400/80 uppercase tracking-widest mb-1.5">
              AI Resolution
            </p>
            <p className="text-[12px] text-white/70">
              <span className={`font-bold ${suggestedAction === 'REFRAME' ? 'text-amber-400' : suggestedAction === 'REROUTE' ? 'text-veridian-purple-400' : suggestedAction === 'DEFER' ? 'text-white/50' : 'text-red-400'}`}>
                {suggestedAction}
              </span>
              {suggestedAction === 'REFRAME' && task.reframed_title && (
                <> — rewrite as: <em className="text-white/60">"{task.reframed_title}"</em></>
              )}
              {suggestedAction === 'REROUTE' && task.rerouted_assignee && (
                <> — reassign to <span className="text-veridian-purple-400">{task.rerouted_assignee}</span></>
              )}
              {suggestedAction === 'DEFER' && <> — move to next budget cycle</>}
              {suggestedAction === 'OVERRIDE' && <> — acknowledge and track async</>}
            </p>

            {/* REFRAME diff view toggle */}
            {suggestedAction === 'REFRAME' && task.reframed_description && (
              <button
                onClick={() => setShowDiff(v => !v)}
                className="mt-2 text-[11px] text-veridian-purple-400/70 hover:text-veridian-purple-400 transition-colors"
              >
                {showDiff ? '▲ Hide diff' : '▼ Show reframe diff'}
              </button>
            )}

            {showDiff && task.reframed_description && (
              <div className="mt-2 p-2 bg-black/30 rounded text-[11px] space-y-1">
                <p className="diff-del font-mono">{task.title}</p>
                <p className="diff-add font-mono">{task.reframed_title}</p>
              </div>
            )}
          </div>
        )}

        {/* Dispatched receipt */}
        {isDispatched && (
          <div className="flex items-center gap-2 text-[12px] text-green-400/80 mt-1">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            <a href={task.jira_url} target="_blank" rel="noopener noreferrer" className="underline hover:text-green-400">
              {task.jira_ticket_id || 'Jira ticket created'}
            </a>
            {task.slack_dm_sent && <span className="text-white/40">· Slack DM sent</span>}
          </div>
        )}

        {/* Action buttons — only show in HITL state */}
        {!isDispatched && hasAFlag && (
          <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-white/[0.05]">
            {['REFRAME','REROUTE','DEFER','OVERRIDE','PROCEED'].map(action => {
              const meta = ACTION_META[action]
              const isSelected = currentDecision === action
              return (
                <button
                  key={action}
                  onClick={() => onDecisionChange(task.task_id, action)}
                  className={`btn ${meta.cls} text-[11px] py-1.5 px-3 ${isSelected ? 'ring-1 ring-white/30' : ''}`}
                >
                  {meta.icon} {meta.label}
                </button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// ── CommandCenterCard (HITL Main Component) ──────────────────────────────────
export default function CommandCenterCard({ tasks, resolutions, phase, threadId, onResume, resuming }) {
  const [decisions, setDecisions] = useState({})

  const taskList = useMemo(() => Object.values(tasks ?? {}), [tasks])
  const resolutionMap = useMemo(() => {
    const m = {}
    ;(resolutions ?? []).forEach(r => { m[r.task_id] = r })
    return m
  }, [resolutions])

  const flaggedTasks  = taskList.filter(t => hasFlag(t))
  const clearTasks    = taskList.filter(t => !hasFlag(t))
  const deferredCount = taskList.filter(t => t.status === 'DEFERRED' || (decisions[t.task_id] || resolutionMap[t.task_id]?.suggested_action) === 'DEFER').length

  // Stats
  const stats = [
    { label: 'Extracted',   value: taskList.length,                   color: 'text-veridian-purple-400' },
    { label: 'Flagged',     value: flaggedTasks.length,                color: 'text-amber-400' },
    { label: 'Clear',       value: clearTasks.length,                  color: 'text-green-400' },
    { label: 'Deferred',    value: deferredCount,                      color: 'text-white/40' },
  ]

  const handleDecisionChange = (taskId, action) => {
    setDecisions(prev => ({ ...prev, [taskId]: action }))
  }

  const allDecisionsMade = flaggedTasks.every(t => {
    const dec = decisions[t.task_id] ?? resolutionMap[t.task_id]?.suggested_action
    return !!dec
  })

  const handleExecute = () => {
    const finalDecisions = {}
    taskList.forEach(t => {
      finalDecisions[t.task_id] = decisions[t.task_id] ?? resolutionMap[t.task_id]?.suggested_action ?? 'PROCEED'
    })
    onResume(threadId, finalDecisions)
  }

  // Show the card once we have tasks
  if (taskList.length === 0 && phase === 'IDLE') return null

  const isHITL   = phase === 'HITL'
  const isDone   = phase === 'COMPLETE' || phase === 'DISPATCHING'

  return (
    <div className="glass-card overflow-hidden animate-fade-in">
      {/* Header */}
      <div className="px-5 py-4 border-b border-white/[0.06]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="pill pill-purple">⚡ Command Center</span>
            {isHITL && (
              <span className="flex items-center gap-1.5 text-[11px] text-amber-400">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 pulse-dot" />
                Awaiting your review
              </span>
            )}
          </div>
          {/* Stats row */}
          <div className="flex items-center gap-5">
            {stats.map(s => (
              <div key={s.label} className="text-center">
                <p className={`text-lg font-bold font-mono ${s.color}`}>{s.value}</p>
                <p className="text-[9px] text-white/30 uppercase tracking-wider">{s.label}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Two Zones */}
      <div className="p-4 space-y-4 overflow-y-auto max-h-[calc(100vh-320px)]">

        {/* Zone 1 — Intervention Required */}
        {flaggedTasks.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <div className="h-px flex-1 bg-amber-500/20" />
              <span className="text-[10px] font-semibold text-amber-400/80 uppercase tracking-widest">Intervention Required ({flaggedTasks.length})</span>
              <div className="h-px flex-1 bg-amber-500/20" />
            </div>
            <div className="space-y-3">
              {flaggedTasks.map(t => (
                <TaskCard
                  key={t.task_id}
                  task={t}
                  resolution={resolutionMap[t.task_id]}
                  decision={decisions[t.task_id]}
                  onDecisionChange={handleDecisionChange}
                  dispatched={isDone ? t.jira_ticket_id : null}
                />
              ))}
            </div>
          </div>
        )}

        {/* Zone 2 — Clear to Proceed */}
        {clearTasks.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <div className="h-px flex-1 bg-green-500/15" />
              <span className="text-[10px] font-semibold text-green-400/70 uppercase tracking-widest">Clear to Proceed ({clearTasks.length})</span>
              <div className="h-px flex-1 bg-green-500/15" />
            </div>
            <div className="space-y-2">
              {clearTasks.map(t => (
                <TaskCard
                  key={t.task_id}
                  task={t}
                  resolution={resolutionMap[t.task_id]}
                  decision={'PROCEED'}
                  onDecisionChange={handleDecisionChange}
                  dispatched={isDone ? t.jira_ticket_id : null}
                />
              ))}
            </div>
          </div>
        )}

        {taskList.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-white/30">
            <div className="w-10 h-10 rounded-full border-2 border-veridian-purple-400/30 border-t-veridian-purple-400 animate-spin mb-3" />
            <p className="text-[13px]">Graph A is processing…</p>
          </div>
        )}
      </div>

      {/* Execute Bar */}
      {isHITL && taskList.length > 0 && (
        <div className="border-t border-white/[0.06] px-5 py-4">
          <div className="flex items-center justify-between gap-4">
            <div className="text-[13px] text-white/50">
              Will fire: <span className="text-white/80">{taskList.filter(t => !((decisions[t.task_id] ?? resolutionMap[t.task_id]?.suggested_action) === 'DEFER')).length} ticket(s)</span>
              {' · '}
              <span className="text-white/80">{taskList.filter(t => !((decisions[t.task_id] ?? resolutionMap[t.task_id]?.suggested_action) === 'DEFER')).length} Slack DM(s)</span>
              {deferredCount > 0 && <> · <span className="text-white/50">{deferredCount} deferred</span></>}
            </div>
            <button
              onClick={handleExecute}
              disabled={!allDecisionsMade || resuming}
              className="btn btn-primary text-sm px-6 py-2.5 font-semibold"
            >
              {resuming
                ? <><span className="animate-spin mr-2">⟳</span> Dispatching…</>
                : <><span>⚡</span> Execute & Dispatch</>
              }
            </button>
          </div>
          {!allDecisionsMade && flaggedTasks.length > 0 && (
            <p className="text-[11px] text-amber-400/70 mt-2">
              ⚠ Confirm all {flaggedTasks.length - Object.keys(decisions).length} remaining flagged task(s) before dispatching.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
