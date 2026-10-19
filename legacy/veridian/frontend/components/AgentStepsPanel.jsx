'use client'

export default function AgentStepsPanel({ steps, phase }) {
  const total = steps.length
  const doneCount = steps.filter(s => s.status === 'done').length
  const progress = Math.round((doneCount / total) * 100)

  const iconFor = (status) => {
    if (status === 'done')   return <DoneIcon />
    if (status === 'active') return <ActiveIcon />
    if (status === 'error')  return <ErrorIcon />
    if (status === 'warn')   return <WarnIcon />
    return <IdleIcon />
  }

  return (
    <aside className="flex flex-col h-full glass-card p-0 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/[0.06]">
        <p className="text-[11px] font-semibold text-veridian-purple-200 uppercase tracking-widest">
          Agent Pipeline
        </p>
        <p className="text-xs text-white/30 mt-0.5">
          {phase === 'IDLE' ? 'Waiting for transcript…' : `Phase: ${phase}`}
        </p>
      </div>

      {/* Steps */}
      <div className="flex-1 overflow-y-auto py-2">
        {steps.map((step, i) => (
          <div key={step.id} className="relative">
            {/* Connector line */}
            {i < steps.length - 1 && (
              <div className="absolute left-[27px] top-[38px] w-px h-[16px] bg-white/[0.07]" />
            )}

            <div className={`flex items-start gap-3 px-4 py-2.5 mx-2 rounded-lg transition-all duration-200 ${
              step.status === 'active' ? 'bg-veridian-purple-800/30 border border-veridian-purple-400/20' : ''
            }`}>
              <div className="mt-0.5 flex-shrink-0">{iconFor(step.status)}</div>
              <div className="min-w-0 flex-1">
                <p className={`text-[13px] font-medium leading-tight ${
                  step.status === 'active' ? 'text-veridian-purple-200' :
                  step.status === 'done'   ? 'text-white/80' :
                  step.status === 'error'  ? 'text-red-400' :
                  'text-white/30'
                }`}>
                  {step.label}
                  {step.status === 'active' && (
                    <span className="inline-block ml-2 w-1 h-1 rounded-full bg-veridian-purple-400 pulse-dot" />
                  )}
                </p>
                <p className={`text-[11px] mt-0.5 ${step.status !== 'idle' ? 'text-white/40' : 'text-white/20'}`}>
                  {step.sublabel}
                </p>
                {step.detail && step.status === 'done' && (
                  <p className="text-[10px] text-veridian-green-400/80 mt-0.5 font-mono">
                    ↳ {step.detail}
                  </p>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div className="px-4 py-3 border-t border-white/[0.06]">
        <div className="flex justify-between items-center mb-1.5">
          <span className="text-[10px] text-white/30 font-medium">Progress</span>
          <span className="text-[10px] text-veridian-purple-400 font-mono">{progress}%</span>
        </div>
        <div className="h-1 bg-white/[0.06] rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-veridian-purple-600 to-veridian-purple-400 rounded-full transition-all duration-700"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
    </aside>
  )
}

function DoneIcon() {
  return (
    <div className="w-7 h-7 rounded-full bg-veridian-green-500/15 border border-veridian-green-500/30 flex items-center justify-center">
      <svg className="w-3.5 h-3.5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
      </svg>
    </div>
  )
}

function ActiveIcon() {
  return (
    <div className="w-7 h-7 rounded-full bg-veridian-purple-600/20 border border-veridian-purple-400/40 flex items-center justify-center">
      <div className="w-2 h-2 rounded-full bg-veridian-purple-400 pulse-dot" />
    </div>
  )
}

function IdleIcon() {
  return (
    <div className="w-7 h-7 rounded-full bg-white/[0.04] border border-white/[0.07] flex items-center justify-center">
      <div className="w-1.5 h-1.5 rounded-full bg-white/20" />
    </div>
  )
}

function ErrorIcon() {
  return (
    <div className="w-7 h-7 rounded-full bg-red-500/15 border border-red-500/30 flex items-center justify-center">
      <svg className="w-3.5 h-3.5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
      </svg>
    </div>
  )
}

function WarnIcon() {
  return (
    <div className="w-7 h-7 rounded-full bg-amber-500/15 border border-amber-500/30 flex items-center justify-center">
      <svg className="w-3.5 h-3.5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
      </svg>
    </div>
  )
}
