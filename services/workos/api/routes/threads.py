"""Org-scoped SSE stream, state fallback, audit trail, and admin mapping routes."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.auth import AuthContext, require_auth, require_manager
from api.sse import sse_manager
from connectors.sync_finance import sync_finance_data
from connectors.sync_hr import sync_hr_data
from connectors.sync_security import sync_security_data
from core.config import get_settings
from core.store import (
    get_thread_snapshot,
    list_audit_trail,
    list_employees,
    list_thread_snapshots,
    upsert_employee_mapping,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class EmployeeMappingUpdate(BaseModel):
    full_name: str
    clerk_user_id: Optional[str] = None
    slack_id: Optional[str] = None
    jira_account_id: Optional[str] = None
    email: Optional[str] = None


def _verify_thread_org_access(thread_id: str, auth_org_id: str) -> Optional[Dict[str, Any]]:
    snap = get_thread_snapshot(thread_id)
    thread_org = (snap or {}).get("org_id") or sse_manager.get_thread_org(thread_id)
    if thread_org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thread '{thread_id}' not found.",
        )
    if thread_org != auth_org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Thread does not belong to the authenticated organization.",
        )
    return snap


@router.get("/stream/{thread_id}")
async def stream_graph_events(
    thread_id: str,
    last_event_id_header: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    last_event_id_query: Optional[int] = Query(default=None, alias="lastEventId"),
    auth: AuthContext = Depends(require_auth),
) -> StreamingResponse:
    """Authenticated, org-scoped SSE stream supporting Last-Event-ID replay & 15s heartbeats."""
    _verify_thread_org_access(thread_id, auth.org_id)

    since_id: Optional[int] = last_event_id_query
    if since_id is None and last_event_id_header:
        try:
            since_id = int(last_event_id_header)
        except ValueError:
            since_id = None

    return StreamingResponse(
        sse_manager.stream_events(thread_id, last_event_id=since_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/threads/{thread_id}/state")
async def get_thread_state(
    thread_id: str,
    auth: AuthContext = Depends(require_auth),
) -> Dict[str, Any]:
    """REST state recovery fallback so page refreshes never lose pipeline progress."""
    snap = _verify_thread_org_access(thread_id, auth.org_id)
    if snap is None:
        return {"thread_id": thread_id, "org_id": auth.org_id, "phase": "IDLE", "tasks": {}}
    return snap


@router.get("/threads")
async def list_org_threads(
    auth: AuthContext = Depends(require_auth),
) -> Dict[str, Any]:
    """List recent Graph A threads belonging strictly to auth.org_id."""
    return {"org_id": auth.org_id, "threads": list_thread_snapshots(auth.org_id)}


@router.get("/audit-trail")
async def get_org_audit_trail(
    meeting_id: Optional[str] = Query(default=None),
    auth: AuthContext = Depends(require_auth),
) -> Dict[str, Any]:
    """Return org-scoped append-only audit trail records."""
    return {"org_id": auth.org_id, "entries": list_audit_trail(auth.org_id, meeting_id=meeting_id)}


@router.get("/admin/employees")
async def admin_list_employees(
    auth: AuthContext = Depends(require_auth),
) -> Dict[str, Any]:
    """List Clerk <-> Slack <-> Jira employee identity mappings & current compliance config."""
    settings = get_settings()
    return {
        "org_id": auth.org_id,
        "employees": list_employees(auth.org_id),
        "config": {
            "evon_model_name": settings.evon_model_name,
            "llm_extraction_model": settings.llm_extraction_model,
            "llm_reasoning_model": settings.llm_reasoning_model,
            "embedding_model": settings.embedding_model,
            "embedding_dim": settings.embedding_dim,
            "security_threshold": settings.security_threshold,
            "finance_threshold": settings.finance_threshold,
            "capacity_limit": settings.capacity_limit,
            "capacity_new_hire_limit": settings.capacity_new_hire_limit,
            "demo_mode": settings.demo_mode,
        },
    }


@router.post("/admin/employees")
async def admin_upsert_employee(
    body: EmployeeMappingUpdate,
    auth: AuthContext = Depends(require_manager),
) -> Dict[str, Any]:
    """Manager-only endpoint to map Clerk user <-> Slack ID <-> Jira account."""
    row = upsert_employee_mapping(
        org_id=auth.org_id,
        full_name=body.full_name,
        clerk_user_id=body.clerk_user_id,
        slack_id=body.slack_id,
        jira_account_id=body.jira_account_id,
        email=body.email,
    )
    return {"status": "updated", "employee": row}


@router.post("/admin/sync")
async def admin_trigger_connector_sync(
    auth: AuthContext = Depends(require_manager),
) -> Dict[str, Any]:
    """Manager-only connector re-sync (HR, Finance CSV, Security Policies) for auth.org_id."""
    hr_count = sync_hr_data(org_id=auth.org_id)
    fin_rows = sync_finance_data(org_id=auth.org_id)
    sec_rows = sync_security_data(org_id=auth.org_id)
    return {
        "org_id": auth.org_id,
        "hr_employees": hr_count,
        "finance_budgets": len(fin_rows),
        "security_policies": len(sec_rows),
    }

