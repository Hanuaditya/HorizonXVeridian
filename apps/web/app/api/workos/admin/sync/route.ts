import { NextResponse } from 'next/server';
import { getWorkOSAuthHeader, getWorkOSBaseUrl } from '@/lib/workos-server';

export const dynamic = 'force-dynamic';

export async function POST() {
  try {
    const { authorization } = await getWorkOSAuthHeader();
    const res = await fetch(`${getWorkOSBaseUrl()}/api/admin/sync`, {
      method: 'POST',
      headers: { Authorization: authorization },
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Connector sync failed';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
