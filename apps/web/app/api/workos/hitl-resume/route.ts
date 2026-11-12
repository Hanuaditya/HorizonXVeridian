import { NextResponse } from 'next/server';
import { getWorkOSAuthHeader, getWorkOSBaseUrl } from '@/lib/workos-server';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { authorization, orgRole } = await getWorkOSAuthHeader();
    if (orgRole && orgRole !== 'org:admin') {
      return NextResponse.json(
        { error: 'Forbidden: Manager role (org:admin) required to approve sprint tickets.' },
        { status: 403 }
      );
    }
    const res = await fetch(`${getWorkOSBaseUrl()}/api/hitl-resume`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: authorization,
      },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to resume HITL';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

