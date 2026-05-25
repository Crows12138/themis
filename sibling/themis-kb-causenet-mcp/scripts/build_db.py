"""Phase B — Build SQLite DB(s) from CauseNet JSONL.bz2 input.

CauseNet relation shape (per Phase A inspection):

    {
      "causal_relation": {
        "cause":  {"concept": "<str>"},
        "effect": {"concept": "<str>"}
      },
      "sources": [
        {
          "type": "wikipedia_sentence" | "clueweb_sentence",
          "payload": {
            "wikipedia_page_title": "...",
            "wikipedia_page_id": "...",
            "sentence": "...",
            "path_pattern": "..."
          }
        },
        ...
      ]
    }

DB schema:

    edges (cause TEXT, effect TEXT, num_sources INT, PRIMARY KEY(cause, effect))
    sources (cause TEXT, effect TEXT, source_type TEXT, source_title TEXT,
             source_id TEXT, sentence TEXT, path_pattern TEXT)
    INDEX edges_effect_idx ON edges(effect)        — reverse lookup ("what causes X")
    INDEX sources_edge_idx ON sources(cause, effect)

The edges table is the fast lookup. The sources table is the evidence trail
for "kb_verified — here are the Wikipedia sentences supporting it".

Two DBs by convention (tiered confidence — see server.py):
    causenet-precision.jsonl.bz2 → causenet-precision.sqlite (~600MB,
        83% precision, high-confidence tier)
    causenet-full.jsonl.bz2 → causenet-full.sqlite (~5-8GB, lower
        precision, broader coverage tier)

Idempotent: drops and rebuilds. Run via:
    python scripts/build_db.py                 # default: precision
    python scripts/build_db.py --variant full  # full 11M version
    python scripts/build_db.py --variant both  # both
"""
from __future__ import annotations

import argparse
import bz2
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"

VARIANTS = {
    "precision": {
        "jsonl_bz2": DATA / "causenet-precision.jsonl.bz2",
        "db_path": DATA / "causenet-precision.sqlite",
    },
    "full": {
        "jsonl_bz2": DATA / "causenet-full.jsonl.bz2",
        "db_path": DATA / "causenet-full.sqlite",
    },
}


SCHEMA_SQL = """
DROP TABLE IF EXISTS edges;
DROP TABLE IF EXISTS sources;
CREATE TABLE edges (
    cause       TEXT NOT NULL,
    effect      TEXT NOT NULL,
    num_sources INTEGER NOT NULL,
    PRIMARY KEY (cause, effect)
);
CREATE INDEX edges_effect_idx ON edges(effect);

CREATE TABLE sources (
    cause         TEXT NOT NULL,
    effect        TEXT NOT NULL,
    source_type   TEXT NOT NULL,
    source_title  TEXT,
    source_id     TEXT,
    sentence      TEXT,
    path_pattern  TEXT
);
CREATE INDEX sources_edge_idx ON sources(cause, effect);
"""


def build(jsonl_bz2: Path, db_path: Path) -> None:
    print(f"Building {db_path.name} from {jsonl_bz2.name} ...")
    if not jsonl_bz2.exists():
        raise SystemExit(
            f"Missing data file: {jsonl_bz2}\n"
            f"Download via: curl -L -o {jsonl_bz2.name} "
            f"'https://zenodo.org/records/3876154/files/{jsonl_bz2.name}?download=1'"
        )

    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    conn.commit()

    edges_batch: list[tuple[str, str, int]] = []
    sources_batch: list[tuple] = []
    BATCH = 5000
    n_edges = 0
    n_sources = 0

    with bz2.open(jsonl_bz2, "rt", encoding="utf-8") as f:
        for line in f:
            rel = json.loads(line)
            cr = rel["causal_relation"]
            cause = cr["cause"]["concept"]
            effect = cr["effect"]["concept"]
            srcs = rel.get("sources", [])
            edges_batch.append((cause, effect, len(srcs)))

            for s in srcs:
                stype = s.get("type", "")
                p = s.get("payload", {}) or {}
                sources_batch.append((
                    cause, effect, stype,
                    p.get("wikipedia_page_title") or p.get("clueweb_page_title"),
                    p.get("wikipedia_page_id") or p.get("clueweb_page_id"),
                    (p.get("sentence") or "")[:500],  # cap sentence length
                    p.get("path_pattern"),
                ))

            if len(edges_batch) >= BATCH:
                conn.executemany(
                    "INSERT OR REPLACE INTO edges(cause, effect, num_sources) VALUES (?, ?, ?)",
                    edges_batch,
                )
                conn.executemany(
                    "INSERT INTO sources(cause, effect, source_type, source_title, source_id, sentence, path_pattern) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    sources_batch,
                )
                conn.commit()
                n_edges += len(edges_batch)
                n_sources += len(sources_batch)
                print(f"  {n_edges:>9,} edges  {n_sources:>10,} sources committed")
                edges_batch.clear()
                sources_batch.clear()

    if edges_batch:
        conn.executemany(
            "INSERT OR REPLACE INTO edges(cause, effect, num_sources) VALUES (?, ?, ?)",
            edges_batch,
        )
        conn.executemany(
            "INSERT INTO sources(cause, effect, source_type, source_title, source_id, sentence, path_pattern) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            sources_batch,
        )
        conn.commit()
        n_edges += len(edges_batch)
        n_sources += len(sources_batch)

    print(f"\nFinal: {n_edges:,} edges, {n_sources:,} sources")
    print(f"DB file size: {db_path.stat().st_size / 1024 / 1024:.1f} MB")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant", choices=["precision", "full", "both"],
        default="precision",
    )
    args = parser.parse_args()
    variants_to_build = (
        ["precision", "full"] if args.variant == "both" else [args.variant]
    )
    for v in variants_to_build:
        cfg = VARIANTS[v]
        build(cfg["jsonl_bz2"], cfg["db_path"])
