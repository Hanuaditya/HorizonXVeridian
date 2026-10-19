'use client'

import { useState } from 'react'

export default function DecisionsCard({ keyDecisions = [] }) {
  const [expanded, setExpanded] = useState(null)

  if (keyDecisions.length === 0) return null

  return (
    <div className="glass-card p-5 animate-fade-in">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="pill pill-purple">⚖️ Decisions Ledger</span>
          <span className="text-[11px] text-white/30">{keyDecisions.length} recorded</span>
        </div>
      </div>

      <div className="space-y-2">
        {keyDecisions.map((d, i) => (
          <div key={i} className="glass-card-alt p-3 cursor-pointer hover:border-veridian-purple-400/20 transition-all" onClick={() => setExpanded(expanded === i ? null : i)}>
            <div className="flex items-start gap-2.5">
              <div className="mt-1.5 w-1.5 h-1.5 rounded-full bg-veridian-purple-400/60 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-[13px] text-white/85 leading-snug font-medium">{d.decision}</p>
                {expanded === i && d.context_quote && (
                  <p className="mt-2 text-[11px] text-white/40 italic border-l-2 border-veridian-purple-400/30 pl-2 leading-snug">
                    "{d.context_quote}"
                  </p>
                )}
              </div>
              <svg className={`w-3.5 h-3.5 text-white/30 flex-shrink-0 mt-1 transition-transform ${expanded === i ? 'rotate-90' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
