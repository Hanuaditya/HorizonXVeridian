import { getWorkOSAuthHeader, getWorkOSBaseUrl } from '@/lib/workos-server';

export const dynamic = 'force-dynamic';

export async function GET(
  request: Request,
  context: { params: Promise<{ threadId: string }> }
) {
  try {
    const { threadId } = await context.params;
    const url = new URL(request.url);
    const lastEventId = url.searchParams.get('lastEventId') || request.headers.get('Last-Event-ID');
    const qs = lastEventId ? `?lastEventId=${encodeURIComponent(lastEventId)}` : '';
    const { authorization } = await getWorkOSAuthHeader();

    const upstream = await fetch(
      `${getWorkOSBaseUrl()}/api/stream/${encodeURIComponent(threadId)}${qs}`,
      {
        headers: {
          Authorization: authorization,
          Accept: 'text/event-stream',
        },
        cache: 'no-store',
      }
    );

    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'SSE proxy error';
    return new Response(`data: ${JSON.stringify({ event_type: 'error', payload: { error: msg } })}\n\n`, {
      status: 500,
      headers: { 'Content-Type': 'text/event-stream' },
    });
  }
}

