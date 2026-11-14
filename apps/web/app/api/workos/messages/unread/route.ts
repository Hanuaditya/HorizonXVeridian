import { NextResponse } from 'next/server';
import { getWorkOSAuthHeader, getWorkOSBaseUrl } from '@/lib/workos-server';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const { authorization } = await getWorkOSAuthHeader();
    const res = await fetch(`${getWorkOSBaseUrl()}/api/messages/unread`, {
      headers: { Authorization: authorization },
      cache: 'no-store',
    });
    if (!res.ok) {
      return NextResponse.json({ unread_total: 0, by_channel: {} }, { status: 200 });
    }
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ unread_total: 0, by_channel: {} }, { status: 200 });
  }
}

