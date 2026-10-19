import { NextResponse } from 'next/server';
import { StreamClient } from '@stream-io/node-sdk';

const apiKey = process.env.STREAM_API_KEY;
const apiSecret = process.env.STREAM_API_SECRET;

// Configure Next.js route timeout (for Vercel deployment)
export const maxDuration = 30; // 30 seconds (adjust based on your Vercel plan)
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  if (!apiKey || !apiSecret) {
    return NextResponse.json({ error: 'Stream API not configured' }, { status: 500 });
  }

  try {
    const { callId } = await request.json();
    if (!callId) {
      return NextResponse.json({ error: 'Call ID is required' }, { status: 400 });
    }

    // Initialize StreamClient with increased timeout
    // Default is 3000ms, increasing to 15000ms (15 seconds)
    const client = new StreamClient(apiKey, apiSecret, { timeout: 15000 });
    
    // Access the video call and delete it
    const call = client.video.call('default', callId);
    await call.delete({ hard: true }); // hard: true permanently deletes recordings too

    return NextResponse.json({ message: 'Call deleted successfully' }, { status: 200 });
  } catch (error) {
    console.error('Error deleting call:', error);
    return NextResponse.json({ 
      error: 'Failed to delete call',
      details: error instanceof Error ? error.message : 'Unknown error'
    }, { status: 500 });
  }
}
