"""Org-aware HRIS connector (reads JSON seed or BambooHR payload, syncs hr_employees + employees)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from core.config import get_settings
from core.store import _normalize_hr_status, upsert_hr_records

logger = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[3]


class EmployeeRecord(BaseModel):
    full_name: str = Field(description="Employee full name")
    email: Optional[str] = None
    department: str = Field(default="Engineering")
    job_title: str = Field(default="Engineer")
    status: Literal[
        "ACTIVE",
        "NEW_HIRE",
        "ON_PATERNITY_LEAVE",
        "ON_MATERNITY_LEAVE",
        "ON_LEAVE",
        "TERMINATED",
        "INACTIVE",
    ]
    leave_until: Optional[str] = None
    open_tickets: int = 0
    slack_id: Optional[str] = None
    jira_account_id: Optional[str] = None


def sync_hr_data(org_id: str, json_path: Optional[str] = None) -> int:
    """Sync HR records for a specific org_id into hr_employees and employees."""
    settings = get_settings()
    path = Path(json_path) if json_path else (_REPO_ROOT / settings.hr_json_path)
    if not path.exists():
        raise FileNotFoundError(f"HR source file not found: {path}")

    raw_data = json.loads(path.read_text(encoding="utf-8"))
    employees = raw_data.get("employees", [])
    now_iso = datetime.now(timezone.utc).isoformat()

    hr_rows: List[Dict] = []
    emp_rows: List[Dict] = []

    for emp in employees:
        validated = EmployeeRecord(
            full_name=emp["displayName"],
            email=emp.get("workEmail"),
            department=emp.get("department", "Engineering"),
            job_title=emp.get("jobTitle", "Engineer"),
            status=_normalize_hr_status(emp.get("employmentStatus", "Active")),  # type: ignore[arg-type]
            leave_until=emp.get("leaveUntil"),
            open_tickets=int(emp.get("openTickets", 0)),
            slack_id=emp.get("slackId"),
            jira_account_id=emp.get("jiraAccountId"),
        )
        hr_rows.append({
            "id": str(uuid.uuid4()),
            "org_id": org_id,
            "full_name": validated.full_name,
            "email": validated.email,
            "department": validated.department,
            "job_title": validated.job_title,
            "status": validated.status,
            "leave_until": validated.leave_until,
            "last_synced_from": "BambooHR connector",
            "synced_at": now_iso,
        })
        emp_rows.append({
            "id": str(uuid.uuid4()),
            "org_id": org_id,
            "full_name": validated.full_name,
            "email": validated.email,
            "slack_id": validated.slack_id,
            "jira_account_id": validated.jira_account_id,
            "status": validated.status,
            "active": validated.status in {"ACTIVE", "NEW_HIRE"},
            "capacity_cache": validated.open_tickets,
            "last_synced_from": "BambooHR connector",
            "synced_at": now_iso,
        })

    count = upsert_hr_records(org_id=org_id, hr_rows=hr_rows, emp_rows=emp_rows)
    logger.info("sync_hr_data: synced %d HR employees for org '%s'.", count, org_id)
    return count
