"""The formula on the envelope, and what used to disagree with it.

``result["formula"]`` is the estimand. The report prints it
(``analysis_report.py`` line 943), the browser shows it to a reader under
识别公式 (``Verdict.tsx`` line 109), and ``analysis_report.py`` line 3767
says every other route's estimand is stated from it. Nothing read it: on
all twenty-three answers that carry one it could be **deleted outright**
and the public door said yes, and its two hundred and sixty-seven leaves —
which predicate each factor is about, which variable the sum binds, which
value of Y the whole thing is for — could each be rewritten. A hundred and
thirty-four of those are closed here; the hundred and thirty-three that
are not are the last test in this file, counted rather than described.

The probe that answers this has existed since Phase 15. It samples random
SCMs consistent with the graph and asks whether the formula computes the
true interventional quantity, and it was reachable from one branch of the
query-kind dispatch, where it reads the formula out of the DERIVATION —
which an effect answer's chain does not carry. A check about the answer,
standing where a route is chosen.

Two things had to change together, and neither is enough alone. The probe
now runs on the envelope's formula, outside that dispatch. And its verdict
vocabulary had one word doing two jobs: a formula naming a predicate this
problem never declared cannot be evaluated, so it came back
"inconclusive", which the probe's own documentation says is NOT a
rejection. Renaming one predicate was therefore the cheapest way past a
semantic check — twenty-two of twenty-two forgeries returned it. Whether a
formula is ABOUT this problem is now asked from the formula's own text,
before any SCM is sampled, and answered as a refusal.

Two questions are asked of the estimand and they do not share a
prerequisite. Whether the formula is ABOUT this problem needs only the
names the problem declares, so it is asked of all twenty-three. Whether it
COMPUTES what was asked needs an (X, Y) pair, and a counterfactual
conjunction names none, so it is asked of twenty-two. Binding both to the
second prerequisite is how the first came to be skipped on a shape whose
graph could have answered it.

Those names come from two places and neither is complete alone: an
estimation route's graph carries every variable while its theta is empty,
and a probability query's theta carries the variable while its graph —
built from the cause statements — has no nodes at all. Asking only the
graph reads "took part in no edge" as "does not exist", and refused an
honest answer for it.

Measured across the forty-four shapes: twenty-one honest formulas match,
one declines for a reason of its own (an IDC query conditions on something
the probe’s graph does not carry), and one query kind has no (X, Y) pair.
What this does NOT close is written down and counted below.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.verifier.errors import VerificationError
from themis.verifier.semantic_probe import ProbeResult, formula_fits

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

WITH_FORMULA = sorted(
    name for name, pair in SHAPES.items() if "formula" in pair["result"])


def _pair(method: str):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _first(node, key, apply):
    """Rewrite the first ``key`` in document order. True if one was found."""
    if isinstance(node, dict):
        if isinstance(node.get(key), str):
            node[key] = apply(node[key])
            return True
        return any(_first(v, key, apply) for v in node.values())
    if isinstance(node, list):
        return any(_first(v, key, apply) for v in node)
    return False


def _names(node, out=None):
    out = set() if out is None else out
    if isinstance(node, dict):
        if isinstance(node.get("predicate"), str):
            out.add(node["predicate"])
        for value in node.values():
            _names(value, out)
    elif isinstance(node, list):
        for value in node:
            _names(value, out)
    return out


# ------------------------------------------------- the fact this rests on


def test_the_estimand_is_carried_by_the_answers_that_identify_one():
    """Stated so it cannot drift: which answers carry a formula, and that
    every one of them is a sum, product or fraction over probabilities."""
    assert len(WITH_FORMULA) == 23, WITH_FORMULA
    for name in WITH_FORMULA:
        written = SHAPES[name]["result"]["formula"]
        assert written["kind"] in (
            "sum", "product", "fraction", "probability_ref", "constant"), (
                name, written["kind"])


# --------------------------------------------------- rewriting the estimand


@pytest.mark.parametrize("shape", WITH_FORMULA)
def test_a_factor_may_not_be_about_a_variable_the_graph_lacks(shape):
    """The cheapest forgery, and the one a semantic check used to answer
    with "no opinion": rename one predicate."""
    program, result = _pair(shape)
    assert _first(result["formula"], "predicate", lambda p: p + "_forged")
    with pytest.raises(VerificationError, match="does not declare"):
        themis.verify(program, result)


@pytest.mark.parametrize("shape", WITH_FORMULA)
def test_a_sum_and_the_references_to_it_are_one_name(shape):
    """Rename what the sum binds and its references dangle. Nothing about
    the graph is wrong; the formula has simply stopped being one."""
    program, result = _pair(shape)
    formula = result["formula"]
    if not isinstance(formula.get("bind"), dict):
        pytest.skip("this estimand binds nothing")
    formula["bind"]["name"] = formula["bind"]["name"] + "_forged"
    with pytest.raises(VerificationError, match="binds those"):
        themis.verify(program, result)


def test_a_forgery_that_stays_inside_the_graph_is_mostly_still_accepted():
    """The remainder, counted rather than skipped.

    Swap two variables the formula actually uses. Every name still exists,
    the formula is still about this graph, and the estimand is a different
    one — so the fit gate above has nothing to say and the question falls
    entirely to the sampled models. Three of twenty-three are refused.

    The twenty that are not divide, measured: thirteen the probe calls a
    genuine match (a backdoor sum over one binary covariate is close to
    symmetric in the two names being exchanged, and three sampled models do
    not separate them); five it cannot evaluate at all, because the swapped
    formula asks the model for a conditional the model has no entry for,
    which arrives as ``inconclusive`` — the same word this change split for
    a different reason, still carrying evidence on this one; one query kind
    has no (X, Y) pair; one is already inconclusive when honest.

    The number is asserted so that improving the probe FAILS here and the
    count has to be brought down deliberately. A gap that only lives in a
    skip message is a gap nobody is counting.
    """
    refused = []
    for shape in WITH_FORMULA:
        program, result = _pair(shape)
        names = sorted(_names(result["formula"]))
        assert len(names) >= 2, shape
        lo, hi = names[0], names[-1]

        def swap(node):
            if isinstance(node, dict):
                if node.get("predicate") == lo:
                    node["predicate"] = hi
                elif node.get("predicate") == hi:
                    node["predicate"] = lo
                for value in node.values():
                    swap(value)
            elif isinstance(node, list):
                for value in node:
                    swap(value)

        swap(result["formula"])
        try:
            themis.verify(program, result)
        except VerificationError:
            refused.append(shape)

    assert refused == [
        "dose_response_causal_forest_dml",
        "dose_response_linear_dml",
        "dose_response_linear_drlearner",
    ], refused


# ------------------------------------------- a decline is not an acquittal


def test_a_formula_that_does_not_fit_is_refused_rather_than_declined():
    """The two species, asked of the gate that separates them.

    ``formula_fits`` is answered from the formula's own text, before any
    model is sampled — not from an exception raised while evaluating it.
    A verifier that read "could not evaluate: KeyError(...)" as a reason
    would be reading a message, and a message belongs to whoever raises it.
    """
    import networkx as nx

    from themis.types import (
        Atom, ProbabilityRefExpr, SumExpr, ValuedAtom, VarRef, BindDecl,
    )

    x, y = Atom("x", ()), Atom("y", ())
    graph = nx.DiGraph()
    graph.add_nodes_from([x, y])
    graph.add_edge(x, y)

    fits = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),))
    assert formula_fits(graph, fits) is None

    stray = ProbabilityRefExpr(
        target=ValuedAtom(atom=Atom("nowhere", ()), value=True), given=())
    verdict = formula_fits(graph, stray)
    assert isinstance(verdict, ProbeResult) and verdict.status == "unfit"
    assert "does not declare" in verdict.detail

    # A variable that causes nothing is still a variable. Asked of the
    # graph alone this is a stray name; asked of the problem it is not,
    # and a probability query is exactly the shape that has one.
    graphless = nx.DiGraph()
    lonely = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=True), given=())
    assert formula_fits(graphless, lonely) is not None
    assert formula_fits(graphless, lonely, {y: (True, False)}) is None

    dangling = SumExpr(
        bind=BindDecl(name="over_x"), over=x,
        body=ProbabilityRefExpr(
            target=ValuedAtom(atom=y, value=True),
            given=(ValuedAtom(atom=x, value=VarRef(name="somebody_else")),)))
    verdict = formula_fits(graph, dangling)
    assert verdict is not None and verdict.status == "unfit"
    assert "binds those" in verdict.detail


def test_an_estimand_this_system_cannot_read_is_refused():
    """A formula whose shape is not one this repository writes is a
    refusal, not a shrug: the only reason to carry one is to be read."""
    program, result = _pair(WITH_FORMULA[0])
    result["formula"] = {"kind": "sum", "bind": {"name": "z"}}
    with pytest.raises(Exception):
        themis.verify(program, result)


def test_the_probe_is_told_which_value_of_the_outcome_it_is_about():
    """An effect answer's formula names Y's value where an identify
    query's leaves it open. Asked about the other value it returns the
    same number, and the probe reads that as a mismatch by 1-p — so an
    honest estimand would be refused. Every honest shape passing is what
    holds this, and it is asserted here because the failure it prevents is
    silent everywhere else."""
    for name in WITH_FORMULA:
        program, result = _pair(name)
        themis.verify(program, result)
