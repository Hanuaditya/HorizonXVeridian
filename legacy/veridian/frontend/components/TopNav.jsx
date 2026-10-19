'use client'

const PHASE_LABELS = {
  IDLE:        { label: 'Ready', color: 'text-white/30' },
  INGESTING:   { label: 'Ingesting transcript…', color: 'text-veridian-purple-400' },
  EXTRACTING:  { label: 'Extracting tasks…', color: 'text-veridian-purple-400' },
  FIREWALL:    { label: 'Agentic Firewall running…', color: 'text-amber-400' },
  RESOLVING:   { label: 'AI resolving conflicts…', color: 'text-amber-400' },
  HITL:        { label: '⏸ Paused — Manager Review Required', color: 'text-amber-400' },
  DISPATCHING: { label: 'Dispatching to Jira + Slack…', color: 'text-veridian-purple-400' },
  COMPLETE:    { label: '✨ Workflow Complete', color: 'text-green-400' },
  ERROR:       { label: '✗ Error — See console', color: 'text-red-400' },
}

export default function TopNav({ phase, meetingId, streamError }) {
  const phaseInfo = PHASE_LABELS[phase] ?? PHASE_LABELS.IDLE

  return (
    <header className="h-12 flex-shrink-0 flex items-center px-5 border-b border-white/[0.06] bg-dark-900/80 backdrop-blur-xl">
      {/* Logo */}
      <div className="flex items-center gap-2.5 mr-6">
        <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-veridian-purple-400 to-veridian-purple-600 flex items-center justify-center">
          <span className="text-[11px] font-bold text-white">V</span>
        </div>
        <span className="text-[14px] font-semibold text-white">Veridian <span className="text-veridian-purple-400">WorkOS</span></span>
      </div>

      {/* Phase breadcrumb */}
      <div className="flex items-center gap-2 flex-1">
        {phase !== 'IDLE' && <div className="h-3 w-px bg-white/10" />}
        {phase !== 'IDLE' && meetingId && (
          <span className="text-[11px] text-white/30 font-mono">meeting:{meetingId}</span>
        )}
        {phase !== 'IDLE' && <div className="h-3 w-px bg-white/10" />}
        <div className="flex items-center gap-1.5">
          {(phase === 'INGESTING' || phase === 'EXTRACTING' || phase === 'FIREWALL' || phase === 'RESOLVING' || phase === 'DISPATCHING') && (
            <div className="w-1.5 h-1.5 rounded-full bg-veridian-purple-400 pulse-dot" />
          )}
          {phase === 'HITL' && (
            <div className="w-1.5 h-1.5 rounded-full bg-amber-400 pulse-dot" />
          )}
          <span className={`text-[12px] font-medium ${phaseInfo.color}`}>{phaseInfo.label}</span>
        </div>
        {streamError && (
          <span className="ml-3 text-[11px] text-red-400 bg-red-400/10 border border-red-400/20 px-2 py-0.5 rounded">
            {streamError}
          </span>
        )}
      </div>

      {/* Right: badge */}
      <div className="flex items-center gap-3">
        <span className="pill pill-gray">AI Chief of Staff</span>
      </div>
    </header>
  )
}
