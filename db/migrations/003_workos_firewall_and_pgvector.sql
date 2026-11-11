-- ============================================================================
-- Migration 003: WorkOS Firewall, Tasks, Audit Trail & pgvector HNSW Indexes
-- Forward-only migration.
--
-- Vector Index Justification (HNSW vs IVFFlat):
--   We use HNSW (`vector_cosine_ops`) on all vector(1024) columns instead of
--   IVFFlat because:
--     1. IVFFlat requires pre-populating representative rows to train k-means
--        centroids (`lists`); newly onboarded tenant orgs start with few rows,
--        which causes IVFFlat to degrade or miss matches. HNSW builds accurately
--        incrementally starting from row 1.
--     2. HNSW yields consistently higher recall (>95%) and sub-millisecond
--        lookup latency for real-time compliance firewall & commit checks.
--
-- Rollback notes (manual emergency only):
--   DROP FUNCTION IF EXISTS public.get_vector_column_dimensions();
--   DROP FUNCTION IF EXISTS public.match_open_tasks(TEXT, vector, TEXT, float, int);
--   DROP FUNCTION IF EXISTS public.match_security_policies(TEXT, vector, float, int);
--   DROP FUNCTION IF EXISTS public.match_finance_budgets(TEXT, vector, float, int);
--   DROP TABLE IF EXISTS public.webhook_events;
--   DROP TABLE IF EXISTS public.slack_threads;
--   DROP TABLE IF EXISTS public.audit_trail;
--   DROP TABLE IF EXISTS public.approvals;
--   DROP TABLE IF EXISTS public.resolutions;
--   DROP TABLE IF EXISTS public.tasks;
--   DROP TABLE IF EXISTS public.processed_meetings;
--   DROP TABLE IF EXISTS public.security_policies;
--   DROP TABLE IF EXISTS public.finance_budgets;
--   DROP TABLE IF EXISTS public.hr_employees;
--   DROP TABLE IF EXISTS public.employees;
-- ============================================================================

-- 1. Employees identity & Jira capacity cache
CREATE TABLE IF NOT EXISTS public.employees (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            TEXT NOT NULL,
    clerk_user_id     TEXT,
    full_name         TEXT NOT NULL,
    email             TEXT,
    slack_id          TEXT,
    jira_account_id   TEXT,
    status            TEXT NOT NULL DEFAULT 'ACTIVE',
    active            BOOLEAN NOT NULL DEFAULT true,
    capacity_cache    INTEGER NOT NULL DEFAULT 0,
    last_synced_from  TEXT DEFAULT 'Seed / Jira API',
    synced_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, full_name)
);

CREATE INDEX IF NOT EXISTS idx_employees_org_status ON public.employees(org_id, status);
CREATE INDEX IF NOT EXISTS idx_employees_org_email  ON public.employees(org_id, email);

-- 2. HR Employees (synced from HR connector)
CREATE TABLE IF NOT EXISTS public.hr_employees (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            TEXT NOT NULL,
    full_name         TEXT NOT NULL,
    email             TEXT,
    department        TEXT,
    job_title         TEXT,
    status            TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE | NEW_HIRE | ON_PATERNITY_LEAVE | ON_MATERNITY_LEAVE | ON_LEAVE | TERMINATED
    leave_until       DATE,
    last_synced_from  TEXT NOT NULL DEFAULT 'BambooHR connector',
    synced_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, full_name)
);

CREATE INDEX IF NOT EXISTS idx_hr_employees_org_name ON public.hr_employees(org_id, full_name);

-- 3. Finance Budgets (vector 1024)
CREATE TABLE IF NOT EXISTS public.finance_budgets (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            TEXT NOT NULL,
    category          TEXT NOT NULL,
    budget_remaining  NUMERIC NOT NULL DEFAULT 0,
    currency          TEXT NOT NULL DEFAULT 'INR',
    owner             TEXT NOT NULL DEFAULT 'Finance Team',
    embedding         vector(1024),
    last_synced_from  TEXT NOT NULL DEFAULT 'finance_budgets.csv',
    synced_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, category)
);

CREATE INDEX IF NOT EXISTS idx_finance_budgets_org ON public.finance_budgets(org_id);
CREATE INDEX IF NOT EXISTS idx_finance_budgets_embedding_hnsw
    ON public.finance_budgets USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 4. Security Policies (vector 1024)
CREATE TABLE IF NOT EXISTS public.security_policies (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         TEXT NOT NULL,
    policy_id      TEXT NOT NULL,
    document_name  TEXT NOT NULL,
    chunk_text     TEXT NOT NULL,
    page_number    INTEGER NOT NULL DEFAULT 1,
    embedding      vector(1024),
    synced_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, policy_id, page_number)
);

