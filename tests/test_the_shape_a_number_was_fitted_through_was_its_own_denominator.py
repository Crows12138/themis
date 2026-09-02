"""The block saying what shape a number was fitted through was never
checked, because it was what the checking was done against.

``mechanism_audit`` is the one place a reader learns which functional form
produced the number in front of them. Two checks already read it, and both
walk the BLOCK: one finds the ledger line for each id the block names, the
other counts the lines the block says the ledger owes. That makes the
block the denominator, which is the one position in which a thing is never
itself checked — emptying ``mechanisms`` did not merely skip its own
audit, it reduced what the ledger was said to owe. A measuring stick can
be shortened.

So the block could be deleted whole, emptied, or have its method
relabelled, and every door accepted. The one edit that was refused —
``settled_by`` set to a word outside the enum — was refused by the schema,
which is not an audit of anything.

What anchors the other direction is that a shape assumption reaches the
ledger because the FIT declared it, which the estimator channel already
holds. Every functional-form line is therefore a shape some fit was
settled under, and the reader is owed the block saying which fit.

WHAT IS NOT CHECKED, AND WHY. One of the block's four fields has no
witness on the envelope, and the tests at the end of this file record
which — a limit written down is a different thing from one nobody looked
for. It recorded two until ``target`` turned out to have a witness the
module holding it could not see; the second test down there is the record
of being wrong, kept rather than deleted.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _edge(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


BACKDOOR = {
    "version": "0.1",
    "domain": {"objects": [{"kind": "object", "name": "me"}]},
    "statements": [
        _var("x"), _var("y"), _var("z"),
        _edge("z", "x"), _edge("z", "y"), _edge("x", "y"),
        {"kind": "query", "id": "q", "query": {"kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True}, "given": []}},
    ],
}


def _df(n=400, seed=0):
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.3 + 0.4 * z).astype(int)
    y = (rng.random(n) < 0.2 + 0.3 * x + 0.2 * z).astype(int)
    return pd.DataFrame({"x": x.astype(bool), "y": y.astype(bool),
                         "z": z.astype(bool)})


@pytest.fixture(scope="module")
def fitted():
    return themis.estimate(BACKDOOR, _df(), ci_bootstrap=0)["results"][0]


def _mech(r):
    return r["extensions"]["mechanism_audit"]["mechanisms"][0]


# ================================================================= honest first


def test_the_honest_answer_passes(fitted):
    """First, or every refusal below proves nothing. The block is really
    there and really names the fit's own declaration."""
    block = _mech(fitted)
    assert block["method"] == fitted["numeric_estimate"]["method"]
    assert block["assumptions"][0]["id"] in \
        fitted["numeric_estimate"]["assumptions"]
    themis.verify(BACKDOOR, fitted)
    themis.verify_assumption_ledger(fitted)


# ======================================= the block stops being the denominator


@pytest.mark.parametrize("tamper,expect", [
    (lambda r: r["extensions"]["mechanism_audit"].__setitem__(
        "mechanisms", []), "under functional_form and no mechanism_audit"),
    (lambda r: r["extensions"].pop("mechanism_audit"),
     "under functional_form and no mechanism_audit"),
], ids=["emptied", "deleted"])
def test_a_shape_the_ledger_names_needs_a_mechanism(fitted, tamper, expect):
    """The two ways to shorten the measuring stick that reach the audit.
    Each used to reduce what the ledger owed and pass. Clearing one
    mechanism's own assumption list is the third and never gets here — the
    schema requires it non-empty, which is a fact about the shape rather
    than about the claim, and is why the other two are the interesting
    ones."""
    r = copy.deepcopy(fitted)
    tamper(r)
    with pytest.raises(VerificationError, match=expect):
        themis.verify(BACKDOOR, r)
    with pytest.raises(VerificationError, match=expect):
        themis.verify_assumption_ledger(r)


@pytest.mark.parametrize("tamper,expect", [
    (lambda r: _mech(r).__setitem__("method", "frontdoor_linear"),
     "weighing the wrong estimator"),
    (lambda r: _mech(r)["assumptions"][0].__setitem__(
        "id", "linear_outcome_regression"),
     "has no line for it|does not introduce one"),
], ids=["method_relabelled", "assumption_invented"])
def test_a_block_that_disagrees_with_the_fit_it_is_a_view_of(
        fitted, tamper, expect):
    """A view that disagrees with what it is a view OF is the one thing
    that cannot be true.

    The invented id fails three ways at once — the ledger has no line for
    it, the fit never declared it, and the fit's own shape line is left
    unclaimed — and the existing block-to-ledger check reaches it first.
    The pattern accepts either wording rather than pinning an order: which
    of three true refusals arrives first is not a claim this file makes.
    """
    r = copy.deepcopy(fitted)
    tamper(r)
    with pytest.raises(VerificationError, match=expect):
        themis.verify(BACKDOOR, r)


