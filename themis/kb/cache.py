"""Phase 11.2 — SQLite-backed KB lookup cache.

Single-table cache keyed on (kb_name, sha256(canonical_query_json)).
Stores the full KBResult JSON; clients use this to dedupe lookups
across orchestrator turns.

No TTL by design — KB facts are not session-state and shouldn't expire
on a clock. Clients that need to refresh call ``delete()`` then ``put()``.

The cache is local-state only. It does NOT participate in the
"Themis has no IO" invariant — it only stores results adapters fetched
elsewhere. Adapters call cache.get() before query() and cache.put()
after, but the cache itself reaches no further than the local SQLite
file.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

from .schemas import KBQuery, KBResult, kb_query_to_dict, kb_result_from_dict, kb_result_to_dict


_DDL = """
CREATE TABLE IF NOT EXISTS kb_cache (
    kb_name TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    result_json TEXT NOT NULL,
    cached_at REAL NOT NULL,
    PRIMARY KEY (kb_name, query_hash)
);
"""


def cache_key(q: KBQuery) -> str:
    """sha256 of the JSON-stable query dict. Two equal KBQuery instances
    always produce the same key; deterministic across processes."""
    payload = json.dumps(kb_query_to_dict(q), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class KBCache:
    """SQLite-backed cache. Default path ``:memory:`` keeps the cache
    process-local — pass a real path to persist across runs."""

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute(_DDL)
        self._conn.commit()

    # ----------------------------------------------------- API

    def get(self, q: KBQuery) -> KBResult | None:
        row = self._conn.execute(
            "SELECT result_json FROM kb_cache WHERE kb_name = ? AND query_hash = ?",
            (q.kb_name, cache_key(q)),
        ).fetchone()
        if row is None:
            return None
        return kb_result_from_dict(json.loads(row[0]))

    def put(self, q: KBQuery, r: KBResult) -> None:
        """Insert or replace. Re-putting the same query updates the
        timestamp, useful for "refresh" semantics."""
        self._conn.execute(
            "INSERT OR REPLACE INTO kb_cache "
            "(kb_name, query_hash, result_json, cached_at) "
            "VALUES (?, ?, ?, ?)",
            (
                q.kb_name,
                cache_key(q),
                json.dumps(kb_result_to_dict(r), ensure_ascii=False),
                time.time(),
            ),
        )
        self._conn.commit()

    def delete(self, q: KBQuery) -> bool:
        """Returns True if a row was actually removed."""
        cur = self._conn.execute(
            "DELETE FROM kb_cache WHERE kb_name = ? AND query_hash = ?",
            (q.kb_name, cache_key(q)),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def stats(self) -> dict:
        row = self._conn.execute(
            "SELECT COUNT(*), MIN(cached_at), MAX(cached_at) FROM kb_cache"
        ).fetchone()
        count, oldest, newest = row
        return {"entries": count, "oldest_at": oldest, "newest_at": newest}

    def clear(self) -> int:
        """Wipe all entries. Returns the number of rows removed."""
        cur = self._conn.execute("DELETE FROM kb_cache")
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------ context manager

    def __enter__(self) -> "KBCache":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
