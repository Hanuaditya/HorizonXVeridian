'use client'

export default function ZenModeBanner({ dispatchedTickets = [] }) {
  const ticketCount = dispatchedTickets.length
  const deferredCount = dispatchedTickets.filter(t => t.resolution_action === 'DEFER').length
  const sentCount = ticketCount - deferredCount

  return (
    <div className="zen-banner p-5 animate-slide-down">
      <div className="relative z-10">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-8 h-8 rounded-full bg-green-500/20 border border-green-500/30 flex items-center justify-center">
            <span className="text-base">✨</span>
          </div>
          <div>
            <p className="text-[15px] font-semibold text-green-400">Workflow Complete</p>
            <p className="text-[12px] text-white/50">
              {sentCount} ticket{sentCount !== 1 ? 's' : ''} dispatched · {deferredCount} deferred
            </p>
          </div>
        </div>

        {dispatchedTickets.filter(t => t.resolution_action !== 'DEFER').map((ticket, i) => (
          <div key={i} className="flex items-center gap-2 py-1">
            <svg className="w-3.5 h-3.5 text-green-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            <a
              href={ticket.jira_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[13px] text-green-400/90 hover:text-green-400 underline font-mono"
            >
              {ticket.jira_ticket_id}
            </a>
            <span className="text-[12px] text-white/50">→ {ticket.assignee}</span>
            {ticket.slack_dm_sent && <span className="text-[10px] text-white/30">· DM sent</span>}
          </div>
        ))}
      </div>
    </div>
  )
}