CREATE INDEX IF NOT EXISTS idx_security_policies_org ON public.security_policies(org_id);
CREATE INDEX IF NOT EXISTS idx_security_policies_embedding_hnsw
    ON public.security_policies USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 5. Processed Meetings (per-org idempotency guard)
CREATE TABLE IF NOT EXISTS public.processed_meetings (
    org_id        TEXT NOT NULL,
    meeting_id    TEXT NOT NULL,
    thread_id     TEXT,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    task_count    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (org_id, meeting_id)
);

-- 6. Tasks (persisted pipeline tasks + open ticket vectors)
CREATE TABLE IF NOT EXISTS public.tasks (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id              TEXT NOT NULL,
    org_id               TEXT NOT NULL,
    meeting_id           TEXT NOT NULL,
    thread_id            TEXT,
    title                TEXT NOT NULL,
    reframed_title       TEXT,
    reframed_description TEXT,
    assignee             TEXT NOT NULL,
    rerouted_assignee    TEXT,
    resource_type        TEXT DEFAULT 'unknown',
    transcript_quote     TEXT DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING | DEFERRED | READY | DISPATCHED | DONE | BLOCKED | CANCELLED
    hr_status            TEXT,
    hr_provenance        TEXT,
    finance_flag         TEXT,
    finance_provenance   TEXT,
    security_flag        TEXT,
    security_confidence  FLOAT,
    security_provenance  TEXT,
    capacity_flag        TEXT,
    capacity_provenance  TEXT,
    jira_key             TEXT,
    jira_url             TEXT,
    slack_dm_sent        BOOLEAN NOT NULL DEFAULT false,
    embedding            vector(1024),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, meeting_id, task_id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_org_thread ON public.tasks(org_id, thread_id);
CREATE INDEX IF NOT EXISTS idx_tasks_org_jira   ON public.tasks(org_id, jira_key);
CREATE INDEX IF NOT EXISTS idx_tasks_embedding_hnsw
    ON public.tasks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 7. Resolutions (AI-proposed remediations)
CREATE TABLE IF NOT EXISTS public.resolutions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            TEXT NOT NULL,
    meeting_id        TEXT NOT NULL,
    thread_id         TEXT,
    task_id           TEXT NOT NULL,
    conflict_type     TEXT NOT NULL,
    suggested_action  TEXT NOT NULL,  -- REFRAME | REROUTE | DEFER | OVERRIDE | PROCEED
    provenance_tag    TEXT,
    new_payload       JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_resolutions_org_thread ON public.resolutions(org_id, thread_id);

-- 8. Approvals (Human-in-the-loop manager decisions with identity & timestamp)
CREATE TABLE IF NOT EXISTS public.approvals (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            TEXT NOT NULL,
    thread_id         TEXT NOT NULL,
    meeting_id        TEXT NOT NULL,
    task_id           TEXT NOT NULL,
    approver_user_id  TEXT NOT NULL,
    decision          TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_approvals_org_thread ON public.approvals(org_id, thread_id);

-- 9. Audit Trail (append-only log with provenance_tag)
CREATE TABLE IF NOT EXISTS public.audit_trail (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          TEXT NOT NULL,
    meeting_id      TEXT NOT NULL,
    thread_id       TEXT,
    task_id         TEXT,
    event_type      TEXT NOT NULL,
    agent_node      TEXT,
    detail          TEXT,
    confidence      FLOAT,
    provenance_tag  TEXT NOT NULL,
    actor_id        TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_trail_org_meeting ON public.audit_trail(org_id, meeting_id);

-- 10. Slack Threads (Graph B closed-loop tracking + anti-loop turn_count)
CREATE TABLE IF NOT EXISTS public.slack_threads (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           TEXT NOT NULL,
    thread_id        TEXT NOT NULL,
    task_id          TEXT NOT NULL,
    jira_key         TEXT,
    slack_channel    TEXT,
    slack_thread_ts  TEXT,
    assignee         TEXT,
    turn_count       INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'OPEN',
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, slack_channel, slack_thread_ts)
);

-- 11. Webhook replay / deduplication registry
CREATE TABLE IF NOT EXISTS public.webhook_events (
    provider      TEXT NOT NULL,
    event_id      TEXT NOT NULL,
    org_id        TEXT,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, event_id)
);

-- ----------------------------------------------------------------------------
-- Tenant-Scoped pgvector RPC Functions
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.match_finance_budgets(
    p_org_id         TEXT,
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
    last_synced_from text,
    similarity       float
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        id,
        category,
        budget_remaining,
        currency,
        owner,
        last_synced_from,
        1 - (embedding <=> query_embedding) AS similarity
    FROM public.finance_budgets
    WHERE org_id = p_org_id
      AND embedding IS NOT NULL
      AND 1 - (embedding <=> query_embedding) >= match_threshold
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;

CREATE OR REPLACE FUNCTION public.match_security_policies(
    p_org_id         TEXT,
    query_embedding  vector(1024),
    match_threshold  float,
    match_count      int
)
RETURNS TABLE (
    id             uuid,
    policy_id      text,
    document_name  text,
    chunk_text     text,
    similarity     float
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        id,
        policy_id,
        document_name,
        chunk_text,
        1 - (embedding <=> query_embedding) AS similarity
    FROM public.security_policies
    WHERE org_id = p_org_id
      AND embedding IS NOT NULL
      AND 1 - (embedding <=> query_embedding) >= match_threshold
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;

CREATE OR REPLACE FUNCTION public.match_open_tasks(
    p_org_id         TEXT,
    query_embedding  vector(1024),
    p_assignee       text,
    match_threshold  float,
    match_count      int
)
RETURNS TABLE (
    id          uuid,
    task_id     text,
    title       text,
    jira_key    text,
    assignee    text,
    status      text,
    similarity  float
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        id,
        task_id,
        COALESCE(reframed_title, title) AS title,
        jira_key,
        COALESCE(rerouted_assignee, assignee) AS assignee,
        status,
        1 - (embedding <=> query_embedding) AS similarity
    FROM public.tasks
    WHERE org_id = p_org_id
      AND status IN ('DISPATCHED', 'OPEN', 'BLOCKED')
      AND (p_assignee IS NULL OR LOWER(COALESCE(rerouted_assignee, assignee)) = LOWER(p_assignee))
      AND embedding IS NOT NULL
      AND 1 - (embedding <=> query_embedding) >= match_threshold
    ORDER BY embedding <=> query_embedding
    LIMIT match_count;
$$;

-- Startup check helper: inspects configured pgvector dimensions on disk
CREATE OR REPLACE FUNCTION public.get_vector_column_dimensions()
RETURNS TABLE (
    table_name   text,
    column_name  text,
    dim          int
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        c.relname::text AS table_name,
        a.attname::text AS column_name,
        a.atttypmod::int AS dim
    FROM pg_attribute a
    JOIN pg_class c ON a.attrelid = c.oid
    JOIN pg_namespace n ON c.relnamespace = n.oid
    JOIN pg_type t ON a.atttypid = t.oid
    WHERE n.nspname = 'public'
      AND t.typname = 'vector'
      AND a.attnum > 0
      AND NOT a.attisdropped
    ORDER BY c.relname, a.attname;
$$;

-- ----------------------------------------------------------------------------
-- Row Level Security (RLS) for All WorkOS Tenant Tables
-- ----------------------------------------------------------------------------
ALTER TABLE public.employees          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hr_employees       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finance_budgets    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.security_policies  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.processed_meetings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tasks              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resolutions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.approvals          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_trail        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.slack_threads      ENABLE ROW LEVEL SECURITY;

CREATE POLICY employees_tenant_isolation ON public.employees
    FOR ALL USING (org_id = public.current_org_id()) WITH CHECK (org_id = public.current_org_id());

CREATE POLICY hr_employees_tenant_isolation ON public.hr_employees
    FOR ALL USING (org_id = public.current_org_id()) WITH CHECK (org_id = public.current_org_id());

CREATE POLICY finance_budgets_tenant_isolation ON public.finance_budgets
    FOR ALL USING (org_id = public.current_org_id()) WITH CHECK (org_id = public.current_org_id());

CREATE POLICY security_policies_tenant_isolation ON public.security_policies
    FOR ALL USING (org_id = public.current_org_id()) WITH CHECK (org_id = public.current_org_id());

CREATE POLICY processed_meetings_tenant_isolation ON public.processed_meetings
    FOR ALL USING (org_id = public.current_org_id()) WITH CHECK (org_id = public.current_org_id());

CREATE POLICY tasks_tenant_isolation ON public.tasks
    FOR ALL USING (org_id = public.current_org_id()) WITH CHECK (org_id = public.current_org_id());

CREATE POLICY resolutions_tenant_isolation ON public.resolutions
    FOR ALL USING (org_id = public.current_org_id()) WITH CHECK (org_id = public.current_org_id());

CREATE POLICY approvals_tenant_isolation ON public.approvals
    FOR ALL USING (org_id = public.current_org_id()) WITH CHECK (org_id = public.current_org_id());

-- Audit trail is strictly append-only (SELECT + INSERT only)
CREATE POLICY audit_trail_tenant_select ON public.audit_trail
    FOR SELECT USING (org_id = public.current_org_id());
CREATE POLICY audit_trail_tenant_insert ON public.audit_trail
    FOR INSERT WITH CHECK (org_id = public.current_org_id());

CREATE POLICY slack_threads_tenant_isolation ON public.slack_threads
    FOR ALL USING (org_id = public.current_org_id()) WITH CHECK (org_id = public.current_org_id());
