"""A block that is absent is not a block nobody has to explain.

Since the precision budget moved to a single walk, a budget hangs wherever
an interval does, and it is what holds that interval's two endpoints: move
one and the half-width beside it stops agreeing. So the rows of a
dose-response curve are held — except the first, which has no budget, and
whose two endpoints could therefore be moved anywhere at all.

The first row is the reference dose. Its effect is a dose contrasted with
itself, which is zero by construction, and its interval is [0, 0], which the
producer writes literally. Two silences met on that row. The audit asked
only that the reference interval BRACKET zero — what one asks of an ESTIMATE
that came out null — so [-5, 0] passed it. And the budget is computed from a
half-width, so a width of zero returned None and no budget was attached,
which is right about the budget (halving nothing buys nothing, and a share
of zero was already refused) and was read as though it were right about the
row.

Both halves are the same sentence this repository keeps meeting: a skip and
a refusal look the same in the code and mean the opposite. Here it is on the
producer's side, and the absence travelled — nothing downstream could tell a
budget that could not be computed from a budget somebody removed.

So the absence is given a meaning it can be held to. A node carrying an
interval and no budget says one of exactly two things: an endpoint is not
there, or the width is zero. Measured over every answer shape this system
produces before the rule was written: sixty-three intervals priced,
forty-three with an endpoint missing, three degenerate, none unexplained.
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
import pathlib

import pytest

import themis
from tests.answer_corpus import the_door_for
from themis.verifier import verify_envelope_arithmetic
from themis.verifier.errors import VerificationError
from themis.verifier.verify import verify_dose_response_curve

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: Every shape whose answer IS a curve over a SAMPLED continuous dose — the
#: convention with a reference row. A curve over a polytomous exposure's
#: declared states samples nothing and carries no reference row at all,
#: because a level contrasted with itself is not one of its answers; it is
#: re-derived row by row from recorded statistics instead. So the marker is
#: the sampling, read off the snapshot rather than listed.
CURVES = sorted(
    name for name, pair in SHAPES.items()
    if isinstance(pair["result"].get("numeric_estimate"), dict)
    and pair["result"]["numeric_estimate"].get("sampling_points") is not None
)


def _pair(method: str):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _nodes(node, path=()):
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from _nodes(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _nodes(value, path + (index,))


def _at(root, path):
    for step in path:
        root = root[step]
    return root


# -------------------------------------- the row the curve is measured from


def test_the_reference_row_is_the_one_row_with_nothing_pricing_it():
    """The fact the whole frontier rests on, stated so it cannot drift.

    A budget prices the WIDTH of an interval — what it would cost to halve
    it — so a row carries one exactly when it has a width to be about.
    The reference row never does: its interval is the point zero to zero,
    because the effect of the reference dose on itself is zero by
    construction.

    Which is why this is not stated as "row zero and no other". A curve
    that reports no interval on any row has nothing to price on any row,
    and one in the corpus is exactly that — a bridge estimate that
    published points without intervals. Pinned as "row zero", that curve
    reads as three missing budgets; pinned as the rule the budgets
    actually follow, it reads as what it is.
    """
    assert CURVES
    for name in CURVES:
        estimate = SHAPES[name]["result"]["numeric_estimate"]
        curve = estimate["dose_response_curve"]
        priced = [i for i, row in enumerate(curve)
                  if "precision_budget" in row]
        has_width = [
            i for i, row in enumerate(curve)
            if row.get("ci_lower") is not None
            and row.get("ci_upper") is not None
            and row["ci_upper"] > row["ci_lower"]]
        assert priced == has_width, (name, priced, has_width)
        assert 0 not in priced, (name, priced)
        assert curve[0]["x"] == estimate["reference_point"]
        assert curve[0]["effect"] == 0.0
        if curve[0]["ci_lower"] is not None:
            assert curve[0]["ci_lower"] == 0.0 and curve[0]["ci_upper"] == 0.0


@pytest.mark.parametrize("shape", CURVES)
@pytest.mark.parametrize("leaf,forged", [
    ("ci_upper", 5.0),
    ("ci_lower", -5.0),
    ("effect", 5.0),
])
def test_nothing_at_the_reference_dose_can_be_moved(shape, leaf, forged):
    """Both endpoints and the effect. The endpoints are the pair that used
    to be free, and the effect is here so the row is asked as a whole."""
    program, result = _pair(shape)
    result["numeric_estimate"]["dose_response_curve"][0][leaf] = forged
    with pytest.raises(VerificationError):
        themis.verify(program, result)


@pytest.mark.parametrize("shape", CURVES)
def test_an_interval_that_brackets_zero_is_not_an_interval_of_zero(shape):
    """The forgery the old wording admitted.

    ``[-0.4, 0.4]`` contains zero, and a null ESTIMATE with that interval
    would be perfectly honest. This row is not an estimate: a dose
    contrasted with itself has no sampling variability for an interval to
    report. Asked at the rule, because the absence rule beside it reaches
    the same edit — which is the arrangement working rather than this one
    being unnecessary.
    """
    program, result = _pair(shape)
    row = result["numeric_estimate"]["dose_response_curve"][0]
    row["ci_lower"], row["ci_upper"] = -0.4, 0.4
    with pytest.raises(VerificationError, match="contrasted with itself"):
        verify_dose_response_curve(result["numeric_estimate"])
    with pytest.raises(VerificationError):
        themis.verify(program, result)


# ------------------------------------------- a price that is not there speaks


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_a_budget_cannot_be_deleted_to_free_what_it_priced(shape):
    """The attack a census that bends one leaf at a time cannot see.

    Remove the budget, then move the endpoint it used to price. Every shape
    that carries a budget at all, at whatever depth its first one sits.
    """
    program, result = _pair(shape)
    estimate = result.get("numeric_estimate")
    if not isinstance(estimate, dict):
        pytest.skip("no numeric estimate on this shape")
    victims = [p for p, node in _nodes(estimate)
               if "precision_budget" in node]
    if not victims:
        pytest.skip("this shape prices no interval")
    node = _at(estimate, victims[0])
    del node["precision_budget"]
    node["ci_upper"] = node["ci_upper"] + 5.0
    # Asked at the door that READS this answer. Three answers in the corpus
    # carry a priced interval and no reasoning chain, and the chain door
    # refuses those for the missing chain — a refusal that never looks at
    # the budget, and would have been scored here as this attack failing.
    with pytest.raises(VerificationError):
        the_door_for(result)(program, result)


def test_an_absence_the_envelope_explains_is_left_alone():
    """Silence with a reason on the envelope is an answer, not a hole.

    Two reasons exist and both must pass: an endpoint that is not there —
    forty-three such nodes across the snapshot — and a width of zero, which
    is the reference row itself.
    """
    seen_null = seen_degenerate = 0
    for name, pair in sorted(SHAPES.items()):
        estimate = pair["result"].get("numeric_estimate")
        if not isinstance(estimate, dict):
            continue
        for _, node in _nodes(estimate):
            if "ci_lower" not in node or "ci_upper" not in node:
                continue
            if "precision_budget" in node:
                continue
            if node["ci_lower"] is None or node["ci_upper"] is None:
                seen_null += 1
            elif node["ci_upper"] == node["ci_lower"]:
                seen_degenerate += 1
        verify_envelope_arithmetic(pair["result"])
    assert seen_null and seen_degenerate


def test_a_run_that_prices_nothing_is_not_asked_why():
    """The producer attaches no budget anywhere without a sample to
    narrow, so on such an envelope the absence carries no information and
    the question is not put."""
    verify_envelope_arithmetic({"numeric_estimate": {
        "sample_size": 0, "ci_lower": 0.1, "ci_upper": 0.9, "point": 0.5,
    }})
    with pytest.raises(VerificationError, match="no precision_budget"):
        verify_envelope_arithmetic({"numeric_estimate": {
            "sample_size": 400, "ci_lower": 0.1, "ci_upper": 0.9,
            "point": 0.5,
        }})


def test_the_question_reaches_wherever_an_interval_sits():
    """The same walk that prices a budget asks after a missing one, so a
    block added under a new name arrives at both."""
    with pytest.raises(VerificationError, match="no precision_budget"):
        verify_envelope_arithmetic({"numeric_estimate": {
            "sample_size": 400,
            "a_block_nobody_has_written_yet": {
                "ci_lower": 0.1, "ci_upper": 0.9, "point": 0.5,
            },
        }})


# --------------------------------------- and the pricing itself happens once


def test_pricing_is_done_once_on_the_way_out_and_not_route_by_route():
    """What made the reader's side of this checkable at all.

    The walk inside the pricer has said "wherever a budget appears, and not
    at a list of places it is known to appear" since it was written — but
    CALLING it was a list: twenty-six sites, one at the end of each route
    whose author remembered, two of them behind an ``if`` that priced only
    the answers with a point. So a block attached after its route's call, or
    a route that reported an interval without a point, reached a reader
    unpriced — and unpriced is unheld.

    Written as a gate over the source, because a twenty-seventh call added
    at the end of the next route is exactly how this comes back, and it
    would look like diligence.
    """
    import themis.estimation.dispatch as dispatch

    source = pathlib.Path(inspect.getsourcefile(dispatch)).read_text(
        encoding="utf-8")
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name)
             and node.func.id == "_attach_precision_budget"]
    assert len(calls) == 1, [node.lineno for node in calls]

    door = next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
                and node.name == "_estimate_program")
    assert calls[0] in list(ast.walk(door))


def test_an_answer_with_an_interval_and_no_point_is_priced_too():
    """One of the two conditional call sites priced only the answers that
    came out as a point. An identified SET has an interval a reader is shown
    and narrows the same way; what it has no room for is the ratio to a
    point, which is a fact about that one figure.
    """
    estimate = {"sample_size": 4000, "counterfactual_cell": {
        "lower": 0.2, "upper": 0.9, "point": None,
        "ci_lower": 0.216, "ci_upper": 1.0,
    }}
    from themis.estimation.dispatch import _attach_precision_budget

    _attach_precision_budget(estimate)
    budget = estimate["counterfactual_cell"]["precision_budget"]
    assert budget["current_ci_half_width"] == pytest.approx(0.392, abs=5e-4)
    assert "relative_width" not in budget
    verify_envelope_arithmetic({"numeric_estimate": estimate})
