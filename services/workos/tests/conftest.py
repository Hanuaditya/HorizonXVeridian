"""Ensure WorkOS root is on sys.path for isolated test execution."""

import os
import sys
from pathlib import Path

WORKOS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]

for p in (str(REPO_ROOT), str(WORKOS_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Isolate unit tests from real external accounts present in local .env
for _k, _v in {
    "APP_ENV": "development",
    "DEMO_MODE": "true",
    "SUPABASE_URL": "",
    "SUPABASE_SERVICE_ROLE_KEY": "",
    "DATABASE_URL": "",
    "NVIDIA_API_KEY": "",
    "EVON_API_KEY": "",
    "HF_TOKEN": "",
    "GEMINI_API_KEY": "",
    "JIRA_API_TOKEN": "",
    "SLACK_BOT_TOKEN": "",
    "SLACK_SIGNING_SECRET": "",
    "GITHUB_WEBHOOK_SECRET": "",
    "CLERK_JWKS_URL": "",
}.items():
    os.environ[_k] = _v

