"""Standalone diagnostic utility to validate .env credentials safely.

Never prints raw secrets; tests connectivity to Gnani Vachana, Supabase, Clerk,
Jira, Slack, Cloudinary, Gemini, HuggingFace/Evon, and reports what falls back
to DEMO_MODE.

Usage:
    python scripts/verify_keys.py
    python scripts/verify_keys.py --strict   # non-zero exit if any live check fails
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, List, Tuple

import httpx
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env", override=True)


def _is_set(key: str) -> bool:
    val = os.getenv(key, "").strip()
    return bool(val and "placeholder" not in val.lower() and "your_" not in val.lower())


def check_gnani_vachana() -> Tuple[str, str]:
    api_key = os.getenv("GNANI_API_KEY", "").strip()
    base_url = os.getenv("GNANI_BASE_URL", "https://api.vachana.ai").strip().rstrip("/")
    tts_url = os.getenv("GNANI_TTS_ENDPOINT", f"{base_url}/api/v1/tts/inference").strip()
    timbre_model = os.getenv("GNANI_TIMBRE_MODEL", "timbre-v2.5").strip()

    if not _is_set("GNANI_API_KEY"):
        return "FALLBACK", "GNANI_API_KEY missing -> DEMO_MODE Hinglish fixture active"

    headers = {"X-API-Key-ID": api_key, "Content-Type": "application/json"}
    try:
        # Lightweight probe against Vachana TTS inference endpoint
        resp = httpx.post(
            tts_url,
            headers=headers,
            json={"model": timbre_model, "text": "Namaste", "language": "en"},
            timeout=12.0,
        )
        if resp.status_code in (200, 201):
            return "PASS", f"Gnani Vachana responded HTTP {resp.status_code} ({tts_url})"
        if resp.status_code in (401, 403):
            return "FAIL", f"Gnani Vachana rejected API key (HTTP {resp.status_code})"
        if resp.status_code in (400, 422):
            return "PASS", f"Gnani Vachana auth accepted, endpoint live (HTTP {resp.status_code})"
        return "WARN", f"Gnani Vachana returned HTTP {resp.status_code}"
    except Exception as exc:
        return "FAIL", f"Gnani Vachana unreachable: {exc}"


def check_evon_and_llms() -> Tuple[str, str]:
    has_evon = _is_set("EVON_API_KEY")
    has_nvidia = _is_set("NVIDIA_API_KEY")
    has_gemini = _is_set("GEMINI_API_KEY")

    notes: List[str] = []
    if has_gemini:
        key = os.getenv("GEMINI_API_KEY", "").strip()
        try:
            r = httpx.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                timeout=8.0,
            )
            notes.append(f"Gemini HTTP {r.status_code}")
        except Exception as exc:
            notes.append(f"Gemini error: {exc}")
    else:
        notes.append("Gemini unset")

    if has_evon:
        notes.append("Evon key SET")
    elif has_gemini and "HTTP 200" in " ".join(notes):
        notes.append("EVON_API_KEY unset (using Gemini live routing)")
    else:
        notes.append("EVON_API_KEY unset (DEMO fallback)")

    if has_nvidia:
        notes.append("NVIDIA key SET")
    else:
        notes.append("NVIDIA_API_KEY unset (offline 1024-dim semantic embedder active)")

    if has_evon or has_nvidia or (has_gemini and "HTTP 200" in " ".join(notes)):
        return "PASS", " | ".join(notes)
    return "FALLBACK", " | ".join(notes)


def check_supabase() -> Tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    srv_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    anon_key = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "").strip()
    if not (url and srv_key and anon_key) or "your-project" in url:
        return "FALLBACK", "Supabase URL/keys missing -> local SQLite + in-memory seeded store"

    try:
        r = httpx.get(
            f"{url}/rest/v1/hr_employees?select=id&limit=1",
            headers={"apikey": srv_key, "Authorization": f"Bearer {srv_key}"},
            timeout=10.0,
        )
        if r.status_code == 200:
            return "PASS", f"Supabase connected & migrations applied (hr_employees HTTP 200)"
        if r.status_code == 404 or "relation" in r.text.lower() or "PGRST" in r.text:
            return "WARN", f"Supabase reachable (HTTP {r.status_code}), apply db/migrations/*.sql in SQL Editor"
        if r.status_code in (401, 403):
            return "FAIL", f"Supabase rejected service key (HTTP {r.status_code})"
        return "WARN", f"Supabase REST returned HTTP {r.status_code}"
    except Exception as exc:
        return "FAIL", f"Supabase connection failed: {exc}"


def check_clerk() -> Tuple[str, str]:
    pub = os.getenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "").strip()
    sec = os.getenv("CLERK_SECRET_KEY", "").strip()
    jwks = os.getenv("CLERK_JWKS_URL", "").strip()
    if not (pub and sec and jwks) or pub.startswith("pk_test_ZXhh"):
        return "FALLBACK", "Clerk keys unset -> Demo Manager AuthBridge active"

    details: List[str] = []
    status = "PASS"
    try:
        j_resp = httpx.get(jwks, timeout=8.0)
        if j_resp.status_code == 200 and j_resp.json().get("keys"):
            details.append(f"JWKS valid ({len(j_resp.json()['keys'])} key)")
        else:
            status = "FAIL"
            details.append(f"JWKS HTTP {j_resp.status_code}")

        o_resp = httpx.get(
            "https://api.clerk.com/v1/organizations?limit=1",
            headers={"Authorization": f"Bearer {sec}"},
            timeout=8.0,
        )
        if o_resp.status_code == 200:
            count = len(o_resp.json().get("data", [])) if isinstance(o_resp.json(), dict) else len(o_resp.json())
            details.append(f"Orgs API OK ({count} org)")
        else:
            status = "WARN" if status == "PASS" else status
            details.append(f"Clerk Orgs HTTP {o_resp.status_code} (check Organizations enabled)")
    except Exception as exc:
        return "FAIL", f"Clerk probe failed: {exc}"

    return status, " | ".join(details)


def check_jira() -> Tuple[str, str]:
    base = os.getenv("JIRA_BASE_URL", "").strip().rstrip("/")
    email = os.getenv("JIRA_EMAIL", "").strip()
    tok = os.getenv("JIRA_API_TOKEN", "").strip()
    proj = os.getenv("JIRA_PROJECT_KEY", "").strip()
    if not all([base, email, tok]) or "yourcompany" in base:
        return "FALLBACK", "Jira credentials unset -> mock tickets in DEMO_MODE"

    try:
        r = httpx.get(f"{base}/rest/api/3/myself", auth=(email, tok), timeout=10.0)
        if r.status_code == 200:
            p = httpx.get(f"{base}/rest/api/3/project/{proj}", auth=(email, tok), timeout=10.0)
            proj_msg = f"project '{proj}' OK" if p.status_code == 200 else f"project '{proj}' HTTP {p.status_code}"
            return "PASS", f"Jira auth OK ({proj_msg})"
        return "FAIL", f"Jira rejected credentials (HTTP {r.status_code})"
    except Exception as exc:
        return "FAIL", f"Jira connection failed: {exc}"


def check_slack() -> Tuple[str, str]:
    tok = os.getenv("SLACK_BOT_TOKEN", "").strip()
    sec = os.getenv("SLACK_SIGNING_SECRET", "").strip()
    if not tok or "placeholder" in tok.lower():
        return "FALLBACK", "Slack token unset -> mock Slack notifications in DEMO_MODE"

    try:
        r = httpx.post(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {tok}"},
            timeout=10.0,
        )
        data = r.json()
        if r.status_code == 200 and data.get("ok"):
            sec_status = "signing secret SET" if sec else "SLACK_SIGNING_SECRET missing!"
            return ("PASS" if sec else "WARN"), f"Slack workspace '{data.get('team')}' connected ({sec_status})"
        return "FAIL", f"Slack auth.test failed: {data.get('error', r.status_code)}"
    except Exception as exc:
        return "FAIL", f"Slack connection failed: {exc}"


def check_cloudinary_and_stream() -> Tuple[str, str]:
    cloud = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
    c_key = os.getenv("CLOUDINARY_API_KEY", "").strip()
    c_sec = os.getenv("CLOUDINARY_API_SECRET", "").strip()
    s_key = os.getenv("STREAM_API_KEY", "").strip()
    s_sec = os.getenv("STREAM_API_SECRET", "").strip()

    parts: List[str] = []
    status = "PASS"
    if cloud and c_key and c_sec:
        try:
            r = httpx.get(
                f"https://api.cloudinary.com/v1_1/{cloud}/ping",
                auth=(c_key, c_sec),
                timeout=8.0,
            )
            parts.append(f"Cloudinary HTTP {r.status_code}")
            if r.status_code >= 400:
                status = "WARN"
        except Exception as exc:
            parts.append(f"Cloudinary error: {exc}")
            status = "WARN"
    else:
        parts.append("Cloudinary unset")
        status = "FALLBACK"

    if s_key and s_sec and "placeholder" not in s_key.lower():
        parts.append("Stream keys SET")
    else:
        parts.append("Stream unset (DEMO fallback)")
        if status == "PASS":
            status = "FALLBACK"

    return status, " | ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Horizon Veridian .env keys cleanly.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on any FAIL.")
    args = parser.parse_args()

    demo_mode = os.getenv("DEMO_MODE", "true").strip()
    print(f"\nHorizon Veridian Key Diagnostics (DEMO_MODE={demo_mode})\n" + "=" * 68)

    checks: List[Tuple[str, Callable[[], Tuple[str, str]]]] = [
        ("Gnani Vachana (STT/TTS)", check_gnani_vachana),
        ("LLMs (Evon / NIM / Gemini)", check_evon_and_llms),
        ("Supabase + pgvector", check_supabase),
        ("Clerk Auth + Orgs", check_clerk),
        ("Jira Cloud API", check_jira),
        ("Slack Bot + Signing", check_slack),
        ("Cloudinary + Stream.io", check_cloudinary_and_stream),
    ]

    badges = {
        "PASS": "[PASS]",
        "FALLBACK": "[FALLBACK]",
        "WARN": "[WARN]",
        "FAIL": "[FAIL]",
    }

    failures = 0
    for name, fn in checks:
        st, detail = fn()
        if st == "FAIL":
            failures += 1
        print(f"{badges.get(st, st):10s} {name:26s} -> {detail}")

    print("=" * 68)
    print("Note: Raw secret values are never printed. Fallback items use local DEMO_MODE mocks.\n")
    if args.strict and failures > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

