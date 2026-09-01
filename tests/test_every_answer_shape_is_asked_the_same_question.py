"""The sweep that produced #515 was run on one answer shape out of forty-four.

Its gate walks whatever the envelope carries and bends every leaf, which is
strictly better than a list of field names — a list passes on the day a
field is added beside it. But it ran against one stratified-Wald answer,
and that shape's leaves are not the leaves of a propensity summary, a
saturation table, a precision budget, a dose-response curve or a four-way
decomposition. Each estimator writes its own blocks, and none of the others
had ever been asked.

Measured here, on the forty-four shapes the suite itself produces: of 1312
distinct leaves a reader is shown, **420 could be edited and still pass the
public door**. Forty-two of the forty-four shapes carried at least one.
Among them the interval endpoints of a longitudinal answer, every
confidence band of a dose-response curve, every cell of the overlap and
saturation diagnostics a reader consults to decide whether to trust the
number at all.

That is not a list of bugs this file fixes. It is a denominator this file
makes impossible to lose: the remainder is declared in
``fixtures/unwitnessed_leaves.json``, and a leaf leaves that file only by
being closed. A leaf that appears in it without being added deliberately is
a new hole, and this test says its name.

What the remainder is right now is not written here. It is written in that
file, and asserted once below — a count restated in prose is a copy that
states no relationship to the thing it copies, and this repository has
already found what that costs.

WHAT THIS TEST TRUSTS. The snapshot: forty-four (program, result) pairs
harvested from the suite by ``harvest_answer_shapes.py``. A snapshot is a
copy, so it states a relationship to what it copies — every pair is
verified honestly before it is swept, and a producer that has moved away
from the snapshot fails there rather than quietly sweeping a fossil.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.verifier import verify_answer_names_its_question
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
UNWITNESSED = json.loads(
    (FIXTURES / "unwitnessed_leaves.json").read_text(encoding="utf-8"))


def _leaves(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _leaves(value, path + (index,))
    else:
        yield path, node


def _shape_of(path) -> str:
    """A leaf's name with list positions collapsed.

    The fifth dose point on a curve carries the same leaves as the first,
    and asking the door about all five says what asking about one says.
    Collapsing is what keeps this gate at a minute rather than five.
    """
    return ".".join("[]" if isinstance(p, int) else p for p in path)


def _bend(value):
    """A different value of the same species, and different enough that the
    quantity actually moved. Strings are bent too: the leaves that name the
    treatment, the outcome and the mediator are strings, and a sweep that
    skipped them would report the most consequential edits as impossible.
    """
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 7
    if isinstance(value, float):
        if 0.0 <= value <= 1.0:
            return 0.9 if value < 0.5 else 0.1
        return value * 3.0 + 1.0
    if isinstance(value, str):
        return value + "_forged"
    return None


def _tamper(result, path, value):
    bad = copy.deepcopy(result)
    node = bad["numeric_estimate"]
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return bad


def _sweep(program, result):
    survived, asked = [], set()
    for path, value in _leaves(result.get("numeric_estimate") or {}):
        shape = _shape_of(path)
        if shape in asked:
            continue
        bent = _bend(value)
        if bent is None or bent == value:
            continue
        asked.add(shape)
        try:
            themis.verify(program, _tamper(result, path, bent))
        except Exception:
            continue
        survived.append(shape)
    return survived, asked


def test_the_snapshot_is_of_answers_this_build_still_gives():
    """First, because a forgery refused by a stale fixture proves nothing
    and a hole found in one proves less."""
    for method, pair in SHAPES.items():
        themis.verify(pair["program"], pair["result"])


def test_no_leaf_a_reader_is_shown_goes_unasked():
    """The measurement, kept as the gate, across every shape.

    A leaf that survives the public door and is not in the declared file is
    a hole opened since it was written. A leaf in the file that no longer
    survives has been closed, and belongs out of it — removing it is the
    only way anything should leave.
    """
    opened, closed = {}, {}
    for method, pair in sorted(SHAPES.items()):
        survived, _ = _sweep(pair["program"], pair["result"])
        declared = set(UNWITNESSED.get(method, ()))
        new = sorted(set(survived) - declared)
        gone = sorted(declared - set(survived))
        if new:
            opened[method] = new
        if gone:
            closed[method] = gone
    assert not opened, (
        "leaves a reader is shown that no rule holds, and that nobody "
        f"declared: {json.dumps(opened, ensure_ascii=False, indent=1)}")
    assert not closed, (
        "leaves declared unwitnessed that are now held — take them out of "
        f"fixtures/unwitnessed_leaves.json: "
        f"{json.dumps(closed, ensure_ascii=False, indent=1)}")


def test_the_declared_remainder_is_what_it_is():
    """The number itself, so that shrinking it is visible in a diff and
    growing it cannot happen by accident."""
    total = sum(len(v) for v in UNWITNESSED.values())
    assert total == 283, total
    assert len(SHAPES) == 44, len(SHAPES)


@pytest.mark.parametrize("method,leaf", [
    ("backdoor_linear", "outcome"),
    ("mediation_linear_imai", "mediator"),
    ("proximal_bridge", "outcome_proxy"),
    ("causation_plugin", "treatment"),
])
def test_the_answer_cannot_rename_the_question_it_answers(method, leaf):
    """What closed first, and why it is the sharpest of the 420 this sweep
    started from: renaming the outcome changes not one number on the
    envelope and changes every one of them into an answer to a question
    nobody asked."""
    pair = SHAPES[method]
    estimate = pair["result"]["numeric_estimate"]
    shown = estimate[leaf]
    bent = [s + "_forged" for s in shown] if isinstance(shown, list) \
        else shown + "_forged"
    with pytest.raises(VerificationError):
        themis.verify(pair["program"], _tamper(pair["result"], (leaf,), bent))


def test_a_sequence_written_into_one_field_is_declined_not_guessed():
    """The longitudinal path writes its whole treatment course into
    ``treatment`` — "A0,A1" where the query's single atom says "A1". That
    is a different estimand spelled a different way, and the rule declines
    it rather than compare. Declining leaves the leaf unheld, which is why
    it is in the declared file: the alternative was refusing an honest
    answer, and #517 is what that costs. Asked of the rule directly,
    because at the door this particular field turns out to be held by the
    chain comparison instead — which is the arrangement working, not the
    rule being unnecessary."""
    pair = SHAPES["longitudinal_gformula"]
    estimate = pair["result"]["numeric_estimate"]
    query_id = pair["result"]["query_id"]
    assert "," in estimate["treatment"]
    verify_answer_names_its_question(
        estimate, pair["program"], query_id=query_id)

    single = dict(estimate, treatment="something_else")
    with pytest.raises(VerificationError, match="question asked about"):
        verify_answer_names_its_question(
            single, pair["program"], query_id=query_id)
