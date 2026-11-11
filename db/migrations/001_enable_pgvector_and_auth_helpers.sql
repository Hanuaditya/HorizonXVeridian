-- ============================================================================
-- Migration 001: Enable pgvector extension & Clerk JWT RLS helper functions
-- Forward-only migration.
--
-- Rollback notes (manual emergency only):
--   DROP FUNCTION IF EXISTS public.current_org_role();
--   DROP FUNCTION IF EXISTS public.current_user_id();
--   DROP FUNCTION IF EXISTS public.current_org_id();
--   DROP EXTENSION IF EXISTS vector;
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Extract active Clerk organization ID from JWT claims.
-- Supports both custom claim ('org_id') and Clerk v2 organization object ('o'->>'id').
CREATE OR REPLACE FUNCTION public.current_org_id()
RETURNS TEXT
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE(
    NULLIF(current_setting('request.jwt.claims', true)::json ->> 'org_id', ''),
    NULLIF(current_setting('request.jwt.claims', true)::json -> 'o' ->> 'id', '')
  );
$$;

-- Extract Clerk user ID ('sub') from JWT claims.
CREATE OR REPLACE FUNCTION public.current_user_id()
RETURNS TEXT
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('request.jwt.claims', true)::json ->> 'sub', '');
$$;

-- Extract Clerk organization role ('org_role' or 'o'->>'rol') from JWT claims.
CREATE OR REPLACE FUNCTION public.current_org_role()
RETURNS TEXT
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE(
    NULLIF(current_setting('request.jwt.claims', true)::json ->> 'org_role', ''),
    NULLIF(current_setting('request.jwt.claims', true)::json -> 'o' ->> 'rol', '')
  );
$$;
