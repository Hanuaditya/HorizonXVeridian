import { NextResponse } from 'next/server';
import { getWorkOSAuthHeader, getWorkOSBaseUrl } from '@/lib/workos-server';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const { authorization } = await getWorkOSAuthHeader();
    const res = await fetch(`${getWorkOSBaseUrl()}/api/threads`, {
      headers: { Authorization: authorization },
      cache: 'no-store',
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to load threads';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
