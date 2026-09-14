"""What is said of an edge is read off the statements the answer rests on.

A proposal-edge gap names the edge it discloses by its two predicates, and
so does the confidence slot an edge fills. Several statements can stand
behind that name: an edge stated twice, or a program unrolled in time or
over units, grounding several edges between the same two predicates. Each
says who put its edge there -- a language model, or which algorithm and how
often the edge survived resampling.

The report and its verifier both knew which statements the answer rests on,
and both looked the words up again by the name: the report took the last
statement written under it, the verifier the first, and the confidence
slot the last. Measured before anything was written, on seven programs
built for it: six were refused whatever the report said, and on the
seventh -- PC's a step back, GES's now, PC's two steps back, the answer
resting on GES's alone -- the report told PC's and every door took it.
"""
from __future__ import annotations

import copy

import pytest

import themis
from tests.answer_corpus import the_door_for
from themis import language
from themis.gaps import DESCRIBED
from themis.verifier.errors import VerificationError

KIND = "unverified_proposal_edge_on_query_path"


def _at(predicate, t=None, unit="me"):
    atom = {"predicate": predicate, "args": [{"type": "const", "name": unit}]}
    if t is not None:
        atom["time_index"] = {"kind": "relative", "value": t}
    return atom


def _edge(tail, head, source, confidence=None):
    annotations = {"source": source}
    if confidence is not None:
        annotations["confidence"] = confidence
    return {"kind": "cause", "from": tail, "to": head, "annotations": annotations}


def _asking(edges, x, y, units=("me",)):
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": u} for u in units]},
            "statements": [
                *({"kind": "variable", "predicate": p, "domain": [True, False]}
                  for p in ("x", "y")),
                *edges,
                {"kind": "query", "id": "q", "query": {
                    "kind": "effect", "given": [],
                    "intervention": {"atom": x, "value": True},
                    "target": {"atom": y, "value": True}}}]}


def _now(*edges):
    return _asking(list(edges), _at("x", 0), _at("y", 0))


def _untimed(*edges):
    return _asking(list(edges), _at("x"), _at("y"))


_PROPOSED = ("the_edge_is_an_llm_proposal",)
_PC = ("the_edge_was_learned_by_discovery", "PC", "40%")
_GES = ("the_edge_was_learned_by_discovery", "GES", "90%")

#: A program, and what its gaps owe the reader about ``x -> y``.
PROGRAMS = {
    "stated_twice_proposed_first": (lambda: _untimed(
        _edge(_at("x"), _at("y"), "llm_proposal"),
        _edge(_at("x"), _at("y"), "discovery:pc", 0.4)), [_PROPOSED, _PC]),
    "stated_twice_learned_first": (lambda: _untimed(
        _edge(_at("x"), _at("y"), "discovery:pc", 0.4),
        _edge(_at("x"), _at("y"), "llm_proposal")), [_PROPOSED, _PC]),
    "stated_twice_by_two_algorithms": (lambda: _untimed(
        _edge(_at("x"), _at("y"), "discovery:pc", 0.4),
        _edge(_at("x"), _at("y"), "discovery:ges", 0.9)), [_PC, _GES]),
    "stated_twice_alike": (lambda: _untimed(
        _edge(_at("x"), _at("y"), "discovery:pc", 0.4),
        _edge(_at("x"), _at("y"), "discovery:pc", 0.404)), [_PC]),
    "a_step_back_written_first": (lambda: _now(
        _edge(_at("x", -1), _at("y", 0), "discovery:pc", 0.4),
        _edge(_at("x", 0), _at("y", 0), "discovery:ges", 0.9)), [_GES]),
    "a_step_back_written_last": (lambda: _now(
        _edge(_at("x", 0), _at("y", 0), "discovery:ges", 0.9),
        _edge(_at("x", -1), _at("y", 0), "discovery:pc", 0.4)), [_GES]),
    "now_between_two_steps_back": (lambda: _now(
        _edge(_at("x", -1), _at("y", 0), "discovery:pc", 0.4),
        _edge(_at("x", 0), _at("y", 0), "discovery:ges", 0.9),
        _edge(_at("x", -2), _at("y", 0), "discovery:pc", 0.4)), [_GES]),
    "another_unit_written_last": (lambda: _asking(
        [_edge(_at("x", unit="a"), _at("y", unit="a"), "discovery:ges", 0.9),
         _edge(_at("x", unit="b"), _at("y", unit="b"), "llm_proposal")],
        _at("x", unit="a"), _at("y", unit="a"), units=("a", "b")), [_GES]),
}


