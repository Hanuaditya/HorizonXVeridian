'use client';

import MeetingSetup from '@/components/shared/MeetingSetup';
import MeetingRoom from '@/components/shared/MeetingRoom';
import { useUser } from '@clerk/nextjs';
import { StreamCall, StreamTheme } from '@stream-io/video-react-sdk';
import React, { useState } from 'react';
import { useGetCallById } from '@/hooks/useGetCallById';
import Loader from '@/components/shared/Loader';

const Meeting = ({ params }: { params: Promise<{ id: string }> }) => {
  // ✅ unwrap params using React.use()
  const { id } = React.use(params);

  const { user, isLoaded } = useUser();
  const [isSetupComplete, setIsSetupComplete] = useState(false);
  const { call, isCallLoading } = useGetCallById(id);

  if (!isLoaded || isCallLoading) return <Loader />;

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

