"""Tenant-isolated data access layer for Horizon Veridian WorkOS.

Uses Supabase (service role) with explicit ``org_id`` filtering on every query
when configured, and seamlessly falls back to an offline tenant-isolated store
seeded from ``db/seed/`` when ``DEMO_MODE=true`` and Supabase keys are unset.
"""

from __future__ import annotations

import csv
import importlib
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import httpx

from core.config import get_settings
from core.embeddings import cosine_similarity, get_embedding

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _is_configured_supabase() -> bool:
    settings = get_settings()
    return bool(
        settings.supabase_url
        and settings.supabase_service_role_key
        and "your-project" not in settings.supabase_url
        and "placeholder" not in settings.supabase_service_role_key
    )


class LocalDemoStore:
    """Thread-safe in-memory multi-tenant backing store for DEMO_MODE & unit tests."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.reset()

    def reset(self, seed_default_org: bool = True) -> None:
        with self._lock:
            self.organizations: Dict[str, Dict[str, Any]] = {}
            self.employees: List[Dict[str, Any]] = []
            self.hr_employees: List[Dict[str, Any]] = []
            self.finance_budgets: List[Dict[str, Any]] = []
            self.security_policies: List[Dict[str, Any]] = []
            self.processed_meetings: Dict[tuple[str, str], Dict[str, Any]] = {}
            self.meetings: Dict[str, Dict[str, Any]] = {}
            self.transcripts: Dict[str, Dict[str, Any]] = {}
            self.tasks: List[Dict[str, Any]] = []
            self.resolutions: List[Dict[str, Any]] = []
            self.approvals: List[Dict[str, Any]] = []
            self.audit_trail: List[Dict[str, Any]] = []
            self.slack_threads: List[Dict[str, Any]] = []
            self.slack_feed: List[Dict[str, Any]] = []
            self.webhook_events: set[tuple[str, str]] = set()
            self.thread_states: Dict[str, Dict[str, Any]] = {}
            self._seeded = False
            if seed_default_org:
                self._seed_org("org_demo_horizon")
                self._seeded = True

    def _seed_org(self, org_id: str) -> None:
        settings = get_settings()
        self.organizations[org_id] = {
            "id": org_id,
            "name": "Horizon Veridian Enterprise Demo",
            "slug": "horizon-veridian-demo",
        }
        hr_path = _REPO_ROOT / settings.hr_json_path
        if hr_path.exists():
            data = json.loads(hr_path.read_text(encoding="utf-8"))
            now_iso = datetime.now(timezone.utc).isoformat()
            for emp in data.get("employees", []):
                raw_status = emp.get("employmentStatus", "Active")
                norm_status = _normalize_hr_status(raw_status)
                skills = [str(s).strip().lower() for s in (emp.get("domainSkills") or emp.get("domain_skills") or []) if str(s).strip()]
                skills_tag = f" | skills:{','.join(skills)}" if skills else ""
                open_cnt = int(emp.get("openTickets", 0))
                self.hr_employees.append({
                    "id": str(uuid.uuid4()),
                    "org_id": org_id,
                    "full_name": emp["displayName"],
                    "email": emp.get("workEmail"),
                    "department": emp.get("department"),
                    "job_title": emp.get("jobTitle"),
                    "status": norm_status,
                    "leave_until": emp.get("leaveUntil"),
                    "last_synced_from": f"BambooHR connector (seed){skills_tag}",
                    "synced_at": now_iso,
                })
                self.employees.append({
                    "id": str(uuid.uuid4()),
                    "org_id": org_id,
                    "clerk_user_id": f"user_demo_{emp['firstName'].lower()}",
                    "full_name": emp["displayName"],
                    "email": emp.get("workEmail"),
                    "slack_id": emp.get("slackId"),
                    "jira_account_id": emp.get("jiraAccountId"),
                    "status": norm_status,
                    "active": norm_status in {"ACTIVE", "NEW_HIRE"},
                    "capacity_cache": open_cnt,
                    "active_task_count": open_cnt,
                    "domain_skills": skills,
                    "last_synced_from": f"Seed / Jira capacity cache{skills_tag}",
                    "synced_at": now_iso,
                })

        csv_path = _REPO_ROOT / settings.finance_csv_path
        if csv_path.exists():
            now_iso = datetime.now(timezone.utc).isoformat()
            with csv_path.open("r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    cat_raw = (row.get("Category") or "").strip()
                    if not cat_raw:
                        continue
                    cat_key = cat_raw.split()[0].lower()
                    notes = (row.get("Notes") or "").strip()
                    emb = get_embedding(f"{cat_raw} {notes}")
                    self.finance_budgets.append({
                        "id": str(uuid.uuid4()),
                        "org_id": org_id,
                        "category": cat_key,
                        "budget_remaining": float(row.get("Budget Remaining") or 0),
                        "currency": (row.get("Currency") or "INR").strip(),
                        "owner": (row.get("Owner") or "Finance").strip(),
                        "embedding": emb,
                        "last_synced_from": "finance_budgets.csv",
                        "synced_at": now_iso,
                    })

        sec_path = _REPO_ROOT / settings.security_policy_path
        if sec_path.exists():
            now_iso = datetime.now(timezone.utc).isoformat()
            chunks = _parse_security_markdown(sec_path.read_text(encoding="utf-8"))
            for idx, (pol_id, chunk_text) in enumerate(chunks, start=1):
                self.security_policies.append({
                    "id": str(uuid.uuid4()),
                    "org_id": org_id,
                    "policy_id": pol_id,
                    "document_name": "Veridian Global Information Security Policy v4.2",
                    "chunk_text": chunk_text,
                    "page_number": idx,
                    "embedding": get_embedding(f"{pol_id} {chunk_text}"),
                    "synced_at": now_iso,
                })


def _normalize_hr_status(raw: str) -> str:
    low = (raw or "").lower()
    if "paternity" in low:
        return "ON_PATERNITY_LEAVE"
    if "maternity" in low:
        return "ON_MATERNITY_LEAVE"
    if "leave" in low:
        return "ON_LEAVE"
    if "terminat" in low:
        return "TERMINATED"
    if "new" in low and "hire" in low:
        return "NEW_HIRE"
    if "active" in low:
        return "ACTIVE"
    return "INACTIVE"


def _parse_security_markdown(text: str) -> List[tuple[str, str]]:
    sections: List[tuple[str, str]] = []
    current_id: Optional[str] = None
    current_lines: List[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_id and current_lines:
                sections.append((current_id, "\n".join(current_lines).strip()))
            header = line[3:].strip()
            current_id = header.split(":", 1)[0].strip()
            current_lines = [header]
        elif current_id:
            if line.strip():
                current_lines.append(line.strip())
    if current_id and current_lines:
        sections.append((current_id, "\n".join(current_lines).strip()))
    return sections


_local_store = LocalDemoStore()
_supabase_client: Any = None


def get_local_store() -> LocalDemoStore:
    return _local_store


class _PostgrestResponse:
    def __init__(self, data: Any = None, count: Optional[int] = None) -> None:
        self.data = data
        self.count = count


class _PostgrestQuery:
    def __init__(self, rest_url: str, headers: Dict[str, str], table: str) -> None:
        self._url = f"{rest_url}/{table}"
        self._headers = dict(headers)
        self._method = "GET"
        self._params: List[tuple[str, str]] = []
        self._json: Any = None
        self._want_count = False

    def select(self, columns: str = "*", count: Optional[str] = None) -> "_PostgrestQuery":
        self._method = "GET"
        self._params.append(("select", columns))
        if count == "exact":
            self._want_count = True
        return self

    def insert(self, payload: Any) -> "_PostgrestQuery":
        self._method = "POST"
        self._json = payload
        self._headers["Prefer"] = "return=representation"
        return self

    def upsert(self, payload: Any, on_conflict: Optional[str] = None) -> "_PostgrestQuery":
        self._method = "POST"
        self._json = payload
        self._headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        if on_conflict:
            self._params.append(("on_conflict", on_conflict))
        return self

    def update(self, payload: Dict[str, Any]) -> "_PostgrestQuery":
        self._method = "PATCH"
        self._json = payload
        self._headers["Prefer"] = "return=representation"
        return self

    def delete(self) -> "_PostgrestQuery":
        self._method = "DELETE"
        return self

    def eq(self, col: str, val: Any) -> "_PostgrestQuery":
        self._params.append((col, f"eq.{val}"))
        return self

    def ilike(self, col: str, pattern: str) -> "_PostgrestQuery":
        self._params.append((col, f"ilike.{pattern}"))
        return self

    def order(self, col: str, desc: bool = False) -> "_PostgrestQuery":
        self._params.append(("order", f"{col}.{'desc' if desc else 'asc'}"))
        return self

    def limit(self, n: int) -> "_PostgrestQuery":
        self._params.append(("limit", str(n)))
        return self

    def execute(self) -> _PostgrestResponse:
        if self._want_count:
            existing = self._headers.get("Prefer", "")
            self._headers["Prefer"] = f"{existing},count=exact".strip(",")
        resp = httpx.request(
            self._method,
            self._url,
            headers=self._headers,
            params=self._params,
            json=self._json,
            timeout=20.0,
        )
        resp.raise_for_status()
        data = resp.json() if resp.content else []
        count_val: Optional[int] = None
        if self._want_count:
            cr = resp.headers.get("content-range", "")
            if "/" in cr:
                total_str = cr.split("/")[-1]
                if total_str.isdigit():
                    count_val = int(total_str)
        return _PostgrestResponse(data=data, count=count_val)


class _PostgrestRpc:
    def __init__(self, rest_url: str, headers: Dict[str, str], fn: str, params: Dict[str, Any]) -> None:
        self._url = f"{rest_url}/rpc/{fn}"
        self._headers = dict(headers)
        self._params = params

    def execute(self) -> _PostgrestResponse:
        resp = httpx.post(self._url, headers=self._headers, json=self._params, timeout=20.0)
        resp.raise_for_status()
        data = resp.json() if resp.content else []
        return _PostgrestResponse(data=data)


class _PostgrestCompatClient:
    """Lightweight httpx-backed PostgREST client when supabase-py is absent."""

    def __init__(self, supabase_url: str, service_role_key: str) -> None:
        self._rest_url = f"{supabase_url.rstrip('/')}/rest/v1"
        self._headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }

    def table(self, name: str) -> _PostgrestQuery:
        return _PostgrestQuery(self._rest_url, self._headers, name)

    def rpc(self, fn_name: str, params: Optional[Dict[str, Any]] = None) -> _PostgrestRpc:
        return _PostgrestRpc(self._rest_url, self._headers, fn_name, params or {})


def _get_supabase():
    global _supabase_client
    if _supabase_client is None:
        settings = get_settings()
        try:
            supabase_mod = importlib.import_module("supabase")
            _supabase_client = supabase_mod.create_client(
                settings.supabase_url,
                settings.supabase_service_role_key,
            )
        except ImportError:
            _supabase_client = _PostgrestCompatClient(
                settings.supabase_url,
                settings.supabase_service_role_key,
            )
    return _supabase_client


def using_live_supabase() -> bool:
    return _is_configured_supabase()


# ----------------------------------------------------------------------------
# Startup Assertion: DB Vector Dimension == EMBEDDING_DIM
# ----------------------------------------------------------------------------

def assert_embedding_dimension_match() -> int:
    """Verify configured EMBEDDING_DIM matches database vector column definitions."""
    settings = get_settings()
    expected_dim = settings.embedding_dim

    if using_live_supabase():
        sb = _get_supabase()
        resp = sb.rpc("get_vector_column_dimensions", {}).execute()
        rows = resp.data or []
        for row in rows:
            col_dim = int(row["dim"])
            if col_dim != expected_dim:
                raise RuntimeError(
                    f"Vector dimension mismatch on {row['table_name']}.{row['column_name']}: "
                    f"DB has vector({col_dim}), EMBEDDING_DIM is {expected_dim}"
                )
        logger.info("Startup vector dimension check passed against Supabase (%d).", expected_dim)
        return expected_dim

    # Validate local store / schema expectation
    for row in _local_store.security_policies + _local_store.finance_budgets:
        emb = row.get("embedding")
        if emb is not None and len(emb) != expected_dim:
            raise RuntimeError(
                f"Local vector dimension mismatch: stored len={len(emb)} vs EMBEDDING_DIM={expected_dim}"
            )
    logger.info("Startup vector dimension check passed in offline mode (%d).", expected_dim)
    return expected_dim


# ----------------------------------------------------------------------------
# Org-Scoped Repository Operations (always explicit org_id)
# ----------------------------------------------------------------------------

def is_meeting_processed(org_id: str, meeting_id: str) -> bool:
    if using_live_supabase():
        sb = _get_supabase()
        res = (
            sb.table("processed_meetings")
            .select("meeting_id")
            .eq("org_id", org_id)
            .eq("meeting_id", meeting_id)
            .execute()
        )
        return bool(res.data)
    with _local_store._lock:
        return (org_id, meeting_id) in _local_store.processed_meetings


def mark_meeting_processed(
    org_id: str,
    meeting_id: str,
    thread_id: str,
    task_count: int = 0,
) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    if using_live_supabase():
        sb = _get_supabase()
        sb.table("processed_meetings").upsert(
            {
                "org_id": org_id,
                "meeting_id": meeting_id,
                "thread_id": thread_id,
                "processed_at": now_iso,
                "task_count": task_count,
            },
            on_conflict="org_id,meeting_id",
        ).execute()
        return
    with _local_store._lock:
        _local_store.processed_meetings[(org_id, meeting_id)] = {
            "org_id": org_id,
            "meeting_id": meeting_id,
            "thread_id": thread_id,
            "processed_at": now_iso,
            "task_count": task_count,
        }


def _load_seed_skills_map() -> Dict[str, List[str]]:
    settings = get_settings()
    hr_path = _REPO_ROOT / settings.hr_json_path
    if not hr_path.exists():
        return {}
    try:
        data = json.loads(hr_path.read_text(encoding="utf-8"))
        return {
            str(e["displayName"]).lower(): [
                str(s).strip().lower() for s in (e.get("domainSkills") or []) if str(s).strip()
            ]
            for e in data.get("employees", [])
            if e.get("displayName")
        }
    except Exception:
        return {}


def _extract_skills_from_row(row: Dict[str, Any], seed_map: Dict[str, List[str]]) -> List[str]:
    explicit = row.get("domain_skills")
    if isinstance(explicit, list) and explicit:
        return [str(s).strip().lower() for s in explicit if str(s).strip()]
    src = str(row.get("last_synced_from") or "")
    if "skills:" in src:
        tail = src.split("skills:", 1)[1].split("|")[0].strip()
        parsed = [s.strip().lower() for s in tail.split(",") if s.strip()]
        if parsed:
            return parsed
    return seed_map.get(str(row.get("full_name") or "").lower(), [])


def list_employees(org_id: str) -> List[Dict[str, Any]]:
    if using_live_supabase():
        sb = _get_supabase()
        res = (
            sb.table("employees")
            .select("*")
            .eq("org_id", org_id)
            .execute()
        )
        rows = res.data or []
    else:
        with _local_store._lock:
            rows = [dict(e) for e in _local_store.employees if e["org_id"] == org_id]

    seed_map = _load_seed_skills_map()
    hydrated: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["domain_skills"] = _extract_skills_from_row(item, seed_map)
        item["active_task_count"] = int(
            item.get("active_task_count")
            if item.get("active_task_count") is not None
            else item.get("capacity_cache") or 0
        )
        hydrated.append(item)
    return hydrated


def upsert_employee_mapping(
    org_id: str,
    full_name: str,
    clerk_user_id: Optional[str] = None,
    slack_id: Optional[str] = None,
    jira_account_id: Optional[str] = None,
    email: Optional[str] = None,
    domain_skills: Optional[List[str]] = None,
    active_task_count: Optional[int] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    skills_tag = f" | skills:{','.join(domain_skills)}" if domain_skills else ""
    if using_live_supabase():
        sb = _get_supabase()
        payload = {
            "org_id": org_id,
            "full_name": full_name,
            "clerk_user_id": clerk_user_id,
            "slack_id": slack_id,
            "jira_account_id": jira_account_id,
            "email": email,
            "domain_skills": domain_skills,
            "active_task_count": active_task_count,
            "status": status,
            "synced_at": now_iso,
        }
        if skills_tag:
            payload["last_synced_from"] = f"Admin identity mapping{skills_tag}"
        payload = {k: v for k, v in payload.items() if v is not None}
        try:
            res = sb.table("employees").upsert(payload, on_conflict="org_id,full_name").execute()
            return (res.data or [payload])[0]
        except Exception:
            fb = {k: v for k, v in payload.items() if k not in {"domain_skills", "active_task_count"}}
            res = sb.table("employees").upsert(fb, on_conflict="org_id,full_name").execute()
            return (res.data or [fb])[0]
    with _local_store._lock:
        for e in _local_store.employees:
            if e["org_id"] == org_id and e["full_name"].lower() == full_name.lower():
                if clerk_user_id is not None:
                    e["clerk_user_id"] = clerk_user_id
                if slack_id is not None:
                    e["slack_id"] = slack_id
                if jira_account_id is not None:
                    e["jira_account_id"] = jira_account_id
                if email is not None:
                    e["email"] = email
                if domain_skills is not None:
                    e["domain_skills"] = domain_skills
                if active_task_count is not None:
                    e["active_task_count"] = active_task_count
                    e["capacity_cache"] = active_task_count
                if status is not None:
                    e["status"] = status
                if skills_tag:
                    e["last_synced_from"] = f"Admin identity mapping{skills_tag}"
                e["synced_at"] = now_iso
                return dict(e)
        row = {
            "id": str(uuid.uuid4()),
            "org_id": org_id,
            "full_name": full_name,
            "clerk_user_id": clerk_user_id,
            "slack_id": slack_id,
            "jira_account_id": jira_account_id,
            "email": email,
            "status": status or "ACTIVE",
            "active": (status or "ACTIVE") in {"ACTIVE", "NEW_HIRE"},
            "capacity_cache": active_task_count or 0,
            "active_task_count": active_task_count or 0,
            "domain_skills": domain_skills or [],
            "last_synced_from": f"Admin identity mapping{skills_tag}" if skills_tag else "Admin identity mapping",
            "synced_at": now_iso,
        }
        _local_store.employees.append(row)
        return dict(row)


def lookup_hr_employee(org_id: str, assignee_name: str) -> Optional[Dict[str, Any]]:
    if using_live_supabase():
        sb = _get_supabase()
        res = (
            sb.table("hr_employees")
            .select("full_name, status, last_synced_from, synced_at")
            .eq("org_id", org_id)
            .ilike("full_name", f"%{assignee_name}%")
            .execute()
        )
        return res.data[0] if res.data else None
    needle = assignee_name.strip().lower()
    with _local_store._lock:
        for row in _local_store.hr_employees:
            if row["org_id"] == org_id and needle in row["full_name"].lower():
                return dict(row)
        return None


def find_best_domain_replacement(
    org_id: str,
    task_text: str,
    resource_type: str = "",
    exclude_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Select an available ACTIVE employee matching task domain skills with the lowest active workload."""
    employees = list_employees(org_id=org_id)
    is_leadership = lambda e: (
        "manager" in str(e.get("job_title") or "").lower()
        or "leadership" in str(e.get("department") or "").lower()
        or "vp" in str(e.get("job_title") or "").lower()
        or str(e.get("full_name") or "").lower() in {"hanu aditya", "scott williamson"}
    )
    candidates = [e for e in employees if e.get("status") == "ACTIVE" and not is_leadership(e)]
    if not candidates:
        candidates = [e for e in employees if e.get("status") in {"ACTIVE", "NEW_HIRE"} and not is_leadership(e)]
    if not candidates:
        candidates = [e for e in employees if e.get("status") in {"ACTIVE", "NEW_HIRE"}]

    filtered = [
        e
        for e in candidates
        if not (exclude_name and exclude_name.lower() in str(e.get("full_name", "")).lower())
    ]
    if not filtered:
        return None

    blob = f"{task_text} {resource_type}".lower()

    def _score(emp: Dict[str, Any]) -> tuple[int, int, str]:
        skills = [str(s).lower() for s in (emp.get("domain_skills") or [])]
        matched = [s for s in skills if s in blob]
        if not matched and resource_type:
            res_low = resource_type.lower()
            if any(k in res_low for k in ("infra", "security", "compute", "deploy")) and any(
                s in skills for s in ("elasticsearch", "aws", "backend", "infra", "kubernetes")
            ):
                matched = [s for s in skills if s in ("elasticsearch", "aws", "backend", "infra", "kubernetes")]
        emp["matched_skills"] = matched or skills[:3]
        workload = int(emp.get("active_task_count") or emp.get("capacity_cache") or 0)
        return (-len(matched), workload, str(emp.get("full_name") or ""))

    filtered.sort(key=_score)
    best = dict(filtered[0])
    best.setdefault("matched_skills", best.get("domain_skills", [])[:3])
    return best


