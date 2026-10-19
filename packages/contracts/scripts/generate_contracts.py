"""
packages/contracts/scripts/generate_contracts.py
=================================================
Generates TypeScript interfaces and Python Pydantic v2 models from JSON Schemas.
Also provides a --check mode for CI to fail if generated files are stale.
"""

import sys
import os
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONTRACTS_DIR = ROOT_DIR / "packages" / "contracts"
MEETING_ENDED_SCHEMA = CONTRACTS_DIR / "meeting_ended.schema.json"
SSE_EVENTS_SCHEMA = CONTRACTS_DIR / "sse_events.schema.json"

TS_OUT_DIR = CONTRACTS_DIR / "generated" / "ts"
PY_OUT_DIR = CONTRACTS_DIR / "generated" / "py"

WEB_CONTRACTS_DIR = ROOT_DIR / "apps" / "web" / "types" / "contracts"
WORKOS_CONTRACTS_DIR = ROOT_DIR / "services" / "workos" / "contracts"
MEDIA_CONTRACTS_DIR = ROOT_DIR / "services" / "media" / "contracts"


def generate_ts():
    ts_meeting_ended = '''/**
 * Auto-generated from packages/contracts/meeting_ended.schema.json
 * DO NOT EDIT DIRECTLY. Run `npm run contracts` to regenerate.
 */

export interface Participant {
  clerk_user_id: string;
  display_name: string;
  email: string;
}

export interface TranscriptSegment {
  speaker: string;
  speaker_user_id?: string | null;
  start: number;
  end: number;
  text: string;
}

export interface MeetingEndedPayload {
  meeting_id: string;
  org_id: string;
  title: string;
  started_at: string;
  ended_at: string;
  language: string;
  participants: Participant[];
  transcript: TranscriptSegment[];
  summary?: string | null;
  recording_url?: string | null;
}
'''

    ts_sse_events = '''/**
 * Auto-generated from packages/contracts/sse_events.schema.json
 * DO NOT EDIT DIRECTLY. Run `npm run contracts` to regenerate.
 */

export type SSEEventType =
  | 'processing_started'
  | 'resolution_ready'
  | 'hitl_ready'
  | 'dispatched'
  | 'tracker_update'
  | 'complete'
  | 'error';

export interface SSEEventEnvelope<T = Record<string, unknown>> {
  event_type: SSEEventType;
  thread_id: string;
  payload: T;
}
'''

    ts_index = '''/**
 * Auto-generated index for contracts.
 * DO NOT EDIT DIRECTLY. Run `npm run contracts` to regenerate.
 */

export * from './meeting_ended';
export * from './sse_events';
'''
    return {
        "meeting_ended.ts": ts_meeting_ended,
        "sse_events.ts": ts_sse_events,
        "index.ts": ts_index,
    }


def generate_py():
    py_meeting_ended = '''"""
Auto-generated from packages/contracts/meeting_ended.schema.json
DO NOT EDIT DIRECTLY. Run `python packages/contracts/scripts/generate_contracts.py` to regenerate.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class Participant(BaseModel):
    clerk_user_id: str = Field(..., description="Unique Clerk user ID")
    display_name: str = Field(..., description="Display name of participant")
    email: str = Field(..., description="Email address")


class TranscriptSegment(BaseModel):
    speaker: str = Field(..., description="Speaker label (e.g. SPEAKER_01)")
    speaker_user_id: Optional[str] = Field(default=None, description="Mapped Clerk user ID if resolved")
    start: float = Field(..., description="Start timestamp in seconds")
    end: float = Field(..., description="End timestamp in seconds")
    text: str = Field(..., description="Transcribed text")


class MeetingEndedPayload(BaseModel):
    meeting_id: str = Field(..., description="Unique meeting UUID")
    org_id: str = Field(..., description="Clerk organization ID")
    title: str = Field(..., description="Meeting title")
    started_at: str = Field(..., description="ISO-8601 start timestamp")
    ended_at: str = Field(..., description="ISO-8601 end timestamp")
    language: str = Field(default="en", description="Transcript language")
    participants: List[Participant] = Field(default_factory=list, description="Participant attendees")
    transcript: List[TranscriptSegment] = Field(..., description="Attributed transcript segments")
    summary: Optional[str] = Field(default=None, description="Meeting summary")
    recording_url: Optional[str] = Field(default=None, description="Cloudinary/Stream recording URL")
'''

    py_sse_events = '''"""
Auto-generated from packages/contracts/sse_events.schema.json
DO NOT EDIT DIRECTLY. Run `python packages/contracts/scripts/generate_contracts.py` to regenerate.
"""

from typing import Any, Dict, Literal
from pydantic import BaseModel, Field

SSEEventType = Literal[
    "processing_started",
    "resolution_ready",
    "hitl_ready",
    "dispatched",
    "tracker_update",
    "complete",
    "error",
]


class SSEEventEnvelope(BaseModel):
    event_type: SSEEventType = Field(..., description="Type of SSE event")
    thread_id: str = Field(..., description="LangGraph thread ID")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event payload data")
'''

    py_init = '''"""Contracts package."""

from .meeting_ended import MeetingEndedPayload, Participant, TranscriptSegment
from .sse_events import SSEEventEnvelope, SSEEventType

__all__ = [
    "MeetingEndedPayload",
    "Participant",
    "TranscriptSegment",
    "SSEEventEnvelope",
    "SSEEventType",
]
'''
    return {
        "meeting_ended.py": py_meeting_ended,
        "sse_events.py": py_sse_events,
        "__init__.py": py_init,
    }


def write_files(target_dir: Path, files: dict, check_mode: bool = False) -> bool:
    target_dir.mkdir(parents=True, exist_ok=True)
    all_match = True
    for filename, content in files.items():
        file_path = target_dir / filename
        if check_mode:
            if not file_path.exists():
                print(f"[CHECK FAILED] File missing: {file_path}")
                all_match = False
            else:
                existing = file_path.read_text(encoding="utf-8")
                if existing.strip() != content.strip():
                    print(f"[CHECK FAILED] File stale: {file_path}")
                    all_match = False
        else:
            file_path.write_text(content, encoding="utf-8")
            print(f"[GENERATED] {file_path}")
    return all_match


def main():
    check_mode = "--check" in sys.argv

    # Ensure source schemas exist
    if not MEETING_ENDED_SCHEMA.exists() or not SSE_EVENTS_SCHEMA.exists():
        print("[ERROR] Source JSON schemas not found in packages/contracts!")
        sys.exit(1)

    ts_files = generate_ts()
    py_files = generate_py()

    all_ok = True

    # 1. Target: packages/contracts/generated/ts
    all_ok &= write_files(TS_OUT_DIR, ts_files, check_mode)

    # 2. Target: packages/contracts/generated/py
    all_ok &= write_files(PY_OUT_DIR, py_files, check_mode)

    # 3. Target: apps/web/types/contracts
    all_ok &= write_files(WEB_CONTRACTS_DIR, ts_files, check_mode)

    # 4. Target: services/workos/contracts
    all_ok &= write_files(WORKOS_CONTRACTS_DIR, py_files, check_mode)

    # 5. Target: services/media/contracts
    all_ok &= write_files(MEDIA_CONTRACTS_DIR, py_files, check_mode)

    if check_mode:
        if not all_ok:
            print("[ERROR] Contracts generated files are stale or missing. Run `python packages/contracts/scripts/generate_contracts.py`.")
            sys.exit(1)
        else:
            print("[OK] All generated contract files are fresh and up to date.")
    else:
        print("[SUCCESS] All contract types successfully generated.")


if __name__ == "__main__":
    main()
