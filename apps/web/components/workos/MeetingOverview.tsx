'use client';

import React from 'react';
import type { WorkOSMeetingContext, WorkOSPhase } from '@/lib/workos-types';

interface MeetingOverviewProps {
  meetingContext?: WorkOSMeetingContext;
  phase: WorkOSPhase;
}

export default function MeetingOverview({ meetingContext, phase }: MeetingOverviewProps) {
  const bullets = meetingContext?.tldr_bullets ?? [];
  const attendees = meetingContext?.attendees ?? [];
  const title = meetingContext?.title || 'Awaiting Transcript Analysis';
  const isLoading = phase === 'INGESTING' || phase === 'EXTRACTING';

  return (
    <div className="flex h-full flex-col rounded-xl border border-white/10 bg-dark-1 p-5 text-white">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-md border border-purple-400/40 bg-purple-500/20 text-xs font-bold text-purple-300">
            1
          </span>
          <h2 className="text-xs font-semibold uppercase tracking-widest text-white/70">
            Meeting Overview
          </h2>
        </div>
        {meetingContext?.date && (
          <span className="font-mono text-[11px] text-white/40">{meetingContext.date}</span>
        )}
      </div>

      {isLoading && bullets.length === 0 ? (
        <div className="flex flex-1 flex-col justify-center gap-3 py-6">
          <div className="h-4 w-3/4 animate-pulse rounded bg-white/10" />
          <div className="h-3 w-full animate-pulse rounded bg-white/10" />
          <div className="h-3 w-5/6 animate-pulse rounded bg-white/10" />
        </div>
      ) : bullets.length === 0 ? (
        <div className="flex flex-1 items-center justify-center py-8 text-center text-sm text-white/35">
          Run a Hinglish or enterprise transcript to view Gnani Evon AI meeting highlights.
        </div>
      ) : (
        <div className="flex flex-1 flex-col justify-between gap-4">
          <div>
            <h3 className="text-base font-semibold text-white">{title}</h3>
            {attendees.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {attendees.map((att) => (
                  <span
                    key={att}
                    className="rounded-full border border-white/10 bg-dark-3 px-2.5 py-0.5 text-[11px] text-sky-1"
                  >
                    {att}
                  </span>
                ))}
              </div>
            )}
            <ul className="mt-3 space-y-2">
              {bullets.map((b, idx) => (
                <li key={idx} className="flex items-start gap-2 text-xs leading-relaxed text-white/80">
                  <span className="mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-purple-400" />
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          </div>

          {meetingContext?.speaker_resolution_scratchpad && (
            <div className="rounded-lg border border-white/10 bg-dark-2 p-2.5 text-[11px] text-white/55">
              <span className="font-semibold text-purple-300">Evon Speaker Context: </span>
              {meetingContext.speaker_resolution_scratchpad}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
