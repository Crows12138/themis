"""A joint answer records the estimand each corner of its box was read off.

A joint general-ID estimate answers do(a, b, ...) with one number per corner
of the treatment box, each read off the estimand the set-valued ID algorithm
derives for that corner. It recorded the numbers and not the estimands, so
all the verifier could ask was whether the producer's engine,
``c_factor.identify_via_tian_joint``, calls the treatment set identifiable.
Measured before this file existed: with that engine blind to added
bidirected edges when a verifier frame asks, the corpus answer passed the
doors on its program with a bidirected edge between each treatment and its
mediator, where the engine asked honestly identifies nothing.

The probe could not have been asked either: it intervened on one variable,
and a corner sets every treatment at once. So the probe takes an
intervention as one argument, the answer records each corner's assignment
and estimand, and the verifier compares each estimand with the engine's and
then puts it to the probe under the whole assignment.
"""
from __future__ import annotations

import copy
import dataclasses
import itertools
import json
import pathlib
import sys

import networkx as nx
import pytest

import themis.verifier.rules as verifier_rules
from themis.runtime import c_factor
from themis.types import (
    Atom, ConstTerm, FractionExpr, ProbabilityRefExpr, ProductExpr, SumExpr, ValuedAtom,
)
from themis.verifier import semantic_probe as sp
from themis.verifier.errors import VerificationError
from tests.answer_corpus import the_door_for

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads((ROOT / "tests" / "fixtures" / "answer_shapes.json")
                    .read_text(encoding="utf-8"))
VERIFIER = str(pathlib.Path(verifier_rules.__file__).parent)
TERMINAL = "numeric_joint_general_id_estimate"
REFUSED = r"does not compute it in models consistent with the graph"
ROWS = sorted(
    name for name, pair in SHAPES.items()
    if TERMINAL in {step["rule"] for step in
                    (pair["result"].get("derivation") or {}).get("steps") or ()})


