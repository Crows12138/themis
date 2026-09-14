"""A selection-recovery verdict is about the subpopulation its question names.

An effect question can condition on a stratum, and then it asks for
P(y | do(x), c). The selection-backdoor analysis took no condition, so under
a question about part of the population it returned the population's verdict
and formula, and on data the population's number -- and every door took it.
Measured before the change on the model below: asked about b=True, where the
effect is 0.50, the answer was 0.30, the average over both strata, as
``numerically_solved``.

The condition is held inside Z⁺. For C ⊆ Z⁺ and Z⁺ free of descendants of
the treatment, do(x) leaves the distribution of Z⁺ alone, so

    P(y | do(x), c) = Σ_{z⁺∖c} [ Σ_{z⁻} P(y | x, z⁺, z⁻, S) · P(z⁻ | x, z⁺) ]
                      · P(z⁺∖c | c)

-- the same sum, with the outer weight taken within the stratum. A condition
downstream of the treatment is not one this criterion can adjust for, and the
verdict about that subpopulation says so rather than answering for all of it.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace

import networkx as nx
import numpy as np
import pandas as pd
import pytest

import themis
from tests.answer_corpus import the_door_for
from themis.runtime.scheduler import _serialize_selection_recovery
from themis.runtime.selection_recovery import recover_effect
from themis.types import Atom, ObservationStatement
from themis.verifier import verify_selection_recovery
from themis.verifier.errors import VerificationError


def A(name):
    return Atom(predicate=name, args=())


RESTRICTED_ON_S = (ObservationStatement(atom=A("s"), value=True),)


def _asking(*given):
    """The effect of x on y, within the stratum ``given`` names."""
    return SimpleNamespace(
        intervention=SimpleNamespace(atom=A("x")),
        target=SimpleNamespace(atom=A("y")),
        given=tuple(SimpleNamespace(atom=A(g)) for g in given))


def _unbiased(expression):
    return {"vocabulary": "unbiased_distribution", "token": "unbiased",
            "said": {"expression": expression}}


#: One graph per shape a verdict about a stratum takes, the condition asked,
#: and what comes back on it: the two halves, the formula and the ledger.
STRUCTURES = {
    # b confounds, and the outcome reaches the selection node only through a,
    # a descendant of the treatment. The condition is all of Z⁺, so there is
    # no outer sum left.
    "the condition is all of Z⁺": (
        [("b", "x"), ("b", "y"), ("x", "y"), ("y", "a"), ("a", "s"),
         ("x", "s")],
        "b", ["b"], ["a"],
        "P(y | do(x), b) = Σ_{a} P(y | x, b, a, S) · P(a | x, b)",
        [_unbiased("P(x, b, a)")]),
    # b and c both confound, and b reaches the selection node directly, so
    # how b is spread within c has to come off a sample selection did not
    # touch.
    "the rest of Z⁺ weighed off unselected data": (
        [("b", "x"), ("b", "y"), ("c", "x"), ("c", "y"), ("x", "y"),
         ("x", "s"), ("b", "s")],
        "c", ["b", "c"], [],
        "P(y | do(x), c) = Σ_{b} P(y | x, b, c, S) · P(b | c)",
        [_unbiased("P(b, c)")]),
    # Selection reaches b only through c, so within c the selected sample
    # already spreads b as the population does.
    "the rest of Z⁺ weighed off the selected sample": (
        [("b", "c"), ("b", "x"), ("b", "y"), ("c", "x"), ("c", "y"),
         ("x", "y"), ("c", "s")],
        "c", ["b", "c"], [],
        "P(y | do(x), c) = Σ_{b} P(y | x, b, c, S) · P(b | c)",
        []),
}

#: A condition downstream of the treatment, on the first graph above.
DOWNSTREAM = (STRUCTURES["the condition is all of Z⁺"][0], "a")


def _block(edges, *given):
    graph = nx.DiGraph([(A(u), A(v)) for u, v in edges])
    rec = recover_effect(graph, A("x"), A("y"), (A("s"),),
                         given=tuple(A(g) for g in given))
    return _serialize_selection_recovery(rec, A("x"), A("y")), graph


def _refusal(block, graph, question):
    try:
        verify_selection_recovery(block, graph, RESTRICTED_ON_S, question)
    except VerificationError as exc:
        return str(exc)
    return None


@pytest.mark.parametrize("shape", sorted(STRUCTURES))
def test_an_honest_verdict_about_a_stratum_is_accepted(shape):
    edges, condition, z_plus, z_minus, formula, ledger = STRUCTURES[shape]
    block, graph = _block(edges, condition)
    assert block["recoverable"] is True
    assert (block["given"], block["z_plus"], block["z_minus"]) == (
        [condition], z_plus, z_minus)
    assert block["recovery_formula"] == formula
    assert block["external_data_needed"] == ledger
    assert _refusal(block, graph, _asking(condition)) is None


def test_a_condition_downstream_of_the_treatment_is_a_verdict_of_its_own():
    edges, condition = DOWNSTREAM
    block, graph = _block(edges, condition)
    assert (block["recoverable"], block["given"]) == (False, [condition])
    assert block["failure_reason"] == {
        "vocabulary": "selection_recovery_shortfall",
        "token": "given_is_not_upstream_of_the_treatment",
        "said": {"variables": "['a']"}}
    assert _refusal(block, graph, _asking(condition)) is None
    # The whole population's effect is recoverable on this graph. Claimed
    # for the subpopulation, it is refused as the claim it is.
    claimed, _ = _block(edges)
    claimed["given"] = [condition]
    assert "not upstream" in (_refusal(claimed, graph, _asking(condition)) or "")


@pytest.mark.parametrize("shape", sorted(STRUCTURES) + ["downstream"])
def test_a_verdict_is_about_the_population_its_question_names(shape):
    """Each verdict, put to the question about the other population, is
    refused for that and not for anything it computed."""
    edges, condition = (DOWNSTREAM if shape == "downstream"
                        else STRUCTURES[shape][:2])
    within, graph = _block(edges, condition)
    whole, _ = _block(edges)
    assert "given" in (_refusal(within, graph, _asking()) or "")
    assert "given" in (_refusal(whole, graph, _asking(condition)) or "")


#: For each shape, what a block about the stratum tells a reader, told
#: otherwise: as the population's, or as another stratum's.
LIES = {
    "the condition is all of Z⁺": {
        "given": ["a"],
        "z_plus": [],
        "recovery_formula": (
            "P(y | do(x)) = Σ_{b} [ Σ_{a} P(y | x, b, a, S) · P(a | x, b) ]"
            " · P(b)"),
    },
    "the rest of Z⁺ weighed off unselected data": {
        "recovery_formula": "P(y | do(x), c) = Σ_{b} P(y | x, b, c, S) · P(b)",
        "external_data_needed": [],
    },
    "the rest of Z⁺ weighed off the selected sample": {
        "external_data_needed": [_unbiased("P(b, c)")],
    },
}


@pytest.mark.parametrize("shape,field", sorted(
    (shape, field) for shape, lies in LIES.items() for field in lies))
def test_what_a_verdict_about_a_stratum_says_is_what_the_stratum_fixes(
        shape, field):
    edges, condition = STRUCTURES[shape][:2]
    block, graph = _block(edges, condition)
    assert block[field] != LIES[shape][field]
    block[field] = copy.deepcopy(LIES[shape][field])
    refusal = _refusal(block, graph, _asking(condition))
    assert refusal is not None and field in refusal, refusal


# --------------------------------------------------------------- on data
#: The effect of x on y where b holds, where it does not, and on average.
TRUTH = {True: 0.50, False: 0.10, None: 0.30}


def _scm(n: int, seed: int) -> pd.DataFrame:
    """b→x, b→y, x→y, y→a→s, x→s, with P(y | x, b) = 0.2 + 0.1x + 0.2b + 0.4xb."""
    rng = np.random.default_rng(seed)
    b = rng.binomial(1, 0.5, n)
    x = rng.binomial(1, 0.3 + 0.4 * b)
    y = rng.binomial(1, 0.2 + 0.1 * x + 0.2 * b + 0.4 * x * b)
    a = rng.binomial(1, 0.2 + 0.5 * y)
    s = rng.binomial(1, 0.1 + 0.4 * x + 0.4 * a)
    return pd.DataFrame({"x": x, "y": y, "a": a, "b": b, "s": s}).astype(bool)


_P = [{"type": "const", "name": "p"}]


def _at(name):
    return {"predicate": name, "args": _P}


def _program(**given):
    statements = [{"kind": "variable", "predicate": v, "domain": [True, False]}
                  for v in "xyabs"]
    statements += [{"kind": "cause", "from": _at(u), "to": _at(v)}
                   for u, v in STRUCTURES["the condition is all of Z⁺"][0]]
    statements.append({"kind": "observation", "atom": _at("s"), "value": True})
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "given": [{"atom": _at(name), "value": value}
                  for name, value in given.items()],
        "intervention": {"atom": _at("x"), "value": True},
        "target": {"atom": _at("y"), "value": True}}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "p"}]},
            "statements": statements}


@pytest.fixture(scope="module")
def samples():
    full = _scm(200_000, seed=2)
    return full[full.s].reset_index(drop=True), _scm(200_000, seed=3)


def _answer(samples, program):
    biased, reference = samples
    return themis.estimate(copy.deepcopy(program), biased,
                           reference_data=reference,
                           ci_bootstrap=100)["results"][0]


@pytest.fixture(scope="module")
def answers(samples):
    out = {}
    for level in TRUTH:
        program = _program() if level is None else _program(b=level)
        out[level] = (program, _answer(samples, program))
    return out


@pytest.mark.parametrize("level", list(TRUTH), ids=str)
def test_the_recovered_number_is_the_effect_in_the_stratum_asked(answers, level):
    program, result = answers[level]
    estimate = result["numeric_estimate"]
    assert estimate["method"] == "selection_backdoor_recovery"
    assert abs(estimate["point"] - TRUTH[level]) < 0.03, estimate["point"]
    assert estimate.get("given", []) == ([] if level is None else [["b", level]])
    the_door_for(result)(program, copy.deepcopy(result))


def test_a_stratum_the_criterion_cannot_adjust_for_gets_no_number(samples):
    program = _program(a=True)
    result = _answer(samples, program)
    assert "numeric_estimate" not in result
    failure = result["estimator_failure"]
    assert failure["failure_type"] == "not_recoverable"
    assert failure["details"]["estimand"] == "P(y|do(x), a)"
    the_door_for(result)(program, copy.deepcopy(result))


def _renamed(result):
    result["numeric_estimate"]["given"] = [["b", False]]


def _unnamed(result):
    del result["numeric_estimate"]["given"]


def _about_everyone(result):
    del result["extensions"]["selection_recovery"]["given"]


def _tables_from_the_other_stratum(result):
    """Every recorded cell of b moved to the other level, the tables still
    agreeing with each other and with the number."""
    suff = (result["numeric_estimate"]["selection_recovery_numeric"]
            ["sufficient_statistics"])
    at = suff["z_plus_vars"].index("b")
    for table in ("ref_p_zplus", "ref_p_zminus_given", "biased_strata"):
        for rec in suff[table]:
            rec["z_plus"][at] = False


#: What the answer about b=True says, said about another population, and the
#: word its refusal names.
NUMERIC_LIES = {
    "the number said to be about b=False": (_renamed, "given"),
    "the number said to be about everyone": (_unnamed, "given"),
    "the verdict said to be about everyone": (_about_everyone, "given"),
    "the tables taken from b=False": (_tables_from_the_other_stratum, "stratum"),
}


@pytest.mark.parametrize("lie", sorted(NUMERIC_LIES))
def test_an_answer_told_about_another_population_is_refused(answers, lie):
    program, honest = answers[True]
    result = copy.deepcopy(honest)
    tell, named = NUMERIC_LIES[lie]
    tell(result)
    with pytest.raises(VerificationError, match=named):
        the_door_for(result)(program, result)
