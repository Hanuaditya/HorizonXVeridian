'use client'

// Section 1 — Meeting Overview (top-left)
export default function MeetingOverview({ meetingContext, phase }) {
  const { title, date, attendees = [], tldr_bullets = [] } = meetingContext ?? {}
  const isLoading = !title && phase !== 'IDLE'

  return (
    <div className="flex flex-col h-full">
      {/* Section header */}
      <div className="flex items-center gap-2 mb-4">
        <div className="w-6 h-6 rounded-md bg-veridian-purple-600/30 border border-veridian-purple-400/30 flex items-center justify-center">
          <span className="text-[11px] font-bold text-veridian-purple-400">1</span>
        </div>
        <h2 className="text-[13px] font-semibold text-white/70 uppercase tracking-widest">Meeting Overview</h2>
      </div>

      {isLoading && !title ? (
        <div className="flex-1 space-y-3 animate-pulse">
          <div className="h-5 bg-white/[0.07] rounded w-2/3" />
          <div className="h-3 bg-white/[0.04] rounded w-1/3" />
          <div className="mt-4 space-y-2">
            {[1,2,3].map(i => <div key={i} className="h-3 bg-white/[0.04] rounded" />)}
          </div>
        </div>
      ) : title ? (
        <div className="flex-1 overflow-y-auto space-y-4">
          {/* Title + date */}
          <div>
            <h3 className="text-[16px] font-bold text-white leading-tight">{title}</h3>
            {date && date !== 'Unknown' && (
              <p className="text-[12px] text-white/40 mt-1 font-mono">{date}</p>
            )}
          </div>

          {/* Attendees */}
          {attendees.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold text-white/30 uppercase tracking-widest mb-2">Attendees ({attendees.length})</p>
              <div className="flex flex-wrap gap-1.5">
                {attendees.map((a, i) => (
                  <span key={i} className="px-2 py-0.5 bg-veridian-purple-800/30 border border-veridian-purple-400/15 rounded-full text-[11px] text-veridian-purple-200/80">
                    {a}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* TL;DR Summary */}
          {tldr_bullets.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold text-white/30 uppercase tracking-widest mb-2">Summary</p>
              <div className="space-y-2">
                {tldr_bullets.map((b, i) => (
                  <div key={i} className="flex items-start gap-2.5">
                    <div className="mt-1.5 w-1 h-1 rounded-full bg-veridian-purple-400 flex-shrink-0" />
                    <p className="text-[13px] text-white/75 leading-snug">{b}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {tldr_bullets.length === 0 && (
            <div className="text-[13px] text-white/30 italic">Summary extracting…</div>
          )}
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-[13px] text-white/25 text-center">Meeting overview will appear<br />once the transcript is processed</p>
        </div>
      )}
    </div>
  )
}
