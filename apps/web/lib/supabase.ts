import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

const isConfigured = Boolean(
  supabaseUrl &&
  supabaseAnonKey &&
  !supabaseUrl.includes('placeholder.supabase.co')
);

// Fallback client for static build phases
const _underlyingClient = createClient(
  isConfigured ? supabaseUrl! : 'https://placeholder.supabase.co',
  isConfigured ? supabaseAnonKey! : 'placeholder-anon-key'
);

export const supabase = new Proxy(_underlyingClient, {
  get(target, prop, receiver) {
    if (!isConfigured) {
      // In client browser or live server runtime, fail loudly
      if (typeof window !== 'undefined' || process.env.NODE_ENV === 'production' || process.env.NODE_ENV === 'development') {
        // If not in static page generation build phase
        if (process.env.NEXT_PHASE !== 'phase-production-build') {
          throw new Error(
            'FATAL [Horizon Veridian]: Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY environment variables. ' +
            'Please configure valid Supabase credentials in your .env file.'
          );
        }
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
  if (!isConfigured) {
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

