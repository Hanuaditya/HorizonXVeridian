import { NextResponse } from 'next/server';
import { getWorkOSAuthHeader, getWorkOSBaseUrl } from '@/lib/workos-server';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  try {
    const { authorization, orgRole } = await getWorkOSAuthHeader();
    if (orgRole && orgRole !== 'org:admin') {
      return NextResponse.json(
        { error: 'Forbidden: Manager role (org:admin) required to trigger check-ins.' },
        { status: 403 }
      );
    }

    let threadId: string | undefined;
    try {
      const body = await request.json();
      threadId = body?.thread_id;
    } catch {
      // Body is optional
    }

    const endpoint = threadId
      ? `${getWorkOSBaseUrl()}/api/threads/${encodeURIComponent(threadId)}/checkin`
      : `${getWorkOSBaseUrl()}/api/checkin/trigger`;

    const res = await fetch(endpoint, {
      method: 'POST',
      headers: {
        Authorization: authorization,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(threadId ? {} : { thread_id: threadId }),
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to trigger check-in';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

