'use client'

import { useState, useEffect } from 'react'
import { useAgentStream, useHITLResume } from '../lib/sse'

import WorkflowHeader  from '../components/v2/WorkflowHeader'
import MeetingOverview from '../components/v2/MeetingOverview'
import DecisionsMade   from '../components/v2/DecisionsMade'
import ApprovalsPanel  from '../components/v2/ApprovalsPanel'
import ProgressTracker from '../components/v2/ProgressTracker'

// ─────────────────────────────────────────────────────────────
// Auto-loader: reads transcript.txt → POSTs to FastAPI
// ─────────────────────────────────────────────────────────────
function AutoLoader({ onStarted, onError }) {
  const [status, setStatus] = useState('loading')
  const [chars,  setChars]  = useState(0)
  const [errMsg, setErrMsg] = useState('')

  useEffect(() => {
    async function run() {
      try {
        setStatus('loading')
        const tRes = await fetch('/api/transcript')
        if (!tRes.ok) throw new Error(`Could not read transcript (${tRes.status})`)
        const { transcript, chars: c } = await tRes.json()
        setChars(c)

        setStatus('submitting')
        const uniqueId = `demo-meeting-${Date.now()}`
        const mRes = await fetch('http://localhost:8000/api/meeting-ended', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ meeting_id: uniqueId, transcript }),
        })
        if (!mRes.ok) throw new Error(`FastAPI error (${mRes.status})`)
        const data = await mRes.json()
        onStarted(data.thread_id, data.meeting_id)
      } catch (err) {
        setErrMsg(err.message)
        setStatus('error')
        onError(err.message)
      }
    }
    run()
  }, [])

  return (
    <div className="h-screen flex flex-col bg-dark-900">
      {/* Mini header */}
      <div className="flex-shrink-0 border-b border-white/[0.06] px-6 py-3 flex items-center gap-3">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-veridian-purple-400 to-veridian-purple-700 flex items-center justify-center">
          <span className="text-[13px] font-bold text-white">V</span>
        </div>
        <span className="text-[15px] font-bold text-white">WorkOS</span>
        <span className="text-[12px] text-white/30">AI Chief of Staff</span>
      </div>

      {/* Centred content */}
      <div className="flex-1 flex items-center justify-center">
        <div className="glass-card p-10 flex flex-col items-center gap-6 w-[380px] text-center">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-veridian-purple-400 to-veridian-purple-800 flex items-center justify-center shadow-lg shadow-veridian-purple-800/40">
            <span className="text-2xl font-bold text-white">V</span>
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">Veridian WorkOS</h1>
            <p className="text-[13px] text-white/40 mt-1">Starting pipeline…</p>
          </div>

          {(status === 'loading' || status === 'submitting') && (
            <>
              <div className="w-9 h-9 rounded-full border-2 border-veridian-purple-400/30 border-t-veridian-purple-400 animate-spin" />
              <div className="space-y-1">
                <p className="text-[13px] text-white/70 font-medium">
                  {status === 'loading' ? 'Reading transcript.txt…' : 'Firing Graph A…'}
                </p>
                {chars > 0 && (
                  <p className="text-[11px] text-white/35 font-mono">{chars.toLocaleString()} chars</p>
                )}
              </div>
            </>
          )}

          {status === 'error' && (
            <div className="w-full p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-[13px] text-red-400 text-left">
              <p className="font-semibold mb-1">Pipeline failed to start</p>
              <p className="text-[12px] opacity-80">{errMsg}</p>
              <p className="text-[11px] text-white/30 mt-2">Ensure FastAPI is running on port 8000</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// Main Dashboard — 4-section 2×2 wireframe layout
// ─────────────────────────────────────────────────────────────
function Dashboard({ threadId, meetingId, agentState, phase, streamError, resuming, resumeError, onResume }) {
  const tasks            = agentState?.tasks            ?? {}
  const resolutions      = agentState?.resolutions      ?? []
  const keyDecisions     = agentState?.key_decisions    ?? []
  const meetingContext   = agentState?.meeting_context  ?? {}
  const dispatchedTickets = agentState?.dispatched_tickets ?? []

  return (
    <div className="h-screen flex flex-col bg-dark-900 overflow-hidden">
      {/* ── Top: Workflow header ─────────────────────────────── */}
      <WorkflowHeader phase={phase} meetingId={meetingId} />

      {/* SSE error banner */}
      {streamError && (
        <div className="flex-shrink-0 bg-red-500/10 border-b border-red-500/20 text-red-400 text-[12px] px-6 py-2">
          Stream error: {streamError} — refresh to reconnect
        </div>
      )}

      {/* ── 2×2 Grid ─────────────────────────────────────────── */}
      <div className="flex-1 grid grid-cols-2 grid-rows-2 gap-3 p-4 overflow-hidden min-h-0">

        {/* ① Meeting Overview — top-left */}
        <div className="glass-card p-5 overflow-hidden">
          <MeetingOverview meetingContext={meetingContext} phase={phase} />
        </div>

        {/* ② Decisions Made — top-right */}
        <div className="glass-card p-5 overflow-hidden">
          <DecisionsMade
            tasks={tasks}
            resolutions={resolutions}
            keyDecisions={keyDecisions}
          />
        </div>

        {/* ③ Approvals HITL — bottom-left */}
        <div className={`glass-card p-5 overflow-hidden transition-all duration-500 ${
          phase === 'HITL' ? 'ring-1 ring-amber-400/30 shadow-lg shadow-amber-400/5' : ''
        }`}>
          <ApprovalsPanel
            tasks={tasks}
            resolutions={resolutions}
            phase={phase}
            threadId={threadId}
            onResume={onResume}
            resuming={resuming}
          />
          {resumeError && (
            <p className="text-[11px] text-red-400 mt-2">{resumeError}</p>
          )}
        </div>

        {/* ④ Jira & Progress Tracker — bottom-right */}
        <div className={`glass-card p-5 overflow-hidden transition-all duration-500 ${
          phase === 'COMPLETE' ? 'ring-1 ring-green-400/20 shadow-lg shadow-green-400/5' : ''
        }`}>
          <ProgressTracker
            dispatchedTickets={dispatchedTickets}
            phase={phase}
          />
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────
// Root Page
// ─────────────────────────────────────────────────────────────
export default function Home() {
  const [threadId,  setThreadId]  = useState(null)
  const [meetingId, setMeetingId] = useState(null)
  const [startError, setStartError] = useState(null)

  const { agentState, phase, steps, streamError } = useAgentStream(threadId)
  const { resuming, resumeError, resume } = useHITLResume()

  const handleStarted = (tid, mid) => {
    setThreadId(tid)
    setMeetingId(mid)
  }

  if (!threadId) {
    return <AutoLoader onStarted={handleStarted} onError={setStartError} />
  }

  return (
    <Dashboard
      threadId={threadId}
      meetingId={meetingId}
      agentState={agentState}
      phase={phase}
      streamError={streamError}
      resuming={resuming}
      resumeError={resumeError}
      onResume={resume}
    />
  )
}
