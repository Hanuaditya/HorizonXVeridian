import { NextResponse } from 'next/server';
import { getWorkOSAuthHeader, getWorkOSBaseUrl } from '@/lib/workos-server';

export const dynamic = 'force-dynamic';

export async function GET(
  _request: Request,
  context: { params: Promise<{ threadId: string }> }
) {
  try {
    const { threadId } = await context.params;
    const { authorization } = await getWorkOSAuthHeader();
    const res = await fetch(
      `${getWorkOSBaseUrl()}/api/threads/${encodeURIComponent(threadId)}/state`,
      {
        headers: { Authorization: authorization },
        cache: 'no-store',
      }
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to fetch thread state';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

