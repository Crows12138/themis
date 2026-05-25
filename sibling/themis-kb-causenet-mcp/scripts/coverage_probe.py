"""Probe both DBs (precision + full) on a fixed set of test queries
to measure tier-1 vs tier-2 coverage lift.

Runs the same 8 queries we used during Phase A schema inspection plus
~12 additional cross-domain queries that should stretch the breadth of
CauseNet's coverage. Reports hit / miss per tier.

Run AFTER `python scripts/build_db.py --variant both` has produced
both data/causenet-precision.sqlite and data/causenet-full.sqlite.

This is a one-shot diagnostic, not a test. It's the empirical answer
to "does going from 197K to 11M actually buy us more coverage?".
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
PRECISION = DATA / "causenet-precision.sqlite"
FULL = DATA / "causenet-full.sqlite"

# 20 queries spanning health / lifestyle / economy / politics /
# environment / education / workplace / commonsense.
QUERIES = [
    # Phase A baseline (8 queries)
    ("aspirin", "bleeding"),
    ("smoking", "lung_cancer"),
    ("exercise", "weight_loss"),
    ("medication", "heart_condition"),
    ("food_sharing", "workplace_warmth"),
    ("minimum_wage", "unemployment"),
    ("class_size", "test_scores"),
    ("caffeine", "productivity"),
    # Health / medical (extra)
    ("obesity", "diabetes"),
    ("alcohol", "liver_disease"),
    ("vaccine", "immunity"),
    # Economy / policy
    ("inflation", "unemployment"),
    ("trade_war", "recession"),
    ("automation", "job_loss"),
    # Environment / society
    ("deforestation", "climate_change"),
    ("pollution", "asthma"),
    # Education / workplace
    ("homework", "learning"),
    ("overtime", "burnout"),
    # Commonsense
    ("rain", "flood"),
    ("stress", "insomnia"),
]


def query(conn: sqlite3.Connection, cause: str, effect: str) -> int | None:
    row = conn.execute(
        "SELECT num_sources FROM edges WHERE cause = ? AND effect = ?",
        (cause, effect),
    ).fetchone()
    return row[0] if row else None


def main() -> int:
    if not PRECISION.exists():
        print(f"Missing: {PRECISION}", file=sys.stderr)
        return 1
    if not FULL.exists():
        print(f"Missing: {FULL}", file=sys.stderr)
        return 1

    p_conn = sqlite3.connect(str(PRECISION))
    f_conn = sqlite3.connect(str(FULL))

    p_hits = 0
    f_only_hits = 0
    misses = 0

    print(f"{'cause':<18} {'effect':<22} {'precision':>10} {'full':>10}  tier")
    print("-" * 75)
    for c, e in QUERIES:
        p = query(p_conn, c, e)
        f = query(f_conn, c, e)
        tier = (
            "high_confidence" if p else
            "extracted (full only)" if f else
            "not_found"
        )
        if p:
            p_hits += 1
        elif f:
            f_only_hits += 1
        else:
            misses += 1
        p_str = str(p) if p else "—"
        f_str = str(f) if f else "—"
        print(f"{c:<18} {e:<22} {p_str:>10} {f_str:>10}  {tier}")

    total = len(QUERIES)
    print("-" * 75)
    print(f"Coverage on {total} queries:")
    print(f"  Tier 1 (precision):     {p_hits} ({p_hits/total*100:.0f}%)")
    print(f"  Tier 2 lift (full only): +{f_only_hits} ({f_only_hits/total*100:.0f}%)")
    print(f"  Combined hit rate:       {(p_hits+f_only_hits)/total*100:.0f}%")
    print(f"  Not found:               {misses}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
