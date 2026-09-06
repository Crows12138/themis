"""The report's headline word had two authors and one of them was guessing.

#588. ``data_gap_report.answer_tier`` tells a reader what answer is still
available: a point, an interval, or none. It is written at identification
time from the question, the status, the gap species and the interval in
hand — and written again by the estimation layer once an answer exists,
because by then the question has changed tense. That second write is not
the defect. What was, is HOW the second author decided what came out.

It read a hand-written set of gap species meaning "no point came out". The
set had one member, would have needed a new one for every estimator that
answers in some other shape, and said POINT for the two bimodal methods'
bounded halves — which is the whole reason a second finaliser existed to
say otherwise. Three literals, three answers to one question.

The question already had an answer. :mod:`themis.answers` has declared
since #543 which shape each method's estimate comes out in, and a shape is
a way of answering: a point, an interval, or neither. So the shapes say
which tier they deliver, and both the estimation layer and the verifier
ask them instead of naming species.

What that buys is the verifier. Recomputing the tier used to refuse six
honest answers in this repository's own corpus — all six the ones the
estimation layer had corrected — so the rule held two one-sided claims and
350 of the 470 wrong words a reader could be told survived it. With the
answer's shape readable on the envelope, the recomputation reproduces all
242 and the remainder is nothing.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

import themis
from themis import answers, blocks
from themis.answers import Shape
from themis.estimation.dispatch import _retier_to_what_came_out
from themis.registry import NoRowDeclared
from themis.types import AnswerTier
from themis.verifier.data_gap_rules import (
    _AN_ANSWER_THE_ESTIMATE_HAD_NO_ROOM_FOR, _A_SINGLE_NUMBER,
    _THE_THREE_PROBABILITIES, _TIER_OF_A_BLOCK_THE_ESTIMATE_CARRIES,
    _an_interval_is_in_hand, _the_tier_the_answer_came_out_as,
)

SHAPES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))


# --- a shape says which tier it is ---------------------------------------


def test_a_shape_cannot_be_declared_without_saying_what_it_delivers():
    """The binding, and the reason it needs no test to enforce coverage.

    ``Shape`` is a frozen dataclass and ``delivers`` has no default, so a
    tenth shape added without a tier does not reach a surface and render
    the wrong thing — it stops the import.
    """
    with pytest.raises(TypeError):
        Shape("nameless", carries="something", lives_in="somewhere")
    assert all(isinstance(s.delivers, AnswerTier) for s in answers.ALL)


def test_the_bimodal_pairs_deliver_different_tiers():
    """Not decoration: this is the distinction the species list could not
    make. Both halves of each pair come out of the same method, and what
    monotonicity buys is the difference between an interval and a point."""
    for sharper, bounded in ((answers.CAUSATION_POINTS,
                              answers.CAUSATION_BOUNDS),
                             (answers.POINT,
                              answers.COUNTERFACTUAL_CELL_BOUNDS)):
        assert sharper.delivers is AnswerTier.POINT
        assert bounded.delivers is AnswerTier.INTERVAL


def test_every_method_can_be_asked_what_tier_it_delivers():
    """The vocabulary is closed both ways already; this says the new field
    is total over it, so no estimate reaches the tier with nothing to say
    about itself."""
    for method, shapes in answers.SHAPES_OF.items():
        assert shapes, method
        assert all(s.delivers in AnswerTier for s in shapes), method


# --- and the estimation layer asks it ------------------------------------


def _result(estimate: dict | None) -> dict:
    result: dict = {"data_gap_report": {"gaps": [], "answer_tier": "point"}}
    if estimate is not None:
        result["numeric_estimate"] = estimate
    return result


def test_a_shape_that_is_not_a_number_overrides_the_road_that_produced_it():
    """The species list's one member, said by the answer instead.

    A proximal null test runs to completion down the road that means "a
    point for the estimand came out", and what came out is a test. The
    caller's word is POINT and the estimate's shape is what corrects it.
    """
    result = _result({"method": "proximal_null_test",
                      "no_effect_test": {"reject": False}})
    _retier_to_what_came_out(result, came_out=AnswerTier.POINT)
    assert result["data_gap_report"]["answer_tier"] == "none"


def test_the_bounded_half_of_a_bimodal_method_is_an_interval():
    """And the sharper half of the same method is not — which is what the
    species list got wrong and needed a second finaliser to paper over."""
    bounded = _result({"method": "causation_plugin",
                       "probabilities_of_causation": {
                           "pn": {"low": 0.1, "high": 0.6}}})
    _retier_to_what_came_out(bounded, came_out=AnswerTier.POINT)
    assert bounded["data_gap_report"]["answer_tier"] == "interval"

    sharp = _result({"method": "causation_plugin",
                     "probabilities_of_causation": {"pn": {"point": 0.4}}})
    _retier_to_what_came_out(sharp, came_out=AnswerTier.INTERVAL)
    assert sharp["data_gap_report"]["answer_tier"] == "point"


def test_a_road_that_ends_in_no_declared_shape_keeps_its_own_word():
    """``None`` from the shape table is not "no answer".

    Not every road to a number ends in a ``numeric_estimate``: the
    structural and plug-in roads write theirs elsewhere, and the vector-IV
    road ends in a confidence region over a treatment VECTOR that lives in
    an extension. Reading silence as "nothing came out" would overwrite a
    correct word on every one of them.
    """
    for estimate in (None, {"method": "iv_wald"}):
        result = _result(estimate)
        _retier_to_what_came_out(result, came_out=AnswerTier.INTERVAL)
        assert result["data_gap_report"]["answer_tier"] == "interval"


def test_a_method_this_build_does_not_declare_is_refused_not_tiered():
    """The other half of that silence, and why it is not a fall-through.

    An estimate whose method has no row is not an answer in some shape
    nobody wrote down — it is an estimator that reached the envelope
    without declaring what it produced, and the tier would be the first
    surface to quietly invent one for it.
    """
    with pytest.raises(NoRowDeclared):
        _retier_to_what_came_out(_result({"point": 0.3}),
                                 came_out=AnswerTier.POINT)


def test_a_result_with_no_report_is_not_given_one():
    result: dict = {"numeric_estimate": {"method": "iv_wald", "point": 0.3}}
    _retier_to_what_came_out(result, came_out=AnswerTier.POINT)
    assert "data_gap_report" not in result


# --- the verifier restates the same table --------------------------------


def test_the_restated_block_table_is_the_shape_vocabulary():
    """Restated rather than imported, for the reason every table in the
    verifier package is — and pinned here so a tenth shape arrives as a red
    suite rather than as a tier the rule cannot see."""
    restated = set(_TIER_OF_A_BLOCK_THE_ESTIMATE_CARRIES) | {
        _A_SINGLE_NUMBER, _THE_THREE_PROBABILITIES}
    assert restated == {s.lives_in for s in answers.ALL}
    for key, tier in _TIER_OF_A_BLOCK_THE_ESTIMATE_CARRIES.items():
        living_there = {s.delivers.value for s in answers.ALL
                        if s.lives_in == key}
        assert living_there == {tier}, key
    # The two held out are held out because presence is not what decides
    # them, and both are genuinely ambiguous on presence alone: a point of
    # ``0.0`` is an answer, and the causation block is on the envelope
    # whichever way the run went.
    assert {s.delivers.value for s in answers.ALL
            if s.lives_in == _THE_THREE_PROBABILITIES} == {"point", "interval"}


def test_the_two_readings_agree_on_every_estimate_this_repository_has():
    """The table above says the same words; this says the same answers.

    Two implementations of one reading — the producer walks the shapes its
    method declares, in the order that puts the sharper one first, and the
    verifier reads what the block carries and takes the strongest. They are
    not the same walk and they are not allowed to disagree, which is a
    thing to check rather than to arrange by sharing code.
    """
    seen = 0
    for name, pair in SHAPES.items():
        estimate = (pair["result"] or {}).get("numeric_estimate")
        if not isinstance(estimate, dict):
            continue
        seen += 1
        theirs = answers.tier_delivered(estimate)
        mine = _the_tier_the_answer_came_out_as(pair["result"])
        assert (None if theirs is None else theirs.value) == mine, name
    assert seen >= 80, seen


# --- an answer the estimate's fields had no room for ----------------------


def test_the_restated_answer_blocks_are_the_ones_with_no_carrier():
    """Restated from ``themis.blocks``, pinned to it here.

    A block the estimate carries is a display copy of a field the shape
    table already reads; counting it here would make one answer into two.
    """
    assert _AN_ANSWER_THE_ESTIMATE_HAD_NO_ROOM_FOR == {
        b.value for b in blocks.declared_as(blocks.Family.ANSWER)
        if b.carried_by is None}


def test_a_region_that_closed_is_an_interval_and_an_open_one_is_not():
    """The counterexample this channel needs to have been checked against.

    An unbounded region is written the same way a bounded one is — the
    same block, on the same road — and it brackets nothing. A channel that
    counted the block rather than its word would tell a reader an interval
    is available on every answer whose region failed to close.
    """
    closed = {"extensions": {"anderson_rubin_region": {
        "region": {"bounded": True, "shape": "bounded"}}}}
    open_ = {"extensions": {"anderson_rubin_region": {
        "region": {"bounded": False, "shape": "unbounded"}}}}
    assert _an_interval_is_in_hand(closed)
    assert not _an_interval_is_in_hand(open_)
    assert not _an_interval_is_in_hand({"extensions": {}})


# --- and nothing spells a tier by hand any more ---------------------------


_THEMIS = pathlib.Path(themis.__file__).parent
_TIER_WORDS = {"point", "interval", "none"}


def _tiers_written_by_hand(tree: ast.AST) -> list[int]:
    """Lines where a tier reaches ``answer_tier`` as a word rather than as
    a value read from something that knows."""
    found: list[int] = []
    for node in ast.walk(tree):
        values = []
        if isinstance(node, ast.keyword) and node.arg == "answer_tier":
            values.append(node.value)
        elif isinstance(node, ast.Assign):
            values.extend(
                node.value for target in node.targets
                if isinstance(target, ast.Subscript)
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == "answer_tier")
        for value in values:
            if any(isinstance(n, ast.Constant) and n.value in _TIER_WORDS
                   for n in ast.walk(value)):
                found.append(value.lineno)
    return found


def test_no_tier_reaches_the_field_as_a_word():
    """The structural half, and the reason the three literals cannot come
    back one at a time.

    A tier written as a word is a claim about what came out, made by
    somebody who did not ask. The denominator is every write of the field
    in the package rather than the ones somebody happened to look at.
    """
    by_hand = [(path.name, line)
               for path in sorted(_THEMIS.rglob("*.py"))
               for line in _tiers_written_by_hand(
                   ast.parse(path.read_text(encoding="utf-8")))]
    assert by_hand == []


def test_the_sweep_would_see_the_three_it_was_written_for():
    """The criterion discriminates: fed the lines as they used to stand,
    the same walk finds all three."""
    tree = ast.parse(
        '_set_gaps(result, gaps, answer_tier="interval")\n'
        '_set_gaps(result, gaps,\n'
        '          answer_tier="none" if gap_kinds & _NO_POINT else "point")\n'
        'report["answer_tier"] = "point"\n'
    )
    assert len(_tiers_written_by_hand(tree)) == 3
    # And accepts the two that read a value from something that knows.
    kept = ast.parse(
        'report["answer_tier"] = (delivered or came_out).value\n'
        'return DataGapReport(gaps=tuple(gaps), answer_tier=answer_tier)\n'
    )
    assert _tiers_written_by_hand(kept) == []
