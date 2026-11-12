import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const isSupabaseConfigured = Boolean(
  supabaseUrl &&
    supabaseAnonKey &&
    !supabaseUrl.includes('placeholder.supabase.co') &&
    !supabaseAnonKey.includes('placeholder')
);

const isDemoRuntime =
  process.env.DEMO_MODE === 'true' ||
  process.env.NEXT_PUBLIC_DEMO_MODE !== 'false';

const DEMO_RECORDINGS = [
  {
    id: 'demo-hinglish-001',
    created_at: '2026-11-11T10:05:00Z',
    original_video_url: 'demo://hinglish_sprint_sync.mp4',
    dubbed_video_url: 'demo://cloudinary/dubbed/demo-hinglish.mp4',
    summary:
      'Hinglish Infrastructure Sync: Elastic production rollout flagged against Jason paternity leave, SEC-POL-089 (14-day staging soak), and Rs 0 compute_infra budget.',
    chapters: [
      { time: '00:00', title: 'Agenda & Elastic Cluster Production Request' },
      { time: '00:30', title: 'HR Alert: Jason on Paternity Leave -> Reroute Josh' },
      { time: '01:05', title: 'Security Alert: SEC-POL-089 14-day Staging Rule' },
      { time: '01:40', title: 'Finance Alert: Compute Infra Budget Rs 0' },
    ],
  },
];

function createDemoQueryChain() {
  const result = { data: DEMO_RECORDINGS, error: null };
  const chain: Record<string, unknown> = {
    select: () => chain,
    insert: () => Promise.resolve({ data: [], error: null }),
    update: () => chain,
    delete: () => chain,
    eq: () => chain,
    neq: () => chain,
    order: () => chain,
    limit: () => chain,
    then: (resolve: (val: typeof result) => unknown) => Promise.resolve(resolve(result)),
  };
  return chain;
}

const _underlyingClient = createClient(
  isSupabaseConfigured ? supabaseUrl! : 'https://placeholder.supabase.co',
  isSupabaseConfigured ? supabaseAnonKey! : 'placeholder-anon-key'
);

export const supabase = new Proxy(_underlyingClient, {
  get(target, prop, receiver) {
    if (!isSupabaseConfigured) {
      if (prop === 'from' && isDemoRuntime) {
        return () => createDemoQueryChain();
      }
      if (
        !isDemoRuntime &&
        process.env.NEXT_PHASE !== 'phase-production-build' &&
        (typeof window !== 'undefined' ||
          process.env.NODE_ENV === 'production' ||
          process.env.NODE_ENV === 'development')
      ) {
        throw new Error(
          'FATAL [Horizon Veridian]: Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY environment variables. ' +
            'Please configure valid Supabase credentials in your .env file (or enable DEMO_MODE=true).'
        );
      }
    }
    return Reflect.get(target, prop, receiver);
  },
});

/**
 * Create a request-scoped Supabase client carrying Clerk's session JWT so
 * PostgreSQL Row Level Security (`current_org_id()`) enforces tenant isolation.
 */
export function createClerkSupabaseClient(clerkSessionToken: string | null) {
  if (!isSupabaseConfigured) {
    throw new Error(
      'Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY for RLS-scoped Supabase query.'
    );
  }
  return createClient(supabaseUrl!, supabaseAnonKey!, {
    auth: { persistSession: false },
    global: {
      headers: clerkSessionToken ? { Authorization: `Bearer ${clerkSessionToken}` } : {},
    },
  });
}
