'use client'

const ROUTE_ICONS = { jira: '🎫', slack: '💬', defer: '⏸', hr: '👤', security: '🔒', budget: '💰' }

function getRouting(task, resolution) {
  const routes = []
  const action = resolution?.suggested_action ?? 'PROCEED'
  if (action === 'DEFER') routes.push({ label: 'Deferred', type: 'defer' })
  else routes.push({ label: 'Jira Ticket', type: 'jira' })
  if (task?.security_flag) routes.push({ label: 'Security Review', type: 'security' })
  if (task?.finance_flag) routes.push({ label: 'Budget Check', type: 'budget' })
  if (task?.hr_status && task.hr_status !== 'ACTIVE') routes.push({ label: 'HR Action', type: 'hr' })
  return routes
}

function getConflictBadge(task) {
  if (task?.security_flag) return { label: 'SECURITY', cls: 'pill pill-red' }
  if (task?.finance_flag)  return { label: 'BUDGET',   cls: 'pill pill-amber' }
  if (task?.capacity_flag) return { label: 'CAPACITY', cls: 'pill pill-purple' }
  if (task?.hr_status && task.hr_status !== 'ACTIVE') return { label: 'HR', cls: 'pill pill-amber' }
  return null
}

// Section 2 — Decisions Made (top-right)
export default function DecisionsMade({ tasks, resolutions, keyDecisions }) {
  const taskList = Object.values(tasks ?? {})
  const resMap = {}
  ;(resolutions ?? []).forEach(r => { resMap[r.task_id] = r })

  return (
    <div className="flex flex-col h-full">
      {/* Section header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-amber-500/20 border border-amber-400/30 flex items-center justify-center">
            <span className="text-[11px] font-bold text-amber-400">2</span>
          </div>
          <h2 className="text-[13px] font-semibold text-white/70 uppercase tracking-widest">Decisions Made</h2>
        </div>
        {taskList.length > 0 && (
          <span className="pill pill-gray">{taskList.length} task{taskList.length !== 1 ? 's' : ''}</span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto space-y-2.5">
        {taskList.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-[13px] text-white/25 text-center">AI-extracted tasks will appear<br />after extraction completes</p>
          </div>
        ) : (
          taskList.map(task => {
            const res = resMap[task.task_id]
            const badge = getConflictBadge(task)
            const routes = getRouting(task, res)
            const action = res?.suggested_action ?? 'PROCEED'
            return (
              <div key={task.task_id} className="glass-card-alt p-3">
                {/* Task header */}
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-[13px] font-semibold text-white leading-tight line-clamp-2">
                      {task.reframed_title ?? task.title}
                    </p>
                    <p className="text-[11px] text-white/40 mt-0.5">
                      → {task.rerouted_assignee ?? task.assignee}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1 flex-shrink-0">
                    {badge && <span className={badge.cls}>{badge.label}</span>}
                    <span className={`pill ${action === 'PROCEED' ? 'pill-green' : action === 'DEFER' ? 'pill-gray' : 'pill-amber'}`}>
                      {action}
                    </span>
                  </div>
                </div>

                {/* Routing chips */}
                <div className="flex flex-wrap gap-1.5">
                  {routes.map((r, i) => (
                    <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 bg-white/[0.04] border border-white/[0.07] rounded-md text-[10px] text-white/50">
                      {ROUTE_ICONS[r.type]} {r.label}
                    </span>
                  ))}
                </div>

                {/* Transcript quote */}
                {task.transcript_quote && (
                  <p className="mt-2 text-[11px] text-white/30 italic border-l border-white/10 pl-2 line-clamp-1">
                    "{task.transcript_quote}"
                  </p>
                )}
              </div>
            )
          })
        )}

        {/* Key decisions */}
        {(keyDecisions ?? []).length > 0 && (
          <div className="mt-1 pt-3 border-t border-white/[0.06]">
            <p className="text-[10px] font-semibold text-white/30 uppercase tracking-widest mb-2">Key Decisions ({keyDecisions.length})</p>
            {keyDecisions.map((d, i) => (
              <div key={i} className="flex items-start gap-2 py-1.5">
                <div className="mt-1.5 w-1 h-1 rounded-full bg-veridian-purple-400/50 flex-shrink-0" />
                <p className="text-[12px] text-white/55 leading-snug">{d.decision}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
