-- =============================================================
-- Veridian WorkOS — Corrected Agent Migration
-- Run in: Supabase Dashboard → SQL Editor → New Query
-- Safe to re-run (uses IF NOT EXISTS / OR REPLACE everywhere)
-- =============================================================


-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- PART A — Patch existing tables with missing columns
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

-- A1. hr_employees — add last_synced_from (read by hr_checker_node)
ALTER TABLE public.hr_employees
    ADD COLUMN IF NOT EXISTS last_synced_from TEXT DEFAULT 'BambooHR connector';

-- A2. hr_employees — add email (needed for employees seed below)
ALTER TABLE public.hr_employees
    ADD COLUMN IF NOT EXISTS email TEXT;

-- A3. security_policies — add policy_id (read by security_checker_node)
ALTER TABLE public.security_policies
    ADD COLUMN IF NOT EXISTS policy_id TEXT;

-- Backfill policy_id for any existing rows
UPDATE public.security_policies
SET policy_id = 'SEC-POL-' || LPAD(id::text, 3, '0')
WHERE policy_id IS NULL;


-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- PART B — Create the 3 new agent tables
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

-- B1. processed_meetings — idempotency guard for ingest_node
CREATE TABLE IF NOT EXISTS public.processed_meetings (
    meeting_id      TEXT        PRIMARY KEY,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    task_count      INTEGER     NOT NULL DEFAULT 0
);

-- B2. audit_trail — written by merge_node after every fan-in
CREATE TABLE IF NOT EXISTS public.audit_trail (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id  TEXT        NOT NULL,
    event_type  TEXT        NOT NULL,
    agent_node  TEXT,
    detail      TEXT,
    confidence  FLOAT,
    provenance  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_trail_meeting
    ON public.audit_trail(meeting_id);

-- B3. employees — capacity cache for capacity_checker + auto_router
CREATE TABLE IF NOT EXISTS public.employees (
    id                SERIAL      PRIMARY KEY,
    full_name         TEXT        NOT NULL,
    email             TEXT,
    status            TEXT        NOT NULL DEFAULT 'ACTIVE',
    open_tickets      INTEGER     NOT NULL DEFAULT 0,
    last_synced_from  TEXT        DEFAULT 'Jira API',
    synced_at         TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_employees_status
    ON public.employees(status);
CREATE INDEX IF NOT EXISTS idx_employees_tickets
    ON public.employees(open_tickets);

-- Seed employees from hr_employees (skips duplicates)
INSERT INTO public.employees
    (full_name, email, status, open_tickets, last_synced_from, synced_at)
SELECT
    h.full_name,
    h.email,
    CASE
        WHEN h.status ILIKE '%active%'    THEN 'ACTIVE'
        WHEN h.status ILIKE '%new%hire%'  THEN 'NEW_HIRE'
        WHEN h.status ILIKE '%paternity%' THEN 'ON_PATERNITY_LEAVE'
        WHEN h.status ILIKE '%maternity%' THEN 'ON_MATERNITY_LEAVE'
        WHEN h.status ILIKE '%leave%'     THEN 'ON_LEAVE'
        WHEN h.status ILIKE '%terminat%'  THEN 'TERMINATED'
        ELSE 'INACTIVE'
    END,
    0,
    'BambooHR connector',
    COALESCE(h.synced_at, now())
FROM public.hr_employees h
WHERE h.full_name IS NOT NULL
ON CONFLICT DO NOTHING;


-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- PART C — pgvector RPC functions
-- These are called by finance_checker_node and security_checker_node
-- using 1024-dim Nvidia NIM embeddings
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

-- C1. match_finance_budgets — cosine similarity over finance_budgets
CREATE OR REPLACE FUNCTION public.match_finance_budgets(
    query_embedding  vector(1024),
    match_threshold  float,
    match_count      int
)
RETURNS TABLE (
    id               uuid,
    category         text,
    budget_remaining numeric,
    currency         text,
    owner            text,
    similarity       float
)
LANGUAGE sql STABLE
AS $$
    SELECT
        id,
        category,
        budget_remaining,
        currency,
        owner,
        1 - (embedding <=> query_embedding) AS similarity
    FROM public.finance_budgets
    WHERE embedding IS NOT NULL
      AND 1 - (embedding <=> query_embedding) > match_threshold
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;

-- C2. match_security_policies — cosine similarity over security_policies
CREATE OR REPLACE FUNCTION public.match_security_policies(
    query_embedding  vector(1024),
    match_threshold  float,
    match_count      int
)
RETURNS TABLE (
    id            uuid,
    policy_id     text,
    document_name text,
    chunk_text    text,
    similarity    float
)
LANGUAGE sql STABLE
AS $$
    SELECT
        id,
        COALESCE(policy_id, 'SEC-POL-' || LEFT(id::text, 8)) AS policy_id,
        document_name,
        chunk_text,
        1 - (embedding <=> query_embedding) AS similarity
    FROM public.security_policies
    WHERE embedding IS NOT NULL
      AND 1 - (embedding <=> query_embedding) > match_threshold
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;


-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- PART D — Verify everything
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SELECT 'hr_employees'       AS table_name, COUNT(*) AS rows FROM public.hr_employees
UNION ALL
SELECT 'finance_budgets',                  COUNT(*)         FROM public.finance_budgets
UNION ALL
SELECT 'security_policies',                COUNT(*)         FROM public.security_policies
UNION ALL
SELECT 'processed_meetings',               COUNT(*)         FROM public.processed_meetings
UNION ALL
SELECT 'audit_trail',                      COUNT(*)         FROM public.audit_trail
UNION ALL
SELECT 'employees',                        COUNT(*)         FROM public.employees;

