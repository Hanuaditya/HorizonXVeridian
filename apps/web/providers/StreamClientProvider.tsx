'use client';

import { StreamVideo, StreamVideoClient } from '@stream-io/video-react-sdk';
import { ReactNode, useEffect, useState } from 'react';
import Loader from '@/components/shared/Loader';
import { isDemoModeEnabled, useAppUser } from '@/providers/AuthBridge';

const apiKey = process.env.NEXT_PUBLIC_STREAM_API_KEY || '';
const hasRealStreamKey = Boolean(apiKey && !apiKey.includes('placeholder'));

export default function StreamClientProvider({ children }: { children: ReactNode }) {
  const [videoClient, setVideoClient] = useState<StreamVideoClient>();
  const { user, isLoaded } = useAppUser();
  const demoMode = isDemoModeEnabled();

  const tokenProvider = async () => {
    const res = await fetch('/api/stream-token');
    if (!res.ok) throw new Error('Failed to fetch Stream token');
    const data = await res.json();
    return data.token;
  };

  useEffect(() => {
    if (!isLoaded || !user || !hasRealStreamKey) return;

    const client = new StreamVideoClient({
      apiKey,
      user: {
        id: user.id,
        name: user.username || user.fullName || 'Anonymous',
        image: user.imageUrl,
      },
      tokenProvider,
    });

    setVideoClient(client);
  }, [user, isLoaded]);

  // In DEMO_MODE or when Stream keys are unset, render children directly without blocking on Loader
  if (!hasRealStreamKey) {
    if (demoMode) {
      return <>{children}</>;
    }
    throw new Error('Missing NEXT_PUBLIC_STREAM_API_KEY when DEMO_MODE=false.');
  }

  if (!videoClient) {
    if (demoMode) return <>{children}</>;
    return <Loader />;
  }

  return <StreamVideo client={videoClient}>{children}</StreamVideo>;
}
