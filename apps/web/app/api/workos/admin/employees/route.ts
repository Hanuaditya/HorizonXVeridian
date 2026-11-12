import { NextResponse } from 'next/server';
import { getWorkOSAuthHeader, getWorkOSBaseUrl } from '@/lib/workos-server';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const { authorization } = await getWorkOSAuthHeader();
    const res = await fetch(`${getWorkOSBaseUrl()}/api/admin/employees`, {
      headers: { Authorization: authorization },
      cache: 'no-store',
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Failed to load admin employees';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { authorization } = await getWorkOSAuthHeader();
    const res = await fetch(`${getWorkOSBaseUrl()}/api/admin/employees`, {
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
    const msg = err instanceof Error ? err.message : 'Failed to update employee mapping';
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

