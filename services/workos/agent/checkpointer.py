"""Checkpointer factory: PostgresSaver when configured, persistent SQLite InMemorySaver in local dev."""

from __future__ import annotations

import logging
import pickle
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Any, Optional, Sequence

from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata, ChannelVersions
from langgraph.checkpoint.memory import InMemorySaver

from core.config import get_settings

logger = logging.getLogger(__name__)


class SQLitePersistentSaver(InMemorySaver):
    """InMemorySaver snapshot-persisted thread-safely to SQLite so HITL pauses survive restarts."""

    def __init__(self, db_path: str = "services/workos/.checkpoints.db") -> None:
        super().__init__()
        self._lock = threading.RLock()
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._load_state()

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self._db_path)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS checkpoint_snapshots (id INTEGER PRIMARY KEY CHECK (id = 1), payload BLOB NOT NULL)"
            )
            conn.commit()

    def _load_state(self) -> None:
        try:
            with self._lock, closing(sqlite3.connect(self._db_path)) as conn:
                row = conn.execute("SELECT payload FROM checkpoint_snapshots WHERE id = 1").fetchone()
                if row and row[0]:
                    storage_raw, writes_raw, blobs_raw = pickle.loads(row[0])
                    for tid, ns_map in storage_raw.items():
                        for ns, cp_map in ns_map.items():
                            self.storage[tid][ns].update(cp_map)
                    for k, v in writes_raw.items():
                        self.writes[k].update(v)
                    self.blobs.update(blobs_raw)
        except Exception as exc:
            logger.warning("SQLitePersistentSaver load warning (starting clean): %s", exc)

    def _flush_locked(self) -> None:
        storage_plain = {
            tid: {ns: dict(cp_map) for ns, cp_map in ns_map.items()}
            for tid, ns_map in self.storage.items()
        }
        writes_plain = {k: dict(v) for k, v in self.writes.items()}
        blobs_plain = dict(self.blobs)
        blob = pickle.dumps((storage_plain, writes_plain, blobs_plain))
        with closing(sqlite3.connect(self._db_path)) as conn:
            conn.execute(
                "INSERT INTO checkpoint_snapshots (id, payload) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
                (blob,),
            )
            conn.commit()

    def put(
        self,
        config: Any,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> Any:
        with self._lock:
            out = super().put(config, checkpoint, metadata, new_versions)
            self._flush_locked()
            return out

    def put_writes(
        self,
        config: Any,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        with self._lock:
            super().put_writes(config, writes, task_id, task_path=task_path)
            self._flush_locked()


def build_checkpointer(db_path: Optional[str] = None) -> Any:
    """Use PostgresSaver if DATABASE_URL is a live Postgres DSN + driver installed; else SQLitePersistentSaver."""
    settings = get_settings()
    if (
        settings.database_url
        and "localhost" not in settings.database_url
        and "postgres:password" not in settings.database_url
    ):
        try:
            from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore

            saver = PostgresSaver.from_conn_string(settings.database_url)
            logger.info("Using LangGraph PostgresSaver checkpointer.")
            return saver
        except Exception as exc:
            logger.warning("PostgresSaver unavailable (%s); falling back to SQLitePersistentSaver.", exc)

    target = db_path or "services/workos/.checkpoints.db"
    return SQLitePersistentSaver(db_path=target)
