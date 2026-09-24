"""What supplying a gap buys back is no more than its question can reach (#774).

A gap's ``blocks`` says what filling it buys back, and five species said
it in the sentence a reader acts on as well: "supply this and you can have
a point estimate". Both were the species' on every occasion. One question
cannot reach a point at all — the probabilities of causation are
Tian–Pearl intervals unless the query declares monotonicity, however much
is supplied — and there the report's own tier said "interval" while every
gap beside it promised a point.

So ``blocks`` is capped by the question
(:data:`themis.types.BLOCKS_CAPPED_AT_AN_INTERVAL`, on the same predicate
the tier reads), the sentence reads the field through a ``{blocks}`` hole
the gap fills from itself, and the verifier holds both: the word to the
field on the answer alone, and the field to the question where the program
is. The sixth sentence, which named the point that comes AFTER what it
buys, now says only what it buys.
"""
from __future__ import annotations

import copy
from dataclasses import replace

import pytest

import themis
from themis import gaps
from themis.types import (
    BLOCKS_OF, DataGap, GapBlocks, GapKind, GapRefKind, cites, raised_by,
    raised_by_ref, ref_kinds_of,
)
from themis.verifier.errors import VerificationError


def _atom(name: str) -> dict:
    return {"predicate": name, "args": []}


def _variables(*names: str) -> list[dict]:
    return [{"kind": "variable", "predicate": n, "domain": [True, False]}
            for n in names]


def _attribution(monotonic: bool, confounded: bool = False) -> dict:
    """Did x cause y — with no data, so the answer is the gap report."""
    statements = [*_variables("x", "y"),
                  {"kind": "cause", "from": _atom("x"), "to": _atom("y")}]
    if confounded:
        statements.append({"kind": "bidirected", "left": _atom("x"),
                           "right": _atom("y")})
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "causation", "cause": _atom("x"), "effect": _atom("y"),
        "monotonic": monotonic}})
    return {"version": "0.1", "domain": {"objects": []},
            "statements": statements}


def _effect() -> dict:
    """The same graph asked for an effect, which can reach a point."""
    return {"version": "0.1", "domain": {"objects": []}, "statements": [
        *_variables("x", "y"),
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "query", "id": "q", "query": {
            "kind": "effect", "given": [],
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True}}}]}


def _answer(program: dict) -> dict:
    return themis.run(copy.deepcopy(program))["results"][0]


def _buying_a_point(result: dict) -> list[dict]:
    """The gaps of species that stand in the way of the point where the
    question can reach one."""
    return [gap for gap in result["data_gap_report"]["gaps"]
            if BLOCKS_OF.get(GapKind(gap["kind"])) is GapBlocks.POINT_ESTIMATE]


def _set_blocks(result: dict, value: str, *, word: bool = True) -> dict:
    forged = copy.deepcopy(result)
    gap = _buying_a_point(forged)[0]
    gap["blocks"] = value
    if word:
        gap["words"][gaps.BLOCKS_HOLE]["token"] = value
    return forged


# --- what the answer says ------------------------------------------------------


def test_a_question_with_no_monotonicity_is_told_supplying_buys_an_interval():
    result = _answer(_attribution(monotonic=False))
    assert result["data_gap_report"]["answer_tier"] == "interval"
    held = _buying_a_point(result)
    assert held
    for gap in held:
        assert gap["blocks"] == "bounds"
        assert gap["words"][gaps.BLOCKS_HOLE] == {
            "vocabulary": gaps.BLOCKS_SPOKEN, "token": "bounds"}
        assert "区间" in gaps.if_provided(gap, "zh")
        assert "点估计" not in gaps.if_provided(gap, "zh")
        assert "an interval" in gaps.if_provided(gap, "en")


def test_a_monotone_question_is_still_told_it_buys_a_point():
    result = _answer(_attribution(monotonic=True))
    assert result["data_gap_report"]["answer_tier"] == "point"
    held = _buying_a_point(result)
    assert held
    for gap in held:
        assert gap["blocks"] == "point_estimate"
        assert "点估计" in gaps.if_provided(gap, "zh")


