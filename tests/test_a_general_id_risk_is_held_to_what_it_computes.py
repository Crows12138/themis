"""A general-ID risk estimand is held to what it computes, not only to the engine.

Numeric probabilities of causation and the numeric counterfactual cell can take
their interventional risks from the general ID algorithm (provenance
``general_id_plug_in``), and they record the estimand each arm was evaluated
from. The verifier compared that estimand with the one
``c_factor.identify_via_tian`` derives on the question's graph: the producer's
engine, re-run, which agrees with the producer by construction. Measured before
this file existed, on both such answers in the corpus, with the engine made
blind to added bidirected edges when a verifier frame asks: each answer passed
the doors on its program with a bidirected edge between the treatment and each
of its children, where the engine asked honestly identifies neither arm.

Every other answer carrying an identified formula already puts it to the
semantic probe, which samples models consistent with the graph and computes the
interventional value in each by intervening on the model. These two now do as
well, after the comparison with the engine.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import pathlib
import random
import sys

import networkx as nx
import pytest

import themis.verifier.rules as verifier_rules
from themis.runtime import c_factor
from themis.types import (
    Atom, ConstTerm, FractionExpr, ProbabilityRefExpr, ProductExpr, SumExpr, ValuedAtom,
)
from themis.verifier.errors import VerificationError
from tests.answer_corpus import the_door_for

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads((ROOT / "tests" / "fixtures" / "answer_shapes.json")
                    .read_text(encoding="utf-8"))
VERIFIER = str(pathlib.Path(verifier_rules.__file__).parent)
FORMULA_KEYS = ("risk_formula", "risk_formula_treated", "risk_formula_control")
REFUSED = r"does not compute it in models consistent with the graph"


def _rows():
    return sorted(
        name for name, pair in SHAPES.items()
        if any(step["inputs"].get("interventional_risk_provenance") == "general_id_plug_in"
               for step in (pair["result"].get("derivation") or {}).get("steps") or ()))


def _treatment(program):
    query = next(s for s in program["statements"] if s.get("kind") == "query")["query"]
    slot = query.get("cause") or query["observed"]
    return slot.get("atom", slot)


def _key(atom):
    return atom["predicate"], json.dumps(atom.get("args") or [], sort_keys=True)


def _latent_beside_each_child(program):
    """The program with a bidirected edge between the treatment and each child
    it does not already share one with, and the predicate pairs added."""
    t = _treatment(program)
    forged = copy.deepcopy(program)
    arcs = {frozenset((_key(s["left"]), _key(s["right"])))
            for s in program["statements"] if s.get("kind") == "bidirected"}
    added = set()
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


def _asked_by_the_verifier(depth=2):
    return sys._getframe(depth).f_code.co_filename.startswith(VERIFIER)


def test_both_general_id_risk_answers_in_the_corpus_are_asked():
    assert len(_rows()) == 2, _rows()


@pytest.mark.parametrize("name", _rows())
def test_each_recorded_estimand_is_put_to_the_probe_and_matches(name, monkeypatch):
    """Without this the tests below could pass on a probe that never ran."""
    pair = SHAPES[name]
    real = verifier_rules.probe_intervention_formula
    asked = []

    def probe(*args, **kwargs):
        verdict = real(*args, **kwargs)
        asked.append(verdict.status)
        return verdict

    monkeypatch.setattr(verifier_rules, "probe_intervention_formula", probe)
    the_door_for(pair["result"])(copy.deepcopy(pair["program"]), copy.deepcopy(pair["result"]))
    recorded = [key for step in pair["result"]["derivation"]["steps"]
                for key in FORMULA_KEYS if step["inputs"].get(key) is not None]
    assert recorded and asked == ["match"] * len(recorded), (recorded, asked)


@pytest.mark.parametrize("name", _rows())
def test_an_engine_blind_to_a_hedge_moves_no_verdict(name, monkeypatch):
    pair = SHAPES[name]
    program, honest = pair["program"], pair["result"]
    forged, added = _latent_beside_each_child(program)
    door = the_door_for(honest)
    with pytest.raises(VerificationError, match="does not point-identify"):
        door(copy.deepcopy(forged), copy.deepcopy(honest))

    real = c_factor.identify_via_tian

    def engine(graph, bidirected, *args, **kwargs):
        if _asked_by_the_verifier():
            bidirected = frozenset(p for p in bidirected
                                   if frozenset(a.predicate for a in p) not in added)
        return real(graph, bidirected, *args, **kwargs)

    monkeypatch.setattr(c_factor, "identify_via_tian", engine)
    door(copy.deepcopy(program), copy.deepcopy(honest))
    with pytest.raises(VerificationError, match=REFUSED):
        door(copy.deepcopy(forged), copy.deepcopy(honest))


def _flip_recorded(node, x):
    """Every boolean bound to the treatment in a serialized formula, flipped."""
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


@pytest.mark.parametrize("name", _rows())
def test_an_engine_writing_the_other_arm_s_estimand_moves_no_verdict(name, monkeypatch):
    pair = SHAPES[name]
    program, honest = pair["program"], pair["result"]
    x = _treatment(program)["predicate"]
    forged = copy.deepcopy(honest)
    for step in forged["derivation"]["steps"]:
        for key in FORMULA_KEYS:
            if step["inputs"].get(key) is not None:
                step["inputs"][key] = _flip_recorded(step["inputs"][key], x)
    assert forged != honest
    door = the_door_for(honest)
    with pytest.raises(VerificationError, match="not the one"):
        door(copy.deepcopy(program), copy.deepcopy(forged))

    real = c_factor.identify_via_tian

    def engine(graph, bidirected, *args, **kwargs):
        derived = real(graph, bidirected, *args, **kwargs)
        if _asked_by_the_verifier() and derived.formula is not None:
            derived = dataclasses.replace(derived, formula=_flip(derived.formula, x))
        return derived

    monkeypatch.setattr(c_factor, "identify_via_tian", engine)
    with pytest.raises(VerificationError, match=REFUSED):
        door(copy.deepcopy(program), copy.deepcopy(forged))


def test_the_probe_refuses_no_estimand_the_engine_derives_on_random_graphs():
    """The honest side, off the corpus: wherever the producer identifies an arm,
    the probe agrees with its estimand, and does so by matching rather than by
    falling silent."""
    from themis.estimation.general_id import identify_arm_risk_formula
    from themis.refusals import EstimatorFailure
    from themis.verifier.semantic_probe import probe_identify_formula

    rng = random.Random(659)
    nodes = [Atom(predicate=p, args=(ConstTerm(name="me"),)) for p in "abcde"]
    seen = {}
    for _ in range(300):
        order = rng.sample(nodes, len(nodes))
        graph = nx.DiGraph()
        graph.add_nodes_from(order)
        graph.add_edges_from((u, v) for i, u in enumerate(order)
                             for v in order[i + 1:] if rng.random() < 0.4)
        bidirected = frozenset(frozenset((u, v)) for i, u in enumerate(order)
                               for v in order[i + 1:] if rng.random() < 0.2)
        i, j = sorted(rng.sample(range(len(order)), 2))
        x, y = order[i], order[j]
        for arm in (True, False):
            try:
                formula = identify_arm_risk_formula(
                    graph, bidirected, treatment_atom=x, outcome_atom=y,
                    arm_value=arm, outcome_value=True)
            except EstimatorFailure:
                seen["unidentified"] = seen.get("unidentified", 0) + 1
                continue
            probe = probe_identify_formula(
                graph, bidirected, x=x, x_value=arm, y=y, given=(),
                formula=formula, y_values=(True,))
            assert not probe.refuses, (sorted(graph.edges), bidirected, x, y, arm, probe)
            seen[probe.status] = seen.get(probe.status, 0) + 1
    assert seen.get("match", 0) > 400 and seen.get("unidentified", 0) > 50, seen
