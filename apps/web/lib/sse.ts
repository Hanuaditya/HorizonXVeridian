'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { SSEEventEnvelope } from '@/types/contracts';
import type { WorkOSPhase, WorkOSThreadState } from '@/lib/workos-types';

const EVENT_TO_PHASE: Record<string, WorkOSPhase> = {
  processing_started: 'INGESTING',
  resolution_ready: 'RESOLVING',
  hitl_ready: 'HITL',
  dispatched: 'DISPATCHING',
  tracker_update: 'COMPLETE',
  complete: 'COMPLETE',
  error: 'ERROR',
};

export interface StepItem {
  id: string;
  label: string;
  sublabel: string;
  status: 'idle' | 'active' | 'done' | 'error';
}

const STEP_DEFS = [
  { id: 'ingest', label: 'Ingestion & Speaker Map', sublabel: 'Hinglish STT -> Assignees' },
  { id: 'firewall', label: '4-Way Firewall', sublabel: 'HR · Capacity · Security · Finance' },
  { id: 'resolve', label: 'Evon 30B Resolver', sublabel: 'Policy remediation proposals' },
  { id: 'hitl', label: 'Manager HITL Gate', sublabel: 'Approve / Override checkpoint' },
  { id: 'dispatch', label: 'Jira + Slack Dispatch', sublabel: 'Idempotent ticket creation' },
  { id: 'complete', label: 'Closed-Loop Ready', sublabel: 'Audit trail persisted' },
];

const PHASE_ORDER: WorkOSPhase[] = [
  'INGESTING',
  'FIREWALL',
  'RESOLVING',
  'HITL',
  'DISPATCHING',
  'COMPLETE',
];

function computeSteps(phase: WorkOSPhase): StepItem[] {
  const idx = PHASE_ORDER.indexOf(phase);
  return STEP_DEFS.map((def, i) => {
    let status: StepItem['status'] = 'idle';
    if (phase === 'ERROR' && i === Math.max(0, idx)) status = 'error';
    else if (idx > i || phase === 'COMPLETE') status = 'done';
    else if (idx === i) status = 'active';
    return { ...def, status };
  });
}

export function useAgentStream(threadId: string | null) {
  const [agentState, setAgentState] = useState<WorkOSThreadState>({});
  const [phase, setPhase] = useState<WorkOSPhase>('IDLE');
  const [streamError, setStreamError] = useState<string | null>(null);
  const lastEventIdRef = useRef<string | null>(null);

  const fetchSnapshot = useCallback(async (tid: string) => {
    try {
      const res = await fetch(`/api/workos/threads/${encodeURIComponent(tid)}/state`);
      if (!res.ok) return;
      const snap: WorkOSThreadState = await res.json();
      setAgentState((prev) => ({ ...prev, ...snap }));
      if (snap.phase) {
        setPhase(snap.phase);
      }
    } catch {
      // Handled by caller banner if persistent
    }
  }, []);

  useEffect(() => {
    if (!threadId) return;

    setPhase('INGESTING');
    setStreamError(null);
    lastEventIdRef.current = null;

    let closed = false;
    let es: EventSource | null = null;

    // Fetch current REST snapshot immediately so reconnects/refreshes recover state
    fetchSnapshot(threadId);

    const connect = () => {
      if (closed) return;
      const qs = lastEventIdRef.current
        ? `?lastEventId=${encodeURIComponent(lastEventIdRef.current)}`
        : '';
      es = new EventSource(`/api/workos/stream/${encodeURIComponent(threadId)}${qs}`);

      es.onmessage = (evt) => {
        if (evt.lastEventId) {
          lastEventIdRef.current = evt.lastEventId;
        }
        try {
          const envelope = JSON.parse(evt.data) as SSEEventEnvelope<Record<string, unknown>>;
          const nextPhase = EVENT_TO_PHASE[envelope.event_type] ?? 'INGESTING';
          setPhase(nextPhase);

          const p = envelope.payload || {};
          if (envelope.event_type === 'resolution_ready' || envelope.event_type === 'hitl_ready') {
            setAgentState((prev) => ({
              ...prev,
              thread_id: threadId,
              meeting_id: (p.meeting_id as string) ?? prev.meeting_id,
              tasks: (p.tasks as WorkOSThreadState['tasks']) ?? prev.tasks,
              resolutions: (p.resolutions as WorkOSThreadState['resolutions']) ?? prev.resolutions,
              key_decisions: (p.key_decisions as WorkOSThreadState['key_decisions']) ?? prev.key_decisions,
              meeting_context: (p.meeting_context as WorkOSThreadState['meeting_context']) ?? prev.meeting_context,
              immediate_alerts:
                (p.immediate_alerts as WorkOSThreadState['immediate_alerts']) ?? prev.immediate_alerts,
              slack_feed: (p.slack_feed as WorkOSThreadState['slack_feed']) ?? prev.slack_feed,
            }));
          } else if (envelope.event_type === 'dispatched' || envelope.event_type === 'tracker_update') {
            setAgentState((prev) => ({
              ...prev,
              tasks: (p.tasks as WorkOSThreadState['tasks']) ?? prev.tasks,
              dispatched_tickets:
                (p.dispatched_tickets as WorkOSThreadState['dispatched_tickets']) ??
                prev.dispatched_tickets,
              slack_feed: (p.slack_feed as WorkOSThreadState['slack_feed']) ?? prev.slack_feed,
              approver_user_id: (p.approved_by as string) ?? prev.approver_user_id,
            }));
          } else if (envelope.event_type === 'error') {
            setStreamError(String(p.error ?? 'Pipeline error'));
            es?.close();
          } else if (envelope.event_type === 'complete') {
            fetchSnapshot(threadId);
            es?.close();
          }
        } catch {
          // Ignore malformed keepalive frames
        }
      };

      es.onerror = () => {
        es?.close();
        if (!closed) {
          // Recover via REST state fallback if stream closed after completion or network blip
          fetchSnapshot(threadId);
        }
      };
    };

    connect();

    // Gentle background sync (10s) only when document is visible so live Slack DM replies reflect in UI
    const syncTimer = setInterval(() => {
      if (!closed && typeof document !== 'undefined' && !document.hidden) {
        fetchSnapshot(threadId);
      }
    }, 10000);

    return () => {
      closed = true;
      clearInterval(syncTimer);
      es?.close();
    };
  }, [threadId, fetchSnapshot]);

  return {
    agentState,
    phase,
    steps: computeSteps(phase),
    streamError,
    refreshState: () => (threadId ? fetchSnapshot(threadId) : Promise.resolve()),
  };
}

export function useHITLResume() {
  const [resuming, setResuming] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);

  const resume = useCallback(async (threadId: string, decisions: Record<string, string>) => {
    setResuming(true);
    setResumeError(null);
    try {
      const res = await fetch('/api/workos/hitl-resume', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: threadId, hitl_decisions: decisions }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.error || `HITL resume failed (${res.status})`);
      }
      return data;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error resuming HITL';
      setResumeError(msg);
      throw err;
    } finally {
      setResuming(false);
    }
  }, []);

  return { resume, resuming, resumeError };
}

