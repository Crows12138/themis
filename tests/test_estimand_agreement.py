"""Rows that declare the same estimand have to give the same number.

``Strategy.produces`` says what a row's number is an estimate OF. It is
what makes an escalation legible — the IV fall-back reports a complier
contrast where the non-parametric route reports a population effect, and
the table says so rather than each estimator's prose saying so. But a
declaration nothing checks is a label: until something compares the
numbers, ``produces`` claims an agreement it never has to keep.

So this compares them. Four entrances reach the same estimand on one
query, through two different rows of the table, and their numbers must
agree to within ``_AGREEMENT``.

That bound is measured, not chosen for comfort, and it is deliberately
far inside the intervals these estimators report. Overlapping intervals
would be the wrong criterion: an interval answers "could the true value
be elsewhere", and on this design each is about 0.042 wide, so requiring
only that each point sit inside the others' intervals would accept two
rows disagreeing by 0.02 about an effect of 0.30. The four points are
deterministic given the data — resampling enters the interval, not the
point — and they span 0.00102. The bound is five times that.

The second test is why the first one is allowed to exist. Comparing
numbers across rows is only meaningful where the table says the rows
answer the same question; on a graph where the IV ladder also applies,
the numbers may legitimately differ, and what licenses or forbids the
comparison is ``produces``, not a reader's judgement about which
estimators "should" match.
"""
import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.dispatch import _EFFECT_STRATEGIES
from themis.estimation.strategy import Estimand

# Every entrance the caller has to a query_effect number on this design.
# g-formula is the default (the ``backdoor`` row); the other three select
# the ``doubly_robust`` row, which is a different row of the same table.
_ENTRANCES = ("g_formula", "ipw", "aipw", "tmle")

_AGREEMENT = 0.005


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _var(p):
    return {"kind": "variable", "predicate": p}


def _cause(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


_EFFECT_QUERY = {
    "kind": "query", "id": "q",
    "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": {"atom": _atom("y"), "value": True},
        "given": [],
    },
}

_CONFOUNDED = {
    "version": "0.1",
    "domain": {"objects": [{"kind": "object", "name": "u"}]},
    "statements": [
        _var("w"), _var("x"), _var("y"),
        _cause("w", "x"), _cause("w", "y"), _cause("x", "y"),
        _EFFECT_QUERY,
    ],
}


@pytest.fixture(scope="module")
def confounded_frame():
    """W confounds X and Y; the ATE is 0.30 by construction."""
    rng = np.random.default_rng(11)
    n = 8_000
    w = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.25 + 0.45 * w).astype(int)
    y = (rng.random(n) < 0.15 + 0.30 * x + 0.25 * w).astype(int)
    return pd.DataFrame({"w": w, "x": x, "y": y})


@pytest.fixture(scope="module")
def answers(confounded_frame):
    out = {}
    for entrance in _ENTRANCES:
        options = {} if entrance == "g_formula" else {"ate_estimator": entrance}
        result = themis.estimate(
            _CONFOUNDED, confounded_frame, ci_bootstrap=200, **options,
        )["results"][0]
        out[entrance] = result["numeric_estimate"]
    return out


def test_the_entrances_reach_more_than_one_row_of_the_table(answers):
    """The premise. Four entrances that all landed on one method would
    make the agreement test vacuous — it would be comparing a number
    with itself."""
    assert len({e["method"] for e in answers.values()}) == len(_ENTRANCES)


def test_every_entrance_to_the_same_estimand_gives_the_same_number(answers):
    points = {name: e["point"] for name, e in answers.items()}
    spread = max(points.values()) - min(points.values())
    assert spread <= _AGREEMENT, (
        f"entrances to one estimand span {spread:.5f}: "
        + ", ".join(f"{n}={p:.5f}" for n, p in sorted(points.items()))
    )


def test_the_agreement_is_tighter_than_the_intervals_it_is_read_beside(answers):
    """Guards the bound itself. If the estimators' intervals ever narrow to
    the width of ``_AGREEMENT``, this test has stopped saying anything the
    intervals did not already say, and the bound needs re-measuring rather
    than the failure being read as agreement."""
    narrowest = min(e["ci_upper"] - e["ci_lower"] for e in answers.values())
    assert _AGREEMENT < narrowest / 4


def test_the_estimand_is_what_licenses_the_comparison():
    """The rows the entrances reach declare one estimand between them, and
    the rows that answer a different question declare a different one. That
    is the whole content of the test above: without it, comparing an IV
    row's complier contrast against a back-door population effect would
    look like the same check."""
    produces = {s.id: s.produces for s in _EFFECT_STRATEGIES}
    assert produces["backdoor"] is produces["doubly_robust"] is (
        Estimand.QUERY_EFFECT
    )
    for laden in ("iv_wald", "iv_overidentified"):
        assert produces[laden] is Estimand.COMPLIER_EFFECT
    assert produces["transport"] is Estimand.TRANSPORTED_EFFECT
    assert produces["mediation_single"] is Estimand.DECOMPOSITION
