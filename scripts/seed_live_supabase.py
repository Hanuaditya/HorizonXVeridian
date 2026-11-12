"""Idempotent tenant-aware Supabase seeder for Horizon Veridian WorkOS.

Ensures ``organizations``, ``employees``, ``hr_employees``, ``finance_budgets``,
and ``security_policies`` are populated for the given Clerk ``--org-id``.
Never prints API keys or secrets.

Usage:
    python scripts/seed_live_supabase.py
    python scripts/seed_live_supabase.py --org-id org_2abcXYZ
    python scripts/seed_live_supabase.py --org-id org_2abcXYZ --force
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKOS_ROOT = REPO_ROOT / "services" / "workos"
for p in (str(REPO_ROOT), str(WORKOS_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

load_dotenv(REPO_ROOT / ".env", override=False)

from db.seed.seed_cli import run_seed  # noqa: E402
from core.store import _get_supabase, using_live_supabase  # noqa: E402


def _slugify(val: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (val or "horizon-veridian").lower()).strip("-")
    return slug or "horizon-veridian"


def _table_count(sb, table: str, org_id: str) -> int:
    res = sb.table(table).select("id", count="exact").eq("org_id", org_id).limit(1).execute()
    if getattr(res, "count", None) is not None:
        return int(res.count)
    return len(res.data or [])


def ensure_org_seeded(org_id: str, org_name: str, force: bool = False) -> dict:
    if not using_live_supabase():
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required in .env to seed live Supabase."
        )

    sb = _get_supabase()
    sb.table("organizations").upsert(
        {"id": org_id, "name": org_name, "slug": _slugify(f"{org_name}-{org_id[-6:]}")},
        on_conflict="id",
    ).execute()

    tables = ("employees", "hr_employees", "finance_budgets", "security_policies")
    before = {tbl: _table_count(sb, tbl, org_id) for tbl in tables}
    needs_seed = force or any(count == 0 for count in before.values())

    action = "already_seeded"
    if needs_seed:
        run_seed(org_id=org_id)
        action = "seeded"

    after = {tbl: _table_count(sb, tbl, org_id) for tbl in tables}
    return {
        "org_id": org_id,
        "action": action,
        "before": before,
        "after": after,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Idempotently seed live Supabase tables for a Clerk org_id.")
    parser.add_argument("--org-id", default="org_demo_horizon", help="Target Clerk organization ID")
    parser.add_argument("--org-name", default="Horizon Veridian Enterprise", help="Organization display name")
    parser.add_argument("--force", action="store_true", help="Re-seed rows even if already present")
    args = parser.parse_args()

    result = ensure_org_seeded(org_id=args.org_id, org_name=args.org_name, force=args.force)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

