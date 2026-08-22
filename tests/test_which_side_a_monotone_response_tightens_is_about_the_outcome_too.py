"""#424 — MTR read the intervention's polarity and called it the answer.

Which side of the interval a monotone-treatment-response assumption tightens
takes TWO facts about TWO variables. One is about X: does intervening at the
queried arm move Y up, for the units observed at the other arm. The other is
about Y: where the target EVENT sits in the outcome's order. MTR constrains Y;
the bound is on the event ``Y=y``; and ``1{Y=y}`` is monotone in Y only at the
TOP of the order — reversed at the bottom, monotone in neither direction in
between.

Only the first fact existed. The symbolic layer, the numeric layer and the
verifier each derived the rule independently and all three wrote
``tighten_lower = treating_high == direction_increases_y`` — the one polarity
they held, standing in for the one nobody had. Three independent derivations
from the same missing input are not three checks.

What it cost is measured below and is not a widened interval: asked for
``P(Y=False | do(X=True))`` the answer EXCLUDED the truth, end to end through
``themis.estimate``, with ``themis.verify_bounds_results`` passing because the
verifier had made the same substitution.

The repair carries the order as an input rather than recovering it: the
scheduler reads the outcome's declared levels, the same reader serves the
symbolic and numeric call sites so they cannot assume different orders, the
producer records the order it used beside the counts it used, and the verifier
derives the order AGAIN from the program and refuses a row that read a
different one.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.bounds_numeric import evaluate_manski_tamer_bounds
from themis.verifier.errors import VerificationError

U = "u"


def _atom(pred):
    return {"predicate": pred, "args": [{"type": "const", "name": U}]}


# ---------------------------------------------------------------------------
# A world where MTR holds and the truth is exact
# ---------------------------------------------------------------------------
#
# Built from response types by COUNT rather than by sampling, so every number
# below is a fraction with a small denominator and can be checked by hand.
# ``(Y(0), Y(1))`` with Y(1) ≥ Y(0) — non_decreasing holds by construction.
_TYPES = {                       # (y0, y1): (units, units assigned X=1)
    (0, 0): (5000, 1000),
    (0, 1): (3000, 2400),
    (1, 1): (2000, 1000),
}


def _frame() -> pd.DataFrame:
    rows = []
    for (y0, y1), (n, n_treated) in _TYPES.items():
        rows += [(True, bool(y1))] * n_treated
        rows += [(False, bool(y0))] * (n - n_treated)
    return pd.DataFrame(rows, columns=["x", "y"])


def _truth(arm: bool, value: bool) -> float:
    total = sum(n for n, _ in _TYPES.values())
    hit = sum(n for (y0, y1), (n, _) in _TYPES.items()
              if bool(y1 if arm else y0) == value)
    return hit / total


def _program(target_value=True, *, domain=(True, False), scale=None):
    outcome = {"kind": "variable", "predicate": "y", "domain": list(domain)}
    if scale is not None:
        outcome["scale"] = scale
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": U}]},
        "extensions": {"monotonicity": [
            {"target": "y", "treatment": "x", "direction": "non_decreasing"},
        ]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            outcome,
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": target_value},
                "given": []}},
        ],
    }


def _mtr_row(program, df=None):
    out = themis.estimate(program, df if df is not None else _frame(),
                          ci_bootstrap=0)
    result = out["results"][0]
    rows = [b for b in (result.get("bounds_results") or ())
            if b.get("method") == "manski_tamer_monotonicity"]
    return result, (rows[0] if rows else None)


def _the_rule_this_replaced(df, *, x_val, y_val, direction):
    """The old rule, transcribed: one side to the observed marginal, and WHICH
    side read off the intervention's polarity alone."""
    same = float(((df.x == x_val) & (df.y == y_val)).mean())
    other = float((df.x != x_val).mean())
    marginal = float((df.y == y_val).mean())
    if bool(x_val) == (direction == "non_decreasing"):
        return marginal, same + other
    return same, marginal


# ---------------------------------------------------------------------------
# What it cost
# ---------------------------------------------------------------------------


