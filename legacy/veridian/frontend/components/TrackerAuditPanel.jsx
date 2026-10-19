'use client'

export default function TrackerAuditPanel({ dispatchedTickets = [], agentState }) {
  const tasks = agentState?.tasks ?? {}

  return (
    <aside className="flex flex-col h-full glass-card p-0 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/[0.06]">
        <p className="text-[11px] font-semibold text-veridian-purple-200 uppercase tracking-widest">
          Tracker & Audit
        </p>
        <p className="text-xs text-white/30 mt-0.5">
          {dispatchedTickets.length > 0 ? `${dispatchedTickets.length} dispatched` : 'Awaiting dispatch…'}
        </p>
      </div>

      <div className="flex-1 overflow-y-auto divide-y divide-white/[0.04]">

        {/* Dispatched Tickets */}
        {dispatchedTickets.length > 0 && (
          <div className="p-3">
            <p className="text-[10px] font-semibold text-white/30 uppercase tracking-widest mb-2">Jira Tickets</p>
            <div className="space-y-2">
              {dispatchedTickets.map((ticket, i) => (
                <div key={i} className="glass-card-alt p-2.5">
                  <div className="flex items-center gap-2 mb-1">
                    <div className={`w-1.5 h-1.5 rounded-full ${ticket.slack_dm_sent ? 'bg-green-400' : 'bg-white/30'}`} />
                    <a
                      href={ticket.jira_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[12px] font-mono text-veridian-purple-400 hover:text-veridian-purple-200 transition-colors"
                    >
                      {ticket.jira_ticket_id || 'VER-???'}
                    </a>
                    <span className="pill pill-green ml-auto text-[9px]">{ticket.resolution_action}</span>
                  </div>
                  <p className="text-[11px] text-white/70 leading-tight line-clamp-2">{ticket.title}</p>
                  <p className="text-[10px] text-white/35 mt-0.5">→ {ticket.assignee}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Task Status List */}
        {Object.values(tasks).length > 0 && (
          <div className="p-3">
            <p className="text-[10px] font-semibold text-white/30 uppercase tracking-widest mb-2">Task Status</p>
            <div className="space-y-1.5">
              {Object.values(tasks).map(task => {
                const color = task.status === 'READY' ? '#22C55E' : task.status === 'DEFERRED' ? '#6b7280' : '#F59E0B'
                return (
                  <div key={task.task_id} className="flex items-center gap-2 py-1">
                    <div className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                    <p className="text-[11px] text-white/60 flex-1 line-clamp-1">{task.title}</p>
                    <span className="text-[10px] font-mono" style={{ color }}>
                      {task.status ?? 'PENDING'}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Decisions Ledger (permanent) */}
        {(agentState?.key_decisions ?? []).length > 0 && (
          <div className="p-3">
            <p className="text-[10px] font-semibold text-white/30 uppercase tracking-widest mb-2">Decisions Ledger</p>
            <div className="space-y-1.5">
              {agentState.key_decisions.map((d, i) => (
                <div key={i} className="flex items-start gap-2">
                  <div className="mt-1.5 w-1 h-1 rounded-full bg-veridian-purple-400/50 flex-shrink-0" />
                  <p className="text-[11px] text-white/50 leading-snug">{d.decision}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {dispatchedTickets.length === 0 && Object.values(tasks).length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
            <div className="w-6 h-6 rounded-full border border-white/10 mb-3" />
            <p className="text-[12px] text-white/25">Audit trail will appear here</p>
          </div>
        )}
      </div>
    </aside>
  )
}
