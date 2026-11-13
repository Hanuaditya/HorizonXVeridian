import { NextResponse } from 'next/server';
import { getWorkOSAuthHeader, getWorkOSBaseUrl } from '@/lib/workos-server';

export const dynamic = 'force-dynamic';

export async function POST() {
  try {
    const { authorization, orgRole } = await getWorkOSAuthHeader();
    if (orgRole && orgRole !== 'org:admin') {
      return NextResponse.json(
        { error: 'Forbidden: Manager role (org:admin) required to reset sprint state.' },
        { status: 403 }
      );
    }
    const res = await fetch(`${getWorkOSBaseUrl()}/api/reset`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: authorization,
      },
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to reset sprint state';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
