"""FastMCP server exposing CauseNet (Heindorf et al. 2020).

Tools (JSON in / JSON out, parallel to Themis's own MCP surface):

- ``causenet_query_edge(cause, effect)`` — does CauseNet support
  cause → effect? Returns verdict + supporting evidence count + sample
  Wikipedia sentences.
- ``causenet_query_edge_aggregated(cause, effect)`` — same as above,
  but instead of a small evidence sample, returns aggregated source
  distributions (title / path_pattern / type) over ALL sources for
  the edge. Lets the caller spot homonym / sense-mismatch issues
  structurally — Wikipedia titles already encode disambiguation, so
  surfacing the title distribution is the no-LLM way to verify a
  string-match isn't a semantic mismatch.
- ``causenet_neighbors(concept, direction, limit)`` — list effects of
  concept (direction="effects_of") OR causes of concept ("causes_of").
- ``causenet_neighbors_among(atoms)`` — given a SET of concept atoms,
  return ALL KB edges between any pair of them. Used by the Themis
  adapter's "did the LLM miss any edges?" suggestion surface.
- ``causenet_search_concept(prefix, limit)`` — autocomplete-style
  prefix match over concept space (useful when caller doesn't know the
  exact CauseNet concept string for an atom).

The server is read-only — no mutations. SQLite handles concurrency at
the WAL level; multiple Themis instances can share one server.

Discipline: this server does NOT call any LLM. The MCP client (Themis)
decides what to do with verdicts. We just expose CauseNet's graph.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve()
PACKAGE_ROOT = HERE.parent.parent.parent  # src/causenet_mcp/server.py -> repo root
DEFAULT_PRECISION_DB = PACKAGE_ROOT / "data" / "causenet-precision.sqlite"
DEFAULT_FULL_DB = PACKAGE_ROOT / "data" / "causenet-full.sqlite"


# Confidence tier labels. precision tier = high_confidence (~83%
# extraction precision per Heindorf 2020). full tier = extracted (no
# precision estimate published; assume lower, ~60-70%, due to including
# all extracted relations not just high-confidence subset).
TIER_HIGH_CONFIDENCE = "high_confidence"
TIER_EXTRACTED = "extracted"
TIER_NOT_FOUND = "not_found"


# Cap how many evidence sentences we return per edge — limits payload.
# Each sentence is already capped to 500 chars at build time.
_DEFAULT_EVIDENCE_CAP = 3
_MAX_EVIDENCE_CAP = 10
_DEFAULT_NEIGHBOR_LIMIT = 20
_MAX_NEIGHBOR_LIMIT = 200


def _normalize_concept(s: str) -> str:
    """CauseNet concepts are lowercase, underscore-joined. Normalize
    user input to match: lowercase, strip, replace spaces with _.

    This is the cheapest possible translator — atom predicate names are
    typically already snake_case (Themis convention), so this is mostly
    a defensive pass. Future translator.py in themis side can do more
    aggressive synonym lookup / stemming.
    """
    return s.strip().lower().replace(" ", "_").replace("-", "_")


def _open_if_exists(db_path: Path) -> sqlite3.Connection | None:
    """Open the SQLite if present; return None if file missing.
    Server gracefully degrades when only one of the two DB variants
    is available (e.g., user has downloaded precision but not full yet)."""
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def build_server(
    precision_db: Path | None = None,
    full_db: Path | None = None,
):
    """Construct FastMCP server with tiered-confidence routing.

    Precision DB (~83% precision, 197K relations) is the primary tier;
    full DB (~60-70% est. precision, ~11M relations) is the broader
    fallback tier. Server queries precision first; on miss, falls back
    to full and labels the result with confidence_tier so consumers
    can weight the verdict accordingly.

    If precision_db is absent → server only uses full (loud warning).
    If full_db is absent → server only uses precision (silent — that's
    the canonical MVP setup; full is optional).
    If both absent → raises at construction.

    Tests / production can spin isolated instances by passing explicit
    paths.
    """
    from mcp.server.fastmcp import FastMCP

    precision_path = precision_db or DEFAULT_PRECISION_DB
    full_path = full_db or DEFAULT_FULL_DB

    precision_conn = _open_if_exists(precision_path)
    full_conn = _open_if_exists(full_path)

    if precision_conn is None and full_conn is None:
        raise FileNotFoundError(
            f"Neither CauseNet SQLite found:\n"
            f"  precision: {precision_path}\n"
            f"  full:      {full_path}\n"
            f"Run `python scripts/build_db.py --variant both` after "
            f"downloading the source bz2 files from Zenodo "
            f"(https://zenodo.org/records/3876154)."
        )

    if precision_conn is None:
        import warnings
        warnings.warn(
            "precision DB missing — server running on full-only mode. "
            "kb_provenance.kg_precision_estimate will drop to ~0.65.",
            stacklevel=2,
        )

    app = FastMCP("causenet")

    def _query_one(conn, c, e, cap):
        """Internal: query one DB connection for one edge."""
        row = conn.execute(
            "SELECT num_sources FROM edges WHERE cause = ? AND effect = ?",
            (c, e),
        ).fetchone()
        if row is None:
            return None
        evidence_rows = conn.execute(
            "SELECT source_type, source_title, source_id, sentence, path_pattern "
            "FROM sources WHERE cause = ? AND effect = ? LIMIT ?",
            (c, e, cap),
        ).fetchall()
        return {
            "num_sources": row["num_sources"],
            "evidence_sample": [
                {
                    "source_type": r["source_type"],
                    "title": r["source_title"],
                    "page_id": r["source_id"],
                    "sentence": r["sentence"],
                    "path_pattern": r["path_pattern"],
                }
                for r in evidence_rows
            ],
        }

    @app.tool()
    def causenet_query_edge(
        cause: str,
        effect: str,
        evidence_cap: int = _DEFAULT_EVIDENCE_CAP,
    ) -> dict:
        """Check whether CauseNet supports a `cause → effect` edge,
        with tiered-confidence routing (precision first, full fallback).

        Returns:

            {
              "verdict": "supported" | "not_found",
              "confidence_tier": "high_confidence" | "extracted" | "not_found",
              "cause": "<normalized cause>",
              "effect": "<normalized effect>",
              "num_sources": <int>,
              "evidence_sample": [...up to evidence_cap...],
              "kb_provenance": {
                "kg": "CauseNet",
                "tier": "precision-1.0" | "full",
                "kg_precision_estimate": 0.83 | 0.65,
                ...
              }
            }

        Tier semantics — IMPORTANT:
        - ``high_confidence`` = hit in precision DB (~83% precision per
          Heindorf 2020). Use for stakes-sensitive verification.
        - ``extracted`` = miss in precision but hit in full (~60-70% est).
          Use as fallback; surface caveat to user.
        - ``not_found`` = absent in both. Honest "no support" — don't
          interpret as "false", just unsupported by this KB.

        Even ``high_confidence`` is NOT ground truth — kg_precision is
        an extraction-pipeline estimate, not epistemic certainty. The
        Themis-side adapter is responsible for surfacing this caveat
        via review_surface.
        """
        c = _normalize_concept(cause)
        e = _normalize_concept(effect)
        cap = max(1, min(evidence_cap, _MAX_EVIDENCE_CAP))

        # Tier 1: precision DB (if available)
        if precision_conn is not None:
            hit = _query_one(precision_conn, c, e, cap)
            if hit is not None:
                return {
                    "verdict": "supported",
                    "confidence_tier": TIER_HIGH_CONFIDENCE,
                    "cause": c,
                    "effect": e,
                    "num_sources": hit["num_sources"],
                    "evidence_sample": hit["evidence_sample"],
                    "kb_provenance": _provenance_block(tier="precision-1.0"),
                }

        # Tier 2: full DB fallback (if available)
        if full_conn is not None:
            hit = _query_one(full_conn, c, e, cap)
            if hit is not None:
                return {
                    "verdict": "supported",
                    "confidence_tier": TIER_EXTRACTED,
                    "cause": c,
                    "effect": e,
                    "num_sources": hit["num_sources"],
                    "evidence_sample": hit["evidence_sample"],
                    "kb_provenance": _provenance_block(tier="full"),
                }

        # Not in either tier
        return {
            "verdict": "not_found",
            "confidence_tier": TIER_NOT_FOUND,
            "cause": c,
            "effect": e,
            "num_sources": 0,
            "evidence_sample": [],
            "kb_provenance": _provenance_block(tier="union"),
        }

    def _aggregate_one(conn, c, e):
        """Internal: aggregate ALL sources of one edge by title /
        path_pattern / source_type. Returns None if edge absent."""
        row = conn.execute(
            "SELECT num_sources FROM edges WHERE cause = ? AND effect = ?",
            (c, e),
        ).fetchone()
        if row is None:
            return None
        title_rows = conn.execute(
            "SELECT source_title AS k, COUNT(*) AS n FROM sources "
            "WHERE cause = ? AND effect = ? "
            "GROUP BY source_title ORDER BY n DESC, k ASC",
            (c, e),
        ).fetchall()
        pattern_rows = conn.execute(
            "SELECT path_pattern AS k, COUNT(*) AS n FROM sources "
            "WHERE cause = ? AND effect = ? "
            "GROUP BY path_pattern ORDER BY n DESC, k ASC",
            (c, e),
        ).fetchall()
        type_rows = conn.execute(
            "SELECT source_type AS k, COUNT(*) AS n FROM sources "
            "WHERE cause = ? AND effect = ? "
            "GROUP BY source_type ORDER BY n DESC, k ASC",
            (c, e),
        ).fetchall()
        unique_pages = conn.execute(
            "SELECT COUNT(DISTINCT source_id) AS n FROM sources "
            "WHERE cause = ? AND effect = ?",
            (c, e),
        ).fetchone()
        return {
            "num_sources": row["num_sources"],
            "unique_source_count": unique_pages["n"] if unique_pages else 0,
            "title_rows": title_rows,
            "pattern_rows": pattern_rows,
            "type_rows": type_rows,
        }

    @app.tool()
    def causenet_query_edge_aggregated(
        cause: str,
        effect: str,
        title_top_n: int = 10,
        pattern_top_n: int = 5,
    ) -> dict:
        """Same edge query as ``causenet_query_edge`` but returns
        AGGREGATE source distributions instead of a sentence sample.

        Surfaces three Top-N distributions over ALL sources of the edge:

        - ``source_title_distribution`` — Wikipedia article titles where
          the (cause, effect) pair was extracted. Critical signal: titles
          encode Wikipedia's word-sense disambiguation work, so a Top-N
          dominated by one cluster ("River bank", "Bank erosion", ...)
          tells the caller this edge is the "river bank" sense, not
          "financial bank". Mixed clusters → genuine homonym ambiguity.
        - ``path_pattern_distribution`` — linguistic patterns ("X causes
          Y", "X leads to Y") that triggered extraction. Single-pattern
          domination is a fragility signal; pattern diversity strengthens.
        - ``source_type_distribution`` — wikipedia_sentence vs.
          clueweb_sentence. Wikipedia is generally cleaner.

        ``unique_source_count`` is the distinct page count (not sentence
        count) — guards against one wordy article inflating num_sources.

        Returns same envelope as query_edge except evidence_sample is
        replaced by the three distributions + unique_source_count.

        Caller (Themis-side adapter) consumes these distributions
        STRUCTURALLY — no LLM judging — to compose the
        ``extensions.kb_verification_report.semantic_alignment`` signal.
        """
        c = _normalize_concept(cause)
        e = _normalize_concept(effect)
        title_n = max(1, min(title_top_n, 50))
        pattern_n = max(1, min(pattern_top_n, 20))

        def _format(agg, tier_label, tier_const):
            return {
                "verdict": "supported",
                "confidence_tier": tier_const,
                "cause": c,
                "effect": e,
                "num_sources": agg["num_sources"],
                "unique_source_count": agg["unique_source_count"],
                "source_title_distribution": [
                    {"title": r["k"], "count": r["n"]}
                    for r in agg["title_rows"][:title_n]
                ],
                "path_pattern_distribution": [
                    {"pattern": r["k"], "count": r["n"]}
                    for r in agg["pattern_rows"][:pattern_n]
                ],
                "source_type_distribution": [
                    {"source_type": r["k"], "count": r["n"]}
                    for r in agg["type_rows"]
                ],
                "kb_provenance": _provenance_block(tier=tier_label),
            }

        if precision_conn is not None:
            agg = _aggregate_one(precision_conn, c, e)
            if agg is not None:
                return _format(agg, "precision-1.0", TIER_HIGH_CONFIDENCE)

        if full_conn is not None:
            agg = _aggregate_one(full_conn, c, e)
            if agg is not None:
                return _format(agg, "full", TIER_EXTRACTED)

        return {
            "verdict": "not_found",
            "confidence_tier": TIER_NOT_FOUND,
            "cause": c,
            "effect": e,
            "num_sources": 0,
            "unique_source_count": 0,
            "source_title_distribution": [],
            "path_pattern_distribution": [],
            "source_type_distribution": [],
            "kb_provenance": _provenance_block(tier="union"),
        }

    def _neighbors_one(conn, c, direction, lim):
        sql = (
            "SELECT effect AS other, num_sources FROM edges "
            "WHERE cause = ? ORDER BY num_sources DESC LIMIT ?"
        ) if direction == "effects_of" else (
            "SELECT cause AS other, num_sources FROM edges "
            "WHERE effect = ? ORDER BY num_sources DESC LIMIT ?"
        )
        return conn.execute(sql, (c, lim)).fetchall()

    @app.tool()
    def causenet_neighbors(
        concept: str,
        direction: str = "effects_of",
        limit: int = _DEFAULT_NEIGHBOR_LIMIT,
    ) -> dict:
        """List neighbors of `concept` in CauseNet across both tiers.

        - ``direction = "effects_of"`` → effects this concept causes
        - ``direction = "causes_of"`` → causes that produce this concept

        Each result entry is labelled ``confidence_tier`` —
        ``high_confidence`` (precision DB) takes precedence over
        ``extracted`` (full DB only) when same edge appears in both.
        Results sorted by num_sources descending within each tier;
        high_confidence neighbors listed first.
        """
        c = _normalize_concept(concept)
        if direction not in ("effects_of", "causes_of"):
            raise ValueError(
                f"direction must be 'effects_of' or 'causes_of', got {direction!r}"
            )
        lim = max(1, min(limit, _MAX_NEIGHBOR_LIMIT))

        seen = set()
        results: list[dict] = []

        if precision_conn is not None:
            for r in _neighbors_one(precision_conn, c, direction, lim):
                other = r["other"]
                if other in seen:
                    continue
                seen.add(other)
                results.append({
                    "concept": other,
                    "num_sources": r["num_sources"],
                    "confidence_tier": TIER_HIGH_CONFIDENCE,
                })

        if full_conn is not None and len(results) < lim:
            remaining = lim - len(results)
            # Over-fetch in case dedupe drops items.
            for r in _neighbors_one(full_conn, c, direction, remaining * 2):
                other = r["other"]
                if other in seen:
                    continue
                seen.add(other)
                results.append({
                    "concept": other,
                    "num_sources": r["num_sources"],
                    "confidence_tier": TIER_EXTRACTED,
                })
                if len(results) >= lim:
                    break

        return {
            "concept": c,
            "direction": direction,
            "results": results,
            "kb_provenance": _provenance_block(tier="union"),
        }

    def _among_one(conn, atoms_list, cap):
        """Internal: find all edges where BOTH endpoints are in atoms_list."""
        # SQLite IN with named placeholders is awkward at scale; build
        # parameterized list manually. atoms_list is already small (typical
        # DAG has < 20 atoms), so no need to chunk.
        if not atoms_list:
            return []
        placeholders = ",".join("?" * len(atoms_list))
        sql = (
            f"SELECT cause, effect, num_sources FROM edges "
            f"WHERE cause IN ({placeholders}) AND effect IN ({placeholders}) "
            f"ORDER BY num_sources DESC LIMIT ?"
        )
        return conn.execute(sql, list(atoms_list) + list(atoms_list) + [cap]).fetchall()

    @app.tool()
    def causenet_neighbors_among(
        atoms: list[str],
        limit: int = 100,
    ) -> dict:
        """Given a set of concept atoms, return all KB edges whose
        BOTH endpoints are in the set.

        Used by the Themis-side adapter to surface "the LLM proposed
        these atoms in its DAG, but it didn't propose these KB-known
        edges between them — should they be added?" suggestions. The
        adapter's caller then decides whether to revise the DAG.

        Precision-tier edges listed first (high_confidence), then full-
        tier edges (extracted). Dedupe by (cause, effect) pair — if an
        edge appears in both tiers, the high_confidence label wins.

        Returns:

            {
              "atoms":   [<normalized atom>, ...],
              "edges":   [
                {"cause": "...", "effect": "...",
                 "num_sources": <int>, "confidence_tier": "..."}, ...
              ],
              "kb_provenance": {...}
            }

        Edge cap = ``limit`` (default 100, max 500) — typical DAG has
        ~10 atoms so the natural upper bound is ~100 directed pairs,
        but most are absent from KB so the actual return is usually
        much smaller.
        """
        normalized_atoms = sorted({_normalize_concept(a) for a in atoms})
        lim = max(1, min(limit, 500))

        seen: set[tuple[str, str]] = set()
        edges: list[dict] = []

        if precision_conn is not None and normalized_atoms:
            for r in _among_one(precision_conn, normalized_atoms, lim):
                key = (r["cause"], r["effect"])
                if key in seen:
                    continue
                seen.add(key)
                edges.append({
                    "cause": r["cause"],
                    "effect": r["effect"],
                    "num_sources": r["num_sources"],
                    "confidence_tier": TIER_HIGH_CONFIDENCE,
                })

        if full_conn is not None and normalized_atoms and len(edges) < lim:
            remaining = lim - len(edges)
            for r in _among_one(full_conn, normalized_atoms, remaining * 2):
                key = (r["cause"], r["effect"])
                if key in seen:
                    continue
                seen.add(key)
                edges.append({
                    "cause": r["cause"],
                    "effect": r["effect"],
                    "num_sources": r["num_sources"],
                    "confidence_tier": TIER_EXTRACTED,
                })
                if len(edges) >= lim:
                    break

        return {
            "atoms": normalized_atoms,
            "edges": edges,
            "kb_provenance": _provenance_block(tier="union"),
        }

    def _search_one(conn, p, lim):
        return conn.execute(
            "SELECT concept, COUNT(*) AS appearances FROM ("
            "  SELECT cause AS concept FROM edges WHERE cause LIKE ? "
            "  UNION ALL "
            "  SELECT effect AS concept FROM edges WHERE effect LIKE ? "
            ") GROUP BY concept ORDER BY appearances DESC LIMIT ?",
            (f"{p}%", f"{p}%", lim),
        ).fetchall()

    @app.tool()
    def causenet_search_concept(prefix: str, limit: int = 20) -> dict:
        """Prefix-match over the concept vocabulary across both tiers.

        Helps the caller find what string CauseNet actually uses for a
        concept (e.g. "asp" → ["aspirin", "asphyxia", ...]). Searches
        cause ∪ effect columns. Each match is labelled with the tier
        it first appeared in; precision-tier matches listed first.
        """
        p = _normalize_concept(prefix)
        lim = max(1, min(limit, _MAX_NEIGHBOR_LIMIT))

        seen = set()
        matches: list[dict] = []

        if precision_conn is not None:
            for r in _search_one(precision_conn, p, lim):
                if r["concept"] in seen:
                    continue
                seen.add(r["concept"])
                matches.append({
                    "concept": r["concept"],
                    "appearances": r["appearances"],
                    "confidence_tier": TIER_HIGH_CONFIDENCE,
                })

        if full_conn is not None and len(matches) < lim:
            remaining = lim - len(matches)
            for r in _search_one(full_conn, p, remaining * 2):
                if r["concept"] in seen:
                    continue
                seen.add(r["concept"])
                matches.append({
                    "concept": r["concept"],
                    "appearances": r["appearances"],
                    "confidence_tier": TIER_EXTRACTED,
                })
                if len(matches) >= lim:
                    break

        return {
            "prefix": p,
            "matches": matches,
            "kb_provenance": _provenance_block(tier="union"),
        }

    return app


def _provenance_block(tier: str = "precision-1.0") -> dict:
    """KB-provenance block stamped on every response. ``tier`` differentiates
    precision-1.0 (~83% precision) from full (~60-70% est.) and "union"
    (when the response spans / failed across both)."""
    precision_estimate = (
        0.83 if tier == "precision-1.0"
        else 0.65 if tier == "full"
        else None  # "union" / not-found: don't claim a precision estimate
    )
    block = {
        "kg": "CauseNet",
        "tier": tier,
        "citation": (
            "Heindorf et al. 2020 — CauseNet: Towards a Causality "
            "Graph Extracted from the Web. CIKM 2020."
        ),
        "data_license": "CC-BY-4.0",
    }
    if precision_estimate is not None:
        block["kg_precision_estimate"] = precision_estimate
    return block


def main() -> None:
    """CLI entry — runs the MCP server over stdio."""
    app = build_server()
    app.run()


if __name__ == "__main__":
    main()
