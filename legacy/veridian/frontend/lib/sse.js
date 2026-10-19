'use client'

import { useEffect, useRef, useState, useCallback } from 'react'

export const API_BASE = 'http://localhost:8000'

// ---------------------------------------------------------------------------
// Step definitions (left panel timeline)
// ---------------------------------------------------------------------------
const STEP_DEFS = [
  { id: 'ingest',   label: 'Ingestion',         sublabel: 'Idempotency check' },
  { id: 'extract',  label: 'Extraction',         sublabel: 'Transcript → Tasks' },
  { id: 'firewall', label: 'Agentic Firewall',  sublabel: 'HR · Finance · Security · Capacity' },
  { id: 'resolve',  label: 'Resolution Engine',  sublabel: 'AI policy reframes' },
  { id: 'hitl',     label: 'Manager Review',     sublabel: 'HITL checkpoint' },
  { id: 'dispatch', label: 'Dispatcher',         sublabel: 'Jira + Slack' },
  { id: 'complete', label: 'Complete',           sublabel: 'Workflow done' },
]

const EVENT_PHASE_MAP = {
  processing_started: 'INGESTING',
  task_extracted:     'EXTRACTING',
  firewall_update:    'FIREWALL',
  resolution_ready:   'RESOLVING',
  hitl_ready:         'HITL',
  hitl_resuming:      'DISPATCHING',
  dispatched:         'DISPATCHING',
  complete:           'COMPLETE',
  error:              'ERROR',
}

const PHASE_ORDER = ['INGESTING','EXTRACTING','FIREWALL','RESOLVING','HITL','DISPATCHING','COMPLETE']

function buildSteps(phase, allEvents) {
  const phaseIdx = PHASE_ORDER.indexOf(phase)
  return STEP_DEFS.map((def, i) => {
    const sIdx = PHASE_ORDER.indexOf(PHASE_ORDER[i]) ?? i
    let status = 'idle'
    if (phase === 'ERROR' && sIdx === phaseIdx) status = 'error'
    else if (sIdx < phaseIdx) status = 'done'
    else if (sIdx === phaseIdx) status = 'active'

    let detail
    if (def.id === 'extract') {
      const ev = allEvents.find(e => e.event_type === 'resolution_ready')
      if (ev?.payload?.tasks) detail = `${Object.keys(ev.payload.tasks).length} tasks extracted`
    }
    if (def.id === 'firewall') {
      const ev = allEvents.find(e => e.event_type === 'resolution_ready')
      if (ev?.payload?.resolutions) {
        const flagged = ev.payload.resolutions.filter(r => r.suggested_action !== 'PROCEED').length
        detail = flagged > 0 ? `${flagged} flag(s) raised` : 'All systems clear'
      }
    }
    if (def.id === 'dispatch') {
      const ev = allEvents.find(e => e.event_type === 'dispatched')
      if (ev?.payload?.dispatched_tickets) detail = `${ev.payload.dispatched_tickets.length} ticket(s) dispatched`
    }
    return { ...def, status, detail }
  })
}

// ---------------------------------------------------------------------------
// useAgentStream — SSE connection hook
// ---------------------------------------------------------------------------
export function useAgentStream(threadId) {
  const [agentState, setAgentState] = useState({})
  const [phase, setPhase] = useState('IDLE')
  const [steps, setSteps] = useState(STEP_DEFS.map(d => ({ ...d, status: 'idle' })))
  const [streamError, setStreamError] = useState(null)
  const allEvents = useRef([])

  useEffect(() => {
    if (!threadId) return
    setPhase('IDLE')
    setStreamError(null)
    allEvents.current = []

    const es = new EventSource(`${API_BASE}/api/stream/${threadId}`)

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)
        allEvents.current.push(event)
        const newPhase = EVENT_PHASE_MAP[event.event_type] ?? 'IDLE'
        setPhase(newPhase)
        setSteps(buildSteps(newPhase, allEvents.current))

        if (event.event_type === 'resolution_ready' || event.event_type === 'hitl_ready') {
          setAgentState(prev => ({
            ...prev,
            tasks:           event.payload.tasks ?? {},
            resolutions:     event.payload.resolutions ?? [],
            key_decisions:   event.payload.key_decisions ?? [],
            meeting_context: event.payload.meeting_context ?? {},
            meeting_id:      event.payload.meeting_id,
            thread_id:       threadId,
          }))
        }
        if (event.event_type === 'dispatched') {
          setAgentState(prev => ({
            ...prev,
            dispatched_tickets: event.payload.dispatched_tickets ?? [],
          }))
        }
        if (event.event_type === 'error') {
          setStreamError(event.payload.error ?? 'Unknown graph error')
          es.close()
        }
        if (event.event_type === 'complete') {
          es.close()
        }
      } catch { /* ignore parse errors */ }
    }

    es.onerror = () => {
      setStreamError('Connection lost. Refresh to retry.')
      es.close()
    }

    return () => es.close()
  }, [threadId])

  return { agentState, phase, steps, streamError }
}

// ---------------------------------------------------------------------------
// useSubmitMeeting
// ---------------------------------------------------------------------------
export function useSubmitMeeting() {
  const [threadId, setThreadId] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  const submit = useCallback(async (meetingId, transcript) => {
    setSubmitting(true)
    setSubmitError(null)
    try {
      const res = await fetch(`${API_BASE}/api/meeting-ended`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ meeting_id: meetingId, transcript }),
      })
      if (!res.ok) throw new Error(`Server returned ${res.status}`)
      const data = await res.json()
      setThreadId(data.thread_id)
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }, [])

  return { threadId, submitting, submitError, submit }
}

// ---------------------------------------------------------------------------
// useHITLResume
// ---------------------------------------------------------------------------
export function useHITLResume() {
  const [resuming, setResuming] = useState(false)
  const [resumeError, setResumeError] = useState(null)

  const resume = useCallback(async (threadId, hitlDecisions) => {
    setResuming(true)
    setResumeError(null)
    try {
      const res = await fetch(`${API_BASE}/api/hitl-resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: threadId, hitl_decisions: hitlDecisions }),
      })
      if (!res.ok) throw new Error(`Server returned ${res.status}`)
    } catch (err) {
      setResumeError(err.message)
    } finally {
      setResuming(false)
    }
  }, [])

  return { resuming, resumeError, resume }
}
