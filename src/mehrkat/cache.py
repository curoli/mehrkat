import hashlib
import json
import sqlite3
import time
from pathlib import Path


def content_key(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Cache:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires REAL NOT NULL)")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def get(self, key: str):
        with self.connect() as db:
            row = db.execute("SELECT value FROM cache WHERE key=? AND expires>?", (key, time.time())).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, value: dict, ttl: int):
        with self.connect() as db:
            db.execute("DELETE FROM cache WHERE expires<=?", (time.time(),))
            db.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", (key, json.dumps(value), time.time() + ttl))
