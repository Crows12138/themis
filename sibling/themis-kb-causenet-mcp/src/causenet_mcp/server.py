"""FastMCP server exposing CauseNet (Heindorf et al. 2020).

Tools (JSON in / JSON out, parallel to Themis's own MCP surface):

- ``causenet_query_edge(cause, effect)`` — does CauseNet support
  cause → effect? Returns verdict + supporting evidence count + sample
  Wikipedia sentences.
- ``causenet_neighbors(concept, direction, limit)`` — list effects of
  concept (direction="effects_of") OR causes of concept ("causes_of").
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
DEFAULT_DB_PATH = PACKAGE_ROOT / "data" / "causenet.sqlite"


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


def _get_conn(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(
            f"CauseNet SQLite not found at {db_path}. "
            f"Run `python scripts/build_db.py` to build it from "
            f"data/causenet-precision.jsonl.bz2."
        )
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def build_server(db_path: Path | None = None):
    """Construct FastMCP server. Same pattern as themis/mcp/server.py
    (function-scoped instantiation so tests can spin up isolated apps)."""
    from mcp.server.fastmcp import FastMCP

    db_path = db_path or DEFAULT_DB_PATH
    conn = _get_conn(db_path)

    app = FastMCP("causenet")

    @app.tool()
    def causenet_query_edge(
        cause: str,
        effect: str,
        evidence_cap: int = _DEFAULT_EVIDENCE_CAP,
    ) -> dict:
        """Check whether CauseNet supports a `cause → effect` edge.

        Returns a verdict dict for the Themis-side adapter to consume:

            {
              "verdict": "supported" | "not_found",
              "cause": "<normalized cause>",
              "effect": "<normalized effect>",
              "num_sources": <int>,
              "evidence_sample": [
                {"source_type": ..., "title": ..., "page_id": ...,
                 "sentence": ..., "path_pattern": ...},
                ...  (up to evidence_cap)
              ],
              "kb_provenance": {
                "kg": "CauseNet",
                "version": "precision-1.0 (CIKM 2020)",
                "kg_precision_estimate": 0.83
              }
            }

        Semantic note: "supported" does NOT mean "definitely true". It
        means "this edge was extracted from web/Wikipedia by Heindorf
        et al. 2020's pipeline, which has ~83% extraction precision."
        The Themis-side adapter is responsible for surfacing this
        caveat to the end user via review_surface.
        """
        c = _normalize_concept(cause)
        e = _normalize_concept(effect)
        cap = max(1, min(evidence_cap, _MAX_EVIDENCE_CAP))

        row = conn.execute(
            "SELECT num_sources FROM edges WHERE cause = ? AND effect = ?",
            (c, e),
        ).fetchone()

        if row is None:
            return {
                "verdict": "not_found",
                "cause": c,
                "effect": e,
                "num_sources": 0,
                "evidence_sample": [],
                "kb_provenance": _provenance_block(),
            }

        evidence_rows = conn.execute(
            "SELECT source_type, source_title, source_id, sentence, path_pattern "
            "FROM sources WHERE cause = ? AND effect = ? LIMIT ?",
            (c, e, cap),
        ).fetchall()
        evidence = [
            {
                "source_type": r["source_type"],
                "title": r["source_title"],
                "page_id": r["source_id"],
                "sentence": r["sentence"],
                "path_pattern": r["path_pattern"],
            }
            for r in evidence_rows
        ]

        return {
            "verdict": "supported",
            "cause": c,
            "effect": e,
            "num_sources": row["num_sources"],
            "evidence_sample": evidence,
            "kb_provenance": _provenance_block(),
        }

    @app.tool()
    def causenet_neighbors(
        concept: str,
        direction: str = "effects_of",
        limit: int = _DEFAULT_NEIGHBOR_LIMIT,
    ) -> dict:
        """List neighbors of `concept` in CauseNet.

        - ``direction = "effects_of"`` → returns effects that this
          concept is recorded as a cause of (downstream)
        - ``direction = "causes_of"`` → returns causes that this
          concept is recorded as an effect of (upstream)

        Results sorted by num_sources descending — most-supported
        relations first. Useful for the LLM agent to discover plausible
        DAG edges before constructing a Themis program.
        """
        c = _normalize_concept(concept)
        if direction not in ("effects_of", "causes_of"):
            raise ValueError(
                f"direction must be 'effects_of' or 'causes_of', got {direction!r}"
            )
        lim = max(1, min(limit, _MAX_NEIGHBOR_LIMIT))

        if direction == "effects_of":
            rows = conn.execute(
                "SELECT effect AS other, num_sources FROM edges "
                "WHERE cause = ? ORDER BY num_sources DESC LIMIT ?",
                (c, lim),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT cause AS other, num_sources FROM edges "
                "WHERE effect = ? ORDER BY num_sources DESC LIMIT ?",
                (c, lim),
            ).fetchall()

        return {
            "concept": c,
            "direction": direction,
            "results": [
                {"concept": r["other"], "num_sources": r["num_sources"]}
                for r in rows
            ],
            "kb_provenance": _provenance_block(),
        }

    @app.tool()
    def causenet_search_concept(prefix: str, limit: int = 20) -> dict:
        """Prefix-match over the concept vocabulary. Helps the caller
        find what string CauseNet actually uses for a fuzzy match
        (e.g. "asp" → ["aspirin", "asphyxia", ...]).

        Searches the union of cause + effect columns so concepts that
        only ever appear as cause OR only as effect are still found.
        """
        p = _normalize_concept(prefix)
        lim = max(1, min(limit, _MAX_NEIGHBOR_LIMIT))
        rows = conn.execute(
            "SELECT concept, COUNT(*) AS appearances FROM ("
            "  SELECT cause AS concept FROM edges WHERE cause LIKE ? "
            "  UNION ALL "
            "  SELECT effect AS concept FROM edges WHERE effect LIKE ? "
            ") GROUP BY concept ORDER BY appearances DESC LIMIT ?",
            (f"{p}%", f"{p}%", lim),
        ).fetchall()
        return {
            "prefix": p,
            "matches": [
                {"concept": r["concept"], "appearances": r["appearances"]}
                for r in rows
            ],
            "kb_provenance": _provenance_block(),
        }

    return app


def _provenance_block() -> dict:
    return {
        "kg": "CauseNet",
        "version": "precision-1.0",
        "citation": (
            "Heindorf et al. 2020 — CauseNet: Towards a Causality "
            "Graph Extracted from the Web. CIKM 2020."
        ),
        "kg_precision_estimate": 0.83,
        "data_license": "CC-BY-4.0",
    }


def main() -> None:
    """CLI entry — runs the MCP server over stdio."""
    app = build_server()
    app.run()


if __name__ == "__main__":
    main()
