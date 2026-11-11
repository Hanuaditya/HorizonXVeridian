"""CLI seed command: loads HR, Finance CSV, and Security policies (with 1024-dim vectors).

Usage:
    python -m db.seed.seed_cli --org-id org_demo_horizon
    python -m db.seed.seed_cli --org-id org_demo_horizon --emit-sql db/seed/seed_data.sql
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import List

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKOS_ROOT = _REPO_ROOT / "services" / "workos"
for _p in (str(_REPO_ROOT), str(_WORKOS_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from connectors.sync_finance import _parse_amount, sync_finance_data
from connectors.sync_hr import sync_hr_data
from connectors.sync_security import sync_security_data
from core.config import get_settings
from core.embeddings import get_embedding
from core.store import _normalize_hr_status, _parse_security_markdown


def _sql_str(val: str | None) -> str:
    if val is None:
        return "NULL"
    escaped = str(val).replace("'", "''")
    return f"'{escaped}'"


def _sql_vector(vec: List[float]) -> str:
    joined = ",".join(f"{v:.6f}" for v in vec)
    return f"'[{joined}]'::vector({len(vec)})"


def generate_seed_sql(org_id: str) -> str:
    settings = get_settings()
    lines: List[str] = [
        "-- ============================================================================",
        "-- Horizon Veridian — Seed Data SQL (Precomputed 1024-dim pgvector embeddings)",
        f"-- Target org_id: {org_id}",
        "-- ============================================================================",
        "",
        "INSERT INTO public.organizations (id, name, slug)",
        f"VALUES ({_sql_str(org_id)}, 'Horizon Veridian Enterprise Demo', 'horizon-veridian-demo')",
        "ON CONFLICT (id) DO NOTHING;",
        "",
    ]

    hr_path = _REPO_ROOT / settings.hr_json_path
    hr_data = json.loads(hr_path.read_text(encoding="utf-8"))
    for emp in hr_data.get("employees", []):
        status = _normalize_hr_status(emp.get("employmentStatus", "Active"))
        leave_until = _sql_str(emp.get("leaveUntil"))
        active = "true" if status in {"ACTIVE", "NEW_HIRE"} else "false"
        open_tickets = int(emp.get("openTickets", 0))
        lines.append(
            "INSERT INTO public.hr_employees "
            "(org_id, full_name, email, department, job_title, status, leave_until, last_synced_from) "
            f"VALUES ({_sql_str(org_id)}, {_sql_str(emp['displayName'])}, {_sql_str(emp.get('workEmail'))}, "
            f"{_sql_str(emp.get('department'))}, {_sql_str(emp.get('jobTitle'))}, {_sql_str(status)}, "
            f"{leave_until}, 'BambooHR connector (seed)') "
            "ON CONFLICT (org_id, full_name) DO UPDATE SET status = EXCLUDED.status, synced_at = now();"
        )
        lines.append(
            "INSERT INTO public.employees "
            "(org_id, clerk_user_id, full_name, email, slack_id, jira_account_id, status, active, capacity_cache, last_synced_from) "
            f"VALUES ({_sql_str(org_id)}, {_sql_str('user_demo_' + emp['firstName'].lower())}, "
            f"{_sql_str(emp['displayName'])}, {_sql_str(emp.get('workEmail'))}, "
            f"{_sql_str(emp.get('slackId'))}, {_sql_str(emp.get('jiraAccountId'))}, "
            f"{_sql_str(status)}, {active}, {open_tickets}, 'Seed / Jira capacity cache') "
            "ON CONFLICT (org_id, full_name) DO UPDATE SET status = EXCLUDED.status, capacity_cache = EXCLUDED.capacity_cache;"
        )

    lines.append("")
    csv_path = _REPO_ROOT / settings.finance_csv_path
    with csv_path.open("r", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            cat_raw = (row.get("Category") or "").strip()
            if not cat_raw:
                continue
            cat_key = cat_raw.split()[0].lower()
            notes = (row.get("Notes") or "").strip()
            budget = _parse_amount(row.get("Budget Remaining", "0"))
            currency = (row.get("Currency") or "INR").strip()
            owner = (row.get("Owner") or "Finance").strip()
            vec = get_embedding(f"{cat_raw} {notes}", dim=settings.embedding_dim)
            lines.append(
                "INSERT INTO public.finance_budgets "
                "(org_id, category, budget_remaining, currency, owner, embedding, last_synced_from) "
                f"VALUES ({_sql_str(org_id)}, {_sql_str(cat_key)}, {budget}, {_sql_str(currency)}, "
                f"{_sql_str(owner)}, {_sql_vector(vec)}, 'finance_budgets.csv') "
                "ON CONFLICT (org_id, category) DO UPDATE SET "
                "budget_remaining = EXCLUDED.budget_remaining, embedding = EXCLUDED.embedding, synced_at = now();"
            )

    lines.append("")
    sec_path = _REPO_ROOT / settings.security_policy_path
    sections = _parse_security_markdown(sec_path.read_text(encoding="utf-8"))
    for idx, (pol_id, chunk_text) in enumerate(sections, start=1):
        vec = get_embedding(f"{pol_id} {chunk_text}", dim=settings.embedding_dim)
        lines.append(
            "INSERT INTO public.security_policies "
            "(org_id, policy_id, document_name, chunk_text, page_number, embedding) "
            f"VALUES ({_sql_str(org_id)}, {_sql_str(pol_id)}, "
            "'Veridian Global Information Security Policy v4.2', "
            f"{_sql_str(chunk_text)}, {idx}, {_sql_vector(vec)}) "
            "ON CONFLICT (org_id, policy_id, page_number) DO UPDATE SET "
            "chunk_text = EXCLUDED.chunk_text, embedding = EXCLUDED.embedding, synced_at = now();"
        )

    lines.append("")
    return "\n".join(lines)


def run_seed(org_id: str, emit_sql: str | None = None) -> dict:
    hr_count = sync_hr_data(org_id=org_id)
    fin_rows = sync_finance_data(org_id=org_id)
    sec_rows = sync_security_data(org_id=org_id)
    if emit_sql:
        sql_content = generate_seed_sql(org_id=org_id)
        out_path = _REPO_ROOT / emit_sql
        out_path.write_text(sql_content, encoding="utf-8")
    return {
        "org_id": org_id,
        "hr_employees": hr_count,
        "finance_budgets": len(fin_rows),
        "security_policies": len(sec_rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Horizon Veridian database for an organization.")
    parser.add_argument("--org-id", default="org_demo_horizon", help="Target Clerk organization ID")
    parser.add_argument("--emit-sql", default=None, help="Optional path to write standalone seed SQL file")
    args = parser.parse_args()

    result = run_seed(org_id=args.org_id, emit_sql=args.emit_sql)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
