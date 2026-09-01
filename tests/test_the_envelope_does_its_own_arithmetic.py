"""What an interval costs was arithmetic, and nobody did it twice.

"Your interval is 0.046 wide, that is 21% of the effect, and 4000 subjects
would halve it" states three sums over the interval, the point and the
sample size sitting beside them on the same envelope.

None of it was checked. The derivation records what the estimator did, not
the sums taken afterwards, so the rule that holds the reader's copy to the
record had nothing to hold these against. Ninety-seven leaves of the sweep
in ``test_every_answer_shape_is_asked_the_same_question`` were this, and
the most actionable figure this system prints -- go and collect four
thousand more subjects -- is the one no reader would recompute by hand.

Nothing had to be recorded to close them: every input is already on the
envelope. That is what makes this a different species from the audits that
re-derive an estimator. There is no independence question, because there is
no second implementation -- only an identity that holds or does not.

WHAT WAS MEASURED AND LEFT OUT. Eight candidate relations were measured
against all forty-four shapes. Two failed on honest answers and are pinned
below as failures, so nobody adds them back from first principles:
``additive_interaction`` is not the sum of the two interaction terms, and
the two blocks that each report a proportion mediated do not agree on the
logit scale. Three more held and are STILL left out: re-running the sweep
with and without them closed exactly the same leaves, because
``verify_mediation_numeric`` already holds every one.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.verifier import verify_envelope_arithmetic
from themis.verifier.errors import VerificationError

SHAPES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

FRONTDOOR = SHAPES["frontdoor_linear"]
MEDIATION = SHAPES["mediation_linear_imai"]
LOGIT = SHAPES["mediation_logit_imai"]
CURVE = SHAPES["dose_response_linear_dml"]
JOINT = SHAPES["joint_backdoor_linear"]


def _blocks(node, path=()):
    """Every dict on the envelope, named — because a budget appears wherever
    a sub-answer carries one, not at a list of known places."""
    if isinstance(node, dict):
        yield ".".join(path) or "numeric_estimate", node
        for key, value in node.items():
            yield from _blocks(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _blocks(value, path + (f"[{index}]",))


def _bend(pair, path, value):
    """One figure moved, everything else left as the run produced it."""
    bad = copy.deepcopy(pair["result"])
    node = bad["numeric_estimate"]
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return bad


# ================================================================ honest first


@pytest.mark.parametrize("method", sorted(SHAPES))
def test_every_shape_the_suite_produces_still_verifies(method):
    """First, and every shape, because an identity is asserted over all of
    them at once: one shape that computes a ratio differently would be
    refused by a rule written from the others."""
    themis.verify(SHAPES[method]["program"], SHAPES[method]["result"])


# ========================================================== the interval's price


@pytest.mark.parametrize("field,value", [
    ("current_ci_half_width", 0.9),
    ("relative_width", 0.01),
    ("n_to_halve_ci", 999),
])
def test_a_budget_the_interval_does_not_support_is_refused(field, value):
    """The three sums, each moved on its own. A budget is what a reader
    acts on — it is the difference between commissioning another study and
    not — and it rested on nothing."""
    bad = _bend(FRONTDOOR, ("precision_budget", field), value)
    with pytest.raises(VerificationError, match="producer's word twice"):
        themis.verify(FRONTDOOR["program"], bad)


def test_moving_the_interval_under_a_budget_is_refused_too():
    """The mirror: leave the budget and move what it prices. Either edit
    breaks the identity, which is what makes it an identity rather than a
    copy of one side."""
    bad = _bend(FRONTDOOR, ("ci_upper",),
                FRONTDOOR["result"]["numeric_estimate"]["ci_upper"] + 0.5)
    with pytest.raises(VerificationError):
        themis.verify(FRONTDOOR["program"], bad)


def test_a_budget_pricing_no_interval_is_refused():
    """Arithmetic with nothing at stake. A budget beside no interval cannot
    be wrong, and a check that let it through would be reporting that."""
    estimate = copy.deepcopy(FRONTDOOR["result"]["numeric_estimate"])
    estimate.pop("ci_lower")
    with pytest.raises(VerificationError, match="not beside it"):
        verify_envelope_arithmetic({"numeric_estimate": estimate})


def test_the_rounding_a_reader_is_shown_is_allowed_and_no_more():
    """The half width reaches a reader rounded to six places, so the
    comparison allows half a place. A tolerance wider than the rounding
    would start accepting numbers that are not the rounding of anything."""
    estimate = FRONTDOOR["result"]["numeric_estimate"]
    shown = estimate["precision_budget"]["current_ci_half_width"]
    themis.verify(FRONTDOOR["program"],
                  _bend(FRONTDOOR, ("precision_budget",
                                    "current_ci_half_width"),
                        shown + 4e-7))
    with pytest.raises(VerificationError):
        themis.verify(FRONTDOOR["program"],
                      _bend(FRONTDOOR, ("precision_budget",
                                        "current_ci_half_width"),
                            shown + 1e-5))


# ===================================================== the decomposition's sums


@pytest.mark.parametrize("path", [
    ("decomposition", "te", "point"),
    ("decomposition", "proportion_mediated", "point"),
    ("four_way_decomposition", "te", "point"),
    ("four_way_decomposition", "prop_mediated", "point"),
    ("four_way_decomposition", "prop_interaction", "point"),
    ("four_way_decomposition", "pie", "point"),
])
def test_the_decompositions_own_sums_are_already_held(path):
    """These are the same species and they were ALREADY checked.

    A mediation total is its two parts; a four-way split obeys the identity
    the block cites in its own ``reference`` field. Both were written into
    this module's rule, and re-running the leaf sweep with and without them
    closed exactly the same leaves — ``verify_mediation_numeric`` holds
    every one. The rule was taken out again and these stay, so the next
    reader finds the measurement instead of repeating it: a second rule
    restating a check is not a second opinion, it is a second place for the
    same thing to be wrong.
    """
    with pytest.raises(VerificationError):
        themis.verify(MEDIATION["program"], _bend(MEDIATION, path, 0.5))


# ================================================================ denominator


def test_the_relations_that_were_measured_and_are_not_asserted():
    """Two guesses that failed on real answers, kept as tests so nobody
    adds them back from first principles.

    ``additive_interaction`` is not the two interaction terms added up, and
    the two blocks that each report a proportion mediated do NOT agree on
    the logit scale — they decompose differently. Either asserted would
    refuse the honest answers below.
    """
    four_way = MEDIATION["result"]["numeric_estimate"]["four_way_decomposition"]
    parts = four_way["intref"]["point"] + four_way["intmed"]["point"]
    assert abs(four_way["additive_interaction"] - parts) > 1e-6

    estimate = LOGIT["result"]["numeric_estimate"]
    natural = estimate["decomposition"]["proportion_mediated"]["point"]
    four = estimate["four_way_decomposition"]["prop_mediated"]["point"]
    assert abs(natural - four) > 1e-6
    themis.verify(LOGIT["program"], LOGIT["result"])


def test_a_curve_point_carries_a_budget_and_it_is_held_too():
    """The exception that turned out not to be one.

    Every point of a dose-response curve carries its own budget, and none
    of them is four times the run's sample. That read as a slice with a
    sample of its own, and the rule was written to decline it. It was the
    rounding that was missing: to the next fifty they hold exactly, the
    exception came out, and three more leaves closed with it. A special
    case is a hypothesis about why something does not fit.
    """
    estimate = CURVE["result"]["numeric_estimate"]
    budgets = [point["precision_budget"]["n_to_halve_ci"]
               for point in estimate["dose_response_curve"]
               if "precision_budget" in point]
    assert budgets, "the fixture is expected to carry per-point budgets"
    assert any(n != 4 * estimate["sample_size"] for n in budgets)
    themis.verify(CURVE["program"], CURVE["result"])

    forged = copy.deepcopy(CURVE["result"])
    for point in forged["numeric_estimate"]["dose_response_curve"]:
        if "precision_budget" in point:
            point["precision_budget"]["n_to_halve_ci"] = 12345
            break
    with pytest.raises(VerificationError, match="n_to_halve_ci"):
        themis.verify(CURVE["program"], forged)


# =========================================================== a share of nothing


def test_no_honest_answer_states_a_share_of_a_figure_it_does_not_have():
    """The denominator, first: refusing a shape the suite really produces
    would be worse than the hole below, so the hole is only closable if
    nothing honest lands in it."""
    for method, pair in sorted(SHAPES.items()):
        for where, node in _blocks(pair["result"].get("numeric_estimate")):
            budget = node.get("precision_budget")
            if not isinstance(budget, dict):
                continue
            if budget.get("relative_width") is None:
                continue
            assert node.get("point") or node.get("effect"), (
                f"{method}:{where} states a share of a figure that is zero "
                f"or absent")


def test_a_share_of_nothing_is_refused_rather_than_skipped():
    """The guard read ``if point:``, written to keep a zero out of a
    denominator. Skipping is not what a zero denominator means: it means the
    ratio beside it cannot be right, and saying nothing about it is the one
    outcome the figure does not support."""
    bad = _bend(JOINT, ("joint_effect", "point"), 0.0)
    with pytest.raises(VerificationError, match="share OF is zero or absent"):
        themis.verify(JOINT["program"], bad)


def test_the_answer_that_zero_walked_out_with():
    """Why it was worth finding. The point estimate of intervening on two
    treatments at once was held by NOTHING except that ratio, so the skip
    was not a gap in an arithmetic check — it was an answer a reader acts on
    passing the public door with any value the forger liked.

    Every kind of lie, because "held" was a fact about the single edit the
    sweep happened to try until it was asked more than once.
    """
    shown = JOINT["result"]["numeric_estimate"]["joint_effect"]["point"]
    for forged in (0.0, shown * 3 + 1, -shown - 1, shown / 2):
        with pytest.raises(VerificationError):
            themis.verify(JOINT["program"],
                          _bend(JOINT, ("joint_effect", "point"), forged))