def test_the_old_rule_excluded_the_truth_at_the_bottom_of_the_order():
    """The measurement, on the frame the numbers below are hand-checkable on.

    ``P(Y=False | do(X=True))`` is 0.50. The old rule bracketed it in
    [0.56, 0.66] — an interval entirely above the answer, not a wide one.
    """
    df = _frame()
    truth = _truth(arm=True, value=False)
    assert truth == pytest.approx(0.50)
    lo, hi = _the_rule_this_replaced(
        df, x_val=True, y_val=False, direction="non_decreasing")
    assert (lo, hi) == pytest.approx((0.56, 0.66))
    assert not lo <= truth <= hi


def test_the_bound_now_contains_it_end_to_end():
    _, row = _mtr_row(_program(target_value=False))
    assert row is not None
    assert (row["lower_value"], row["upper_value"]) == pytest.approx(
        (0.10, 0.56))
    assert row["lower_value"] <= _truth(arm=True, value=False) \
        <= row["upper_value"]


def test_the_verifier_accepts_the_corrected_row():
    result, row = _mtr_row(_program(target_value=False))
    assert row is not None
    themis.verify_bounds_results(_program(target_value=False), result)


def test_the_top_of_the_order_is_where_the_old_rule_was_right():
    """Not a coincidence and worth pinning: at ``y = y_max`` the general form
    reduces to the old one exactly, which is why the defect survived every
    test written about it."""
    df = _frame()
    old = _the_rule_this_replaced(
        df, x_val=True, y_val=True, direction="non_decreasing")
    _, row = _mtr_row(_program(target_value=True))
    assert (row["lower_value"], row["upper_value"]) == pytest.approx(old)
    assert (row["lower_value"], row["upper_value"]) == pytest.approx(
        (0.44, 0.90))


# ---------------------------------------------------------------------------
# The order is a fact about the outcome's TYPE where it has one
# ---------------------------------------------------------------------------


def test_a_boolean_domain_is_read_in_the_order_bools_have():
    """``domain: [true, false]`` is how these programs habitually list a
    boolean. A declaration records the levels in the order they were WRITTEN
    because for a labelled column that is the only order there is — reading it
    as "false is the higher level" here would tighten the wrong side just as
    surely as reading no order at all."""
    _, backwards = _mtr_row(_program(target_value=True,
                                     domain=(True, False)))
    _, forwards = _mtr_row(_program(target_value=True,
                                    domain=(False, True)))
    assert backwards["lower_expression"] == forwards["lower_expression"]
    assert backwards["lower_expression"] == "P(y=true)"


def test_an_outcome_declared_nominal_gets_no_mtr_row_at_all():
    """"Monotone in an unordered variable" is not a weaker assumption but an
    empty one, so the method does not fire rather than firing loosely."""
    _, row = _mtr_row(_program(target_value=True, scale="nominal"))
    assert row is None


# ---------------------------------------------------------------------------
# The contrast — the quantity the effect query actually asked
# ---------------------------------------------------------------------------


def test_the_contrast_is_reported_and_contains_the_true_effect():
    _, row = _mtr_row(_program(target_value=True))
    contrast = row["contrast"]
    assert contrast["kind"] == "ace"
    assert contrast["reference_value"] is False
    ace = _truth(arm=True, value=True) - _truth(arm=False, value=True)
    assert ace == pytest.approx(0.30)
    assert (contrast["lower_value"], contrast["upper_value"]) == \
        pytest.approx((0.0, 0.80))
    assert contrast["lower_value"] <= ace <= contrast["upper_value"]


def test_the_contrast_carries_the_sign_the_assumption_asserts():
    """Half the logically possible range is excluded on every dataset: the
    assumption says the effect on the TOP level has a sign, and the interval
    is where that shows up rather than in a sentence beside it."""
    _, row = _mtr_row(_program(target_value=True))
    assert row["contrast"]["lower_value"] == pytest.approx(0.0)


def test_the_contrast_is_sharp_and_says_so():
    _, row = _mtr_row(_program(target_value=True))
    assert row["contrast"]["tightness"] == "sharp"


# ---------------------------------------------------------------------------
# Soundness and sharpness, over cardinalities and both directions
# ---------------------------------------------------------------------------