def _answer(program):
    return next(r for r in themis.run(program)["results"]
                if r.get("query_id") == "q")


def _edge_gaps(result):
    return [k for k, gap in enumerate(
        (result.get("data_gap_report") or {}).get("gaps") or ())
        if gap.get("kind") == KIND]


def _told(result):
    told = []
    gaps = result["data_gap_report"]["gaps"]
    for k in _edge_gaps(result):
        first, *rest = gaps[k]["describes"]
        words = [first["sentence"]]
        if "algorithm" in first["said"]:
            words.append(first["said"]["algorithm"])
        words.extend(one["said"]["confidence"] for one in rest)
        told.append(tuple(words))
    return sorted(told)


def _restated(describes):
    return [dict(language.restate(e, DESCRIBED, "sentence")) for e in describes]


def _rewritten(result, k, describes):
    """``result`` with its k-th gap saying ``describes`` -- or gone, when
    that is ``None`` -- and the ledger line that copies the gap with it."""
    bent = copy.deepcopy(result)
    gaps = bent["data_gap_report"]["gaps"]
    before = _restated(gaps[k]["describes"])
    lines = bent["extensions"]["assumption_ledger"]["assumptions"]
    line = next(e for e in lines if not e.get("id") and e.get("claim") == before)
    if describes is None:
        del gaps[k]
        lines.remove(line)
        if not lines:
            del bent["extensions"]["assumption_ledger"]
    else:
        gaps[k]["describes"] = describes
        line["claim"] = _restated(describes)
    return bent


@pytest.mark.parametrize("case", sorted(PROGRAMS))
def test_each_reading_the_answer_rests_on_is_told_once(case):
    build, owed = PROGRAMS[case]
    program = build()
    result = _answer(program)
    assert _told(result) == sorted(owed)
    the_door_for(result)(program, result)


@pytest.mark.parametrize("case", sorted(
    case for case, (_build, owed) in PROGRAMS.items() if len(owed) > 1))
def test_no_reading_the_answer_rests_on_may_go_untold(case):
    program = PROGRAMS[case][0]()
    result = _answer(program)
    for k in _edge_gaps(result):
        bent = _rewritten(result, k, None)
        with pytest.raises(VerificationError, match="rests on"):
            the_door_for(bent)(program, bent)


def test_a_reading_of_a_statement_the_answer_does_not_rest_on_may_not_be_told():
    """What the report told before: the words of the statements two steps
    and one step back, which the answer does not rest on. A statement behind
    the name says them, so what refuses is which statements the answer
    rests on."""
    program = PROGRAMS["now_between_two_steps_back"][0]()
    result = _answer(program)
    (k,) = _edge_gaps(result)
    pc = [{"sentence": "the_edge_was_learned_by_discovery",
           "said": {"edge": "x → y", "algorithm": "PC"}},
          {"sentence": "the_edge_survived_this_share_of_resamples",
           "said": {"confidence": "40%"}}]
    bent = _rewritten(result, k, pc)
    with pytest.raises(VerificationError, match="T10-2"):
        the_door_for(bent)(program, bent)


@pytest.mark.parametrize(("case", "weakest"), [
    # Both statements are the one edge; the last written is the stronger.
    ("stated_twice_by_two_algorithms", ("discovery:pc", 0.4)),
    # The last written is two steps back, which the answer does not rest on.
    ("now_between_two_steps_back", ("discovery:ges", 0.9)),
])
def test_an_edge_s_confidence_is_the_weakest_statement_the_answer_rests_on(
        case, weakest):
    result = _answer(PROGRAMS[case][0]())
    assert [(s["source"], s["confidence"])
            for s in result.get("confidence_sources") or ()
            if s["slot_label"] == "edge:x->y"] == [weakest]
