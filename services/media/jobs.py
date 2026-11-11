"""Bounded asynchronous media job runner (ThreadPoolExecutor + status store)."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pipeline.dubber import process_media_job


class MediaJobManager:
    """Manages async dubbing & transcription jobs with bounded concurrency."""

    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def submit_job(self, params: Dict[str, Any]) -> Dict[str, Any]:
        job_id = str(params.get("job_id") or uuid.uuid4())
        meeting_id = str(params.get("meeting_id") or uuid.uuid4())
        org_id = str(params.get("org_id") or "org_demo_horizon")

        record = {
            "job_id": job_id,
            "meeting_id": meeting_id,
            "org_id": org_id,
            "status": "QUEUED",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "result": None,
            "error": None,
        }
        with self._lock:
            self._jobs[job_id] = record

        def _run() -> None:
            with self._lock:
                self._jobs[job_id]["status"] = "PROCESSING"
                self._jobs[job_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
            try:
                res = process_media_job(
                    job_id=job_id,
                    meeting_id=meeting_id,
                    org_id=org_id,
                    video_url=params["video_url"],
                    title=params.get("title", "Horizon Veridian Meeting"),
                    target_lang=params.get("target_lang", "en"),
                    language_hint=params.get("language_hint", "auto-detect"),
                    participants=params.get("participants"),
                    speaker_map=params.get("speaker_map"),
                    generate_dub=bool(params.get("generate_dub", True)),
                    emit_meeting_ended=bool(params.get("emit_meeting_ended", True)),
                )
                with self._lock:
                    self._jobs[job_id]["status"] = "COMPLETED"
                    self._jobs[job_id]["result"] = res
                    self._jobs[job_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
            except Exception as exc:
                with self._lock:
                    self._jobs[job_id]["status"] = "FAILED"
                    self._jobs[job_id]["error"] = str(exc)
                    self._jobs[job_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

        self._executor.submit(_run)
        return dict(record)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None


job_manager = MediaJobManager()
