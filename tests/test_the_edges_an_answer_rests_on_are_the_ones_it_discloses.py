"""A proposed edge the answer rests on is disclosed, and only such an edge.

A gap of kind ``unverified_proposal_edge_on_query_path`` tells a reader that
an edge the answer needs came from a language model or a discovery
algorithm rather than from evidence — the sentence a reader decides from
whether to go and find some. What such a gap says was held to the edge it
cites. Which edges have one was held by nothing.

Measured on the corpus before anything was written. Each of its 21 such
gaps, removed together with the ledger line that copies it — or with the
ledger, when that line was its last — was accepted by every door. A gap
added for an annotated edge that owes none was accepted 18 times of 18: six
proposals no path the answer rests on runs through, and twelve edges whose
source is evidence, told as a language model's.

Which edges owe one is decided from the program, the question, and two
blocks of the answer, so the audit states that once, on its own, and holds
the gaps to it both ways, on the ground graph the answer was reached on.
On every corpus answer the two sets are equal.
Three parts of the statement carry no weight there — an IV route's
instrument, a mediation's mediators, a supporting path walked against an
arrow — and each is witnessed by a program built for it.

Three more have programs of their own because a first version got them
wrong or could have. Read over predicates, a program unrolled in time
has cycles: the one path an answer rests on can pass a predicate twice,
and an edge on no path the answer rests on is reachable — that version
refused an honest answer. And the graph keeps one statement per edge,
while nothing refuses a program that states an edge twice, so an edge
stated once as a proposal is read from every statement behind it.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis import kernel, language
from themis.gaps import DESCRIBED
from themis.verifier.data_gap_rules import (
    _what_the_edge_says,
    verify_proposed_edges_are_disclosed,
)
from themis.verifier.errors import VerificationError
from tests.answer_corpus import the_door_for

SHAPES = json.loads((pathlib.Path(__file__).parent / "fixtures" /
                     "answer_shapes.json").read_text(encoding="utf-8"))
KIND = "unverified_proposal_edge_on_query_path"
_RANK = {"invalidating": 0, "distorting": 1, "confidence_only": 2}


def _gaps(result):
    return (result.get("data_gap_report") or {}).get("gaps") or []


def _ledger(result):
    return (((result.get("extensions") or {})
             .get("assumption_ledger") or {}).get("assumptions") or [])


def _edges_said(statements):
    return [str((s.get("said") or {}).get("edge")) for s in statements or ()
            if isinstance(s, dict) and (s.get("said") or {}).get("edge")]


def _cited(gap):
    return [ref["ref_id"] for ref in gap.get("provenance") or ()
            if ref.get("ref_kind") == "program_site"]


def _without(result, k):
    """``result`` with its k-th gap gone, and every copy of it: the ledger
    line that restates it, or the ledger, when that line was its last."""
    bent = copy.deepcopy(result)
    gap = _gaps(bent).pop(k)
    lines = _ledger(bent)
    lines[:] = [e for e in lines
                if e.get("id") or e.get("layer") != "structural_edge"
                or _edges_said(e.get("claim")) != _edges_said(gap.get("describes"))]
    if not lines and "assumption_ledger" in (bent.get("extensions") or {}):
        del bent["extensions"]["assumption_ledger"]
    return bent


REMOVALS = [pytest.param(name, k, id=f"{name}-{_cited(gap)[0].split(':')[2]}")
            for name in sorted(SHAPES)
            for k, gap in enumerate(_gaps(SHAPES[name]["result"]))
            if gap.get("kind") == KIND]


def _annotated_edges(program):
    for statement in program.get("statements") or ():
        source = (statement.get("annotations") or {}).get("source")
        if statement.get("kind") == "cause" and source is not None:
            yield ((statement["from"]["predicate"], statement["to"]["predicate"]),
                   source)


ADDITIONS = [
    pytest.param(name, ends, source, id=f"{name}-{ends[0]}->{ends[1]}")
    for name in sorted(SHAPES)
    for ends, source in _annotated_edges(SHAPES[name]["program"])
    if f"program:cause:{ends[0]}->{ends[1]}:annotations.source" not in {
        ref for gap in _gaps(SHAPES[name]["result"]) if gap.get("kind") == KIND
        for ref in _cited(gap)}
]

_A_GAP = next(g for p in SHAPES.values() for g in _gaps(p["result"])
              if g.get("kind") == KIND)
_A_LINE = next(e for p in SHAPES.values() for e in _ledger(p["result"])
               if not e.get("id") and e.get("layer") == "structural_edge")


def _with_a_gap_for(result, ends, source):
    """``result`` telling its reader the edge ``ends`` is a proposal it
    rests on, in the words that edge's annotation would give, and with the
    ledger line that copies such a gap, placed where its severity reads."""
    says = _what_the_edge_says("cause", ends, {"source": source})
    bent = copy.deepcopy(result)
    gap = copy.deepcopy(_A_GAP)
    gap["describes"] = says
    gap["provenance"] = [
        {**ref, "ref_id": f"program:cause:{ends[0]}->{ends[1]}:annotations.source"}
        if ref.get("ref_kind") == "program_site" else dict(ref)
        for ref in _A_GAP["provenance"]]
    bent.setdefault("data_gap_report", {}).setdefault("gaps", []).append(gap)
    line = copy.deepcopy(_A_LINE)
    line["claim"] = [language.restate(s, DESCRIBED, "sentence") for s in says]
    line["provenance"] = ("discovery" if source.startswith("discovery:")
                          else "llm_proposal")
    lines = bent.setdefault("extensions", {}).setdefault(
        "assumption_ledger", {"assumptions": []})["assumptions"]
    lines.insert(sum(1 for e in lines
                     if _RANK[e["severity"]] <= _RANK[line["severity"]]), line)
    return bent


# ------------------------------------------------- the fact this rests on


def test_on_every_corpus_answer_the_edges_it_rests_on_are_the_ones_disclosed():
    for name in sorted(SHAPES):
        program, result = SHAPES[name]["program"], SHAPES[name]["result"]
        _ast, prog, _query, ctx = kernel._premises_of(program, result)
        verify_proposed_edges_are_disclosed(result, prog, ctx)


def test_the_measured_sizes():
    assert (len(REMOVALS), len(ADDITIONS)) == (21, 18), (
        len(REMOVALS), len(ADDITIONS))


def test_the_forgeries_start_from_answers_their_door_reads():
    for name in sorted({p.values[0] for p in REMOVALS + ADDITIONS}):
        program, result = SHAPES[name]["program"], SHAPES[name]["result"]
        the_door_for(result)(program, result)


# ------------------------------------------------------------ both ways


@pytest.mark.parametrize(("name", "k"), REMOVALS)
def test_a_disclosure_the_answer_owes_may_not_be_removed(name, k):
    program = SHAPES[name]["program"]
    bent = _without(SHAPES[name]["result"], k)
    with pytest.raises(VerificationError, match="rests on"):
        the_door_for(bent)(program, bent)


@pytest.mark.parametrize(("name", "k"), REMOVALS)
def test_the_ledger_s_own_door_does_not_see_the_removal(name, k):
    """What refuses above is not the ledger's copy of the gap: removed
    together, the two agree."""
    bent = _without(SHAPES[name]["result"], k)
    themis.verify_assumption_ledger(bent)


@pytest.mark.parametrize(("name", "ends", "source"), ADDITIONS)
def test_a_disclosure_the_answer_does_not_owe_may_not_be_added(
        name, ends, source):
    program = SHAPES[name]["program"]
    bent = _with_a_gap_for(SHAPES[name]["result"], ends, source)
    with pytest.raises(VerificationError, match="discloses"):
        the_door_for(bent)(program, bent)


def test_an_answer_owing_a_disclosure_may_not_drop_the_report():
    name = REMOVALS[0].values[0]
    program = SHAPES[name]["program"]
    bent = copy.deepcopy(SHAPES[name]["result"])
    del bent["data_gap_report"]
    _ast, prog, _query, ctx = kernel._premises_of(program, bent)
    with pytest.raises(VerificationError, match="rests on"):
        verify_proposed_edges_are_disclosed(bent, prog, ctx)


# ------------------------------------------ the parts the corpus never needs


def _atom(predicate):
    return {"predicate": predicate, "args": [{"type": "const", "name": "me"}]}


def _proposed_at(name, index):
    program = copy.deepcopy(SHAPES[name]["program"])
    program["statements"][index]["annotations"] = {"source": "llm_proposal"}
    return program, SHAPES[name]["result"]["query_id"]


def _a_fork_with_its_backward_arm_proposed():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *({"kind": "variable", "predicate": p, "domain": [True, False]}
              for p in "xyz"),
            {"kind": "cause", "from": _atom("z"), "to": _atom("x"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "assoc", "left": _atom("x"), "right": _atom("y"),
                "given": []}},
        ],
    }, "q"


WITNESSES = {
    # z -> x is on a directed path only from the instrument the route used.
    "an_iv_route_s_instrument": lambda: _proposed_at("iv_2sls", 4),
    # w -> x is on a directed path only to a mediator the block names.
    "a_mediation_s_mediators": lambda: _proposed_at("mediation_joint_logit", 10),
    # z -> x is on no directed path between x and y; the open path walks it.
    "a_supporting_path_walked_backward": _a_fork_with_its_backward_arm_proposed,
}


@pytest.mark.parametrize("part", sorted(WITNESSES))
def test_each_part_the_corpus_never_needs_has_an_answer_that_needs_it(part):
    program, query_id = WITNESSES[part]()
    result = next(r for r in themis.run(program)["results"]
                  if r.get("query_id") == query_id)
    the_door_for(result)(program, result)
    owed = [k for k, gap in enumerate(_gaps(result)) if gap.get("kind") == KIND]
    assert owed, "the witness has to owe a disclosure for this to ask anything"
    for k in owed:
        bent = _without(result, k)
        with pytest.raises(VerificationError, match="rests on"):
            the_door_for(bent)(program, bent)


# ----------------------------------------- on the graph the answer was reached on


def _at(predicate, t=None):
    atom = {"predicate": predicate, "args": [{"type": "const", "name": "me"}]}
    if t is not None:
        atom["time_index"] = {"kind": "relative", "value": t}
    return atom


def _asked(kind, x, y):
    if kind == "cause":
        return {"kind": "cause", "from": x, "to": y}
    return {"kind": "effect", "given": [],
            "intervention": {"atom": x, "value": True},
            "target": {"atom": y, "value": True}}


def _program(statements, names):
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": p, "domain": [True, False]}
                for p in sorted(names)] + statements}


#: ``b`` a step back moves ``a``, which moves ``b`` now: a loop over the
#: predicates, a chain over the ground atoms. The two differ in the ``b``
#: that moves ``y``; ``a -> b`` is a language model's.
_THROUGH_THE_LOOP = (("x", -1, "b", -1), ("b", -1, "a", -1),
                     ("a", -1, "b", 0), ("b", 0, "y", 0))
_BESIDE_THE_LOOP = (("x", -1, "b", -1), ("b", -1, "a", -1),
                    ("a", -1, "b", 0), ("b", -1, "y", 0))


def _unrolled(edges, kind):
    statements = [
        {"kind": "cause", "from": _at(a, ta), "to": _at(b, tb),
         **({"annotations": {"source": "llm_proposal"}} if (a, b) == ("a", "b")
            else {})}
        for a, ta, b, tb in edges]
    statements.append({"kind": "query", "id": "q", "query": _asked(
        kind, _at("x", -1), _at("y", 0))})
    return _program(statements, {e[0] for e in edges} | {e[2] for e in edges})


def _fifteen_atoms_long():
    edges = (("x", "y"), ("x", "n1"),
             *((f"n{i}", f"n{i + 1}") for i in range(1, 13)), ("n13", "y"))
    statements = [
        {"kind": "cause", "from": _at(a), "to": _at(b),
         **({"annotations": {"source": "llm_proposal"}} if (a, b) == ("n12", "n13")
            else {})}
        for a, b in edges]
    statements.append({"kind": "query", "id": "q", "query": _asked(
        "effect", _at("x"), _at("y"))})
    return _program(statements, {p for edge in edges for p in edge})


def _stated_twice(proposal_first):
    """``smokes -> cancer`` for every unit as a language model's proposal,
    and for this one as evidence. Nothing refuses a program that states an
    edge twice, and the graph keeps one statement per edge."""
    every = {"kind": "cause", "forall": ["X"],
             "from": {"predicate": "smokes", "args": [{"type": "var", "name": "X"}]},
             "to": {"predicate": "cancer", "args": [{"type": "var", "name": "X"}]},
             "annotations": {"source": "llm_proposal"}}
    this_one = {"kind": "cause", "from": _at("smokes"), "to": _at("cancer"),
                "annotations": {"source": "literature_rct"}}
    pair = [every, this_one] if proposal_first else [this_one, every]
    return _program(pair + [{"kind": "query", "id": "q", "query": _asked(
        "cause", _at("smokes"), _at("cancer"))}], {"smokes", "cancer"})


GROUND = {
    # The only path passes b twice; over predicates it is no simple path.
    "a_path_through_one_predicate_twice": lambda: _unrolled(_THROUGH_THE_LOOP, "effect"),
    # Longer than any bound on how deep a walk of paths goes.
    "a_path_fifteen_atoms_long": _fifteen_atoms_long,
    # The graph keeps the evidence; one of the statements is a proposal.
    "an_edge_stated_twice_the_proposal_first": lambda: _stated_twice(True),
    "an_edge_stated_twice_the_evidence_first": lambda: _stated_twice(False),
}


@pytest.mark.parametrize("case", sorted(GROUND))
def test_what_an_answer_rests_on_is_read_on_its_ground_graph(case):
    program = GROUND[case]()
    result = next(r for r in themis.run(program)["results"]
                  if r.get("query_id") == "q")
    the_door_for(result)(program, result)
    owed = [k for k, gap in enumerate(_gaps(result)) if gap.get("kind") == KIND]
    assert owed, "the case has to owe a disclosure for this to ask anything"
    for k in owed:
        bent = _without(result, k)
        with pytest.raises(VerificationError, match="rests on"):
            the_door_for(bent)(program, bent)


@pytest.mark.parametrize("kind", ["cause", "effect"])
def test_an_edge_on_no_ground_path_owes_nothing(kind):
    """The answer a reading over predicates refused. ``a -> b`` lies on no
    path from ``x`` a step back to ``y`` now, and the answer says nothing of
    it; over predicates ``x`` reaches ``a`` and ``b`` reaches ``y``."""
    program = _unrolled(_BESIDE_THE_LOOP, kind)
    result = next(r for r in themis.run(program)["results"]
                  if r.get("query_id") == "q")
    assert not [gap for gap in _gaps(result) if gap.get("kind") == KIND]
    the_door_for(result)(program, result)
