"""SQLite keeps immutable, content-addressed snapshots for audit and rollback."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def snapshot(data, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS snapshots (sha256 TEXT PRIMARY KEY, created_at TEXT, payload TEXT)")
        db.execute("INSERT OR IGNORE INTO snapshots VALUES (?, ?, ?)",
                   (digest, datetime.now(timezone.utc).isoformat(), raw))
    return digest
