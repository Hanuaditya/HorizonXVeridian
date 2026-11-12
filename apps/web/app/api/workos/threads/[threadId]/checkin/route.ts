import { NextResponse } from 'next/server';
import { getWorkOSAuthHeader, getWorkOSBaseUrl } from '@/lib/workos-server';

export const dynamic = 'force-dynamic';

export async function POST(
  _request: Request,
  context: { params: Promise<{ threadId: string }> }
) {
  try {
    const { threadId } = await context.params;
    const { authorization } = await getWorkOSAuthHeader();
    const res = await fetch(
      `${getWorkOSBaseUrl()}/api/threads/${encodeURIComponent(threadId)}/checkin`,
      {
        method: 'POST',
        headers: { Authorization: authorization },
      }
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to trigger check-in';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

