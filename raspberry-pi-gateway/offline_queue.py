"""
Persistent SQLite-based Offline Queue for Raspberry Pi IoT Gateway (FR-058 to FR-064).
Ensures zero data loss during internet interruptions and synchronizes buffered messages
in chronological FIFO order upon cloud reconnection.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any
from config import OFFLINE_DB_PATH, MAX_OFFLINE_QUEUE_SIZE
from logger import get_logger

log = get_logger("offline_queue")


class OfflineQueue:
    def __init__(self, db_path: Path = OFFLINE_DB_PATH):
        self.db_path = Path(db_path)
        self.lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS buffered_readings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id TEXT UNIQUE NOT NULL,
                        patient_id TEXT NOT NULL,
                        device_id TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        enqueued_at TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def enqueue(self, payload: Dict[str, Any]) -> bool:
        """Persists a validated reading to disk when AWS Cloud is unreachable."""
        marked = dict(payload)
        marked["bufferedOffline"] = True
        msg_id = marked["messageId"]

        with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cur = conn.execute("SELECT COUNT(*) FROM buffered_readings")
                count = cur.fetchone()[0]
                if count >= MAX_OFFLINE_QUEUE_SIZE:
                    # Drop oldest record to prevent SD card exhaustion
                    conn.execute(
                        "DELETE FROM buffered_readings WHERE id IN (SELECT id FROM buffered_readings ORDER BY id ASC LIMIT 1)"
                    )

                conn.execute(
                    """
                    INSERT OR IGNORE INTO buffered_readings
                    (message_id, patient_id, device_id, timestamp, payload_json, enqueued_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        msg_id,
                        marked["patientId"],
                        marked["deviceId"],
                        marked["timestamp"],
                        json.dumps(marked),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()
                log.info(f"Buffered reading {msg_id} for {marked['patientId']} in persistent SQLite queue.")
                return True
            except Exception as exc:
                log.error(f"Failed to enqueue reading {msg_id}: {exc}")
                return False
            finally:
                conn.close()

    def peek_batch(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Retrieves up to `limit` buffered messages in FIFO order without deleting them yet."""
        with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cur = conn.execute(
                    "SELECT message_id, payload_json FROM buffered_readings ORDER BY id ASC LIMIT ?",
                    (limit,),
                )
                rows = cur.fetchall()
                return [json.loads(r[1]) for r in rows]
            finally:
                conn.close()

    def mark_synchronized(self, message_ids: List[str]) -> int:
        """Removes successfully transmitted messages from the persistent buffer."""
        if not message_ids:
            return 0
        with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                placeholders = ",".join("?" for _ in message_ids)
                cur = conn.execute(
                    f"DELETE FROM buffered_readings WHERE message_id IN ({placeholders})",
                    message_ids,
                )
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()

    def size(self) -> int:
        """Returns the current number of unsent readings in the persistent queue."""
        with self.lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                cur = conn.execute("SELECT COUNT(*) FROM buffered_readings")
                return int(cur.fetchone()[0])
            finally:
                conn.close()
