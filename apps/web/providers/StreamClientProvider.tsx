'use client';

import { StreamVideo, StreamVideoClient } from '@stream-io/video-react-sdk';
import { ReactNode, useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import Loader from '@/components/shared/Loader';
import { isDemoModeEnabled, useAppUser } from '@/providers/AuthBridge';

const apiKey = process.env.NEXT_PUBLIC_STREAM_API_KEY || '';
const hasRealStreamKey = Boolean(apiKey && !apiKey.includes('placeholder'));

const VIDEO_ROUTES = [
  '/',
  '/meetings',
  '/upcoming',
  '/previous',
  '/recordings',
  '/insights',
];

export default function StreamClientProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isVideoRoute =
    VIDEO_ROUTES.includes(pathname) || (pathname?.startsWith('/meeting/') ?? false);

  const [videoClient, setVideoClient] = useState<StreamVideoClient | null>(null);
  const { user, isLoaded } = useAppUser();
  const demoMode = isDemoModeEnabled();

  const tokenProvider = async () => {
    const res = await fetch('/api/stream-token');
    if (!res.ok) throw new Error('Failed to fetch Stream token');
    const data = await res.json();
    return data.token;
  };

  useEffect(() => {
    // Completely skip Stream initialization on non-video routes (/messages, /workos, /admin, etc.)
    if (!isVideoRoute || !isLoaded || !user || !hasRealStreamKey) {
      return;
    }

    try {
      const client = StreamVideoClient.getOrCreateInstance({
        apiKey,
        user: {
          id: user.id,
          name: user.username || user.fullName || 'Anonymous',
          image: user.imageUrl,
        },
        tokenProvider,
      });

      setVideoClient(client);
    } catch (err) {
      console.warn('StreamVideoClient initialization skipped:', err);
    }
  }, [isVideoRoute, user, isLoaded]);

  // Non-video routes: render children directly with zero Stream WebSocket overhead
  if (!isVideoRoute) {
    return <>{children}</>;
  }

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