def test_a_result_with_no_shape_to_disclose_is_left_alone():
    """The denominator. A check that demanded a mechanism block of every
    result would refuse a structural answer, and would say nothing by
    refusing the three forgeries above."""
    res = themis.run(BACKDOOR)["results"][0]
    assert "mechanism_audit" not in (res.get("extensions") or {})
    themis.verify_assumption_ledger(res)


# ================================== where the fit is reported is not one place


def _region():
    n, rng = 4000, np.random.default_rng(5)
    u = rng.standard_normal(n)
    z1, z2 = rng.standard_normal(n), rng.standard_normal(n)
    a = 0.9 * z1 + 0.7 * u + 0.3 * rng.standard_normal(n)
    b = 0.8 * z2 + 0.6 * u + 0.3 * rng.standard_normal(n)
    y = 1.2 * a + 0.7 * b + 1.5 * u + 0.4 * rng.standard_normal(n)
    frame = pd.DataFrame({"z1": z1, "z2": z2, "a": a, "b": b, "y": y})

    def at(p):
        return {"predicate": p, "args": [{"type": "const", "name": "u"}]}

    def ed(a_, b_):
        return {"kind": "cause", "from": at(a_), "to": at(b_)}

    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            *({"kind": "variable", "predicate": p, "scale": "continuous"}
              for p in ("z1", "z2", "a", "b", "y")),
            ed("z1", "a"), ed("z2", "b"), ed("a", "y"), ed("b", "y"),
            {"kind": "bidirected", "left": at("a"), "right": at("y")},
            {"kind": "bidirected", "left": at("b"), "right": at("y")},
            {"kind": "query", "id": "q", "query": {"kind": "effect",
                "intervention": {"atom": at("a"), "value": 1.0},
                "extra_interventions": [{"atom": at("b"), "value": 1.0}],
                "target": {"atom": at("y"), "value": 1.0}, "given": []}},
        ],
    }
    return program, themis.estimate(
        program, frame, ci_bootstrap=0)["results"][0]


def test_an_answer_that_is_a_region_still_reports_its_fit():
    """An answer that is a region rather than a point carries no
    numeric_estimate, and the shape it was fitted through is real all the
    same. Holding the block to ``numeric_estimate`` alone refused three
    honest results, which is how the second place a run reports its fit
    came to be named rather than assumed.
    """
    program, res = _region()
    assert res.get("numeric_estimate") is None
    region = res["extensions"]["anderson_rubin_region"]
    block = _mech(res)
    assert block["method"] == region["method"]
    themis.verify(program, res)

    bad = copy.deepcopy(res)
    bad["extensions"]["mechanism_audit"]["mechanisms"][0]["method"] = "iv_wald"
    with pytest.raises(VerificationError, match="weighing the wrong estimator"):
        themis.verify(program, bad)


# ================================================= the limit, written down


def test_one_field_has_no_witness_and_this_records_which(fitted):
    """``form`` is the producer's word and stays so.

    It reaches the envelope through this block alone — the fit reports
    which method ran, never the shape word — so there is nothing to
    disagree with. A rule invented for it (that the method spells the
    form) holds for the outcome models and fails on the honest
    ``logistic_propensity`` beside ``aipw``. What would hold it is a
    table of shape words this repository would then own, which is a
    different root cause and its own frontier.

    Recorded rather than left silent: the day it gains a second copy
    written by the same run, this test is what says the record is stale.
    """
    r = copy.deepcopy(fitted)
    _mech(r)["form"] = "linear"
    themis.verify(BACKDOOR, r)


def test_the_target_was_the_other_one_and_the_record_was_wrong(fitted):
    """What this test used to say, and why the record was stale.

    It read: the field means two things — a variable where the shape was
    fitted for one, an estimand where it was not — and a field with two
    meanings has no witness for either. The evidence was real: holding it
    to the estimate's outcome refused seventeen honest results.

    But that stand-in is the ANSWER's copy of its own outcome, and it was
    the only one in reach, because every other mechanism check is entered
    through ``verify_assumption_ledger(result)`` — a door with no program
    beside it. A target names the thing the QUESTION is about. Asked of
    the question, twenty-six of the thirty-one targets on the answer
    shapes are its outcome exactly. "Has no witness" and "was held to the
    wrong copy" are the same sentence from inside a module that has only
    the wrong copy, which is what this test recorded for one release.
    """
    r = copy.deepcopy(fitted)
    _mech(r)["target"] = "z"
    with pytest.raises(VerificationError, match="fitted for 'z'"):
        themis.verify(BACKDOOR, r)