def _simulate(rng, levels, direction, n=20000):
    """A confounded world in which MTR genuinely holds."""
    k = len(levels)
    u = rng.random(n)
    x = rng.random(n) < (0.2 + 0.6 * u)
    base = rng.integers(0, k, size=n)
    step = (rng.random(n) < (0.3 + 0.5 * u)).astype(int) * rng.integers(
        0, k, size=n)
    hi = np.minimum(base + step, k - 1)
    lo_rank, hi_rank = (base, hi) if direction == "non_decreasing" \
        else (hi, base)
    arr = np.array(levels)
    return (pd.DataFrame({"x": x, "y": arr[np.where(x, hi_rank, lo_rank)]}),
            arr[lo_rank], arr[hi_rank])


def _attained(df, levels, direction, x_val, y_val, endpoint):
    """P(Y(x)=y) in an MTR world that reproduces the data exactly and pushes
    the queried event as far as the assumption allows — the sharpness oracle.

    Constructed rather than asserted: a bound is sharp when some admissible
    world sits on it, and this builds that world, checks it still satisfies
    MTR against every unit's own observation, and reads the value off.
    """
    order = {v: i for i, v in enumerate(levels)}
    up = bool(x_val) == (direction == "non_decreasing")
    extreme = levels[-1] if up else levels[0]
    out = []
    for xi, yi in zip(df["x"].to_numpy(), df["y"].to_numpy()):
        if bool(xi) == bool(x_val):
            out.append(yi)                       # observed at the queried arm
            continue
        reachable = (order[yi] <= order[y_val]) if up \
            else (order[yi] >= order[y_val])
        if endpoint == "upper":
            out.append(y_val if reachable else yi)
        elif yi != y_val or y_val == extreme:
            out.append(yi)                       # already off y, or forced on
        else:
            out.append(levels[order[y_val] + (1 if up else -1)])
    counterfactual = np.array(out)
    for xi, yi, cf in zip(df["x"].to_numpy(), df["y"].to_numpy(),
                          counterfactual):
        if bool(xi) == bool(x_val):
            continue
        assert (order[cf] >= order[yi]) if up else (order[cf] <= order[yi])
    return float((counterfactual == y_val).mean())


@pytest.mark.parametrize("levels", [[False, True], [0, 1, 2], [0, 1, 2, 3]])
@pytest.mark.parametrize(
    "direction", ["non_decreasing", "non_increasing"])
def test_every_position_in_the_order_is_bracketed_and_sharp(levels, direction):
    rng = np.random.default_rng(7)
    df, arm0, arm1 = _simulate(rng, levels, direction)
    for x_val in (True, False):
        truth_arm = arm1 if x_val else arm0
        for y_val in levels:
            nb = evaluate_manski_tamer_bounds(
                df, treatment="x", outcome="y", monotonicity=direction,
                outcome_levels=levels, treatment_value=x_val,
                outcome_value=y_val, ci_bootstrap=0)
            truth = float((truth_arm == y_val).mean())
            assert nb.lower_value <= truth <= nb.upper_value, (
                f"do(x={x_val}) y={y_val}: {nb.lower_value}..{nb.upper_value} "
                f"excludes {truth}")
            assert nb.lower_value == pytest.approx(_attained(
                df, levels, direction, x_val, y_val, "lower"))
            assert nb.upper_value == pytest.approx(_attained(
                df, levels, direction, x_val, y_val, "upper"))


@pytest.mark.parametrize("levels", [[False, True], [0, 1, 2]])
def test_the_contrast_brackets_the_true_effect_at_every_level(levels):
    rng = np.random.default_rng(11)
    df, arm0, arm1 = _simulate(rng, levels, "non_decreasing")
    for y_val in levels:
        nb = evaluate_manski_tamer_bounds(
            df, treatment="x", outcome="y", monotonicity="non_decreasing",
            outcome_levels=levels, treatment_value=True,
            outcome_value=y_val, ci_bootstrap=0)
        ace = float((arm1 == y_val).mean()) - float((arm0 == y_val).mean())
        assert nb.contrast is not None
        assert nb.contrast["lower_value"] <= ace <= nb.contrast["upper_value"]


