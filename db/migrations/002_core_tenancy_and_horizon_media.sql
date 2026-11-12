-- ============================================================================
-- Migration 002: Core Multi-Tenancy & Horizon Media Tables + RLS
-- Forward-only migration.
--
-- Backward-compatibility strategy for legacy Horizon Meet 'recordings':
--   Existing Horizon frontend/media queries insert/select on `recordings`.
--   We retain `recordings` (scoped by org_id + RLS) and attach an BEFORE/AFTER
--   trigger `trg_sync_recordings_to_unified` that mirrors new recordings into
--   the normalized `meetings` and `dubbing_jobs` tables automatically.
--
-- Rollback notes (manual emergency only):
--   DROP TRIGGER IF EXISTS trg_sync_recordings_to_unified ON public.recordings;
--   DROP FUNCTION IF EXISTS public.sync_recordings_to_unified();
--   DROP TABLE IF EXISTS public.recordings;
--   DROP TABLE IF EXISTS public.dubbing_jobs;
--   DROP TABLE IF EXISTS public.transcripts;
--   DROP TABLE IF EXISTS public.meetings;
--   DROP TABLE IF EXISTS public.members;
--   DROP TABLE IF EXISTS public.organizations;
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.organizations (
    id          TEXT PRIMARY KEY,              -- Clerk org_id (e.g. org_2abc...)
    name        TEXT NOT NULL,
    slug        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.members (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         TEXT NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    clerk_user_id  TEXT NOT NULL,
    email          TEXT,
    role           TEXT NOT NULL DEFAULT 'org:member',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, clerk_user_id)
);

CREATE TABLE IF NOT EXISTS public.meetings (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         TEXT NOT NULL,
    stream_call_id TEXT,
    title          TEXT NOT NULL DEFAULT 'Untitled Meeting',
    recording_url  TEXT,
    status         TEXT NOT NULL DEFAULT 'ENDED',
    summary        TEXT,
    chapters       JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at     TIMESTAMPTZ,
    ended_at       TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_meetings_org_id ON public.meetings(org_id);
CREATE INDEX IF NOT EXISTS idx_meetings_stream_call_id ON public.meetings(stream_call_id);

CREATE TABLE IF NOT EXISTS public.transcripts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id  UUID NOT NULL REFERENCES public.meetings(id) ON DELETE CASCADE,
    org_id      TEXT NOT NULL,
    segments    JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{speaker, speaker_user_id, start, end, text}]
    language    TEXT NOT NULL DEFAULT 'en',
    provider    TEXT NOT NULL DEFAULT 'gnani_prisma',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_transcripts_org_meeting ON public.transcripts(org_id, meeting_id);

CREATE TABLE IF NOT EXISTS public.dubbing_jobs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id     UUID NOT NULL REFERENCES public.meetings(id) ON DELETE CASCADE,
    org_id         TEXT NOT NULL,
    source_lang    TEXT DEFAULT 'hi-IN',
    target_lang    TEXT NOT NULL DEFAULT 'en',
    provider       TEXT NOT NULL DEFAULT 'gnani_timbre',
    status         TEXT NOT NULL DEFAULT 'QUEUED',   -- QUEUED | PROCESSING | COMPLETED | FAILED
    output_url     TEXT,
    chapters       JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_message  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dubbing_jobs_org_meeting ON public.dubbing_jobs(org_id, meeting_id);

-- Backward-compatible Horizon Meet recordings table
CREATE TABLE IF NOT EXISTS public.recordings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              TEXT NOT NULL DEFAULT 'org_demo_horizon',
    meeting_id          UUID REFERENCES public.meetings(id) ON DELETE SET NULL,
    original_video_url  TEXT NOT NULL,
    dubbed_video_url    TEXT DEFAULT '',
    summary             TEXT DEFAULT '',
    chapters            JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_recordings_org_id ON public.recordings(org_id);

-- Sync trigger from legacy `recordings` inserts/updates -> normalized `meetings` & `dubbing_jobs`
CREATE OR REPLACE FUNCTION public.sync_recordings_to_unified()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_meeting_id UUID;
BEGIN
    v_meeting_id := COALESCE(NEW.meeting_id, NEW.id);
    NEW.meeting_id := v_meeting_id;

    INSERT INTO public.meetings (id, org_id, recording_url, status, summary, chapters, created_at)
    VALUES (
        v_meeting_id,
        NEW.org_id,
        NEW.original_video_url,
        'COMPLETED',
        NULLIF(NEW.summary, ''),
        COALESCE(NEW.chapters, '[]'::jsonb),
        NEW.created_at
    )
    ON CONFLICT (id) DO UPDATE SET
        recording_url = EXCLUDED.recording_url,
        summary       = COALESCE(EXCLUDED.summary, public.meetings.summary),
        chapters      = CASE
            WHEN jsonb_array_length(EXCLUDED.chapters) > 0 THEN EXCLUDED.chapters
            ELSE public.meetings.chapters
        END;

    IF NEW.dubbed_video_url IS NOT NULL AND NEW.dubbed_video_url <> '' THEN
        INSERT INTO public.dubbing_jobs (id, meeting_id, org_id, target_lang, status, output_url, chapters)
        VALUES (
            NEW.id,
            v_meeting_id,
            NEW.org_id,
            'en',
            'COMPLETED',
            NEW.dubbed_video_url,
            COALESCE(NEW.chapters, '[]'::jsonb)
        )
        ON CONFLICT (id) DO UPDATE SET
            output_url = EXCLUDED.output_url,
            chapters   = EXCLUDED.chapters,
            status     = 'COMPLETED',
            updated_at = now();
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sync_recordings_to_unified ON public.recordings;
CREATE TRIGGER trg_sync_recordings_to_unified
    BEFORE INSERT OR UPDATE ON public.recordings
    FOR EACH ROW
    EXECUTE FUNCTION public.sync_recordings_to_unified();

-- ----------------------------------------------------------------------------
-- Row Level Security (RLS)
-- ----------------------------------------------------------------------------
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.members       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.meetings      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.transcripts   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dubbing_jobs  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recordings    ENABLE ROW LEVEL SECURITY;

CREATE POLICY org_select_own ON public.organizations
    FOR SELECT USING (id = public.current_org_id());

CREATE POLICY members_tenant_isolation ON public.members
    FOR ALL
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY meetings_tenant_isolation ON public.meetings
    FOR ALL
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY transcripts_tenant_isolation ON public.transcripts
    FOR ALL
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY dubbing_jobs_tenant_isolation ON public.dubbing_jobs
    FOR ALL
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

CREATE POLICY recordings_tenant_isolation ON public.recordings
    FOR ALL
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

