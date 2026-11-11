import { NextResponse } from 'next/server';
import { getWorkOSAuthHeader, getWorkOSBaseUrl } from '@/lib/workos-server';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const meetingId = url.searchParams.get('meeting_id');
    const qs = meetingId ? `?meeting_id=${encodeURIComponent(meetingId)}` : '';
    const { authorization } = await getWorkOSAuthHeader();
    const res = await fetch(`${getWorkOSBaseUrl()}/api/audit-trail${qs}`, {
      headers: { Authorization: authorization },
      cache: 'no-store',
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to load audit trail';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
