'use client';
import { useCall, useCallStateHooks } from '@stream-io/video-react-sdk';
import React, { useState } from 'react';
import { Button } from '../ui/button';
import { useRouter } from 'next/navigation';

const EndCallButton = () => {
  const call = useCall();
  const router = useRouter();
  const { useLocalParticipant } = useCallStateHooks();
  const localParticipant = useLocalParticipant();
  const [ending, setEnding] = useState(false);

  const isMeetingOwner =
    localParticipant &&
    call?.state.createdBy &&
    localParticipant.userId === call.state.createdBy.id;

  if (!isMeetingOwner) return null;

  return (
    <Button
      disabled={ending}
      className='bg-red-500 font-semibold hover:bg-red-600 disabled:opacity-50'
      onClick={async () => {
        setEnding(true);
        try {
          const callId = call.id;
          const custom = call.state.custom || {};
          await call.endCall();
          try {
            await fetch('/api/media/demo-simulate', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                meeting_id: callId,
                title: custom.description || `Meeting ${callId}`,
              }),
            });
          } catch (e) {
            console.warn('Post-meeting WorkOS handoff trigger notice:', e);
          }
        } finally {
          router.push('/workos');
        }
      }}
    >
      {ending ? 'Ending & Handing off...' : 'End call for everyone'}
    </Button>
  );
};

export default EndCallButton;