def find_least_loaded_active_employee(
    org_id: str,
    exclude_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    return find_best_domain_replacement(
        org_id=org_id,
        task_text="",
        resource_type="",
        exclude_name=exclude_name,
    )


def query_finance_budgets_semantic(
    org_id: str,
    query_embedding: List[float],
    threshold: float,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    if using_live_supabase():
        sb = _get_supabase()
        res = sb.rpc(
            "match_finance_budgets",
            {
                "p_org_id": org_id,
                "query_embedding": query_embedding,
                "match_threshold": threshold,
                "match_count": limit,
            },
        ).execute()
        return res.data or []

    scored: List[Dict[str, Any]] = []
    with _local_store._lock:
        for row in _local_store.finance_budgets:
            if row["org_id"] != org_id or not row.get("embedding"):
                continue
            sim = cosine_similarity(query_embedding, row["embedding"])
            if sim >= threshold:
                item = {k: v for k, v in row.items() if k != "embedding"}
                item["similarity"] = sim
                scored.append(item)
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]


def query_security_policies_semantic(
    org_id: str,
    query_embedding: List[float],
    threshold: float,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    if using_live_supabase():
        sb = _get_supabase()
        res = sb.rpc(
            "match_security_policies",
            {
                "p_org_id": org_id,
                "query_embedding": query_embedding,
                "match_threshold": threshold,
                "match_count": limit,
            },
        ).execute()
        return res.data or []

    scored: List[Dict[str, Any]] = []
    with _local_store._lock:
        for row in _local_store.security_policies:
            if row["org_id"] != org_id or not row.get("embedding"):
                continue
            sim = cosine_similarity(query_embedding, row["embedding"])
            if sim >= threshold:
                item = {k: v for k, v in row.items() if k != "embedding"}
                item["similarity"] = sim
                scored.append(item)
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]


def query_open_tasks_semantic(
    org_id: str,
    query_embedding: List[float],
    assignee: Optional[str],
    threshold: float,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    if using_live_supabase():
        sb = _get_supabase()
        res = sb.rpc(
            "match_open_tasks",
            {
                "p_org_id": org_id,
                "query_embedding": query_embedding,
                "p_assignee": assignee,
                "match_threshold": threshold,
                "match_count": limit,
            },
        ).execute()
        return res.data or []

    scored: List[Dict[str, Any]] = []
    with _local_store._lock:
        for row in _local_store.tasks:
            if row["org_id"] != org_id:
                continue
            if row.get("status") not in {"DISPATCHED", "OPEN", "BLOCKED"}:
                continue
            effective_assignee = (row.get("rerouted_assignee") or row.get("assignee") or "").lower()
            if assignee and assignee.lower() not in effective_assignee and effective_assignee not in assignee.lower():
                continue
            emb = row.get("embedding")
            if not emb:
                continue
            sim = cosine_similarity(query_embedding, emb)
            if sim >= threshold:
                item = {k: v for k, v in row.items() if k != "embedding"}
                item["similarity"] = sim
                scored.append(item)
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]


def upsert_tasks(org_id: str, meeting_id: str, thread_id: str, tasks: Dict[str, Dict[str, Any]]) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    rows: List[Dict[str, Any]] = []
    for task_id, task in tasks.items():
        title_for_vec = task.get("reframed_title") or task.get("title") or ""
        try:
            task_emb: Optional[List[float]] = get_embedding(
                f"{title_for_vec} {task.get('transcript_quote', '')}"
            )
        except Exception as exc:
            logger.debug("upsert_tasks: optional task embedding skipped (%s)", exc)
            task_emb = None
        rows.append({
            "task_id": task_id,
            "org_id": org_id,
            "meeting_id": meeting_id,
            "thread_id": thread_id,
            "title": task.get("title", ""),
            "reframed_title": task.get("reframed_title"),
            "reframed_description": task.get("reframed_description"),
            "assignee": task.get("assignee", "UNASSIGNED"),
            "rerouted_assignee": task.get("rerouted_assignee"),
            "resource_type": task.get("resource_type", "unknown"),
            "transcript_quote": task.get("transcript_quote", ""),
            "status": task.get("status", "PENDING"),
            "hr_status": task.get("hr_status"),
            "hr_provenance": task.get("hr_provenance"),
            "finance_flag": task.get("finance_flag"),
            "finance_provenance": task.get("finance_provenance"),
            "security_flag": task.get("security_flag"),
            "security_confidence": task.get("security_confidence"),
            "security_provenance": task.get("security_provenance"),
            "capacity_flag": task.get("capacity_flag"),
            "capacity_provenance": task.get("capacity_provenance"),
            "jira_key": task.get("jira_ticket_id") or task.get("jira_key"),
            "jira_url": task.get("jira_url"),
            "slack_dm_sent": bool(task.get("slack_dm_sent", False)),
            "embedding": task_emb,
            "updated_at": now_iso,
        })

    if not rows:
        return

    if using_live_supabase():
        sb = _get_supabase()
        sb.table("tasks").upsert(rows, on_conflict="org_id,meeting_id,task_id").execute()
        return

    with _local_store._lock:
        for r in rows:
            matched = next(
                (
                    existing
                    for existing in _local_store.tasks
                    if existing["org_id"] == org_id
                    and existing["meeting_id"] == meeting_id
                    and existing["task_id"] == r["task_id"]
                ),
                None,
            )
            if matched is not None:
                matched.update(r)
            else:
                r["id"] = str(uuid.uuid4())
                r["created_at"] = now_iso
                _local_store.tasks.append(r)


def save_resolutions(org_id: str, meeting_id: str, thread_id: str, resolutions: List[Dict[str, Any]]) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "org_id": org_id,
            "meeting_id": meeting_id,
            "thread_id": thread_id,
            "task_id": r["task_id"],
            "conflict_type": r["conflict_type"],
            "suggested_action": r["suggested_action"],
            "provenance_tag": r.get("provenance_tag"),
            "new_payload": r.get("new_payload"),
            "created_at": now_iso,
        }
        for r in resolutions
    ]
    if not rows:
        return
    if using_live_supabase():
        sb = _get_supabase()
        sb.table("resolutions").insert(rows).execute()
        return
    with _local_store._lock:
        _local_store.resolutions.extend(rows)


