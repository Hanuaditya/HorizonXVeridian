import crypto from 'crypto';
import { auth } from '@clerk/nextjs/server';

export function getWorkOSBaseUrl(): string {
  return (process.env.WORKOS_URL || 'http://localhost:8000').replace(/\/$/, '');
}

function base64UrlEncode(buf: Buffer | string): string {
  const b = typeof buf === 'string' ? Buffer.from(buf, 'utf-8') : buf;
  return b.toString('base64').replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
}

function mintLocalDemoJwt(role: 'org:admin' | 'org:member' = 'org:admin'): string {
  const secret = process.env.SHARED_HMAC_SECRET || 'dev-demo-secret';
  const now = Math.floor(Date.now() / 1000);
  const header = base64UrlEncode(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = base64UrlEncode(
    JSON.stringify({
      sub: role === 'org:admin' ? 'user_demo_manager' : 'user_demo_member',
      org_id: 'org_demo_horizon',
      org_role: role,
      demo: true,
      iat: now,
      exp: now + 3600,
    })
  );
  const sig = base64UrlEncode(
    crypto.createHmac('sha256', secret).update(`${header}.${payload}`).digest()
  );
  return `${header}.${payload}.${sig}`;
}

export async function getWorkOSAuthHeader(): Promise<{
  authorization: string;
  isDemo: boolean;
}> {
  const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY || '';
  const hasRealClerk = Boolean(clerkKey && !clerkKey.startsWith('pk_test_ZXhh'));

  if (hasRealClerk) {
    try {
      const session = await auth();
      const token = await session.getToken();
      if (token) {
        return { authorization: `Bearer ${token}`, isDemo: false };
      }
    } catch {
      // Fall through only in explicit local DEMO_MODE
    }
  }

  const demoAllowed =
    (process.env.DEMO_MODE === 'true' || process.env.NEXT_PUBLIC_DEMO_MODE === 'true') &&
    process.env.NODE_ENV !== 'production';

  if (demoAllowed) {
    return { authorization: `Bearer ${mintLocalDemoJwt('org:admin')}`, isDemo: true };
  }

  throw new Error('Unauthorized: Clerk authentication session required.');
}
