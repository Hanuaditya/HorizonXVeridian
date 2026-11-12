# Database Migrations (Unified Supabase + pgvector)

Migrations in this directory are **strictly numbered and forward-only**. Never modify an already-applied migration.

## Apply Order
1. `001_enable_pgvector_and_auth_helpers.sql` — Enables `vector` (`pgvector`) & `pgcrypto` extensions and installs `current_org_id()`, `current_user_id()`, and `current_org_role()` JWT claim readers.
2. `002_core_tenancy_and_horizon_media.sql` — Creates `organizations`, `members`, `meetings`, `transcripts`, `dubbing_jobs`, plus backward-compatible `recordings` with auto-sync trigger (`trg_sync_recordings_to_unified`) and RLS policies.
3. `003_workos_firewall_and_pgvector.sql` — Creates WorkOS tables (`employees`, `hr_employees`, `finance_budgets`, `security_policies`, `processed_meetings`, `tasks`, `resolutions`, `approvals`, `audit_trail`, `slack_threads`, `webhook_events`), **HNSW** `vector(1024)` indexes, tenant-scoped RPCs, `get_vector_column_dimensions()`, and RLS policies.

## How to Apply

### Option A: Supabase Dashboard SQL Editor
Paste and execute `001`, `002`, and `003` in order inside **Supabase Dashboard → SQL Editor**, then run `db/seed/seed_data.sql` (or `python -m db.seed.seed_cli`).

### Option B: `psql` CLI (or local Docker Postgres)
```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/001_enable_pgvector_and_auth_helpers.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/002_core_tenancy_and_horizon_media.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/migrations/003_workos_firewall_and_pgvector.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f db/seed/seed_data.sql
```

