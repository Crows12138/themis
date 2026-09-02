"""Every leaf of the envelope, asked whether anything holds it.

The sweep that produced #515 ran on one answer shape out of forty-four, so
this file was written to run it on all of them: each estimator writes its
own blocks, and one stratified-Wald answer has none of a propensity
summary's leaves, or a dose-response curve's, or a four-way split's. That
fixed the rows.

It did not fix the columns, and for twelve frontiers nobody noticed,
because a scope is invisible in a passing test. The sweep read
``result["numeric_estimate"]`` while its name said "no leaf a reader is
shown" and this paragraph said "whatever the envelope carries": **1560 leaf
shapes of 7568**. A reader is shown the bounds rows, the gap report, the
assumption ledger, the investigation requests and the audit footer, and the
run records its own inference inputs so that a verifier can reason about
reproducibility — none of it had been bent even once. So the declared
remainder, whose entire value is that it is not the producer's word, was a
statement about one block wearing the clothes of a statement about the
answer. And every frontier picked from its output was necessarily a
frontier inside that block: the instrument had been steering the work.

Asked of the whole envelope, 1671 leaf shapes survive. Among them the
identification formula — which can be deleted outright on all twenty-three
answers that carry one — the run's own sample size and draw count, whether
a bounds row calls itself uninformative, whether a ledger premise calls
itself testable, and which intervention a data gap says it is about.

That is not a list of bugs this file fixes. It is a denominator this file
makes impossible to lose: the remainder is declared in
``fixtures/unwitnessed_leaves.json``, and a leaf leaves that file only by
being closed. A leaf that appears in it without being added deliberately is
a new hole, and this test says its name.

What the remainder is right now is not written here. It is written in that
file, and asserted once below — a count restated in prose is a copy that
states no relationship to the thing it copies, and this repository has
already found what that costs. The SCOPE is asserted beside it, for the
reason this paragraph exists: a narrowing is a passing test.

WHAT THIS TEST TRUSTS, and what each piece of trust cost when it was
examined.

The snapshot: forty-four (program, result) pairs harvested from the suite
by ``harvest_answer_shapes.py``. A snapshot is a copy, so it states a
relationship to what it copies — every pair is verified honestly before it
is swept, and a producer that has moved away from the snapshot fails there
rather than quietly sweeping a fossil.

The bend set. This asked each leaf ONE kind of lie, so "held" was in part a
fact about which lie was chosen — a rule that catches that edit and no
other reports the leaf as held, and the declared remainder is then a lower
bound wearing the clothes of a measurement. Asked several kinds, eight more
leaves survive. What that concealed was not only arithmetic: a joint
effect's point estimate was held by nothing but a ratio computed from it,
and a point of exactly zero walked through the ratio's denominator guard.
A coverage claim is only as wide as the question that was asked.
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


#: Two numbers are the same number unless they differ by more than this.
#: Every comparison in this system is numerical and every numerical
#: comparison has a floor, so a bend inside the floor is not a lie any rule
#: was written to catch — counting it as a survivor reports a correct
#: tolerance as a hole. Declared here, wider than any tolerance the rules
#: state, because this gate must decide materiality without reading them.
_ATOL = 1e-6
_RTOL = 1e-5


def _is_material(old, new) -> bool:
    """Is the bend a different value, or the same value written again?

    Asked of the DIFFERENCE, not of the recipe that produced it. A recipe
    cannot stay honest across magnitudes: replacing a value with ``0.0`` is
    a replacement at 0.5 and a nudge at 1e-229, and it was exactly that
    degeneration — a Hansen p-value of 1.09e-229 shown as zero — that this
    gate reported as a hole in a rule that is correct.
    """
    if isinstance(old, bool) or isinstance(new, bool):
        return old != new
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        return abs(new - old) > _ATOL + _RTOL * abs(old)
    return old != new


def _bends(value):
    """Several KINDS of lie per leaf, not one.

    This returned a single value, and "held" was then partly a fact about
    which edit happened to be chosen. Measured: eleven leaves the one-edit
    sweep called held survive a different edit — among them a joint effect's
    point estimate, which was held only by a ratio computed from it, and a
    point of exactly zero walked through the division guard.

    Kinds, and only kinds. Whether any of them lands far enough away to be
    a lie is ``_is_material``'s question, asked of the two numbers rather
    than of the recipe. Strings are bent too: the leaves naming the
    treatment, the outcome and the mediator are strings, and skipping them
    would report the most consequential edits as impossible.
    """
    if isinstance(value, bool):
        return [not value]
    if isinstance(value, int):
        return [value + 7, 0, value * 2 + 1, -abs(value) - 1]
    if isinstance(value, float):
        if 0.0 <= value <= 1.0:
            return [0.9 if value < 0.5 else 0.1, value / 2 + 0.01, 0.0]
        return [value * 3.0 + 1.0, -value - 1.0, 0.0, value / 2.0]
    if isinstance(value, str):
        return [value + "_forged", "", "x"]
    return []


def _tamper(result, path, value):
    bad = copy.deepcopy(result)
    node = bad
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return bad


def _asked(result):
    """Every leaf this gate puts a question to, once per distinct shape.

    The gate's SCOPE, and the only statement of it: what ``_sweep`` bends
    and what the scope test measures are the same walk, so a narrowing is
    one edit and it fails rather than passes. For twelve frontiers the
    scope was a subscript inside the sweep — ``result["numeric_estimate"]``
    — and nothing anywhere said so.
    """
    seen = set()
    for path, value in _leaves(result):
        shape = _shape_of(path)
        if shape in seen:
            continue
        seen.add(shape)
        yield shape, path, value


def _sweep(program, result):
    """A leaf is held only if EVERY kind of lie about it is refused."""
    survived, asked = [], set()
    for shape, path, value in _asked(result):
        asked.add(shape)
        for bent in _bends(value):
            if not _is_material(value, bent):
                continue
            try:
                themis.verify(program, _tamper(result, path, bent))
            except Exception:
                continue
            survived.append(shape)
            break
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


def test_what_this_sweep_calls_a_lie_is_asked_of_the_difference():
    """The gate's own assumption, pinned where it can be argued with.

    A Hansen p-value in these fixtures is 1.09e-229. Shown as ``0.0`` it is
    the same number to every reader and every rule, and the sweep reported
    the rule that accepts it as a hole — because materiality had been
    written as a recipe ("do not nudge") rather than as a question about
    the two numbers. The same recipe is a replacement one magnitude up.
    """
    tiny = SHAPES["iv_2sls_overid"]["result"]["numeric_estimate"][
        "over_identification"]["hansen_p_value"]
    assert abs(tiny) < _ATOL
    assert not _is_material(tiny, 0.0)
    assert not _is_material(500.0, 500.001)
    assert _is_material(16.43, 0.0)
    assert _is_material(0.5, 0.9)
    assert _is_material("a", "a_forged")


def test_the_declared_remainder_is_what_it_is():
    """The number itself, so that shrinking it is visible in a diff and
    growing it cannot happen by accident."""
    total = sum(len(v) for v in UNWITNESSED.values())
    assert total == 918, total
    assert len(SHAPES) == 44, len(SHAPES)


def test_the_sweep_asks_about_the_whole_envelope():
    """The denominator, stated where narrowing it fails rather than passes.

    This gate spent twelve frontiers reading ``result["numeric_estimate"]``
    while its name and its prose said the envelope — 1560 leaf shapes of
    7568, and every frontier it produced was therefore a frontier inside
    one block. A scope is not visible in a passing test, so it is asserted:
    every top-level key any answer carries is asked about, and the count of
    asked shapes is the envelope's own.
    """
    top_level, asked_top = set(), set()
    asked_total = 0
    for pair in SHAPES.values():
        top_level.update(pair["result"])
        shapes = [shape for shape, _, _ in _asked(pair["result"])]
        asked_total += len(shapes)
        asked_top.update(shape.split(".")[0] for shape in shapes)
    assert top_level - asked_top == set(), top_level - asked_top
    assert asked_total == 7568, asked_total


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
    where = ("numeric_estimate", leaf)
    with pytest.raises(VerificationError):
        themis.verify(pair["program"], _tamper(pair["result"], where, bent))


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
