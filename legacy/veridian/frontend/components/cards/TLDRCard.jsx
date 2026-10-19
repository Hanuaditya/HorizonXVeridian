'use client'

import { useState } from 'react'

export default function TLDRCard({ meetingContext }) {
  const { title, date, attendees = [], tldr_bullets = [], not_actioned = [] } = meetingContext ?? {}
  const [showNotActioned, setShowNotActioned] = useState(false)

  if (!title) {
    return (
      <div className="glass-card p-5 animate-pulse">
        <div className="h-3 bg-white/10 rounded w-1/3 mb-3" />
        <div className="h-4 bg-white/10 rounded w-2/3 mb-4" />
        <div className="space-y-2">
          {[1,2,3].map(i => <div key={i} className="h-3 bg-white/[0.06] rounded w-full" />)}
        </div>
      </div>
    )
  }

  return (
    <div className="glass-card p-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="pill pill-purple">📋 Meeting Summary</span>
            {date && <span className="text-[11px] text-white/30 font-mono">{date}</span>}
          </div>
          <h2 className="text-base font-semibold text-white leading-tight">{title}</h2>
        </div>
      </div>

      {/* Attendees */}
      {attendees.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-4">
          {attendees.map((a, i) => (
            <span key={i} className="inline-flex items-center gap-1.5 px-2 py-0.5 bg-white/[0.05] border border-white/[0.08] rounded-full text-[11px] text-white/60">
              <span className="w-4 h-4 rounded-full bg-veridian-purple-600/40 flex items-center justify-center text-[9px] font-bold text-veridian-purple-200">
                {a[0]?.toUpperCase()}
              </span>
              {a}
            </span>
          ))}
        </div>
      )}

      {/* TL;DR Bullets */}
      <div className="space-y-2">
        {tldr_bullets.map((bullet, i) => (
          <div key={i} className="flex items-start gap-2.5">
            <div className="mt-1.5 w-1.5 h-1.5 rounded-full bg-veridian-purple-400 flex-shrink-0" />
            <p className="text-[13px] text-white/80 leading-snug">{bullet}</p>
          </div>
        ))}
      </div>

      {/* Not Actioned collapsible */}
      {not_actioned.length > 0 && (
        <div className="mt-4 border-t border-white/[0.06] pt-3">
          <button
            onClick={() => setShowNotActioned(v => !v)}
            className="flex items-center gap-1.5 text-[11px] text-white/40 hover:text-white/60 transition-colors"
          >
            <svg className={`w-3 h-3 transition-transform ${showNotActioned ? 'rotate-90' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
            {not_actioned.length} topic{not_actioned.length !== 1 ? 's' : ''} discussed, not actioned
          </button>
          {showNotActioned && (
            <ul className="mt-2 space-y-1 pl-3">
              {not_actioned.map((t, i) => (
                <li key={i} className="text-[12px] text-white/40 list-disc ml-2">{t}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
