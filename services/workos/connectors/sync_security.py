"""Org-aware Security Policy connector (supports Markdown, plain text, and PDF)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from core.config import get_settings
from core.embeddings import get_embedding
from core.store import _parse_security_markdown, upsert_security_policies

logger = logging.getLogger(__name__)
_REPO_ROOT = Path(__file__).resolve().parents[3]


def sync_security_data(org_id: str, policy_path: Optional[str] = None) -> List[Dict]:
    """Read security policy document, chunk into policies, embed, and upsert for org_id."""
    settings = get_settings()
    path = Path(policy_path) if policy_path else (_REPO_ROOT / settings.security_policy_path)
    if not path.exists():
        raise FileNotFoundError(f"Security policy file not found: {path}")

    now_iso = datetime.now(timezone.utc).isoformat()
    clean_records: List[Dict] = []

    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        for idx, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            pol_id = f"SEC-POL-{idx:03d}"
            vector = get_embedding(f"{pol_id} {text}", dim=settings.embedding_dim)
            clean_records.append({
                "id": str(uuid.uuid4()),
                "org_id": org_id,
                "policy_id": pol_id,
                "document_name": path.name,
                "chunk_text": text,
                "page_number": idx,
                "embedding": vector,
                "synced_at": now_iso,
            })
    else:
        raw_text = path.read_text(encoding="utf-8")
        sections = _parse_security_markdown(raw_text)
        if not sections:
            sections = [("SEC-POL-089", raw_text.strip())]
        for idx, (pol_id, chunk_text) in enumerate(sections, start=1):
            vector = get_embedding(f"{pol_id} {chunk_text}", dim=settings.embedding_dim)
            clean_records.append({
                "id": str(uuid.uuid4()),
                "org_id": org_id,
                "policy_id": pol_id,
                "document_name": "Veridian Global Information Security Policy v4.2",
                "chunk_text": chunk_text,
                "page_number": idx,
                "embedding": vector,
                "synced_at": now_iso,
            })

    count = upsert_security_policies(org_id=org_id, rows=clean_records)
    logger.info("sync_security_data: synced %d policy chunks for org '%s'.", count, org_id)
    return clean_records
