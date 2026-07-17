"""Independent audit of an interactive orientation-resolution session
(2026-07-17, interactive equivalence-class resolution — Phase 3).

The producer (``estimation.orientation_session``) runs the loop: ingest answers,
replay the Phase 1 closure, re-compile the Phase 2 questions, report status. A
session artifact embeds a Phase 1 ``orientation_propagation`` dict and a Phase 2
``orientation_question_set`` dict, so this verifier does not re-transcribe Meek a
fourth time — it delegates:

- ``verify_orientation_propagation`` audits the embedded closure (that ``oriented``
  is exactly the Meek closure of the input CPDAG + constraints, that a
  data-contradicting answer was flagged not applied, that provenance is
  justified);
- ``verify_orientation_questions`` audits the embedded question set (leverage,
  coverage, ranking).

On top of those, this verifier certifies the SESSION GLUE — the parts only Phase 3
introduces — all re-derived independently from the recorded answers:

- **answers → constraints.** The constraints fed to the closure are exactly each
  edge's LATEST directional answer, in the order that latest answer appeared
  (revisions dropped). A producer that applied a stale or extra constraint is
  caught.
- **the embedded artifacts are the session's.** The propagation and question-set
  dicts are over the session's own input CPDAG, derived constraints, and asserted
  adjacencies, and share one ``oriented`` / ``remaining_undirected`` — not some
  other consistent graph smuggled in. (The CI-side adjacency conflicts those
  assertions raise are audited inside the delegated verifiers.)
- **unknown → deferred.** ``deferred`` is exactly the edges whose latest answer
  was "unknown" and that are still undetermined — no forced edge hidden as
  deferred, no unknown silently asked again.
- **source trail.** Every applied directional answer appears once with its source
  and its true entailment (the edges the closure forced from it, from the recorded
  provenance); every non-applied directional answer appears in ``rejected`` with
  the closure's reason. Nothing applied is missing a trail entry; nothing rejected
  is quietly credited.
- **status.** ``open`` iff a conflict is pending or a non-deferred edge is still
  askable; else ``resolved`` iff nothing is undetermined; else ``blocked`` (edges
  remain but all are deferred — needs a human).

Trust boundary: as in Phase 1/2, the input CPDAG is taken as given — this audits
the SESSION mechanics, not the upstream discovery. No producer call.
"""
from __future__ import annotations

from .errors import VerificationError
from .orientation_rules import verify_orientation_propagation
from .orientation_question_rules import verify_orientation_questions


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _pair(a: str, b: str):
    return (a, b) if a <= b else (b, a)


