"""Org-aware Finance Budget CSV connector (replaces legacy Google Sheets dependency)."""

from __future__ import annotations

import csv
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from core.config import get_settings
from core.embeddings import get_embedding
from core.store import upsert_finance_budgets

logger = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _parse_amount(raw: str) -> float:
    cleaned = str(raw or "0").replace("$", "").replace("₹", "").replace(",", "").strip()
    return float(cleaned or 0.0)


def sync_finance_data(org_id: str, csv_path: Optional[str] = None) -> List[Dict]:
    """Load budget rows from CSV, embed descriptions, and upsert scoped by org_id."""
    settings = get_settings()
    path = Path(csv_path) if csv_path else (_REPO_ROOT / settings.finance_csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Finance CSV file not found: {path}")

    now_iso = datetime.now(timezone.utc).isoformat()
    clean_records: List[Dict] = []

    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            raw_category = str(row.get("Category", "")).strip()
            if not raw_category:
                continue
            notes = str(row.get("Notes", "")).strip()
            category_key = raw_category.split()[0].lower()
            budget_remaining = _parse_amount(row.get("Budget Remaining", "0"))
            currency = str(row.get("Currency", "INR")).strip()
            owner = str(row.get("Owner", "Finance")).strip()

            embed_input = f"{raw_category} {notes}".strip()
            vector = get_embedding(embed_input, dim=settings.embedding_dim)

            clean_records.append({
                "id": str(uuid.uuid4()),
                "org_id": org_id,
                "category": category_key,
                "budget_remaining": budget_remaining,
                "currency": currency,
                "owner": owner,
                "embedding": vector,
                "last_synced_from": path.name,
                "synced_at": now_iso,
            })

    count = upsert_finance_budgets(org_id=org_id, rows=clean_records)
    logger.info("sync_finance_data: synced %d budget categories for org '%s'.", count, org_id)
    return clean_records
