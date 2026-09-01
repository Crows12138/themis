"""A proximal descriptor, held to the question it describes.

``_rule_proximal_criterion`` re-runs Miao's model (f) on the graph — the
proxy criteria W ⊥ (Z, X) | (U, C) and Z ⊥ Y | (U, X, C), plus {U, C}
sufficient — and it is a real re-derivation. It takes the roles from
``ctx.query``. Never from ``extensions.proximal_estimand``, which is where
a reader is told which variables the answer rests on.

So identifiability was established for the question that was asked while
the block could name a different one, and the two swaps that matter most
were invisible: the treatment-inducing proxy and the outcome-inducing proxy
exchanged — which is not a relabelling but the opposite study, since the
two roles carry opposite independence requirements — and the UNOBSERVED
confounder named as one of the observed variables, which is the whole
premise of proximal inference stated backwards.

Every field here is the query restated, so the check is the whole of it,
and nothing about the graph is re-derived twice: the criterion rule owns
that, and owns it on the same roles once these are held equal to them.

The proxy roles compare as SETS. One source of confounding rarely has one
shadow, and which shadow the producer sorted first is not a fact about the
study.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier.errors import VerificationError
from themis.verifier.verify import verify_proximal_estimand


def _atom(p):
    return {"predicate": p, "args": []}


def _program(proxies=(("z",), ("w",)), covariates=(), k=2):
    treatment_proxy, outcome_proxy = proxies
    names = ["x", "y", "u", *treatment_proxy, *outcome_proxy, *covariates]
    edges = [("u", "x"), ("u", "y"), ("x", "y")]
    edges += [("u", z) for z in treatment_proxy]
    edges += [("u", w) for w in outcome_proxy]
    edges += [(z, "x") for z in treatment_proxy]
    edges += [(w, "y") for w in outcome_proxy]
    edges += [(c, "x") for c in covariates] + [(c, "y") for c in covariates]
    return {
        "version": "0.1", "domain": {"objects": []},
        "statements": [
            *({"kind": "variable", "predicate": p, "domain": [True, False]}
              for p in names),
            *({"kind": "cause", "from": _atom(a), "to": _atom(b)}
              for a, b in edges),
            {"kind": "query", "id": "q", "query": {
                "kind": "proximal_effect",
                "treatment": _atom("x"), "outcome": _atom("y"),
                "latent": _atom("u"),
                "treatment_proxy": [_atom(z) for z in treatment_proxy],
                "outcome_proxy": [_atom(w) for w in outcome_proxy],
                "covariates": [_atom(c) for c in covariates],
                "channel": {"kind": "discrete_channel",
                            "latent_cardinality": k}}},
        ]}


ONE_EACH = _program()


def _bridge_program():
    """Two shadows per side, which only the bridge channel allows.

    The discrete channel inverts a k×k measurement matrix and so takes
    exactly one proxy per side; the roles are sets because the bridge
    channel's design matrix is a sum of terms and holds as many as a study
    has. So the set comparison has to be exercised here.
    """
    def _factor(name):
        return {"variable": _atom(name), "basis": "polynomial",
                "dimension": 2}

    zs, ws = ("z1", "z2"), ("w1", "w2")
    return {
        "version": "0.1", "domain": {"objects": []},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "scale": "continuous"},
            {"kind": "variable", "predicate": "u"},
            *({"kind": "variable", "predicate": n, "scale": "continuous"}
              for n in (*zs, *ws)),
            *({"kind": "cause", "from": _atom(a), "to": _atom(b)}
              for a, b in [("u", "x"), ("u", "y"), ("x", "y"),
                           *(("u", n) for n in (*zs, *ws))]),
            {"kind": "query", "id": "q", "query": {
                "kind": "proximal_effect", "treatment": _atom("x"),
                "outcome": _atom("y"), "latent": _atom("u"),
                "treatment_proxy": [_atom(z) for z in zs],
                "outcome_proxy": [_atom(w) for w in ws],
                "channel": {"kind": "bridge_channel", "outcome_bridge": {
                    "span_terms": [{"factors": [_factor(w)]} for w in ws],
                    "moment_terms": [{"factors": [_factor(z)]} for z in zs],
                }}}},
        ]}


def _typed_query(program):
    from themis.input.semantic_validator import validate_program
    from themis.input.syntactic_validator import validate_ast
    from themis.types import QueryStatement

    parsed = validate_program(validate_ast(copy.deepcopy(program)))
    return next(s for s in parsed.statements
                if isinstance(s, QueryStatement)).query


def _frame(program, n=6000, seed=4):
    rng = np.random.default_rng(seed)
    u = rng.random(n) < 0.5
    columns = {"u": u}
    names = [s["predicate"] for s in program["statements"]
             if s["kind"] == "variable"]
    for name in names:
        if name.startswith("z"):
            columns[name] = rng.random(n) < np.where(u, 0.80, 0.20)
        elif name.startswith("w"):
            columns[name] = rng.random(n) < np.where(u, 0.85, 0.25)
    z_first = next(c for c in columns if c.startswith("z"))
    x = rng.random(n) < (np.where(u, 0.7, 0.3)
                         * np.where(columns[z_first], 1.0, 0.6))
    y = rng.random(n) < (0.1 + 0.35 * x + 0.3 * u)
    columns["x"], columns["y"] = x, y
    del columns["u"]
    return pd.DataFrame(columns)


@pytest.fixture(scope="module")
def answer():
    result = themis.estimate(
        ONE_EACH, _frame(ONE_EACH), ci_bootstrap=0)["results"][0]
    assert "proximal_estimand" in (result.get("extensions") or {}), result
    return result


def _tampered(answer, change):
    bad = copy.deepcopy(answer)
    change(bad["extensions"]["proximal_estimand"])
    return bad


def _refuses(result, fragment, program=ONE_EACH):
    with pytest.raises(VerificationError) as caught:
        themis.verify(program, result)
    assert fragment in str(caught.value), str(caught.value)


# ------------------------------------------------------------- denominators


def test_an_untouched_proximal_answer_passes(answer):
    themis.verify(ONE_EACH, answer)


def test_reordering_a_proxy_set_is_not_a_tamper():
    """Which shadow was written first is not a fact about the study.

    Held against the rule rather than the door, and deliberately: the
    claim is about the COMPARISON, and pinning it needs two proxies per
    side, which the discrete channel refuses outright — it inverts a k×k
    measurement matrix and takes one each. Reaching for an estimate would
    make this a test of the bridge estimator instead.
    """
    program = _bridge_program()
    query = _typed_query(program)
    block = {
        "method": "proximal_bridge",
        "treatment": "x()", "outcome": "y()", "latent": "u()",
        "treatment_proxy": ["z2()", "z1()"],
        "outcome_proxy": ["w2()", "w1()"],
        "covariates": [], "data_conditions": ["completeness"],
        "channel_kind": "bridge_channel",
    }
    verify_proximal_estimand(block, query)

    block["treatment_proxy"] = ["z1()", "w1()"]
    with pytest.raises(VerificationError) as caught:
        verify_proximal_estimand(block, query)
    assert "as treatment_proxy beside a query that declares" in str(
        caught.value), str(caught.value)


# --------------------------------------------------------- the two swaps


def test_exchanging_the_two_proxy_roles_is_refused(answer):
    """Not a relabelling. The two roles carry opposite independence
    requirements, so an answer with them exchanged describes a study
    nobody ran."""
    def change(block):
        block["treatment_proxy"], block["outcome_proxy"] = (
            block["outcome_proxy"], block["treatment_proxy"])
    _refuses(_tampered(answer, change), "beside a query that declares")


def test_naming_an_observed_variable_as_the_latent_is_refused(answer):
    """The premise of proximal inference is that the confounder is
    unobserved; a block naming an observed one states it backwards."""
    _refuses(_tampered(answer, lambda b: b.__setitem__("latent", "z()")),
             "as the latent beside a query that asks about")


# ------------------------------------------------------ the rest of the ask


@pytest.mark.parametrize("field,value", [
    ("treatment", "y()"), ("outcome", "x()"),
])
def test_a_renamed_end_is_refused(answer, field, value):
    _refuses(_tampered(answer, lambda b: b.__setitem__(field, value)),
             "beside a query that asks about")


def test_invented_covariates_are_refused(answer):
    """``covariates`` is what every model (f) condition was read WITHIN, so
    inventing one claims the criteria were checked somewhere else."""
    _refuses(_tampered(answer, lambda b: b.__setitem__("covariates", ["z()"])),
             "as covariates beside a query that declares")


def test_a_different_latent_cardinality_is_refused(answer):
    """k is how many states the unobserved confounder is ASSUMED to have —
    the size of the matrix being inverted — and it comes from the caller,
    so a block reporting another number reports another assumption."""
    _refuses(_tampered(
        answer, lambda b: b.__setitem__("latent_cardinality", 9)),
        "states while the query declares")


def test_a_different_channel_kind_is_refused(answer):
    """The discriminator decides which algebra recovers the effect, and
    therefore which of the block's own fields should be present at all."""
    _refuses(_tampered(
        answer, lambda b: b.__setitem__("channel_kind", "bridge_channel")),
        "while the query declares")
