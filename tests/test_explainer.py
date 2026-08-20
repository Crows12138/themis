# -*- coding: utf-8 -*-
"""A status and a point value are two facts, so they can disagree.

``ResultStatus`` says how far the kernel got with a query.
``NumericResult.value`` (``float | None``) says whether a point actually
came out — a ``NumericResult`` carrying only an interval is a legitimate
shape, which is exactly why the two can come apart. Their combination has
four cells and the explainer used to have sentences for two of them: it
entered the "solved" branch only when a point was in hand, so a result
whose status claimed a point and whose payload had none fell through to
whatever branch came next.

What came next was fluent and wrong. An effect landed on "在当前结构下不可
识别" or "结果未分类"; a probability and a counterfactual landed on "结果未
分类" — three credible sentences describing three situations this result
was not in, with nothing in the text to let the reader notice. That is the
failure mode these tests exist against: not a missing sentence, but a
plausible substitute for a missing sentence.

So each test below asserts two things about the same render. First, that
the reader is told about the contradiction itself. Second — and this is
the half that catches a regression sliding back into the old shape — that
the reader is NOT told one of the neighbouring branches' stories, because
a fix that merely reworded the fall-through would still be a lie.
"""
from __future__ import annotations

import pytest

from themis.output import explainer
from themis.types import (
    NumericInterval,
    NumericResult,
    QueryKind,
    QueryResult,
    ResultStatus,
    StructuralResult,
)

#: The words the three fall-through branches use. A render that reaches
#: the reader with any of these, while the status claims a point, is the
#: original defect however the contradiction clause is phrased.
BORROWED_SENTENCES = ("结果未分类", "不可识别")


def _solved(kind: QueryKind, status: ResultStatus, numeric, **kw) -> QueryResult:
    return QueryResult(
        status=status,
        query_kind=kind,
        query_id="q1",
        numeric_result=numeric,
        **kw,
    )


def _assert_names_the_contradiction(text: str) -> None:
    """Both halves of the property, in one place.

    The positive half is deliberately about the *content* of the claim —
    that the status says a point and the payload has none — rather than
    about a fixed string, so rewording the sentence keeps it green while
    dropping the disclosure turns it red.
    """
    assert "没有点值" in text, f"the contradiction is not stated: {text!r}"
    assert "已解出点值" in text, f"the status half is not stated: {text!r}"
    assert "不可采信" in text, f"the answer is not withheld: {text!r}"
    for borrowed in BORROWED_SENTENCES:
        assert borrowed not in text, (
            f"the reader was handed another branch's sentence ({borrowed!r}) "
            f"for a result whose status claims a point: {text!r}"
        )


# ------------------------------------------------------------- the triplet

@pytest.mark.parametrize(
    ("kind", "status"),
    [
        (QueryKind.EFFECT, ResultStatus.NUMERICALLY_SOLVED),
        (QueryKind.PROBABILITY, ResultStatus.NUMERICALLY_SOLVED),
        (QueryKind.COUNTERFACTUAL, ResultStatus.COUNTERFACTUAL_SOLVED),
    ],
    ids=["effect", "probability", "counterfactual"],
)
def test_a_solved_status_without_a_point_says_so(kind, status):
    """The reported case, on all three sites that share the shape.

    Parametrised rather than written out three times because the defect
    was a triplet: the same two-cell condition copied into three
    renderers, so a fourth renderer growing the same shape is the thing
    to make expensive, and a shared property is what makes it expensive.
    """
    result = _solved(
        kind, status,
        NumericResult(value=None, interval=NumericInterval(low=0.1, high=0.4)),
    )
    _assert_names_the_contradiction(explainer.explain(result))


def test_the_interval_the_payload_did_carry_is_shown():
    """Saying "no point" while silently dropping the interval that IS
    there would replace one omission with another. The reader needs to
    see what the kernel actually shipped in order to judge which of the
    two disagreeing facts is the broken one."""
    result = _solved(
        QueryKind.EFFECT, ResultStatus.NUMERICALLY_SOLVED,
        NumericResult(value=None, interval=NumericInterval(low=0.125, high=0.4)),
    )
    text = explainer.explain(result)
    assert "0.125" in text and "0.4" in text, text


def test_a_missing_numeric_payload_is_the_same_contradiction():
    """``numeric_result=None`` under a solved status is the same lie with
    less evidence, and it used to take the same fall-through. Guarding on
    the status rather than on the payload is what covers both; this holds
    the fix to that shape instead of to a ``value is None`` special case."""
    result = _solved(QueryKind.EFFECT, ResultStatus.NUMERICALLY_SOLVED, None)
    text = explainer.explain(result)
    _assert_names_the_contradiction(text)
    assert "数值结果整段缺失" in text, text


def test_a_structural_no_does_not_get_to_answer_for_a_solved_status():
    """The effect renderer's next branch is "no valid back-door set", and
    it is the one a real result is most likely to carry alongside a stale
    status — which is why it, not the generic fallback, is what the reader
    would have got. Both facts are on this envelope and they contradict
    each other; the renderer must not pick one and stay quiet."""
    result = _solved(
        QueryKind.EFFECT, ResultStatus.NUMERICALLY_SOLVED,
        NumericResult(value=None),
        structural_result=StructuralResult(value=False),
    )
    _assert_names_the_contradiction(explainer.explain(result))


# --------------------------------------------------- the cells still honest

def test_a_point_still_renders_as_the_answer():
    """The guard moved from the payload to the status, so the ordinary
    path has to be re-stated: a solved status with a point in hand still
    reaches the reader as the number, with no contradiction clause."""
    for kind, status, expected in (
        (QueryKind.EFFECT, ResultStatus.NUMERICALLY_SOLVED, "0.42"),
        (QueryKind.PROBABILITY, ResultStatus.NUMERICALLY_SOLVED, "0.42"),
        (QueryKind.COUNTERFACTUAL, ResultStatus.COUNTERFACTUAL_SOLVED, "0.42"),
    ):
        text = explainer.explain(_solved(kind, status, NumericResult(value=0.42)))
        assert expected in text, text
        assert "没有点值" not in text, text


def test_a_bounded_counterfactual_is_not_a_contradiction():
    """``COUNTERFACTUAL_BOUNDED`` with an interval and no point is the
    honest, expected shape — the same payload as the failing case above,
    under a status that agrees with it. Widening the contradiction clause
    to fire on "no point" alone would swallow this one."""
    result = _solved(
        QueryKind.COUNTERFACTUAL, ResultStatus.COUNTERFACTUAL_BOUNDED,
        NumericResult(value=None, interval=NumericInterval(low=0.1, high=0.4)),
    )
    text = explainer.explain(result)
    assert "得到界而非点值" in text, text
    assert "不可采信" not in text, text
