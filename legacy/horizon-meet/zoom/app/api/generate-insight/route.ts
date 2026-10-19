import { NextResponse } from 'next/server';

export const maxDuration = 300; // 5 minutes
export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  try {
    const { videoUrl } = await request.json();

    if (!videoUrl) {
      return NextResponse.json(
        { error: 'Video URL is required' },
        { status: 400 }
      );
    }

    // Adjust URL if running backend elsewhere:
    const PYTHON_SERVICE_URL = process.env.PYTHON_SERVICE_URL || 'http://localhost:5001';

    const response = await fetch(`${PYTHON_SERVICE_URL}/api/generate-insight`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ videoUrl }),
      signal: AbortSignal.timeout(300000), // 5 min timeout
    });

    const result = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        { error: 'Insight generation failed', details: result },
        { status: response.status }
      );
    }

    return NextResponse.json({
      message: 'Insight generated successfully',
      summary: result.summary,
      chapters: result.chapters,
    });
  } catch (error: any) {
    return NextResponse.json(
      {
        error: 'Unexpected error',
        details: error.message || 'Unknown error'
      },
      { status: 500 }
    );
  }
}
