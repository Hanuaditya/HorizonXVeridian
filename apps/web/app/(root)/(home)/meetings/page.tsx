'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { OrgOnboardingGuard } from '@/providers/AuthBridge';

export default function MeetingsHubPage() {
  return (
    <OrgOnboardingGuard pageName="Unified Meetings Hub">
      <MeetingsHubContent />
    </OrgOnboardingGuard>
  );
}

function MeetingsHubContent() {
  const router = useRouter();
  const [videoUrl, setVideoUrl] = useState('demo://hinglish_sprint_sync.mp4');
  const [title, setTitle] = useState('Hinglish Engineering Sync');
  const [running, setRunning] = useState(false);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRunGnaniPipeline = async () => {
    setRunning(true);
    setError(null);
    setJobStatus('Submitting async Gnani Prisma V3.0 + Timbre job...');
    try {
      const submitRes = await fetch('/api/media/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recording_url: videoUrl,
          title,
          target_lang: 'en',
          generate_dub: true,
          emit_meeting_ended: true,
        }),
      });
      const job = await submitRes.json();
      if (!submitRes.ok) {
        throw new Error(job.error || `Media service error (${submitRes.status})`);
      }

      setJobStatus(`Job ${job.job_id} queued (${job.status}). Polling...`);

      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 400));
        const pollRes = await fetch(`/api/media/jobs?jobId=${encodeURIComponent(job.job_id)}`);
        if (!pollRes.ok) continue;
        const polled = await pollRes.json();
        setJobStatus(`Job ${job.job_id}: ${polled.status}`);
        if (polled.status === 'COMPLETED') {
          if (typeof window !== 'undefined') {
            window.sessionStorage.setItem(
              `hv_meeting_${polled.meeting_id}`,
              JSON.stringify(polled.result)
            );
          }
          router.push(`/meetings/${encodeURIComponent(polled.meeting_id)}`);
          return;
        }
        if (polled.status === 'FAILED') {
          throw new Error(polled.error || 'Media job failed');
        }
      }
      throw new Error('Timed out polling media job');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to run Gnani pipeline');
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="flex flex-col gap-6 text-white">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Unified Meetings Hub</h1>
          <p className="mt-1 text-sm text-white/60">
            Capture calls via Stream.io, transcribe Hinglish with Gnani Prisma V3.0, dub via Gnani
            Timbre, and view WorkOS compliance handoffs.
          </p>
        </div>
        <div className="flex gap-3">
          <Link
            href="/recordings"
            className="rounded-lg border border-white/15 bg-dark-1 px-4 py-2 text-sm font-medium text-white hover:bg-dark-3"
          >
            Legacy Recordings
          </Link>
          <Link
            href="/workos"
            className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-semibold text-white hover:bg-purple-500"
          >
            Open WorkOS Hub
          </Link>
        </div>
      </div>

      <div className="rounded-xl border border-white/10 bg-dark-1 p-6">
        <h2 className="text-lg font-bold">Run Gnani Prisma V3.0 + Timbre Media Pipeline</h2>
        <p className="mt-1 text-xs text-white/55">
          Processes any video/recording URL (or uses `demo://hinglish_sprint_sync.mp4` offline),
          produces speaker-attributed transcripts, dubs audio, and triggers `meeting.ended` to
          WorkOS.
        </p>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs text-white/70">Meeting Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-lg border border-white/15 bg-dark-2 px-3 py-2 text-sm text-white"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-white/70">Recording / Video URL</label>
            <input
              type="text"
              value={videoUrl}
              onChange={(e) => setVideoUrl(e.target.value)}
              className="w-full rounded-lg border border-white/15 bg-dark-2 px-3 py-2 font-mono text-xs text-sky-1"
            />
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-4">
          <button
            type="button"
            disabled={running}
            onClick={handleRunGnaniPipeline}
            className="rounded-lg bg-blue-1 px-5 py-2.5 text-sm font-bold text-white transition hover:bg-blue-600 disabled:opacity-50"
          >
            {running ? 'Processing Audio & Dubbing...' : 'Process with Gnani Prisma + Timbre'}
          </button>
          <Link
            href="/meetings/demo-hinglish-showcase"
            className="rounded-lg border border-white/15 bg-dark-3 px-4 py-2.5 text-sm font-medium text-sky-1 hover:bg-white/10"
          >
            Preview Unified Meeting Detail Page
          </Link>
        </div>

        {jobStatus && (
          <p className="mt-3 font-mono text-xs text-emerald-300">{jobStatus}</p>
        )}
        {error && (
          <p className="mt-3 rounded border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
            {error} — Make sure Flask media service is running on port 5001.
          </p>
        )}
      </div>
    </section>
  );
}

