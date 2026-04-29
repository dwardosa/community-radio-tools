"""
Persistent state tracker using SQLite.

Tracks which audio files have already been processed so they are never
uploaded twice, even if the process is restarted.

For local files:  the ID is  "local:{absolute_path}:{mtime_int}"
For Drive files:  the ID is  "drive:{drive_file_id}"

Using mtime in local IDs means a re-recorded file with the same name
(different mtime) will be treated as new and re-uploaded.
"""
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS processed_files (
        id                  TEXT PRIMARY KEY,
        source              TEXT NOT NULL,
        processed_at        TEXT NOT NULL,
        soundcloud_track_id TEXT
    )
"""


class StateTracker:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()
        logger.debug("State DB opened: %s", db_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_processed(self, file_id: str) -> bool:
        """Return True if this file_id has already been processed."""
        row = self._conn.execute(
            "SELECT 1 FROM processed_files WHERE id = ?", (file_id,)
        ).fetchone()
        return row is not None

    def mark_processed(
        self,
        file_id: str,
        source: str,
        soundcloud_track_id: str | None = None,
    ):
        """Record a file as successfully processed."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO processed_files
                (id, source, processed_at, soundcloud_track_id)
            VALUES (?, ?, ?, ?)
            """,
            (file_id, source, now, soundcloud_track_id),
        )
        self._conn.commit()
        logger.debug("Marked processed: %s (track %s)", file_id, soundcloud_track_id)

    def close(self):
        self._conn.close()


# ------------------------------------------------------------------
# Helper to build a stable local file ID
# ------------------------------------------------------------------

def local_file_id(path: str) -> str:
    """
    Build a unique ID for a local file that changes if the file is replaced
    (different mtime) but stays stable while the file is untouched.
    """
    mtime = int(Path(path).stat().st_mtime)
    return f"local:{Path(path).resolve()}:{mtime}"
