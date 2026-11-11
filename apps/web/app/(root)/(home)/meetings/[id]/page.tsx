'use client';

import React, { use, useEffect, useState } from 'react';
import Link from 'next/link';
import type { TranscriptSegment } from '@/types/contracts';
import type { WorkOSThreadState } from '@/lib/workos-types';

interface StoredMeetingDetail {
  meeting_id: string;
  provider?: string;
  language?: string;
  dubbed_url?: string;
  summary?: string;
  chapters?: Array<{ time: string; title: string }>;
  segments?: TranscriptSegment[];
  workos_ack?: { thread_id?: string; status?: string };
}

const DEMO_DETAIL: StoredMeetingDetail = {
  meeting_id: 'demo-hinglish-showcase',
  provider: 'gnani_prisma (Gnani Prisma V3.0)',
  language: 'hi-en',
  dubbed_url: 'demo://cloudinary/dubbed/demo-hinglish.mp4',
  summary:
    'Hinglish engineering sync covering Elastic cluster AWS production rollout, Jason paternity leave handover to Josh Lambert, SEC-POL-089 14-day staging compliance rule, and Rs 2.5 Lakhs Q4 compute budget shortfall.',
  chapters: [
    { time: '00:00', title: 'Agenda & Elastic Search rollout assignment' },
    { time: '00:30', title: 'HR leave alert: Arjun Rao on paternity leave' },
    { time: '01:05', title: 'Security compliance: SEC-POL-089 14-day staging soak' },
    { time: '01:25', title: 'Finance alert: Compute infra budget Rs 0 remaining' },
  ],
  segments: [
    { speaker: 'SPEAKER_01', speaker_user_id: 'user_demo_dov', start: 12.5, end: 28.0, text: 'First, Jason, please deploy the Elastic search cluster directly to production by Thursday.' },
    { speaker: 'SPEAKER_02', speaker_user_id: 'user_demo_amit', start: 28.5, end: 42.0, text: 'Par Dov bhai, Jason toh agle Monday tak paternity leave pe hai!' },
    { speaker: 'SPEAKER_01', speaker_user_id: 'user_demo_dov', start: 42.5, end: 62.0, text: 'Oh right. Josh, can you take that over and deploy it directly to AWS production?' },
    { speaker: 'SPEAKER_03', speaker_user_id: 'user_demo_scott', start: 62.5, end: 82.0, text: 'Wait, our staging policy says any major database upgrade needs at least 14 days bake time in staging first.' },
    { speaker: 'SPEAKER_02', speaker_user_id: 'user_demo_amit', start: 98.5, end: 116.0, text: 'Hamara compute budget for this quarter is already 0.' },
  ],
};

export default function UnifiedMeetingDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [detail, setDetail] = useState<StoredMeetingDetail>(DEMO_DETAIL);
  const [threadState, setThreadState] = useState<WorkOSThreadState | null>(null);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const raw = window.sessionStorage.getItem(`hv_meeting_${id}`);
      if (raw) {
        try {
          const parsed = JSON.parse(raw) as StoredMeetingDetail;
          setDetail(parsed);
          if (parsed.workos_ack?.thread_id) {
            fetch(`/api/workos/threads/${encodeURIComponent(parsed.workos_ack.thread_id)}/state`)
              .then((r) => (r.ok ? r.json() : null))
              .then((s) => s && setThreadState(s))
              .catch(() => {});
          }
          return;
        } catch {
          // Fall back cleanly
        }
      }
    }
    setDetail((prev) => ({ ...prev, meeting_id: id }));
  }, [id]);

  return (
    <section className="flex flex-col gap-6 text-white">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <span className="font-mono text-xs text-purple-300">
            Meeting ID: {detail.meeting_id} · Provider: {detail.provider || 'gnani_prisma'} ({detail.language || 'hi-en'})
          </span>
          <h1 className="mt-1 text-3xl font-bold">Unified Meeting & WorkOS Dossier</h1>
        </div>
        <Link
          href="/workos"
          className="rounded-lg bg-blue-1 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-600"
        >
          Open in WorkOS Hub
        </Link>
      </div>

      {/* Video / Dubbing Comparison */}
      <div className="grid gap-5 md:grid-cols-2">
        <div className="rounded-xl border border-white/10 bg-dark-1 p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
            Original Meeting Recording
          </h2>
          <div className="mt-3 flex h-44 items-center justify-center rounded-lg border border-white/10 bg-dark-2 text-xs text-white/50">
            Original Stream.io / Audio Track ({detail.language || 'hi-en'})
          </div>
        </div>
        <div className="rounded-xl border border-purple-500/30 bg-dark-1 p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-purple-300">
            Gnani Timbre Dubbed Output
          </h2>
          <div className="mt-3 flex h-44 flex-col items-center justify-center rounded-lg border border-white/10 bg-dark-2 p-4 text-center">
            <p className="font-mono text-xs text-emerald-300">
              {detail.dubbed_url || 'Dubbing ready when generated via /meetings'}
            </p>
            <p className="mt-2 text-[11px] text-white/50">
              Timestamp-aligned dubbed audio track generated by Gnani Timbre + MoviePy drift guard.
            </p>
          </div>
        </div>
      </div>

      {/* Summary + Chapters + Diarized Transcript */}
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="rounded-xl border border-white/10 bg-dark-1 p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
            AI Summary & Chapters
          </h2>
          <p className="mt-3 text-sm leading-relaxed text-white/85">{detail.summary}</p>
          <div className="mt-4 space-y-2 border-t border-white/10 pt-3">
            {(detail.chapters || []).map((c, idx) => (
              <div key={idx} className="flex items-center gap-3 text-xs">
                <span className="rounded bg-dark-3 px-2 py-0.5 font-mono text-sky-1">{c.time}</span>
                <span className="text-white/80">{c.title}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-dark-1 p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
            Gnani Prisma Code-Mixed Diarized Transcript
          </h2>
          <div className="mt-3 max-h-72 space-y-2.5 overflow-y-auto pr-1">
            {(detail.segments || []).map((seg, i) => (
              <div key={i} className="rounded-lg border border-white/10 bg-dark-2 p-3 text-xs">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-semibold text-purple-300">
                    {seg.speaker} {seg.speaker_user_id ? `(${seg.speaker_user_id})` : '(Unmapped)'}
                  </span>
                  <span className="font-mono text-white/45">
                    {seg.start.toFixed(1)}s – {seg.end.toFixed(1)}s
                  </span>
                </div>
                <p className="mt-1 text-white/85">{seg.text}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {threadState && (
        <div className="rounded-xl border border-emerald-500/25 bg-dark-1 p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-emerald-300">
            Linked WorkOS Thread ({threadState.thread_id}) · Phase: {threadState.phase}
          </h2>
          <p className="mt-1 text-xs text-white/70">
            Dispatched Tickets: {(threadState.dispatched_tickets || []).length}
          </p>
        </div>
      )}
    </section>
  );
}