def record_approval(
    org_id: str,
    thread_id: str,
    meeting_id: str,
    decisions: Dict[str, str],
    approver_user_id: str,
) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "org_id": org_id,
            "thread_id": thread_id,
            "meeting_id": meeting_id,
            "task_id": tid,
            "approver_user_id": approver_user_id,
            "decision": dec,
            "created_at": now_iso,
        }
        for tid, dec in decisions.items()
    ]
    if not rows:
        return
    if using_live_supabase():
        sb = _get_supabase()
        sb.table("approvals").insert(rows).execute()
        return
    with _local_store._lock:
        _local_store.approvals.extend(rows)


def write_audit_trail(
    org_id: str,
    meeting_id: str,
    event_type: str,
    provenance_tag: str,
    agent_node: str = "",
    detail: str = "",
    confidence: Optional[float] = None,
    thread_id: Optional[str] = None,
    task_id: Optional[str] = None,
    actor_id: Optional[str] = None,
) -> None:
    row = {
        "org_id": org_id,
        "meeting_id": meeting_id,
        "thread_id": thread_id,
        "task_id": task_id,
        "event_type": event_type,
        "agent_node": agent_node,
        "detail": detail,
        "confidence": confidence,
        "provenance_tag": provenance_tag,
        "actor_id": actor_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if using_live_supabase():
        try:
            sb = _get_supabase()
            sb.table("audit_trail").insert(row).execute()
        except Exception as exc:
            logger.warning("write_audit_trail failed (non-fatal): %s", exc)
        return
    with _local_store._lock:
        row["id"] = str(uuid.uuid4())
        _local_store.audit_trail.append(row)


def list_audit_trail(org_id: str, meeting_id: Optional[str] = None) -> List[Dict[str, Any]]:
    if using_live_supabase():
        sb = _get_supabase()
        q = sb.table("audit_trail").select("*").eq("org_id", org_id)
        if meeting_id:
            q = q.eq("meeting_id", meeting_id)
        res = q.order("created_at", desc=True).limit(100).execute()
        return res.data or []
    with _local_store._lock:
        items = [dict(r) for r in _local_store.audit_trail if r["org_id"] == org_id]
        if meeting_id:
            items = [r for r in items if r["meeting_id"] == meeting_id]
        return list(reversed(items))


def record_webhook_event_once(provider: str, event_id: str, org_id: Optional[str] = None) -> bool:
    """Return True if event_id is new and recorded; False if it was already processed."""
    if not event_id:
        return True
    if using_live_supabase():
        sb = _get_supabase()
        existing = (
            sb.table("webhook_events")
            .select("event_id")
            .eq("provider", provider)
            .eq("event_id", event_id)
            .execute()
        )
        if existing.data:
            return False
        sb.table("webhook_events").insert({
            "provider": provider,
            "event_id": event_id,
            "org_id": org_id,
        }).execute()
        return True
    key = (provider, event_id)
    with _local_store._lock:
        if key in _local_store.webhook_events:
            return False
        _local_store.webhook_events.add(key)
        return True


def upsert_slack_thread(
    org_id: str,
    thread_id: str,
    task_id: str,
    jira_key: Optional[str],
    slack_channel: str,
    slack_thread_ts: str,
    assignee: str,
    turn_count: int = 0,
    status: str = "OPEN",
) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    row = {
        "org_id": org_id,
        "thread_id": thread_id,
        "task_id": task_id,
        "jira_key": jira_key,
        "slack_channel": slack_channel,
        "slack_thread_ts": slack_thread_ts,
        "assignee": assignee,
        "turn_count": turn_count,
        "status": status,
        "updated_at": now_iso,
    }
    if using_live_supabase():
        sb = _get_supabase()
        res = sb.table("slack_threads").upsert(
            row, on_conflict="org_id,slack_channel,slack_thread_ts"
        ).execute()
        return (res.data or [row])[0]
    with _local_store._lock:
        for existing in _local_store.slack_threads:
            if (
                existing["org_id"] == org_id
                and existing["slack_channel"] == slack_channel
                and existing["slack_thread_ts"] == slack_thread_ts
            ):
                existing.update(row)
                return dict(existing)
        row["id"] = str(uuid.uuid4())
        _local_store.slack_threads.append(row)
        return dict(row)


def get_slack_thread(org_id: str, slack_channel: str, slack_thread_ts: str) -> Optional[Dict[str, Any]]:
    if using_live_supabase():
        sb = _get_supabase()
        res = (
            sb.table("slack_threads")
            .select("*")
            .eq("org_id", org_id)
            .eq("slack_channel", slack_channel)
            .eq("slack_thread_ts", slack_thread_ts)
            .execute()
        )
        return res.data[0] if res.data else None
    with _local_store._lock:
        for row in _local_store.slack_threads:
            if (
                row["org_id"] == org_id
                and row["slack_channel"] == slack_channel
                and row["slack_thread_ts"] == slack_thread_ts
            ):
                return dict(row)
        return None


def update_task_status_by_id(org_id: str, task_id: str, status: str, jira_key: Optional[str] = None) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    if using_live_supabase():
        sb = _get_supabase()
        q = sb.table("tasks").update({"status": status, "updated_at": now_iso}).eq("org_id", org_id).eq("task_id", task_id)
        q.execute()
        return
    with _local_store._lock:
        for t in _local_store.tasks:
            if t["org_id"] == org_id and t["task_id"] == task_id:
                t["status"] = status
                t["updated_at"] = now_iso
                if jira_key:
                    t["jira_key"] = jira_key


def save_thread_snapshot(thread_id: str, org_id: str, snapshot: Dict[str, Any]) -> None:
    with _local_store._lock:
        existing = dict(_local_store.thread_states.get(thread_id) or {})
        existing.update(snapshot)
        existing["thread_id"] = thread_id
        existing["org_id"] = org_id
        existing["updated_at"] = datetime.now(timezone.utc).isoformat()
        existing.setdefault("slack_feed", [])
        _local_store.thread_states[thread_id] = existing


def record_slack_feed_message(
    org_id: str,
    thread_id: str,
    role: str,
    sender: str,
    recipient: str,
    text: str,
    slack_channel: str = "",
    slack_ts: str = "",
    task_id: Optional[str] = None,
    jira_key: Optional[str] = None,
    kind: str = "message",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    msg = {
        "id": str(uuid.uuid4()),
        "org_id": org_id,
        "thread_id": thread_id,
        "role": role,
        "sender": sender,
        "recipient": recipient,
        "text": text,
        "slack_channel": slack_channel,
        "slack_ts": slack_ts,
        "task_id": task_id,
        "jira_key": jira_key,
        "kind": kind,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _local_store._lock:
        _local_store.slack_feed.append(msg)
        snap = _local_store.thread_states.setdefault(
            thread_id,
            {"thread_id": thread_id, "org_id": org_id, "phase": "INGESTING", "tasks": {}},
        )
        feed = list(snap.get("slack_feed") or [])
        feed.append(msg)
        snap["slack_feed"] = feed
        snap["updated_at"] = msg["created_at"]
    return msg


def list_slack_feed(org_id: str, thread_id: str) -> List[Dict[str, Any]]:
    with _local_store._lock:
        return [
            dict(m)
            for m in _local_store.slack_feed
            if m.get("org_id") == org_id and m.get("thread_id") == thread_id
        ]


def list_open_slack_threads_all() -> List[Dict[str, Any]]:
    with _local_store._lock:
        return [
            dict(r)
            for r in _local_store.slack_threads
            if r.get("status") not in {"DONE", "CLOSED"}
        ]


def get_thread_snapshot(thread_id: str) -> Optional[Dict[str, Any]]:
    with _local_store._lock:
        snap = _local_store.thread_states.get(thread_id)
        return dict(snap) if snap else None


def list_thread_snapshots(org_id: str) -> List[Dict[str, Any]]:
    with _local_store._lock:
        items = [
            dict(s)
            for s in _local_store.thread_states.values()
            if s.get("org_id") == org_id
        ]
        items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return items


def upsert_hr_records(org_id: str, hr_rows: List[Dict[str, Any]], emp_rows: List[Dict[str, Any]]) -> int:
    if using_live_supabase():
        sb = _get_supabase()
        sb.table("hr_employees").delete().eq("org_id", org_id).execute()
        if hr_rows:
            sb.table("hr_employees").insert(hr_rows).execute()
        for emp in emp_rows:
            try:
                sb.table("employees").upsert(emp, on_conflict="org_id,full_name").execute()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 400:
                    fallback_emp = {
                        k: v for k, v in emp.items() if k not in {"domain_skills", "active_task_count"}
                    }
                    sb.table("employees").upsert(fallback_emp, on_conflict="org_id,full_name").execute()
                else:
                    raise
        return len(hr_rows)
    with _local_store._lock:
        _local_store.hr_employees = [r for r in _local_store.hr_employees if r["org_id"] != org_id] + hr_rows
        for emp in emp_rows:
            existing = next(
                (e for e in _local_store.employees if e["org_id"] == org_id and e["full_name"] == emp["full_name"]),
                None,
            )
            if existing:
                existing.update(emp)
            else:
                _local_store.employees.append(emp)
        return len(hr_rows)


def upsert_finance_budgets(org_id: str, rows: List[Dict[str, Any]]) -> int:
    if using_live_supabase():
        sb = _get_supabase()
        if rows:
            sb.table("finance_budgets").upsert(rows, on_conflict="org_id,category").execute()
        return len(rows)
    with _local_store._lock:
        _local_store.finance_budgets = [
            r for r in _local_store.finance_budgets if r["org_id"] != org_id
        ] + rows
        return len(rows)


def upsert_security_policies(org_id: str, rows: List[Dict[str, Any]]) -> int:
    if using_live_supabase():
        sb = _get_supabase()
        sb.table("security_policies").delete().eq("org_id", org_id).execute()
        if rows:
            sb.table("security_policies").insert(rows).execute()
        return len(rows)
    with _local_store._lock:
        _local_store.security_policies = [
            r for r in _local_store.security_policies if r["org_id"] != org_id
        ] + rows
        return len(rows)
