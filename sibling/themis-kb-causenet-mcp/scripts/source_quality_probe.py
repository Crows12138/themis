"""Probe CauseNet source quality: Wikipedia vs ClueWeb12 split.

Two outputs:

1. Quantitative — histogram of wikipedia_share buckets across all edges
   in the precision DB. Tells us empirically what fraction of edges
   would survive a "wikipedia-only" filter.

2. Qualitative — for representative edges from each bucket, dump sample
   sentences from wikipedia vs clueweb so we can assess actual content
   quality side-by-side.

Run after `python scripts/build_db.py --variant precision` (or both).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
PRECISION = DATA / "causenet-precision.sqlite"

# Representative edges to inspect by hand
QUALITY_SAMPLE_EDGES = [
    # Medical/health
    ("smoking", "lung_cancer"),
    ("vaccines", "autism"),       # known misinformation magnet
    ("aspirin", "bleeding"),
    ("stress", "insomnia"),
    # Social / workplace
    ("overtime", "burnout"),
    # Common sense
    ("rain", "flood"),
    # Economy
    ("inflation", "unemployment"),
    ("minimum_wage", "unemployment"),
]


def main() -> int:
    if not PRECISION.exists():
        print(f"Missing: {PRECISION}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(str(PRECISION))
    conn.row_factory = sqlite3.Row

    # ============================================
    # PART 1 — Quantitative distribution
    # ============================================
    print("=" * 70)
    print("PART 1 — wikipedia_share distribution across all precision edges")
    print("=" * 70)

    # Per-edge: wiki count / total count
    rows = conn.execute("""
        SELECT
          cause, effect,
          SUM(CASE WHEN source_type LIKE 'wikipedia%' THEN 1 ELSE 0 END) AS wiki_n,
          COUNT(*) AS total_n
        FROM sources
        GROUP BY cause, effect
    """).fetchall()

    total_edges = len(rows)
    buckets = {
        "wiki_only (share=1.0)": 0,
        "wiki_majority (0.5 <= share < 1.0)": 0,
        "mixed (0 < share < 0.5)": 0,
        "clueweb_only (share=0)": 0,
    }
    wiki_shares = []
    for r in rows:
        share = r["wiki_n"] / r["total_n"] if r["total_n"] else 0
        wiki_shares.append(share)
        if share == 1.0:
            buckets["wiki_only (share=1.0)"] += 1
        elif share >= 0.5:
            buckets["wiki_majority (0.5 <= share < 1.0)"] += 1
        elif share > 0:
            buckets["mixed (0 < share < 0.5)"] += 1
        else:
            buckets["clueweb_only (share=0)"] += 1

    print(f"\nTotal precision-tier edges: {total_edges:,}\n")
    for bucket, count in buckets.items():
        pct = count / total_edges * 100
        bar = "#" * int(pct / 2)
        print(f"  {bucket:<40} {count:>8,} ({pct:5.1f}%) {bar}")

    wiki_shares.sort()
    median = wiki_shares[len(wiki_shares)//2]
    mean = sum(wiki_shares) / len(wiki_shares)
    pct_zero = sum(1 for s in wiki_shares if s == 0) / len(wiki_shares) * 100
    pct_one  = sum(1 for s in wiki_shares if s == 1.0) / len(wiki_shares) * 100
    print(f"\n  median wiki_share: {median:.3f}")
    print(f"  mean   wiki_share: {mean:.3f}")
    print(f"  edges with wiki_share = 0:   {pct_zero:5.1f}%")
    print(f"  edges with wiki_share = 1.0: {pct_one:5.1f}%")

    # Aggregate sentence count too — perhaps more informative than edges
    print()
    sent_split = conn.execute("""
        SELECT source_type, COUNT(*) AS n
        FROM sources GROUP BY source_type
        ORDER BY n DESC
    """).fetchall()
    total_sents = sum(r["n"] for r in sent_split)
    print(f"Sentence-level breakdown (total {total_sents:,} sentences):")
    for r in sent_split:
        pct = r["n"] / total_sents * 100
        print(f"  {r['source_type']:<28} {r['n']:>10,} ({pct:5.1f}%)")

    # ============================================
    # PART 2 — Qualitative content inspection
    # ============================================
    print()
    print("=" * 70)
    print("PART 2 — content inspection: wiki vs clueweb sentences side-by-side")
    print("=" * 70)

    for cause, effect in QUALITY_SAMPLE_EDGES:
        row = conn.execute(
            "SELECT num_sources FROM edges WHERE cause=? AND effect=?",
            (cause, effect),
        ).fetchone()
        if row is None:
            print(f"\n--- {cause} -> {effect} : NOT IN PRECISION ---")
            continue

        total = row["num_sources"]
        # Split by source type
        wiki = conn.execute("""
            SELECT source_title, sentence FROM sources
            WHERE cause=? AND effect=? AND source_type LIKE 'wikipedia%'
            LIMIT 3
        """, (cause, effect)).fetchall()
        clueweb = conn.execute("""
            SELECT source_title, sentence FROM sources
            WHERE cause=? AND effect=? AND source_type LIKE 'clueweb%'
            LIMIT 3
        """, (cause, effect)).fetchall()

        wiki_n = conn.execute("""
            SELECT COUNT(*) AS n FROM sources
            WHERE cause=? AND effect=? AND source_type LIKE 'wikipedia%'
        """, (cause, effect)).fetchone()["n"]
        clueweb_n = total - wiki_n
        share = wiki_n / total if total else 0

        print(f"\n--- {cause} -> {effect} ---")
        print(f"  total sources: {total}  |  wiki: {wiki_n}  |  clueweb: {clueweb_n}  |  wiki_share: {share:.3f}")

        if wiki:
            print(f"  WIKI samples:")
            for r in wiki:
                title = (r["source_title"] or "(no title)")[:50]
                sent = (r["sentence"] or "")[:200].replace("\n", " ")
                print(f"    [{title}] {sent}")
        if clueweb:
            print(f"  CLUEWEB samples:")
            for r in clueweb:
                title = (r["source_title"] or "(no title)")[:50]
                sent = (r["sentence"] or "")[:200].replace("\n", " ")
                print(f"    [{title}] {sent}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
