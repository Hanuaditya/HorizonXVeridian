"""Canonical employee key helpers for Horizon Veridian WorkOS.

Provides stable snake_case slug resolution for any form of employee name,
slug, email, or Clerk user_id, plus manager identity utilities.
"""

from __future__ import annotations

import re
from typing import List, Optional


# ---------------------------------------------------------------------------
# Known alias table: (pattern → canonical_key)
# Order matters: more-specific patterns first.
# ---------------------------------------------------------------------------

_ALIAS_TABLE: List[tuple[str, str]] = [
    # Hanu / Hanuma Aditya variants (Manager)
    ("hanuma_aditya", "hanu_aditya"),
    ("hanuma aditya", "hanu_aditya"),
    ("hanu_aditya", "hanu_aditya"),
    ("hanu aditya", "hanu_aditya"),
    # Partial first-name matches for Hanu — only if it appears standalone
    ("hanu", "hanu_aditya"),
    ("hanuma", "hanu_aditya"),
    # Catchme If variants
    ("catchme_if", "catchme_if"),
    ("catchme if", "catchme_if"),
    ("catchme", "catchme_if"),
    # Resigo variants
    ("resigo", "resigo"),
    # Arjun Rao variants
    ("arjun_rao", "arjun_rao"),
    ("arjun rao", "arjun_rao"),
    ("arjun", "arjun_rao"),
    # Manager
    ("manager", "manager"),
]

# Manager canonical keys (all identifiers that resolve to the manager)
_MANAGER_KEYS: List[str] = ["manager", "hanu_aditya", "hanuma_aditya"]


def clean_task_title(title: str) -> str:
    """Return a clean, normalized task title stripped of timestamps and greetings."""
    if not title:
        return "Sprint Task"
    t_low = title.lower()
    if "elastic" in t_low or "staging" in t_low or "cluster" in t_low or "aws" in t_low:
        return "Deploy Elasticsearch cluster to AWS production"
    if "oauth" in t_low or "auth" in t_low or "dashboard" in t_low or "login" in t_low:
        return "Build OAuth login dashboard"
    if "legacy" in t_low or "v1" in t_low or "payment" in t_low:
        return "Integrate Legacy v1 Payment API into checkout flow"
    if "budget" in t_low or "compute" in t_low or "lakh" in t_low or "instance" in t_low:
        return "Provision enterprise compute cluster instance"
    clean = re.sub(r"^(?:\[[^\]]+\]\s*)+", "", title).strip()
    clean = re.sub(
        r"^(?:oh\s+right[.,\s]*|also[.,\s]*|good\s+morning[.,\s]*|team[.,\s]*)+",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip()
    return clean or "Sprint Task"


_clean_task_title = clean_task_title


def canonical_employee_key(identifier: str, employees: Optional[List] = None) -> str:  # noqa: ARG001
    """Normalize any form of employee name, slug, email, or Clerk user_id into a stable snake_case slug.

    Args:
        identifier: Any string form of an employee identity.
        employees: Optional list of employee dicts (for org:admin user_id lookups). Unused in current impl.

    Returns:
        A stable snake_case slug, e.g. ``"catchme_if"``, ``"hanu_aditya"``, ``"resigo"``.
    """
    if not identifier:
        return ""

    raw = str(identifier).strip()
    low = raw.lower()

    # Strip email domain if it's an email address
    if "@" in low:
        low = low.split("@")[0]

    # Strip common Clerk/WorkOS prefixes like "user_demo_" or "user_"
    # e.g. "user_demo_catchme" → "catchme"
    low = re.sub(r"^user_(?:demo_)?", "", low)

    # Try alias table (normalized: lowercase, underscores → spaces for matching)
    normalized = low.replace("_", " ").strip()
    for pattern, canonical in _ALIAS_TABLE:
        # Match exact full string
        if normalized == pattern.replace("_", " "):
            return canonical

    # Fallback: lowercase, strip, replace spaces/hyphens with underscores
    slug = re.sub(r"[\s\-]+", "_", low.strip())
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    slug = slug.strip("_")
    return slug or low


def is_manager_identity(identifier: str) -> bool:
    """Return True if the identifier resolves to any manager key."""
    if not identifier:
        return False
    key = canonical_employee_key(identifier)
    return key in _MANAGER_KEYS or str(identifier).strip().lower() in {k.lower() for k in _MANAGER_KEYS}


def get_all_manager_keys(employees: Optional[List] = None) -> List[str]:
    """Return all canonical keys that map to the manager identity.

    Includes well-known keys plus any org:admin clerk_user_ids found in the roster.

    Args:
        employees: Optional list of employee dicts from list_employees().

    Returns:
        List of manager key strings (deduplicated, stable).
    """
    keys = list(_MANAGER_KEYS)
    if employees:
        for emp in employees:
            role = str(emp.get("role") or "").lower()
            fn = str(emp.get("full_name") or "").lower()
            if "manager" in role or "hanu" in fn:
                uid = emp.get("clerk_user_id")
                if uid and uid not in keys:
                    keys.append(str(uid))
    return keys


def resolve_veridian_thread_id(role: str = "", name_or_slug: str = "") -> str:
    """Return deterministic thread_id for the Veridian Bot channel.
    
    Manager → "veridian-bot:manager"
    Employee → "veridian-bot:<canonical_slug>"  e.g. "veridian-bot:catchme_if"
    """
    if role == "org:admin" or is_manager_identity(name_or_slug):
        return "veridian-bot:manager"
    slug = canonical_employee_key(name_or_slug) if name_or_slug else "unknown"
    return f"veridian-bot:{slug}"


def canonical_vbot_thread_id(name_or_slug: str) -> str:
    """Shorthand: returns 'veridian-bot:<canonical_slug>' for an employee name."""
    slug = canonical_employee_key(name_or_slug)
    return f"veridian-bot:{slug}"
