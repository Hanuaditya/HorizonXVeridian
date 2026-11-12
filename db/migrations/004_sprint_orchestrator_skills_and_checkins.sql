-- ============================================================================
-- Migration 004: Sprint Orchestrator Domain Skills, Workloads & Check-In Loop
-- Forward-only migration (safe/idempotent).
-- ============================================================================

ALTER TABLE public.employees
    ADD COLUMN IF NOT EXISTS domain_skills TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS active_task_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE public.tasks
    ADD COLUMN IF NOT EXISTS commit_message TEXT,
    ADD COLUMN IF NOT EXISTS progress_pct INTEGER NOT NULL DEFAULT 0;

