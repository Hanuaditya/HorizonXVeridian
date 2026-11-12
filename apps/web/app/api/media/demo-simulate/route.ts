import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

function getMediaBaseUrl(): string {
  return (
    process.env.MEDIA_URL ||
    process.env.PYTHON_SERVICE_URL ||
    'http://localhost:5001'
  ).replace(/\/$/, '');
}

export async function POST(request: Request) {
  try {
    const body = await request.json().catch(() => ({}));
    const res = await fetch(`${getMediaBaseUrl()}/media/demo-simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg =
      err instanceof Error ? err.message : 'Unable to reach Media service on port 5001';
    return NextResponse.json({ error: msg }, { status: 503 });
  }
}

