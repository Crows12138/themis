"""A missing-data verdict is held in what it tells a reader, not only in the verdict.

The recovery block says whether an effect can be recovered from data with
holes in it, by which mechanism, and with what formula, and the verifier
re-derived exactly those three. A report shows a reader more than that: the
variables that are partially observed, the factors the recovery is assembled
from -- shown in place of the formula whenever there are any -- the target
each factor stands for, the adjustment set, the covariate half, the factors
the estimand requires, and why a negative is negative. Measured: on every
corpus answer carrying the block, each of those could be emptied, renamed or
replaced, and the strongest door took the answer.

Each is re-derived from the same search the verdict is, in the spelling the
block uses.
"""
from __future__ import annotations

import copy

import pytest

import themis
from themis.verifier.errors import VerificationError

_P = [{"type": "const", "name": "p"}]


def _atom(predicate):
    return {"predicate": predicate, "args": _P}


def _program(edges, missing, caused_by):
    predicates = sorted({v for edge in edges for v in edge})
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            *({"kind": "variable", "predicate": v, "domain": [True, False]}
              for v in predicates),
            *({"kind": "cause", "from": _atom(a), "to": _atom(b)}
              for a, b in edges),
            {"kind": "missingness_indicator", "id": f"R_{missing}",
             "missing_var": _atom(missing),
             "caused_by": [_atom(c) for c in caused_by]},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect", "given": [],
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True}}},
        ],
    }


_CONFOUNDED = [("z", "x"), ("z", "y"), ("x", "y")]

PROGRAMS = {
    #: z confounds, y is missing because of z: MAR, and both halves recover.
    "recoverable": _program(_CONFOUNDED, "y", ("z",)),
    #: the confounder hides itself: the conditional recovers, P(z) does not.
    "the_covariate_marginal_is_blocked": _program(_CONFOUNDED, "z", ("z",)),
    #: the outcome hides itself: the conditional does not recover.
    "the_adjusted_conditional_is_blocked": _program([("x", "y")], "y", ("y",)),
}


def _run(name):
    return next(r for r in themis.run(PROGRAMS[name])["results"]
                if r.get("query_id") == "q")


def _door(result):
    return themis.verify if result.get("derivation") else themis.verify_answer_claims


def _block(result):
    return result["extensions"]["missing_data_recovery"]


def _set(block, path, value):
    *head, last = path.split(".")
    node = block
    for step in head:
        node = node[int(step)] if step.isdigit() else node[step]
    node[int(last) if last.isdigit() else last] = value


# ================================================================ honest first


@pytest.mark.parametrize("name", sorted(PROGRAMS))
def test_each_honest_block_passes_its_door(name):
    result = _run(name)
    block = _block(result)
    assert block["partially_observed"]
    _door(result)(PROGRAMS[name], result)


def test_the_three_programs_are_the_three_shapes():
    """First, or the forgeries below are aimed at shapes nobody wrote."""
    recoverable = _block(_run("recoverable"))
    assert recoverable["recoverable"] and recoverable["estimand"]["recoverable"]
    assert recoverable["covariate_recovery"]["factorization"]
    covariate = _block(_run("the_covariate_marginal_is_blocked"))
    assert covariate["recoverable"]
    assert not covariate["covariate_recovery"]["recoverable"]
    conditional = _block(_run("the_adjusted_conditional_is_blocked"))
    assert not conditional["recoverable"] and conditional["failure_reason"]


# ============================================================== the forgery


FORGERIES = [
    ("recoverable", "partially_observed", []),
    ("recoverable", "partially_observed", ["x"]),
    ("recoverable", "factorization", []),
    ("recoverable", "factorization.0.factor", "x"),
    ("recoverable", "factorization.0.conditioned_on", []),
    ("recoverable", "target", "P(y | x)"),
    ("recoverable", "complete_criterion", True),
    ("recoverable", "adjustment_set", []),
    ("recoverable", "covariate_recovery.target", "P(x)"),
    ("recoverable", "covariate_recovery.factorization", []),
    ("recoverable", "estimand.target", "P(y | do(z))"),
    ("recoverable", "estimand.requires.1.said.target", "P(x)"),
    ("the_covariate_marginal_is_blocked", "covariate_recovery.failure_reason", None),
    ("the_covariate_marginal_is_blocked", "covariate_recovery.recovery_formula", "P(z) = P(z)"),
    ("the_covariate_marginal_is_blocked", "estimand.failure_reason.words.factors.0.said.target", "P(y | x, z)"),
    ("the_covariate_marginal_is_blocked", "estimand.recovery_formula", "P(y | do(x)) = P(y)"),
    ("the_adjusted_conditional_is_blocked", "failure_reason", None),
    ("the_adjusted_conditional_is_blocked", "recovery_formula", "P(y | x) = P(y | x)"),
]


@pytest.mark.parametrize("name,path,value", FORGERIES,
                         ids=[f"{n}:{p}" for n, p, _ in FORGERIES])
def test_what_the_block_tells_a_reader_is_re_derived(name, path, value):
    result = _run(name)
    forged = copy.deepcopy(result)
    _set(_block(forged), path, value)
    assert _block(forged) != _block(result)
    field = path.split(".")[0] if not path.startswith(("covariate_recovery", "estimand")) \
        else ".".join(p for p in path.split(".")[:2])
    with pytest.raises(VerificationError, match=f"missing_data_recovery: {field}"):
        _door(forged)(PROGRAMS[name], forged)
