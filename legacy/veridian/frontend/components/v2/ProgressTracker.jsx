'use client'

function ProgressBar({ label, pct, color = '#7F77DD' }) {
  return (
    <div className="mb-3">
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-[12px] text-white/70 font-medium line-clamp-1">{label}</span>
        <span className="text-[12px] font-mono font-bold" style={{ color }}>{pct}%</span>
      </div>
      <div className="h-2 bg-white/[0.06] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-1000 ease-out"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  )
}

// Section 4 — Jira Ticket & Progress Tracker (bottom-right)
export default function ProgressTracker({ dispatchedTickets = [], phase }) {
  const isComplete = phase === 'COMPLETE'
  const isDispatching = phase === 'DISPATCHING'

  const doneCount   = dispatchedTickets.filter(t => t.resolution_action !== 'DEFER').length
  const deferCount  = dispatchedTickets.filter(t => t.resolution_action === 'DEFER').length
  const totalCount  = dispatchedTickets.length

  // Build per-ticket progress bars
  const dispatched = dispatchedTickets.filter(t => t.resolution_action !== 'DEFER')
  const deferred   = dispatchedTickets.filter(t => t.resolution_action === 'DEFER')

  const slackChannels = [...new Set(
    dispatchedTickets.filter(t => t.slack_dm_sent).map(t => t.assignee).filter(Boolean)
  )]

  return (
    <div className="flex flex-col h-full">
      {/* Section header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-green-500/20 border border-green-400/30 flex items-center justify-center">
            <span className="text-[11px] font-bold text-green-400">4</span>
          </div>
          <h2 className="text-[13px] font-semibold text-white/70 uppercase tracking-widest">Jira & Progress</h2>
        </div>
        {isComplete && <span className="pill pill-green">✓ Complete</span>}
        {isDispatching && <span className="pill pill-purple">Dispatching…</span>}
      </div>

      <div className="flex-1 overflow-y-auto">
        {!isComplete && !isDispatching && dispatchedTickets.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-[13px] text-white/25 text-center">Progress bars and Jira tickets<br />will appear after dispatch</p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Overall progress bars */}
            <div>
              <p className="text-[10px] font-semibold text-white/30 uppercase tracking-widest mb-3">Progress</p>
              {totalCount > 0 ? (
                <>
                  <ProgressBar
                    label={`Tickets Created (${doneCount}/${totalCount})`}
                    pct={totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0}
                    color="#22C55E"
                  />
                  {deferCount > 0 && (
                    <ProgressBar
                      label={`Deferred (${deferCount}/${totalCount})`}
                      pct={Math.round((deferCount / totalCount) * 100)}
                      color="#6b7280"
                    />
                  )}
                  {slackChannels.length > 0 && (
                    <ProgressBar
                      label={`Slack DMs Sent (${slackChannels.length})`}
                      pct={100}
                      color="#7F77DD"
                    />
                  )}
                </>
              ) : (
                <>
                  <ProgressBar label="Tickets Created" pct={90} color="#22C55E" />
                  <ProgressBar label="Slack DMs" pct={10} color="#7F77DD" />
                </>
              )}
            </div>

            {/* Jira ticket list */}
            {dispatched.length > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-white/30 uppercase tracking-widest mb-2">Jira Tickets</p>
                <div className="space-y-1.5">
                  {dispatched.map((t, i) => (
                    <div key={i} className="flex items-center gap-2 py-1.5 px-2 bg-green-500/5 border border-green-500/15 rounded-lg">
                      <div className="w-1.5 h-1.5 rounded-full bg-green-400 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        {t.jira_url ? (
                          <a href={t.jira_url} target="_blank" rel="noopener noreferrer"
                            className="text-[12px] font-mono text-veridian-purple-400 hover:text-veridian-purple-200 transition-colors">
                            {t.jira_ticket_id || 'VER-???'}
                          </a>
                        ) : (
                          <span className="text-[12px] font-mono text-white/50">{t.jira_ticket_id || 'Creating…'}</span>
                        )}
                        <span className="text-[11px] text-white/40 ml-2">→ {t.assignee}</span>
                      </div>
                      {t.slack_dm_sent && <span className="text-[10px] text-veridian-purple-400">💬 DM</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Deferred list */}
            {deferred.length > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-white/30 uppercase tracking-widest mb-2">Deferred</p>
                {deferred.map((t, i) => (
                  <div key={i} className="flex items-center gap-2 py-1 text-[12px] text-white/40">
                    <div className="w-1 h-1 rounded-full bg-white/20 flex-shrink-0" />
                    <span className="line-clamp-1">{t.title}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Open Slack button */}
      <div className="mt-4 pt-4 border-t border-white/[0.06]">
        {slackChannels.length > 0 || isComplete ? (
          <a
            href="https://slack.com"
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-ghost w-full py-2.5 text-[13px] font-medium justify-center border-veridian-purple-400/20 text-veridian-purple-200 hover:bg-veridian-purple-600/20"
          >
            <svg className="w-4 h-4 mr-1.5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312zM15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zM15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z"/>
            </svg>
            Open Slack
          </a>
        ) : (
          <button disabled className="btn btn-ghost w-full py-2.5 text-[13px] justify-center opacity-30">
            Open Slack (after dispatch)
          </button>
        )}
      </div>
    </div>
  )
}
