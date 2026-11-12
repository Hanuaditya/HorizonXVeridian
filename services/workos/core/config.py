"""Centralized configuration for services/workos."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Tuple
from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WorkOSSettings:
    app_env: str
    demo_mode: bool
    frontend_url: str
    workos_port: int
    shared_hmac_secret: str
    max_hmac_skew_seconds: int

    # Clerk
    clerk_jwks_url: str
    clerk_issuer: str
    manager_roles: Tuple[str, ...]

    # Database / Supabase
    supabase_url: str
    supabase_service_role_key: str
    database_url: str

    # Models (never hardcoded in graph nodes)
    evon_model_name: str
    evon_api_base: str
    evon_api_key: str
    gemini_api_key: str
    llm_extraction_model: str
    nvidia_api_key: str
    nvidia_base_url: str
    llm_reasoning_model: str
    embedding_model: str
    embedding_dim: int

    # Compliance thresholds & capacity
    security_threshold: float
    finance_threshold: float
    commit_match_threshold: float
    commit_match_margin: float
    capacity_limit: int
    capacity_new_hire_limit: int

    # External integrations (strict webhook secrets)
    jira_base_url: str
    jira_email: str
    jira_api_token: str
    jira_project_key: str
    slack_bot_token: str
    slack_signing_secret: str
    slack_manager_channel: str
    slack_summary_channel: str
    github_webhook_secret: str

    # Paths
    finance_csv_path: str
    hr_json_path: str
    security_policy_path: str


def get_settings() -> WorkOSSettings:
    """Build fresh settings snapshot from environment variables."""
    app_env = os.getenv("APP_ENV", "development").strip()
    demo_mode = _as_bool(os.getenv("DEMO_MODE"), default=True)
    hmac_secret = os.getenv("SHARED_HMAC_SECRET", "").strip()
    if not hmac_secret and demo_mode and app_env == "development":
        hmac_secret = "horizon_veridian_demo_hmac_secret_min_32_bytes_2026"

    service_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_KEY")
        or ""
    ).strip()

    evon_key = os.getenv("EVON_API_KEY", "").strip()

    roles_raw = os.getenv("CLERK_MANAGER_ROLES", "org:admin,admin,manager")
    manager_roles = tuple(r.strip() for r in roles_raw.split(",") if r.strip())

    return WorkOSSettings(
        app_env=app_env,
        demo_mode=demo_mode,
        frontend_url=os.getenv("FRONTEND_URL", "http://localhost:3000").strip(),
        workos_port=int(os.getenv("WORKOS_PORT", "8000")),
        shared_hmac_secret=hmac_secret,
        max_hmac_skew_seconds=int(os.getenv("MAX_HMAC_SKEW_SECONDS", "300")),
        clerk_jwks_url=os.getenv("CLERK_JWKS_URL", "").strip(),
        clerk_issuer=os.getenv("CLERK_ISSUER", "").strip(),
        manager_roles=manager_roles,
        supabase_url=os.getenv("SUPABASE_URL", "").strip(),
        supabase_service_role_key=service_key,
        database_url=os.getenv("DATABASE_URL", "").strip(),
        evon_model_name=os.getenv("EVON_MODEL_NAME", "gnani-ai/evon-30b").strip(),
        evon_api_base=os.getenv(
            "EVON_API_BASE",
            "https://api-inference.huggingface.co/models/gnani-ai/evon-30b/v1",
        ).strip(),
        evon_api_key=evon_key,
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        llm_extraction_model=os.getenv("LLM_EXTRACTION_MODEL", "gemini-2.0-flash").strip(),
        nvidia_api_key=os.getenv("NVIDIA_API_KEY", "").strip(),
        nvidia_base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").strip(),
        llm_reasoning_model=os.getenv("LLM_REASONING_MODEL", "meta/llama-3.1-70b-instruct").strip(),
        embedding_model=os.getenv("EMBEDDING_MODEL", "nvidia/nv-embedqa-e5-v5").strip(),
        embedding_dim=int(os.getenv("EMBEDDING_DIM", "1024")),
        security_threshold=float(os.getenv("SECURITY_THRESHOLD", "0.50")),
        finance_threshold=float(os.getenv("FINANCE_THRESHOLD", "0.50")),
        commit_match_threshold=float(os.getenv("COMMIT_MATCH_THRESHOLD", "0.75")),
        commit_match_margin=float(os.getenv("COMMIT_MATCH_MARGIN", "0.15")),
        capacity_limit=int(os.getenv("CAPACITY_LIMIT", "10")),
        capacity_new_hire_limit=int(os.getenv("CAPACITY_NEW_HIRE_LIMIT", "2")),
        jira_base_url=os.getenv("JIRA_BASE_URL", "").strip(),
        jira_email=os.getenv("JIRA_EMAIL", "").strip(),
        jira_api_token=os.getenv("JIRA_API_TOKEN", "").strip(),
        jira_project_key=os.getenv("JIRA_PROJECT_KEY", "VER").strip(),
        slack_bot_token=os.getenv("SLACK_BOT_TOKEN", "").strip(),
        slack_signing_secret=os.getenv("SLACK_SIGNING_SECRET", "").strip(),
        slack_manager_channel=os.getenv("SLACK_MANAGER_CHANNEL", "#product-team").strip(),
        slack_summary_channel=os.getenv("SLACK_SUMMARY_CHANNEL", "#product-team").strip(),
        github_webhook_secret=os.getenv("GITHUB_WEBHOOK_SECRET", "").strip(),
        finance_csv_path=os.getenv("FINANCE_CSV_PATH", "db/seed/finance_budgets.csv").strip(),
        hr_json_path=os.getenv("HR_JSON_PATH", "db/seed/hr_employees.json").strip(),
        security_policy_path=os.getenv("SECURITY_POLICY_PATH", "db/seed/security_policy.md").strip(),
    )