def _A(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _terminal(result):
    return next(step for step in result["derivation"]["steps"] if step["rule"] == TERMINAL)


def _recorded(result):
    return _terminal(result)["inputs"]["corner_estimands"]["items"]


def _treatments(program):
    query = next(s for s in program["statements"] if s.get("kind") == "query")["query"]
    return [query["intervention"]["atom"],
            *(iv["atom"] for iv in query.get("extra_interventions") or ())]


def _key(atom):
    return atom["predicate"], json.dumps(atom.get("args") or [], sort_keys=True)


def _asked_by_the_verifier(depth=2):
    return sys._getframe(depth).f_code.co_filename.startswith(VERIFIER)


def test_the_joint_general_id_answer_in_the_corpus_is_asked():
    assert len(ROWS) == 1, ROWS


@pytest.mark.parametrize("name", ROWS)
def test_every_corner_is_recorded_and_probed_under_its_whole_assignment(name, monkeypatch):
    pair = SHAPES[name]
    real = verifier_rules.probe_intervention_formula
    asked = []

    def probe(*args, **kwargs):
        verdict = real(*args, **kwargs)
        asked.append((len(kwargs["intervention"]), verdict.status))
        return verdict

    monkeypatch.setattr(verifier_rules, "probe_intervention_formula", probe)
    the_door_for(pair["result"])(copy.deepcopy(pair["program"]), copy.deepcopy(pair["result"]))
    k = len(_treatments(pair["program"]))
    assert len(pair["result"]["numeric_estimate"]["corner_risks"]) == 2 ** k
    assert len(_recorded(pair["result"])) == 2 ** k
    assert asked == [(k, "match")] * 2 ** k, asked


def _latent_beside_each_child(program):
    """The program with a bidirected edge between every treatment and each child
    it does not already share one with, and the predicate pairs added."""
    forged = copy.deepcopy(program)
    arcs = {frozenset((_key(s["left"]), _key(s["right"])))
            for s in program["statements"] if s.get("kind") == "bidirected"}
    added = set()
    for t in _treatments(program):
        for s in program["statements"]:
            if s.get("kind") != "cause" or _key(s["from"]) != _key(t):
                continue
            if frozenset((_key(t), _key(s["to"]))) in arcs:
                continue
            forged["statements"].append({"kind": "bidirected", "left": copy.deepcopy(t),
                                         "right": copy.deepcopy(s["to"])})
            added.add(frozenset((t["predicate"], s["to"]["predicate"])))
    assert added
    return forged, added


@pytest.mark.parametrize("name", ROWS)
def test_an_engine_blind_to_a_hedge_moves_no_verdict(name, monkeypatch):
    pair = SHAPES[name]
    program, honest = pair["program"], pair["result"]
    forged, added = _latent_beside_each_child(program)
    door = the_door_for(honest)
    with pytest.raises(VerificationError, match="identifiable=False"):
        door(copy.deepcopy(forged), copy.deepcopy(honest))

    real = c_factor.identify_via_tian_joint

    def engine(graph, bidirected, *args, **kwargs):
        if _asked_by_the_verifier():
            bidirected = frozenset(p for p in bidirected
                                   if frozenset(a.predicate for a in p) not in added)
        return real(graph, bidirected, *args, **kwargs)

    monkeypatch.setattr(c_factor, "identify_via_tian_joint", engine)
    door(copy.deepcopy(program), copy.deepcopy(honest))
    with pytest.raises(VerificationError, match=REFUSED):
        door(copy.deepcopy(forged), copy.deepcopy(honest))


def _flip_recorded(node, x):
    """Every boolean bound to ``x`` in a serialized formula, flipped."""
    if isinstance(node, list):
        return [_flip_recorded(v, x) for v in node]
    if not isinstance(node, dict):
        return node
    out = {k: _flip_recorded(v, x) for k, v in node.items()}
    if (out.get("kind") == "valued_atom"
            and (out.get("atom") or {}).get("predicate") == x
            and isinstance(out.get("value"), bool)):
        out["value"] = not out["value"]
    return out


def _flip(formula, x):
    """The same flip on a formula object."""
    if isinstance(formula, ProbabilityRefExpr):
        def one(va):
            if va.atom.predicate == x and isinstance(va.value, bool):
                return ValuedAtom(atom=va.atom, value=not va.value)
            return va
        return dataclasses.replace(formula, target=one(formula.target),
                                   given=tuple(one(g) for g in formula.given))
    if isinstance(formula, ProductExpr):
        return dataclasses.replace(formula, terms=tuple(_flip(t, x) for t in formula.terms))
    if isinstance(formula, SumExpr):
        return dataclasses.replace(formula, body=_flip(formula.body, x))
    if isinstance(formula, FractionExpr):
        return dataclasses.replace(formula, numerator=_flip(formula.numerator, x),
                                   denominator=_flip(formula.denominator, x))
    return formula


@pytest.mark.parametrize("name", ROWS)
def test_an_engine_writing_another_corner_s_estimand_moves_no_verdict(name, monkeypatch):
    pair = SHAPES[name]
    program, honest = pair["program"], pair["result"]
    x = _treatments(program)[0]["predicate"]
    forged = copy.deepcopy(honest)
    for entry in _recorded(forged):
        entry["items"]["estimand"] = _flip_recorded(entry["items"]["estimand"], x)
    assert forged != honest
    door = the_door_for(honest)
    with pytest.raises(VerificationError, match="not the one"):
        door(copy.deepcopy(program), copy.deepcopy(forged))

    real = c_factor.identify_via_tian_joint

    def engine(graph, bidirected, *args, **kwargs):
        derived = real(graph, bidirected, *args, **kwargs)
        if _asked_by_the_verifier() and derived.formula is not None:
            derived = dataclasses.replace(derived, formula=_flip(derived.formula, x))
        return derived

    monkeypatch.setattr(c_factor, "identify_via_tian_joint", engine)
    with pytest.raises(VerificationError, match=REFUSED):
        door(copy.deepcopy(program), copy.deepcopy(forged))


@pytest.mark.parametrize("name", ROWS)
def test_a_corner_the_interaction_sums_over_cannot_go_unrecorded(name):
    pair = SHAPES[name]
    program, honest = pair["program"], pair["result"]
    door = the_door_for(honest)
    short = copy.deepcopy(honest)
    _recorded(short).pop()
    with pytest.raises(VerificationError, match="sum over all"):
        door(copy.deepcopy(program), short)
    unrecorded = copy.deepcopy(honest)
    del _terminal(unrecorded)["inputs"]["corner_estimands"]
    with pytest.raises(VerificationError, match="must record the estimand"):
        door(copy.deepcopy(program), unrecorded)


@pytest.mark.parametrize("name", ROWS)
def test_a_corner_sets_the_question_s_treatments(name):
    pair = SHAPES[name]
    program, honest = pair["program"], pair["result"]
    forged = copy.deepcopy(honest)
    _recorded(forged)[0]["items"]["do"]["items"][-1]["atom"]["predicate"] = "y"
    with pytest.raises(VerificationError, match="set each of the question's treatments once"):
        the_door_for(honest)(copy.deepcopy(program), forged)


def test_the_probe_tells_one_corner_s_estimand_from_another_s():
    """The double front door: each corner's estimand matches under its own
    assignment and under no other corner of the box."""
    a, b, ma, mb, y = (_A(p) for p in ("a", "b", "ma", "mb", "y"))
    graph = nx.DiGraph([(a, ma), (ma, y), (b, mb), (mb, y)])
    bidirected = frozenset({frozenset({a, y}), frozenset({b, y})})
    box = list(itertools.product((True, False), repeat=2))
    for mask in box:
        derived = c_factor.identify_via_tian_joint(graph, bidirected, dict(zip((a, b), mask)), y)
        assert derived.identifiable
        for other in box:
            verdict = sp.probe_intervention_formula(
                graph, bidirected, intervention=dict(zip((a, b), other)), y=y,
                given=(), formula=derived.formula)
            assert verdict.status == ("match" if other == mask else "mismatch"), (
                mask, other, verdict)
