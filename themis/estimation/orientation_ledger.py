"""Export a resolved orientation session into the query-side provenance vocabulary
(2026-07-17, interactive equivalence-class resolution — Phase 5, ledger wiring).

Phases 1-3 resolve a CPDAG by ingesting answers and propagating the forced
orientations; every oriented edge carries a provenance (the Meek rule that forced
it and the root constraints it rests on), and every applied answer carries a
source (``llm_proposal`` / ``human`` / ``temporal_order`` / …). None of that yet
reaches the place a query discloses its assumptions: the assumption ledger, which
is fed by the ``data_gap_report`` from a program's edge ``annotations.source``
(``UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH`` when an edge is an ``llm_proposal``,
``GRAPH_LEARNED_FROM_DATA`` when the graph came from discovery). A resolved graph
used in a query would silently present LLM-guessed orientations as if verified.

This module bridges the two. It maps each oriented edge to the ``source`` string
the query-side machinery already recognises (``themis.output.data_gap_report.
_is_non_evidence_source``), so the resolved graph, dropped into a program, fires
exactly the right disclosures — with NO change to that machinery. The one piece
that is not a pass-through is the **taint propagation**: an edge Meek FORCED from
an ``llm_proposal`` answer is only as trustworthy as that answer, so it must be
disclosed ``llm_proposal`` too. That is the source trail's blast radius turned
into ledger provenance: an edge is a proposal edge iff ANY root constraint it
rests on is an ``llm_proposal`` answer (weakest-root-wins).

The per-edge source is derived as:
- a data collider (``collider_input``), or an edge Meek-forced with no constraint
  root at all → ``data_source`` (a ``discovery:*`` marker so the query side treats
  it as learned-from-data);
- an edge resting on ≥1 ``llm_proposal`` root → ``"llm_proposal"``;
- an edge resting only on trusted (human / temporal / domain) roots → that root's
  own source if unique, else ``"orientation_multiple"`` — evidence-backed, no gap.

Scope / tradeoffs (stated): the export produces the source-annotated cause
statements (the queryable seam) and the auditable per-edge provenance; assembling
them with variable declarations and a query is the caller's job (they supply the
query anyway). The whole-graph ``GRAPH_LEARNED_FROM_DATA`` caveat is the upstream
discovery run's ``discovery_metadata`` responsibility — here every data-collider
edge is per-edge sourced ``data_source``, which the query side already discloses;
re-synthesising ``discovery_metadata`` is not redone. Trusted-source detail
(human vs temporal vs domain) that does not change gap-firing is collapsed to one
marker only when an edge rests on several different trusted answers. CPDAG setting
(causal sufficiency), inherited from Phase 1. No library dependency.
"""
from __future__ import annotations

from .orientation_session import OrientationSession, session_to_dict

Edge = tuple[str, str]


def _derive_edge_source(rule: str, roots, answer_source: dict, data_source: str) -> str:
    """The ledger ``source`` for one oriented edge (see the module docstring)."""
    if rule == "collider_input" or not roots:
        return data_source
    root_sources = {answer_source.get(r) for r in roots}
    if "llm_proposal" in root_sources:
        return "llm_proposal"
    trusted = {s for s in root_sources if s is not None}
    if len(trusted) == 1:
        return next(iter(trusted))
    return "orientation_multiple"


def orientation_ledger_export(
    session: OrientationSession,
    *,
    data_source: str = "discovery:unspecified",
    subjects=(),
) -> dict:
    """Export a resolved ``OrientationSession`` as a ledger artifact.

    Returns a JSON-serialisable dict embedding the session (so the verifier can
    audit it) plus, for every oriented edge, its derived ledger ``source`` (with
    the ``llm_proposal`` taint propagated through the Meek closure). It also emits
    ``cause_statements`` — source-annotated dict-AST ``cause`` edges the caller can
    drop into a program (with variable declarations + a query) so the existing
    ``data_gap_report`` machinery discloses the LLM-proposed orientations.

    ``data_source`` is the ``discovery:*`` marker put on data-collider edges (the
    algorithm is upstream of this algorithm-agnostic module; pass e.g.
    ``"discovery:pc"`` when known). ``subjects`` are the constant subjects for the
    synthesised atoms (empty → predicate-only atoms).
    """
    if not data_source.startswith("discovery:"):
        raise ValueError(
            f"data_source must start with 'discovery:' so the query side treats "
            f"data-collider edges as learned-from-data; got {data_source!r}")

    sd = session_to_dict(session)
    prop = sd["propagation"]
    answer_source = {tuple(e["direction"]): e["source"] for e in sd["source_trail"]}

    edges = []
    proposal_edges = []
    for p in prop["provenance"]:
        edge = (p["from"], p["to"])
        roots = [tuple(r) for r in p["roots"]]
        source = _derive_edge_source(p["rule"], roots, answer_source, data_source)
        edges.append({
            "edge": [edge[0], edge[1]], "rule": p["rule"],
            "roots": [list(r) for r in roots], "source": source,
        })
        if source == "llm_proposal":
            proposal_edges.append([edge[0], edge[1]])

    args = [{"type": "const", "name": s} for s in subjects]
    cause_statements = [
        {
            "kind": "cause",
            "from": {"predicate": e["edge"][0], "args": args},
            "to": {"predicate": e["edge"][1], "args": args},
            "annotations": {"source": e["source"]},
        }
        for e in edges
    ]

    return {
        "kind": "orientation_ledger_export",
        "session": sd,
        "data_source": data_source,
        "edges": edges,
        "proposal_edges": sorted(proposal_edges),
        "graph_learned_from_data": any(
            p["rule"] == "collider_input" for p in prop["provenance"]),
        "cause_statements": cause_statements,
    }
