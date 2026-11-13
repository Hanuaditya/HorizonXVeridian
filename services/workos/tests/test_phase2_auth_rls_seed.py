"""Phase 2 / Sprint 1 tests: Clerk JWKS Auth, Tenant Isolation (RLS), Seed & Vector Dim."""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.auth import (
    AuthContext,
    clear_jwks_cache,
    require_auth,
    require_manager,
)
from core.embeddings import get_embedding
from core.store import (
    assert_embedding_dimension_match,
    get_local_store,
    list_audit_trail,
    list_employees,
    lookup_hr_employee,
    query_finance_budgets_semantic,
    query_security_policies_semantic,
    write_audit_trail,
)
from db.seed.seed_cli import run_seed


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture()
def rsa_jwks_mock(monkeypatch):
    private_key, public_key = _make_rsa_keypair()
    clear_jwks_cache()
    monkeypatch.setenv("CLERK_JWKS_URL", "https://example.clerk.accounts.dev/.well-known/jwks.json")
    monkeypatch.setenv("CLERK_ISSUER", "https://example.clerk.accounts.dev")
    monkeypatch.setattr(
        "api.auth.get_jwk_client",
        lambda _url: SimpleNamespace(
            get_signing_key_from_jwt=lambda _tok: SimpleNamespace(key=public_key)
        ),
    )
    return private_key


def _build_auth_test_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    async def protected(auth: AuthContext = Depends(require_auth)):
        return {"user_id": auth.user_id, "org_id": auth.org_id, "role": auth.role}

    @app.post("/manager-only")
    async def manager_only(
        target_org: str,
        auth: AuthContext = Depends(require_manager),
    ):
        if auth.org_id != target_org:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Cross-org access forbidden")
        return {"approved_by": auth.user_id, "org_id": auth.org_id}

    return app


def test_clerk_auth_valid_manager_and_v2_org_claim(rsa_jwks_mock):
    app = _build_auth_test_app()
    client = TestClient(app)
    now = int(time.time())

    # Standard claim format
    token_v1 = jwt.encode(
        {
            "sub": "user_mgr_1",
            "org_id": "org_alpha",
            "org_role": "org:admin",
            "iss": "https://example.clerk.accounts.dev",
            "iat": now,
            "exp": now + 300,
        },
        rsa_jwks_mock,
        algorithm="RS256",
    )
    res = client.get("/protected", headers={"Authorization": f"Bearer {token_v1}"})
    assert res.status_code == 200
    assert res.json() == {"user_id": "user_mgr_1", "org_id": "org_alpha", "role": "org:admin"}

    # Clerk v2 `o` object claim format
    token_v2 = jwt.encode(
        {
            "sub": "user_mgr_2",
            "o": {"id": "org_alpha", "rol": "org:admin"},
            "iss": "https://example.clerk.accounts.dev",
            "iat": now,
            "exp": now + 300,
        },
        rsa_jwks_mock,
        algorithm="RS256",
    )
    res2 = client.post(
        "/manager-only?target_org=org_alpha",
        headers={"Authorization": f"Bearer {token_v2}"},
    )
    assert res2.status_code == 200
    assert res2.json()["approved_by"] == "user_mgr_2"


def test_clerk_auth_expired_token_rejected(rsa_jwks_mock):
    app = _build_auth_test_app()
    client = TestClient(app)
    past = int(time.time()) - 600
    expired_tok = jwt.encode(
        {
            "sub": "user_1",
            "org_id": "org_alpha",
            "org_role": "org:admin",
            "iss": "https://example.clerk.accounts.dev",
            "exp": past,
        },
        rsa_jwks_mock,
        algorithm="RS256",
    )
    res = client.get("/protected", headers={"Authorization": f"Bearer {expired_tok}"})
    assert res.status_code == 401


def test_clerk_auth_wrong_org_rejected(rsa_jwks_mock):
    app = _build_auth_test_app()
    client = TestClient(app)
    now = int(time.time())
    tok_org_b = jwt.encode(
        {
            "sub": "user_b",
            "org_id": "org_beta",
            "org_role": "org:admin",
            "iss": "https://example.clerk.accounts.dev",
            "exp": now + 300,
        },
        rsa_jwks_mock,
        algorithm="RS256",
    )
    res = client.post(
        "/manager-only?target_org=org_alpha",
        headers={"Authorization": f"Bearer {tok_org_b}"},
    )
    assert res.status_code == 403