def test_an_unidentified_attribution_is_not_promised_a_point_after_it():
    """The sixth sentence. Identification is what this species buys on
    every question; the shape after it is the question's."""
    result = _answer(_attribution(monotonic=False, confounded=True))
    stuck = [gap for gap in result["data_gap_report"]["gaps"]
             if gap["kind"] == "unidentifiable_no_admissible_set"]
    assert stuck
    for gap in stuck:
        assert "点估计" not in gaps.if_provided(gap, "zh")
        assert "point estimate" not in gaps.if_provided(gap, "en")


@pytest.mark.parametrize("monotonic", [False, True])
def test_both_doors_take_the_answer_as_it_is_written(monotonic):
    program = _attribution(monotonic)
    result = _answer(program)
    themis.verify_data_gap_report(result)
    themis.verify_answer_claims(program, result)


# --- what the verifier holds ---------------------------------------------------


def test_a_point_where_the_question_cannot_reach_one_is_refused():
    """Asked where the program is. The narrow door takes it, because an
    answer with no data records the question's monotonicity nowhere: it can
    tell that this is a question which MIGHT be lowered, not whether this
    one was."""
    program = _attribution(monotonic=False)
    forged = _set_blocks(_answer(program), "point_estimate")
    themis.verify_data_gap_report(forged)
    with pytest.raises(VerificationError, match="declares no monotonicity"):
        themis.verify_answer_claims(program, forged)


def test_an_interval_where_the_question_can_reach_a_point_is_refused():
    program = _attribution(monotonic=True)
    forged = _set_blocks(_answer(program), "bounds")
    with pytest.raises(VerificationError, match="can reach the species"):
        themis.verify_answer_claims(program, forged)


def test_the_answer_alone_refuses_a_lowered_gap_off_an_attribution_question():
    """No question but an attribution can be lowered, and the answer says
    which kind of question it answers."""
    forged = _set_blocks(_answer(_effect()), "bounds")
    with pytest.raises(VerificationError, match="T10-5"):
        themis.verify_data_gap_report(forged)


def test_a_word_that_is_not_its_gaps_blocks_is_refused_on_the_answer_alone():
    forged = copy.deepcopy(_answer(_attribution(monotonic=False)))
    gap = _buying_a_point(forged)[0]
    gap["words"][gaps.BLOCKS_HOLE]["token"] = "point_estimate"
    with pytest.raises(VerificationError, match="the sentence's word is"):
        themis.verify_data_gap_report(forged)


def test_a_sentence_whose_word_is_missing_is_refused():
    program = _attribution(monotonic=False)
    forged = copy.deepcopy(_answer(program))
    _buying_a_point(forged)[0].pop("words")
    with pytest.raises(VerificationError, match="has a hole"):
        themis.verify_answer_claims(program, forged)


# --- the gap is the word's one author --------------------------------------------


def _gap(kind: GapKind, **kw) -> DataGap:
    said = sorted(gaps.says_of(kind), key=str)[0]
    space = sorted(ref_kinds_of(kind), key=str)[0]
    provenance = (raised_by_ref(kind, "x", check=sorted(raised_by(kind))[0])
                  if space is GapRefKind.VERIFIER_CHECK
                  else cites(kind, "x", ref_kind=space))
    return DataGap(kind=kind, describes=(gaps.sentence(said),),
                   provenance=provenance, **kw)


def test_a_gap_is_built_lowered_and_no_further():
    lowered = _gap(GapKind.MISSING_DISTRIBUTION, blocks=GapBlocks.BOUNDS)
    assert lowered.words[gaps.BLOCKS_HOLE]["token"] == "bounds"
    with pytest.raises(ValueError, match="not a site's to set"):
        _gap(GapKind.MISSING_DISTRIBUTION, blocks=GapBlocks.IDENTIFICATION)


def test_a_gap_rewritten_with_a_lowered_blocks_says_the_lowered_one():
    """What the report does to cap a gap, and why the word follows: the
    rewrite passes back through the gap's own construction."""
    gap = _gap(GapKind.MISSING_DISTRIBUTION)
    assert gap.words[gaps.BLOCKS_HOLE]["token"] == "point_estimate"
    lowered = replace(gap, blocks=GapBlocks.BOUNDS)
    assert lowered.words[gaps.BLOCKS_HOLE]["token"] == "bounds"
