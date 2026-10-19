"use client";

import { useUser } from "@clerk/nextjs";
import { StreamVideo, StreamVideoClient } from "@stream-io/video-react-sdk";
import { ReactNode, useEffect, useState } from "react";
import Loader from "@/components/shared/Loader";

const apiKey = process.env.NEXT_PUBLIC_STREAM_API_KEY!;

export default function StreamClientProvider({ children }: { children: ReactNode }) {
  const [videoClient, setVideoClient] = useState<StreamVideoClient>();
  const { user, isLoaded } = useUser();

  // ✅ tokenProvider fetches from your API route (server handles secret)
  const tokenProvider = async () => {
    const res = await fetch("/api/stream-token");
    if (!res.ok) throw new Error("Failed to fetch Stream token");
    const data = await res.json();
    return data.token;
  };

  useEffect(() => {
    console.log("Stream API Key on client:", apiKey);
    console.log("Clerk user.id:", user?.id);

    if (!isLoaded || !user) return;
    if (!apiKey) throw new Error("❌ Missing Stream API key");
    const client = new StreamVideoClient({
      apiKey,
      user: {
        id: user.id,
        name: user.username || user.fullName || "Anonymous",
        image: user.imageUrl,
      },
      tokenProvider,
    });

    setVideoClient(client);
  }, [user, isLoaded]);

  if (!videoClient) return <Loader />;

  return <StreamVideo client={videoClient}>{children}</StreamVideo>;
}
