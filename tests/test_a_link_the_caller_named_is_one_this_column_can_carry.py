"""#605 — the shape a caller names, asked of the column it would be fitted to.

#602 gave every route its own vocabulary and made each word reach the route
that answers. ``logistic`` had been accepted at the entry and refused by the
route for years, so it had never reached a fitter; afterwards it did, and
nothing between the caller and the fit asked whether the column could carry
it. On a continuous outcome the answer came back as a library's exception
leaving the public entry — ``Unknown label type: continuous`` from sklearn on
the back-door and front-door routes, ``endog must be in the unit interval``
from statsmodels on mediation.

The root cause is one line's division of labour. ``outcome_form`` reads the
outcome column when it is CHOOSING (``auto`` looks at the dtype and takes the
line unless the column is bool) and does not read it when it is being TOLD.
Its docstring gave the reason — which forms an estimator can fit is that
estimator's question — and that reason is true of the vocabulary and false of
the data: whether P(Y=1) exists is a fact about the column, and the column is
in this function's hand.

What the two fitters happened to accept is the evidence that nobody had
decided it. sklearn took three levels and fitted a multinomial, reported as a
logistic ATE; statsmodels took proportions and fitted a fractional logit; each
refused what the other allowed. A set of admissible outcomes that is the union
of two libraries' input validation is not a decision, so this file pins the
one that was made: the link models a probability, and the column has to be
one — two values, and both of them the values the estimand names.

Both directions, because both were live: a binary column stored as bool, as
0/1 float or as 0/1 int must still fit, on every family, or the repair has
taken away the option #602 handed over.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.form import AUTO, LOGISTIC, carries_a_probability, outcome_form
from themis.ledger import Provenance
from themis.refusals import EstimatorFailure, Refusal

SPECIES = str(Refusal.A_NAMED_LOGIT_LINK_NEEDS_A_BINARY_OUTCOME)


# ============================================ the predicate


def _series(values, dtype=None) -> pd.Series:
    return pd.Series(values, dtype=dtype, name="Y")


CAN_CARRY = {
    "bool": _series([True, False, True, False]),
    "zero_one_float": _series([0.0, 1.0, 1.0, 0.0]),
    "zero_one_int": _series([0, 1, 1, 0]),
    "zero_one_with_nulls": _series([0.0, 1.0, np.nan, 1.0]),
    "all_ones": _series([1.0, 1.0, 1.0]),
}

CANNOT = {
    "three_levels": _series([0.0, 1.0, 2.0, 1.0]),
    "proportion": _series([0.1, 0.4, 0.9, 0.5]),
    "continuous": _series([-1.2, 0.3, 4.4, 2.0]),
    "labels": _series(["yes", "no", "yes"]),
    "all_null": _series([np.nan, np.nan]),
}


@pytest.mark.parametrize("name", sorted(CAN_CARRY))
def test_a_binary_column_carries_a_probability_whatever_its_dtype(name):
    """``auto`` reads ``is_bool_dtype`` because it is choosing a default and
    may prefer the line when unsure. This judges a caller who has already
    chosen, and a 0/1 column is a probability whichever box pandas put it
    in — refusing those would take away the option rather than guard it."""
    assert carries_a_probability(CAN_CARRY[name])


@pytest.mark.parametrize("name", sorted(CANNOT))
def test_a_column_with_a_third_value_carries_no_probability(name):
    assert not carries_a_probability(CANNOT[name])


# ============================================ the translator


@pytest.mark.parametrize("name", sorted(CAN_CARRY) + sorted(CANNOT))
def test_auto_is_untouched_and_still_reads_the_column(name):
    """The guard is about being told, not about choosing. ``auto`` already
    read this column and its answer has not moved."""
    column = {**CAN_CARRY, **CANNOT}[name]
    shape, provenance = outcome_form(AUTO, column)
    assert provenance is Provenance.DEFAULT
    assert shape == ("logistic" if name == "bool" else "linear")


@pytest.mark.parametrize("name", sorted(CAN_CARRY) + sorted(CANNOT))
def test_the_line_is_never_refused(name):
    """A linear fit of a 0/1 column is a linear probability model and a
    legitimate thing to ask for, so naming the other arm stays open on every
    column shape."""
    shape, provenance = outcome_form("linear", {**CAN_CARRY, **CANNOT}[name])
    assert (shape, provenance) == ("linear", Provenance.CALLER_ASSERTED)


@pytest.mark.parametrize("name", sorted(CAN_CARRY))
def test_a_named_logit_on_a_binary_column_resolves(name):
    shape, provenance = outcome_form(LOGISTIC, CAN_CARRY[name])
    assert (shape, provenance) == ("logistic", Provenance.CALLER_ASSERTED)


@pytest.mark.parametrize("name", sorted(CANNOT))
def test_a_named_logit_on_any_other_column_refuses(name):
    with pytest.raises(EstimatorFailure) as caught:
        outcome_form(LOGISTIC, CANNOT[name])
    assert caught.value.failure_type == (
        Refusal.A_NAMED_LOGIT_LINK_NEEDS_A_BINARY_OUTCOME)


def test_the_family_spelling_travels_with_the_arm():
    """Mediation calls the same arm ``logit``. The guard is about the column,
    so it may not change which word comes back."""
    assert outcome_form(LOGISTIC, CAN_CARRY["bool"], logistic="logit")[0] == (
        "logit")


# ============================================ through the public door


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


A, M, Y, W = (_atom(n) for n in ("A", "M", "Y", "W"))
_EFFECT = {"kind": "effect", "target": {"atom": Y, "value": True},
           "intervention": {"atom": A, "value": True}, "given": []}


def _v(name):
    return {"kind": "variable", "predicate": name}


def _c(a, b):
    return {"kind": "cause", "from": a, "to": b}


def _program(statements, query=_EFFECT):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": statements + [
            {"kind": "query", "id": "q1", "query": query}],
    }


ROUTES = {
    "backdoor": _program([_v("A"), _v("Y"), _v("W"),
                          _c(W, A), _c(W, Y), _c(A, Y)]),
    "frontdoor": _program([_v("A"), _v("M"), _v("Y"), _c(A, M), _c(M, Y),
                           {"kind": "bidirected", "left": A, "right": Y}]),
    "mediation": _program([_v("A"), _v("M"), _v("Y"),
                           _c(A, M), _c(M, Y), _c(A, Y)],
                          {**_EFFECT, "mediator": M}),
}


def _frame(kind: str, n: int = 700) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    w = rng.standard_normal(n)
    a = (rng.random(n) < 0.3 + 0.2 * (w > 0)).astype(float)
    m = (rng.random(n) < 0.2 + 0.5 * a).astype(float)
    raw = 0.5 * a + 0.6 * m + 0.4 * w + rng.standard_normal(n) * 0.5
    y = {
        "continuous": raw,
        "bool": raw > raw.mean(),
        "zero_one_float": (raw > raw.mean()).astype(float),
        "three_levels": np.digitize(
            raw, [raw.mean() - 0.5, raw.mean() + 0.5]).astype(float),
        "proportion": 1.0 / (1.0 + np.exp(-raw)),
    }[kind]
    return pd.DataFrame({"A": a, "M": m, "Y": y, "W": w})


@pytest.mark.parametrize("route", sorted(ROUTES))
def test_a_named_logit_on_a_continuous_outcome_comes_back_as_a_refusal(route):
    """The measured defect, through the door a caller uses. What used to
    leave here was the fitter's own exception, in the fitter's own words, and
    which sentence a reader got depended on which library the family used."""
    result = themis.estimate(
        ROUTES[route], _frame("continuous"), model="logistic")["results"][0]
    failure = result["estimator_failure"]
    assert failure["failure_type"] == SPECIES
    assert failure["kind"] == "request"
    assert failure["details"]["outcome"] == "Y"
    assert {"remedy": "change_input", "subject": "model"} in failure["remedies"]
    assert result.get("numeric_estimate") is None


@pytest.mark.parametrize("route", sorted(ROUTES))
@pytest.mark.parametrize("kind", ["bool", "zero_one_float"])
def test_a_named_logit_on_a_binary_outcome_still_answers(route, kind):
    """The side a guard takes away if it is drawn one value too wide."""
    result = themis.estimate(
        ROUTES[route], _frame(kind), model="logistic")["results"][0]
    assert result.get("estimator_failure") is None
    method = result["numeric_estimate"]["method"]
    assert "logistic" in method or "logit" in method


@pytest.mark.parametrize("route", sorted(ROUTES))
def test_auto_on_a_continuous_outcome_is_unmoved(route):
    """The default path is the one this repair must not have touched."""
    result = themis.estimate(
        ROUTES[route], _frame("continuous"))["results"][0]
    assert result.get("estimator_failure") is None
    assert "linear" in result["numeric_estimate"]["method"]


# ============================================ the two answers withdrawn


def test_a_three_level_outcome_is_no_longer_fitted_as_a_multinomial():
    """Declared rather than slipped in. sklearn takes three labels and fits a
    multinomial, and the back-door route reported the result as
    ``backdoor_logistic`` — an ATE on the probability of one of three levels,
    with nothing on the envelope saying which. It is a refusal now."""
    result = themis.estimate(
        ROUTES["backdoor"], _frame("three_levels"),
        model="logistic")["results"][0]
    assert result["estimator_failure"]["failure_type"] == SPECIES
    assert result["estimator_failure"]["details"]["distinct"] == 3


def test_a_fractional_outcome_is_no_longer_fitted_as_a_proportion():
    """The other half of the same declaration. statsmodels takes anything in
    the unit interval, so mediation answered on proportions while the
    back-door route raised on them — one library's tolerance, standing in for
    a decision nobody made."""
    result = themis.estimate(
        ROUTES["mediation"], _frame("proportion"),
        model="logistic")["results"][0]
    assert result["estimator_failure"]["failure_type"] == SPECIES


def test_the_refusal_leaves_by_the_callers_door_and_not_the_producers():
    """The criterion #602 arrived at: construct the case that must say no,
    send it through the public entry, and watch WHICH door the exception
    leaves by. A guard that raises past the envelope has re-created the defect
    it was written to remove."""
    out = themis.estimate(ROUTES["backdoor"], _frame("continuous"),
                          model="logistic")
    result = out["results"][0]
    assert result["status"] == "needs_investigation"
    assert result["estimator_failure"]["failure_type"] == SPECIES
