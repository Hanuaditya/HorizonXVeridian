'use client'

const WORKFLOW_STEPS = [
  { key: 'INGESTING',   label: 'Ingesting',  icon: '📥' },
  { key: 'EXTRACTING',  label: 'Extracting', icon: '🧠' },
  { key: 'FIREWALL',    label: 'Firewall',   icon: '🔒' },
  { key: 'RESOLVING',   label: 'Resolving',  icon: '⚡' },
  { key: 'HITL',        label: 'Review',     icon: '👤' },
  { key: 'DISPATCHING', label: 'Dispatch',   icon: '🚀' },
  { key: 'COMPLETE',    label: 'Done',       icon: '✓'  },
]

const PHASE_ORDER = ['INGESTING','EXTRACTING','FIREWALL','RESOLVING','HITL','DISPATCHING','COMPLETE']

function stepStatus(stepKey, currentPhase) {
  const currentIdx = PHASE_ORDER.indexOf(currentPhase)
  const stepIdx = PHASE_ORDER.indexOf(stepKey)
  if (currentIdx === -1) return 'idle'
  if (stepIdx < currentIdx) return 'done'
  if (stepIdx === currentIdx) return 'active'
  return 'idle'
}

export default function WorkflowHeader({ phase, meetingId }) {
  const isLive = phase && phase !== 'IDLE'

  return (
    <header className="flex-shrink-0 bg-dark-900/90 backdrop-blur-xl border-b border-white/[0.06]">
      {/* Top row */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-white/[0.04]">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-veridian-purple-400 to-veridian-purple-700 flex items-center justify-center shadow-lg shadow-veridian-purple-800/40">
            <span className="text-[13px] font-bold text-white">V</span>
          </div>
          <div>
            <span className="text-[15px] font-bold text-white tracking-tight">WorkOS</span>
            <span className="text-[12px] text-white/30 ml-2 hidden sm:inline">AI Chief of Staff</span>
          </div>
        </div>

        {/* Meeting ID + status */}
        <div className="flex items-center gap-3">
          {meetingId && (
            <span className="text-[11px] text-white/30 font-mono bg-white/[0.04] px-2 py-1 rounded">
              {meetingId}
            </span>
          )}
          {phase === 'HITL' && (
            <span className="flex items-center gap-1.5 text-[12px] text-amber-400 font-medium">
              <span className="w-2 h-2 rounded-full bg-amber-400 pulse-dot" />
              Manager Review Required
            </span>
          )}
          {phase === 'COMPLETE' && (
            <span className="pill pill-green">✨ Workflow Complete</span>
          )}
          {isLive && phase !== 'HITL' && phase !== 'COMPLETE' && (
            <span className="flex items-center gap-1.5 text-[12px] text-veridian-purple-400">
              <span className="w-2 h-2 rounded-full bg-veridian-purple-400 pulse-dot" />
              Processing
            </span>
          )}
        </div>
      </div>

      {/* Agent workflow steps */}
      <div className="flex items-center px-6 py-2.5 gap-0">
        {WORKFLOW_STEPS.map((step, i) => {
          const status = stepStatus(step.key, phase)
          return (
            <div key={step.key} className="flex items-center">
              {/* Step node */}
              <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-all ${
                status === 'active' ? 'bg-veridian-purple-600/20 border border-veridian-purple-400/30' :
                status === 'done' ? 'opacity-60' : 'opacity-25'
              }`}>
                <span className="text-[13px]">{step.icon}</span>
                <span className={`text-[11px] font-medium ${
                  status === 'active' ? 'text-veridian-purple-300' :
                  status === 'done' ? 'text-white/60' : 'text-white/30'
                }`}>
                  {status === 'active' && <span className="mr-1">●</span>}
                  {step.label}
                </span>
              </div>
              {/* Connector arrow */}
              {i < WORKFLOW_STEPS.length - 1 && (
                <div className={`mx-1 text-[11px] transition-all ${
                  stepStatus(WORKFLOW_STEPS[i+1].key, phase) !== 'idle' ? 'text-white/30' : 'text-white/10'
                }`}>→</div>
              )}
            </div>
          )
        })}
      </div>
    </header>
  )
}
