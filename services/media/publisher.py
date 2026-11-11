"""HMAC-signed MeetingEnded contract publisher with exponential backoff & dead-lettering."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

from config import get_media_settings
from contracts.meeting_ended import MeetingEndedPayload

logger = logging.getLogger(__name__)


def compute_hmac_signature(raw_body: bytes, secret: str) -> str:
    """Return 'sha256=<hex>' HMAC digest over exact raw request body bytes."""
    digest = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def _write_dead_letter(payload: MeetingEndedPayload, error_message: str) -> Path:
    settings = get_media_settings()
    dl_dir = Path(settings.dead_letter_dir)
    dl_dir.mkdir(parents=True, exist_ok=True)
    record_path = dl_dir / f"{payload.meeting_id}_{uuid.uuid4().hex[:8]}.json"
    record = {
        "failed_at": datetime.now(timezone.utc).isoformat(),
        "meeting_id": payload.meeting_id,
        "org_id": payload.org_id,
        "error": error_message,
        "payload": payload.model_dump(mode="json"),
    }
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    logger.error("Dead-lettered meeting.ended payload to %s: %s", record_path, error_message)
    return record_path


def publish_meeting_ended(
    payload: MeetingEndedPayload,
    workos_url: Optional[str] = None,
    shared_secret: Optional[str] = None,
    max_retries: int = 3,
    backoff_base: float = 0.5,
) -> dict:
    """Validate MeetingEndedPayload against shared contract and POST signed webhook."""
    settings = get_media_settings()
    validated = MeetingEndedPayload.model_validate(payload.model_dump())
    target_url = (workos_url or settings.workos_url).rstrip("/") + "/api/meeting-ended"
    secret = (shared_secret if shared_secret is not None else settings.shared_hmac_secret).strip()

    if not secret:
        raise EnvironmentError("SHARED_HMAC_SECRET must be set before publishing meeting.ended events.")

    raw_body = json.dumps(validated.model_dump(mode="json"), separators=(",", ":")).encode("utf-8")
    last_error = "Unknown publish error"

    for attempt in range(1, max_retries + 1):
        timestamp = str(int(time.time()))
        signature = compute_hmac_signature(raw_body, secret)
        headers = {
            "Content-Type": "application/json",
            "X-Signature": signature,
            "X-Timestamp": timestamp,
            "Idempotency-Key": validated.meeting_id,
        }
        try:
            resp = requests.post(target_url, data=raw_body, headers=headers, timeout=15)
            if 200 <= resp.status_code < 300:
                return resp.json()
            last_error = f"HTTP {resp.status_code}: {resp.text[:250]}"
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                break
        except Exception as exc:
            last_error = str(exc)

        if attempt < max_retries:
            time.sleep(backoff_base * (2 ** (attempt - 1)))

    dl_path = _write_dead_letter(validated, last_error)
    raise RuntimeError(f"Failed to deliver meeting.ended after {max_retries} attempt(s): {last_error} (dl={dl_path})")
