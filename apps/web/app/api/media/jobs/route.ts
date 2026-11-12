import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

function getMediaBaseUrl(): string {
  return (process.env.MEDIA_URL || process.env.PYTHON_SERVICE_URL || 'http://localhost:5001').replace(/\/$/, '');
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const res = await fetch(`${getMediaBaseUrl()}/media/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to submit media job';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const jobId = url.searchParams.get('jobId');
    if (!jobId) {
      return NextResponse.json({ error: 'jobId query param is required' }, { status: 400 });
    }
    const res = await fetch(`${getMediaBaseUrl()}/media/jobs/${encodeURIComponent(jobId)}`, {
      cache: 'no-store',
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to poll media job';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

