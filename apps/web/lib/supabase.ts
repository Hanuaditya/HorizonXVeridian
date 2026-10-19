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

