import { NextResponse } from 'next/server';
import { getWorkOSAuthHeader, getWorkOSBaseUrl } from '@/lib/workos-server';

export const dynamic = 'force-dynamic';

export async function POST(
  request: Request,
  context: { params: Promise<{ threadId: string }> }
) {
  try {
    const { threadId } = await context.params;
    const body = await request.json();
    const { authorization } = await getWorkOSAuthHeader();
    const res = await fetch(
      `${getWorkOSBaseUrl()}/api/threads/${encodeURIComponent(threadId)}/employee-reply`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: authorization,
        },
        body: JSON.stringify(body),
      }
    );
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to submit employee reply';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

