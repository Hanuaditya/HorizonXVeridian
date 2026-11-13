import { NextRequest, NextResponse } from 'next/server';
import { getWorkOSAuthHeader, getWorkOSBaseUrl } from '@/lib/workos-server';

export const dynamic = 'force-dynamic';

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ channelKey: string }> }
) {
  try {
    const { channelKey } = await params;
    const { authorization } = await getWorkOSAuthHeader();
    const { searchParams } = new URL(req.url);
    const qs = searchParams.toString() ? `?${searchParams.toString()}` : '';

    const res = await fetch(`${getWorkOSBaseUrl()}/api/messages/${encodeURIComponent(channelKey)}${qs}`, {
      headers: { Authorization: authorization },
      cache: 'no-store',
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to load channel messages';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ channelKey: string }> }
) {
  try {
    const { channelKey } = await params;
    const { authorization } = await getWorkOSAuthHeader();
    const body = await req.json();

    const res = await fetch(`${getWorkOSBaseUrl()}/api/messages/${encodeURIComponent(channelKey)}`, {
      method: 'POST',
      headers: {
        Authorization: authorization,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to send message';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