def test_clerk_auth_non_manager_rejected(rsa_jwks_mock):
    app = _build_auth_test_app()
    client = TestClient(app)
    now = int(time.time())
    member_tok = jwt.encode(
        {
            "sub": "user_member",
            "org_id": "org_alpha",
            "org_role": "org:member",
            "iss": "https://example.clerk.accounts.dev",
            "exp": now + 300,
        },
        rsa_jwks_mock,
        algorithm="RS256",
    )
    res = client.post(
        "/manager-only?target_org=org_alpha",
        headers={"Authorization": f"Bearer {member_tok}"},
    )
    assert res.status_code == 403


def test_clerk_auth_missing_header_rejected(rsa_jwks_mock):
    app = _build_auth_test_app()
    client = TestClient(app)
    res = client.get("/protected")
    assert res.status_code == 401


def test_migrations_enable_rls_and_hnsw_on_all_tenant_tables():
    m001 = (_REPO_ROOT / "db/migrations/001_enable_pgvector_and_auth_helpers.sql").read_text(encoding="utf-8")
    m002 = (_REPO_ROOT / "db/migrations/002_core_tenancy_and_horizon_media.sql").read_text(encoding="utf-8")
    m003 = (_REPO_ROOT / "db/migrations/003_workos_firewall_and_pgvector.sql").read_text(encoding="utf-8")

    assert "CREATE EXTENSION IF NOT EXISTS vector;" in m001
    assert "current_org_id()" in m001
    assert "trg_sync_recordings_to_unified" in m002
    assert "USING hnsw" in m003

    combined_rls = m002 + "\n" + m003
    tenant_tables = [
        "members",
        "meetings",
        "transcripts",
        "dubbing_jobs",
        "recordings",
        "employees",
        "hr_employees",
        "finance_budgets",
        "security_policies",
        "processed_meetings",
        "tasks",
        "resolutions",
        "approvals",
        "audit_trail",
        "slack_threads",
    ]
    for tbl in tenant_tables:
        assert f"ENABLE ROW LEVEL SECURITY" in combined_rls
        assert f"public.{tbl}" in combined_rls
        assert f"{tbl}_tenant_" in combined_rls


def test_org_a_cannot_read_org_b_and_seed_loads():
    store = get_local_store()
    store.reset(seed_default_org=False)

    res_a = run_seed(org_id="org_alpha")
    assert res_a["hr_employees"] == 6
    assert res_a["finance_budgets"] == 4
    assert res_a["security_policies"] == 4

    # Write org_beta secret policy/audit that org_alpha must never see
    write_audit_trail(
        org_id="org_beta",
        meeting_id="m_secret_beta",
        event_type="SECRET_EVENT",
        provenance_tag="beta-only",
        detail="Top secret beta data",
    )

    assert len(list_employees("org_alpha")) == 6
    assert len(list_employees("org_beta")) == 0
    arjun_emp = lookup_hr_employee("org_alpha", "Arjun")
    assert arjun_emp is not None and arjun_emp["status"] == "ON_PATERNITY_LEAVE"
    assert lookup_hr_employee("org_beta", "Arjun") is None

    assert len(list_audit_trail("org_alpha")) == 0
    assert len(list_audit_trail("org_beta")) == 1

    # Vector search checks scoped strictly by org_id
    q_sec = get_embedding("Deploy Elastic search cluster directly to AWS production")
    hits_a = query_security_policies_semantic("org_alpha", q_sec, threshold=0.50, limit=3)
    hits_b = query_security_policies_semantic("org_beta", q_sec, threshold=0.50, limit=3)
    assert hits_a and hits_a[0]["policy_id"] == "SEC-POL-089"
    assert hits_b == []

    q_fin = get_embedding("enterprise compute cluster provisioning AWS cost budget")
    fin_a = query_finance_budgets_semantic("org_alpha", q_fin, threshold=0.50, limit=2)
    fin_b = query_finance_budgets_semantic("org_beta", q_fin, threshold=0.50, limit=2)
    assert fin_a and fin_a[0]["category"] == "compute_infra"
    assert float(fin_a[0]["budget_remaining"]) == 0.0
    assert fin_b == []


def test_startup_embedding_dimension_assertion(monkeypatch):
    store = get_local_store()
    store.reset(seed_default_org=True)
    assert assert_embedding_dimension_match() == 1024

    monkeypatch.setenv("EMBEDDING_DIM", "384")
    with pytest.raises(RuntimeError, match="dimension mismatch"):
        assert_embedding_dimension_match()
