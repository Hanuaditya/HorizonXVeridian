'use client';

import MeetingSetup from '@/components/shared/MeetingSetup';
import MeetingRoom from '@/components/shared/MeetingRoom';
import { useAppUser } from '@/providers/AuthBridge';
import { StreamCall, StreamTheme } from '@stream-io/video-react-sdk';
import React, { useState } from 'react';
import { useGetCallById } from '@/hooks/useGetCallById';
import Loader from '@/components/shared/Loader';
import Link from 'next/link';

const Meeting = ({ params }: { params: Promise<{ id: string }> }) => {
  const { id } = React.use(params);

  const { isLoaded } = useAppUser();
  const [isSetupComplete, setIsSetupComplete] = useState(false);
  const { call, isCallLoading } = useGetCallById(id);

  if (!isLoaded || isCallLoading) return <Loader />;

  if (!call) {
    return (
      <main className="flex h-screen w-full flex-col items-center justify-center gap-4 bg-dark-2 p-8 text-center text-white">
        <h1 className="text-2xl font-bold">Demo Mode — Live Video Stream Unavailable</h1>
        <p className="max-w-md text-sm text-white/65">
          Meeting room <span className="font-mono text-sky-1">{id}</span> requires live Stream.io keys.
          Explore the post-meeting Gnani AI × Veridian pipeline offline instead:
        </p>
        <div className="flex gap-3">
          <Link href="/workos" className="rounded-lg bg-blue-1 px-4 py-2 text-sm font-semibold">
            Open WorkOS Hub
          </Link>
          <Link href="/meetings" className="rounded-lg bg-dark-3 px-4 py-2 text-sm font-semibold">
            Open Meetings Hub
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="h-screen w-full">
      <StreamCall call={call}>
        <StreamTheme>
          {!isSetupComplete ? (
            <MeetingSetup setIsSetupComplete={setIsSetupComplete} />
          ) : (
            <MeetingRoom />
          )}
        </StreamTheme>
      </StreamCall>
    </main>
  );
};

export default Meeting;
