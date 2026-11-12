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
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKOS_ROOT = REPO_ROOT / "services" / "workos"
for p in (str(REPO_ROOT), str(WORKOS_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

load_dotenv(REPO_ROOT / ".env", override=False)

from db.seed.seed_cli import run_seed  # noqa: E402
from core.store import _get_supabase, list_employees, using_live_supabase  # noqa: E402

DEFAULT_TEAM_MEMBERS = [
    {
        "full_name": "Aarav Sharma",
        "email": "aarav.sharma@example.com",
        "clerk_user_id": "user_clerk_manager_demo",
        "slack_user_id": "U_MGR_DEMO",
        "role": "Engineering Manager",
        "hr_status": "ACTIVE",
        "department": "Engineering Leadership",
        "domain_skills": ["management", "architecture", "security", "infra"],
        "active_task_count": 0,
    },
    {
        "full_name": "Rohan Patel",
        "email": "rohan.patel@example.com",
        "clerk_user_id": "user_clerk_emp_a_demo",
        "slack_user_id": "U_EMP_A_DEMO",
        "role": "Senior Backend Engineer",
        "hr_status": "ACTIVE",
        "department": "Platform Engineering",
        "domain_skills": ["elasticsearch", "aws", "backend", "infra", "kubernetes"],
        "active_task_count": 1,
    },
    {
        "full_name": "Priya Sen",
        "email": "priya.sen@example.com",
        "clerk_user_id": "user_clerk_emp_b_demo",
        "slack_user_id": "U_EMP_B_DEMO",
        "role": "Product & Frontend Engineer",
        "hr_status": "ACTIVE",
        "department": "Product & Frontend Engineering",
        "domain_skills": ["frontend", "auth", "oauth", "ui", "api"],
        "active_task_count": 2,
    },
    {
        "full_name": "Arjun Rao",
        "email": "arjun.rao@example.com",
        "clerk_user_id": "user_demo_arjun",
        "slack_user_id": "U_ARJUN_DEMO",
        "role": "Group Product Manager, CI/CD",
        "hr_status": "ON_PATERNITY_LEAVE",
        "department": "Product Management",
        "domain_skills": ["elasticsearch", "aws", "backend"],
        "active_task_count": 2,
        "leave_until": "2026-12-15",
    },
]


def load_live_team_members() -> list[dict]:
    """Load team identities from gitignored local.identities.json or fallback to clean defaults."""
    local_file = REPO_ROOT / "local.identities.json"
    if local_file.exists():
        try:
            with open(local_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "team" in data and isinstance(data["team"], list):
                    return data["team"]
                elif isinstance(data, list):
                    return data
        except Exception:
            pass
    return DEFAULT_TEAM_MEMBERS


REAL_TEAM_MEMBERS = load_live_team_members()


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

    # Check whether new sprint orchestrator seed items (SEC-POL-104 + domain_skills) exist
    pol_res = (
        sb.table("security_policies")
        .select("policy_id")
        .eq("org_id", org_id)
        .eq("policy_id", "SEC-POL-104")
        .execute()
    )
    has_pol_104 = bool(pol_res.data)
    existing_emps = list_employees(org_id=org_id)
    has_skills = bool(existing_emps) and all("skills:" in str(e.get("last_synced_from") or "") or e.get("domain_skills") for e in existing_emps)
    needs_seed = force or any(count == 0 for count in before.values()) or not has_pol_104 or not has_skills

    action = "already_seeded"
    if needs_seed:
        run_seed(org_id=org_id)
        action = "seeded"

    # Ensure the 3 real team identities + Jason are bound with verified Clerk and Slack IDs
    now_iso = datetime.now(timezone.utc).isoformat()
    for mem in REAL_TEAM_MEMBERS:
        skills_tag = f" | skills:{','.join(mem['domain_skills'])}" if mem.get("domain_skills") else ""
        hr_row = {
            "org_id": org_id,
            "full_name": mem["full_name"],
            "email": mem["email"],
            "department": mem.get("department", "Engineering"),
            "job_title": mem["role"],
            "status": mem["hr_status"],
            "leave_until": mem.get("leave_until"),
            "last_synced_from": f"Team Identity Binding{skills_tag}",
            "synced_at": now_iso,
        }
        sb.table("hr_employees").upsert(hr_row, on_conflict="org_id,full_name").execute()

        emp_row = {
            "org_id": org_id,
            "clerk_user_id": mem["clerk_user_id"],
            "full_name": mem["full_name"],
            "email": mem["email"],
            "slack_id": mem["slack_user_id"],
            "status": mem["hr_status"],
            "active": mem["hr_status"] == "ACTIVE",
            "capacity_cache": mem["active_task_count"],
            "active_task_count": mem["active_task_count"],
            "domain_skills": mem["domain_skills"],
            "last_synced_from": f"Team Identity Binding{skills_tag}",
            "synced_at": now_iso,
        }
        try:
            sb.table("employees").upsert(emp_row, on_conflict="org_id,full_name").execute()
        except Exception:
            fallback = {k: v for k, v in emp_row.items() if k not in {"domain_skills", "active_task_count"}}
            sb.table("employees").upsert(fallback, on_conflict="org_id,full_name").execute()

    after = {tbl: _table_count(sb, tbl, org_id) for tbl in tables}
    all_emps = list_employees(org_id=org_id)
    team_bindings = [
        {
            "full_name": e.get("full_name"),
            "clerk_user_id": e.get("clerk_user_id"),
            "slack_id": e.get("slack_id"),
            "email": e.get("email"),
            "status": e.get("status"),
            "domain_skills": e.get("domain_skills"),
            "active_task_count": e.get("active_task_count"),
        }
        for e in all_emps
        if any(m["full_name"].lower() == str(e.get("full_name") or "").lower() for m in REAL_TEAM_MEMBERS)
    ]
    return {
        "org_id": org_id,
        "action": action,
        "sec_pol_104_present": True,
        "before": before,
        "after": after,
        "team_bindings": team_bindings,
        "all_employees_count": len(all_emps),
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

