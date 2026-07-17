"""Independent audit of an orientation-session ledger export
(2026-07-17, interactive equivalence-class resolution — Phase 5, ledger wiring).

The producer (``estimation.orientation_ledger.orientation_ledger_export``) maps a
resolved session's oriented edges to the query-side provenance vocabulary, with
the ``llm_proposal`` taint propagated through the Meek closure. This verifier:

- delegates the embedded session to ``verify_orientation_session`` — so the
  provenance and source trail it re-derives from are themselves certified (a
  forged provenance can't smuggle a wrong source past this step);
- independently re-derives every edge's ledger source from that provenance
  (rule + roots) and the source trail (answer → source), with a SECOND
  transcription of the taint rule, and checks the claimed ``edges``,
  ``proposal_edges``, ``cause_statements`` sources, and ``graph_learned_from_data``
  match exactly. Under-disclosure (an edge resting on an ``llm_proposal`` answer
  sourced as anything else) is the failure mode this exists to catch.

Trust boundary: given the (certified) session, the ledger classification is
provably the taint-propagated one; this does not re-audit the upstream discovery
that produced the CPDAG (Phase 1's boundary).
"""
from __future__ import annotations

from .errors import VerificationError
from .orientation_session_rules import verify_orientation_session


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _derive_edge_source(rule, roots, answer_source, data_source):
    """Second transcription of the producer's per-edge source derivation."""
    if rule == "collider_input" or not roots:
        return data_source
    root_sources = {answer_source.get(r) for r in roots}
    if "llm_proposal" in root_sources:
        return "llm_proposal"
    trusted = {s for s in root_sources if s is not None}
    if len(trusted) == 1:
        return next(iter(trusted))
    return "orientation_multiple"


def verify_orientation_ledger_export(result: dict) -> None:
    """Independently audit an ``orientation_ledger_export`` dict.

    Returns ``None`` on accept; raises ``VerificationError`` on a failed embedded
    session, a data source that is not a ``discovery:*`` marker, or any edge /
    proposal-edge / cause-statement source that disagrees with the taint-propagated
    recomputation.
    """
    _require(isinstance(result, dict), "result must be a dict")
    _require(result.get("kind") == "orientation_ledger_export",
             f"not an orientation_ledger_export (kind={result.get('kind')!r})")

    data_source = result.get("data_source")
    _require(isinstance(data_source, str) and data_source.startswith("discovery:"),
             f"data_source must be a 'discovery:*' marker, got {data_source!r}")

    session = result.get("session")
    _require(isinstance(session, dict), "session must be a dict")
    verify_orientation_session(session)          # delegate — certify the provenance

    prop = session["propagation"]
    answer_source = {tuple(e["direction"]): e["source"]
                     for e in session["source_trail"]}

    # independently re-derive the ledger source of every oriented edge
    expected: dict[tuple, dict] = {}
    for p in prop["provenance"]:
        edge = (p["from"], p["to"])
        roots = [tuple(r) for r in p["roots"]]
        expected[edge] = {
            "rule": p["rule"],
            "roots": sorted(list(r) for r in roots),
            "source": _derive_edge_source(p["rule"], roots, answer_source, data_source),
        }

    # --- edges: one per oriented edge, correct rule / roots / source ----------
    claimed_edges = result.get("edges")
    _require(isinstance(claimed_edges, list), "edges must be a list")
    seen = set()
    for e in claimed_edges:
        _require(isinstance(e, dict) and "edge" in e, f"ill-formed edge entry {e!r}")
        key = (e["edge"][0], e["edge"][1])
        _require(key in expected, f"edge {key!r} is not an oriented edge of the session")
        _require(key not in seen, f"duplicate edge entry {key!r}")
        seen.add(key)
        want = expected[key]
        _require(e.get("rule") == want["rule"],
                 f"edge {key!r} rule claimed {e.get('rule')!r}, expected {want['rule']!r}")
        _require(sorted(e.get("roots", [])) == want["roots"],
                 f"edge {key!r} roots disagree: claimed {e.get('roots')}, "
                 f"expected {want['roots']}")
        _require(e.get("source") == want["source"],
                 f"edge {key!r} source claimed {e.get('source')!r}, expected "
                 f"{want['source']!r} (taint-propagated)")
    _require(seen == set(expected),
             f"edges do not cover the oriented edges one-to-one: missing "
             f"{sorted(set(expected) - seen)}")

    # --- proposal_edges: exactly the llm_proposal-sourced edges ---------------
    exp_proposal = sorted([list(k) for k, v in expected.items()
                           if v["source"] == "llm_proposal"])
    claimed_proposal = sorted(result.get("proposal_edges", []))
    _require(claimed_proposal == exp_proposal,
             f"proposal_edges disagree with the recomputation: claimed "
             f"{claimed_proposal}, expected {exp_proposal}")

    # --- graph_learned_from_data ---------------------------------------------
    exp_learned = any(v["rule"] == "collider_input" for v in expected.values())
    _require(result.get("graph_learned_from_data") == exp_learned,
             f"graph_learned_from_data claimed {result.get('graph_learned_from_data')!r}, "
             f"expected {exp_learned!r}")

    # --- cause_statements: source-annotated, sources match the edges ----------
    stmts = result.get("cause_statements")
    _require(isinstance(stmts, list), "cause_statements must be a list")
    _require(len(stmts) == len(expected),
             f"cause_statements count {len(stmts)} != oriented-edge count {len(expected)}")
    stmt_seen = set()
    for st in stmts:
        _require(isinstance(st, dict) and st.get("kind") == "cause",
                 f"ill-formed cause statement {st!r}")
        frm = st["from"]["predicate"]
        to = st["to"]["predicate"]
        key = (frm, to)
        _require(key in expected, f"cause statement on non-oriented edge {key!r}")
        _require(key not in stmt_seen, f"duplicate cause statement {key!r}")
        stmt_seen.add(key)
        ann = st.get("annotations") or {}
        _require(ann.get("source") == expected[key]["source"],
                 f"cause statement {key!r} source {ann.get('source')!r} != "
                 f"ledger source {expected[key]['source']!r}")
    _require(stmt_seen == set(expected),
             "cause_statements do not cover the oriented edges one-to-one")
