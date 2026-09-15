"""A time-varying answer is held to the specification it was fitted from.

``options.longitudinal`` is the caller's own words — which strategies to
contrast, how many forward simulations to draw, whether the IP weights are
stabilized — and the numeric block repeats them beside its numbers, where a
reader is shown them. Nothing read them: the rule auditing that block is
handed the estimate alone, so every leaf it holds is one it recomputes from
the block's own figures, and the rule that does read the option block audits
the identification half of the answer. The four leaves the sweep declared
unwitnessed on the two longitudinal rows were exactly those copies.

The leaves are named here rather than read out of the table the rule uses: a
test that asks the implementation which claims it checks agrees with it about
the answer.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.verifier import VerificationError

SHAPES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

#: The option every one of these answers repeats, per block.
COPIED = {
    "longitudinal_gformula": ("strategy_treated", "strategy_control", "n_sim"),
    "longitudinal_ipw_msm": ("strategy_treated", "strategy_control", "stabilized"),
}


def _bend(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return type(value)(value + 7)
    return "forged"


def test_both_stored_longitudinal_answers_are_accepted():
    for name in COPIED:
        pair = SHAPES[name]
        themis.verify_answer_claims(pair["program"], pair["result"])


@pytest.mark.parametrize("name", sorted(COPIED))
def test_an_answer_that_restates_a_specification_nobody_wrote_is_refused(name):
    pair = SHAPES[name]
    block = pair["result"]["numeric_estimate"][name]
    for leaf in COPIED[name]:
        assert leaf in block, leaf
        forged = copy.deepcopy(pair["result"])
        forged["numeric_estimate"][name][leaf] = _bend(block[leaf])
        with pytest.raises(VerificationError):
            themis.verify_answer_claims(pair["program"], forged)


def test_a_level_written_as_an_integer_and_as_a_float_is_one_level():
    """A caller writes ``1``; an estimator that declares the level a float
    records ``1.0``. Those are one level, and neither is the boolean."""
    from themis.verifier.program_copy_rules import _one_option_value

    assert _one_option_value(1, 1.0) and _one_option_value(1.0, 1)
    assert not _one_option_value(True, 1)
    assert not _one_option_value(False, 0)
    assert _one_option_value(True, True) and _one_option_value(False, False)


def test_a_program_that_declares_nothing_still_pins_the_estimators_default():
    """Silence in the program is not freedom in the answer: the block shows a
    value either way, and the value it may show is the estimator's default."""
    from themis.verifier.program_copy_rules import verify_longitudinal_option_copy

    program = {"version": "0.1", "domain": {"objects": []}, "statements": [],
               "options": {"longitudinal": {"treatments": ["a0"],
                                            "confounders_by_time": [["l0"]],
                                            "outcome": "y"}}}
    honest = {"longitudinal_ipw_msm": {"stabilized": True, "strategy_treated": 1,
                                       "strategy_control": 0}}
    verify_longitudinal_option_copy(honest, program)
    for leaf, forged in (("stabilized", False), ("strategy_treated", 2),
                         ("strategy_control", 1)):
        bad = copy.deepcopy(honest)
        bad["longitudinal_ipw_msm"][leaf] = forged
        with pytest.raises(VerificationError):
            verify_longitudinal_option_copy(bad, program)


def test_what_the_program_declares_beats_the_default():
    """A caller who asks for Horvitz-Thompson weights gets an answer that says
    so, and the default is then the wrong thing to hold it to."""
    from themis.verifier.program_copy_rules import verify_longitudinal_option_copy

    program = {"version": "0.1", "domain": {"objects": []}, "statements": [],
               "options": {"longitudinal": {"treatments": ["a0"],
                                            "confounders_by_time": [["l0"]],
                                            "outcome": "y",
                                            "stabilized": False,
                                            "strategy_control": -1}}}
    verify_longitudinal_option_copy(
        {"longitudinal_ipw_msm": {"stabilized": False, "strategy_control": -1}},
        program)
    with pytest.raises(VerificationError):
        verify_longitudinal_option_copy(
            {"longitudinal_ipw_msm": {"stabilized": True}}, program)