def verify_orientation_session(result: dict) -> None:
    """Independently audit an orientation-session dict (from ``session_to_dict``).

    Returns ``None`` on accept; raises ``VerificationError`` on any structural
    inconsistency, an embedded artifact that fails its own verifier or does not
    match the session, a constraint set that is not the latest-wins projection of
    the answers, a mis-derived deferred set / source trail, or a wrong status.
    """
    _require(isinstance(result, dict), "result must be a dict")
    _require(result.get("kind") == "orientation_session",
             f"not an orientation_session (kind={result.get('kind')!r})")
    nodes = result.get("nodes")
    _require(isinstance(nodes, list) and nodes, "nodes must be a non-empty list")
    _require(len(set(nodes)) == len(nodes), "duplicate node names")
    node_set = set(nodes)

    def _edges(raw, name):
        _require(isinstance(raw, list), f"{name} must be a list")
        out = []
        for e in raw:
            _require(isinstance(e, list) and len(e) == 2
                     and e[0] in node_set and e[1] in node_set,
                     f"{name} entry {e!r} is not a pair of known nodes")
            _require(e[0] != e[1], f"{name} has a self-loop {e!r}")
            out.append((e[0], e[1]))
        return out

    input_directed = _edges(result.get("input_directed"), "input_directed")
    input_undirected = _edges(result.get("input_undirected"), "input_undirected")

    # asserted adjacencies may name unknown nodes (they become CI-side conflicts),
    # so they are not routed through _edges; the embedded verifiers classify them.
    raw_asserted = result.get("asserted_adjacencies", [])
    _require(isinstance(raw_asserted, list), "asserted_adjacencies must be a list")
    asserted = []
    for e in raw_asserted:
        _require(isinstance(e, list) and len(e) == 2,
                 f"asserted_adjacencies entry {e!r} is not a pair")
        _require(e[0] != e[1], f"asserted_adjacencies has a self-loop {e!r}")
        asserted.append((e[0], e[1]))
    asserted_set = {_pair(a, b) for (a, b) in asserted}

    # --- parse + validate answers, re-derive constraints (latest-wins) --------
    raw_answers = result.get("answers")
    _require(isinstance(raw_answers, list), "answers must be a list")
    answers = []
    for a in raw_answers:
        _require(isinstance(a, dict) and "edge" in a, f"ill-formed answer {a!r}")
        edge = a["edge"]
        _require(isinstance(edge, list) and len(edge) == 2
                 and edge[0] in node_set and edge[1] in node_set,
                 f"answer edge {edge!r} not a pair of known nodes")
        e = _pair(edge[0], edge[1])
        direction = a.get("direction")
        if direction is not None:
            _require(isinstance(direction, list) and len(direction) == 2
                     and {direction[0], direction[1]} == {e[0], e[1]},
                     f"direction {direction!r} not an orientation of edge {e!r}")
            direction = (direction[0], direction[1])
        answers.append((e, direction, a.get("source", "unspecified"), a.get("note", "")))

    latest = {}
    for i, (e, d, src, note) in enumerate(answers):
        latest[e] = (i, d, src, note)
    ordered = sorted(latest.items(), key=lambda kv: kv[1][0])
    constraints = [list(d) for (_e, (_i, d, _s, _n)) in ordered if d is not None]

    claimed_constraints = [list(c) for c in _edges(result.get("constraints"), "constraints")]
    _require(constraints == claimed_constraints,
             f"constraints are not the latest-wins projection of the answers: "
             f"recomputed {constraints}, claimed {claimed_constraints}")

    # --- embedded artifacts: each passes its own verifier ---------------------
    prop = result.get("propagation")
    _require(isinstance(prop, dict), "propagation must be a dict")
    verify_orientation_propagation(prop)

    qset = result.get("question_set")
    _require(isinstance(qset, dict), "question_set must be a dict")
    verify_orientation_questions(qset)

    # --- and they are THIS session's (same inputs, one shared CPDAG) ----------
    def _pset(raw):
        return {_pair(a, b) for (a, b) in raw}

    def _dset(raw):
        return {(a, b) for (a, b) in raw}

    _require(_dset(prop["input_directed"]) == _dset(input_directed),
             "embedded propagation is over a different input_directed")
    _require(_pset(prop["input_undirected"]) == _pset(input_undirected),
             "embedded propagation is over a different input_undirected")
    _require([list(c) for c in prop["constraints"]] == constraints,
             "embedded propagation uses different constraints than the answers imply")

    oriented = _dset(prop["oriented"])
    remaining = _pset(prop["remaining_undirected"])
    _require(_dset(qset["oriented"]) == oriented,
             "question set and propagation disagree on the oriented edges")
    _require(_pset(qset["remaining_undirected"]) == remaining,
             "question set and propagation disagree on the remaining edges")
    _require(_pset(prop.get("asserted_adjacencies", [])) == asserted_set,
             "embedded propagation is over different asserted adjacencies")
    _require(_pset(qset.get("asserted_adjacencies", [])) == asserted_set,
             "question set and propagation disagree on the asserted adjacencies")

    # --- unknown → deferred ---------------------------------------------------
    deferred_recompute = {e for (e, (_i, d, _s, _n)) in latest.items()
                          if d is None and e in remaining}
    claimed_deferred = _pset(_edges(result.get("deferred"), "deferred"))
    _require(claimed_deferred == deferred_recompute,
             f"deferred set wrong: recomputed {sorted(deferred_recompute)}, "
             f"claimed {sorted(claimed_deferred)}")

    # --- source trail + rejected ----------------------------------------------
    conflict_pairs = {_pair(c["constraint"][0], c["constraint"][1])
                      for c in prop["conflicts"] if "constraint" in c}
    prov_roots = {(p["from"], p["to"]): {tuple(r) for r in p["roots"]}
                  for p in prop["provenance"]}
    exp_trail, exp_rejected = {}, {}
    for e in sorted(latest):
        _i, d, src, note = latest[e]
        if d is None:
            continue
        if d in oriented and _pair(d[0], d[1]) not in conflict_pairs:
            entails = sorted([list(edge) for edge, roots in prov_roots.items()
                              if d in roots and edge != d])
            exp_trail[tuple(d)] = {"edge": list(e), "direction": [d[0], d[1]],
                                   "source": src, "note": note, "entails": entails}
        else:
            exp_rejected[tuple(d)] = {"edge": list(e), "source": src, "direction": [d[0], d[1]]}

    trail = result.get("source_trail")
    _require(isinstance(trail, list), "source_trail must be a list")
    seen_trail = set()
    for entry in trail:
        _require(isinstance(entry, dict) and "direction" in entry,
                 f"ill-formed source_trail entry {entry!r}")
        key = (entry["direction"][0], entry["direction"][1])
        _require(key in exp_trail, f"source_trail credits a non-applied answer {key}")
        _require(key not in seen_trail, f"duplicate source_trail entry for {key}")
        seen_trail.add(key)
        want = exp_trail[key]
        _require(entry.get("source") == want["source"],
                 f"source_trail source for {key} claimed {entry.get('source')!r} "
                 f"but the answer's source was {want['source']!r}")
        _require(sorted(map(tuple, entry.get("entails", []))) == sorted(map(tuple, want["entails"])),
                 f"source_trail entails for {key} disagree: claimed "
                 f"{entry.get('entails')}, recomputed {want['entails']}")
    _require(seen_trail == set(exp_trail),
             f"source_trail is missing applied answers: {sorted(set(exp_trail) - seen_trail)}")

    rejected = result.get("rejected")
    _require(isinstance(rejected, list), "rejected must be a list")
    seen_rej = {(r["direction"][0], r["direction"][1]) for r in rejected}
    _require(seen_rej == set(exp_rejected),
             f"rejected set disagrees: claimed {sorted(seen_rej)}, "
             f"recomputed {sorted(exp_rejected)}")

    # --- status ---------------------------------------------------------------
    q_questions = qset.get("questions", [])
    askable = any(
        q.get("kind") == "conflict"
        or (q.get("kind") == "orientation"
            and _pair(q["edge"][0], q["edge"][1]) not in claimed_deferred)
        for q in q_questions
    )
    if askable:
        want_status = "open"
    elif not remaining:
        want_status = "resolved"
    else:
        want_status = "blocked"
    _require(result.get("status") == want_status,
             f"status claimed {result.get('status')!r} but recomputed {want_status!r}")