def test_a_column_value_outside_the_declared_levels_is_refused_not_placed():
    """A value the declaration does not name has no position in the order, and
    the order is the whole of what the bound is computed from."""
    df, _, _ = _simulate(np.random.default_rng(1), [0, 1, 2],
                         "non_decreasing", n=500)
    with pytest.raises(ValueError, match="outside the declared levels"):
        evaluate_manski_tamer_bounds(
            df, treatment="x", outcome="y", monotonicity="non_decreasing",
            outcome_levels=[0, 1], treatment_value=True,
            outcome_value=1, ci_bootstrap=0)


def test_a_target_event_outside_the_declared_levels_is_refused():
    """Where the event sits in the order is what decides the bound, so an
    event with no place in the order is unanswerable rather than wide."""
    df, _, _ = _simulate(np.random.default_rng(2), [0, 1, 2],
                         "non_decreasing", n=500)
    with pytest.raises(ValueError, match="not one of the outcome's declared"):
        evaluate_manski_tamer_bounds(
            df, treatment="x", outcome="y", monotonicity="non_decreasing",
            outcome_levels=[0, 1, 2], treatment_value=True,
            outcome_value=9, ci_bootstrap=0)


def test_a_declared_level_the_sample_never_shows_still_sets_the_top():
    """The order is DECLARED, not observed. A level with no rows in it moves
    where the top is, and with it which side the assumption tightens — so a
    method reading the observed levels would tighten past what MTR supports.
    """
    df = _frame()
    kwargs = dict(treatment="x", outcome="y",
                  monotonicity="non_decreasing", treatment_value=True,
                  outcome_value=1, ci_bootstrap=0)
    at_top = evaluate_manski_tamer_bounds(df, outcome_levels=[0, 1], **kwargs)
    below_top = evaluate_manski_tamer_bounds(
        df, outcome_levels=[0, 1, 2], **kwargs)
    assert at_top.lower_value == pytest.approx(0.44)      # forced, = P(Y=1)
    assert below_top.lower_value == pytest.approx(0.34)   # nothing forced


# ---------------------------------------------------------------------------
# The verifier's own noes
# ---------------------------------------------------------------------------


def _verifiable(target_value=True):
    program = _program(target_value=target_value)
    result, row = _mtr_row(program)
    assert row is not None
    return program, copy.deepcopy(result), row["method"]


def _refused(program, result, match):
    with pytest.raises(VerificationError, match=match):
        themis.verify_bounds_results(program, result)


def _row_of(result):
    return [b for b in result["bounds_results"]
            if b["method"] == "manski_tamer_monotonicity"][0]


def test_a_row_that_read_a_different_order_is_refused():
    """The root cause, made into a gate: the producer records the order it
    read, the verifier derives one from the program, and two orders are two
    different bounds rather than one bound described twice."""
    program, result, _ = _verifiable()
    _row_of(result)["sufficient_statistics"]["outcome_levels"] = [True, False]
    _refused(program, result, "recorded the outcome order")


def test_a_row_that_placed_the_event_elsewhere_in_the_order_is_refused():
    program, result, _ = _verifiable()
    _row_of(result)["sufficient_statistics"]["arm_outcome_index"] = 0
    _refused(program, result, "position")


def test_an_interval_the_recorded_counts_do_not_yield_is_refused():
    program, result, _ = _verifiable()
    _row_of(result)["lower_value"] = 0.30
    _refused(program, result, "lower_expression|lower_value")


def test_a_contrast_the_recorded_counts_do_not_yield_is_refused():
    program, result, _ = _verifiable()
    _row_of(result)["contrast"]["lower_value"] = 0.05
    _refused(program, result, r"contrast\.lower_value")


def test_a_contrast_with_no_counts_under_it_is_refused():
    program, result, _ = _verifiable()
    _row_of(result).pop("sufficient_statistics")
    _refused(program, result, "without the joint counts")


def test_counts_that_do_not_add_up_to_the_sample_are_refused():
    program, result, _ = _verifiable()
    _row_of(result)["sufficient_statistics"]["n_xy"][0][0] += 7
    _refused(program, result, "counts total")


def test_a_baseline_arm_the_recorded_levels_do_not_name_is_refused():
    program, result, _ = _verifiable()
    _row_of(result)["contrast"]["reference_value"] = True
    _refused(program, result, "as the baseline arm")
