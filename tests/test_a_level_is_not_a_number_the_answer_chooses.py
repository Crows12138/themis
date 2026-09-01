"""What "95%" is worth when nothing on the envelope disagrees with it.

An interval and the level it is stated at are one statement. [0.326, 0.426]
at 50% and the same pair at 95% are different claims about how much of a
reader's belief those two numbers have earned, and the envelope carried the
second number with nothing holding it: thirty-eight of the forty-four answer
shapes accepted every level on the envelope being rewritten at once, and
thirty-one accepted ONE block claiming a level its neighbours do not, which
is how one interval comes to look tighter than the ones printed beside it.

Six shapes did refuse, and all six by accident: their level enters an
arithmetic the envelope can redo — the Anderson-Rubin inversions take an F
or chi-square quantile at it, SIMEX a normal one — so moving it broke an
identity somebody was checking for its own sake. Which is the shape of the
defect: whether a level could be moved was a fact about whether some other
rule happened to need the number.

Nothing stronger than a restated constant is available, and that is a fact
about the object. A percentile bootstrap's interval keeps no multiplier to
invert; the two shapes that record a standard error report no interval
beside it; and a caller cannot ask for another level, because
``themis.estimate`` takes every other run-level inference input and has no
slot for this one. So the line is one this system draws, and this repository
already settled how those are held: restate the constant, and pin the two
copies with a test.

The line had been drawn fifty-five times — forty-seven signature defaults
and eight dispatch literals — and asked after thirteen, always as
``0 < ci_level < 1``, which is a type in the shape of a claim and is also
how thirteen authors each managed not to ask the question above.
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
import pathlib

import pytest

import themis
from themis.input.syntactic_validator import SyntacticError
from themis.intervals import CONFIDENCE_LEVEL
from themis.verifier import verify_confidence_level
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

PACKAGE = pathlib.Path(themis.__file__).parent


def _pair(method: str):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _levels(node, path=()):
    """Every slot on an envelope that names a confidence level."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and key.endswith("ci_level"):
                yield path + (key,), value
            else:
                yield from _levels(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _levels(value, path + (index,))


def _at(root, path):
    for step in path:
        root = root[step]
    return root


# ------------------------------------------------ the fact this rests on


def test_one_run_states_one_level_and_it_is_the_declared_one():
    """Stated so it cannot drift: every level the snapshot carries, under
    every spelling, is the one line this system draws."""
    seen = 0
    for name in sorted(SHAPES):
        for path, value in _levels(SHAPES[name]["result"]):
            seen += 1
            assert value == CONFIDENCE_LEVEL, (name, path, value)
    assert seen > 100, seen


def test_the_verifier_states_the_line_itself_rather_than_reading_it():
    """The two copies, and the test that is the point of there being two.

    A verifier that imported the producer's constant would agree with it by
    construction. Two copies make moving the line something somebody
    declares; this is where the declaring is caught.
    """
    from themis.verifier import confidence_level_rules as rules

    assert rules._LEVEL == CONFIDENCE_LEVEL
    source = pathlib.Path(inspect.getsourcefile(rules)).read_text(
        encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            text = ast.get_source_segment(source, node) or ""
            assert "estimation" not in text and "intervals" not in text, text


# ----------------------------------------------------- moving the number


@pytest.mark.parametrize("shape", sorted(SHAPES))
@pytest.mark.parametrize("forged", [0.5, 0.999])
def test_no_single_block_may_claim_a_level_of_its_own(shape, forged):
    """One block at a different level from its neighbours.

    The reader is shown two intervals side by side and told they are
    comparable. This is the forgery that makes one of them look like the
    tighter piece of evidence.
    """
    program, result = _pair(shape)
    path, _ = next(iter(_levels(result)))
    _at(result, path[:-1])[path[-1]] = forged
    with pytest.raises(VerificationError):
        themis.verify(program, result)


@pytest.mark.parametrize("shape", sorted(SHAPES))
@pytest.mark.parametrize("forged", [0.5, 0.999])
def test_moving_every_copy_together_moves_nothing(shape, forged):
    """The attack a rule comparing copies cannot see, and the reason this
    one is not written as a comparison of copies: both copies come off one
    variable in one call, so agreeing with each other costs the producer
    nothing."""
    program, result = _pair(shape)
    paths = [path for path, _ in _levels(result)]
    assert paths
    for path in paths:
        _at(result, path[:-1])[path[-1]] = forged
    with pytest.raises(VerificationError):
        themis.verify(program, result)


def test_a_level_that_is_not_a_number_is_refused_by_its_own_rule():
    with pytest.raises(VerificationError, match="not a number"):
        verify_confidence_level({"numeric_estimate": {"ci_level": "95%"}})


# ------------------------------------------------- and taking it away


def _reports_an_interval(result) -> bool:
    if isinstance(result, dict):
        if _num(result.get("ci_lower")) and _num(result.get("ci_upper")):
            return True
        return any(_reports_an_interval(v) for v in result.values())
    if isinstance(result, list):
        return any(_reports_an_interval(v) for v in result)
    return False


#: The shapes whose run actually made a confidence statement. A run told
#: not to bootstrap makes none, and its recorded level is then a knob's
#: echo rather than a claim about anything — asked of it, the question
#: would be a rule with no reader behind it.
WITH_INTERVALS = sorted(
    name for name in SHAPES if _reports_an_interval(SHAPES[name]["result"]))


@pytest.mark.parametrize("shape", WITH_INTERVALS)
def test_a_run_that_reports_an_interval_says_what_level_it_states(shape):
    """Take away the run's record and the envelope stops answering the
    question at all, however many blocks still carry a copy."""
    program, result = _pair(shape)
    assert result["estimation_context"]["ci_level"] == CONFIDENCE_LEVEL
    del result["estimation_context"]["ci_level"]
    with pytest.raises(VerificationError, match="what level this run"):
        verify_confidence_level(result)
    with pytest.raises((VerificationError, SyntacticError)):
        themis.verify(program, result)


def test_every_shape_records_the_level_its_run_was_made_at():
    """Recorded whether or not an interval came out, the way the other
    run-level inputs beside it are: what a reader can establish should not
    depend on whether this particular run was told to bootstrap."""
    assert WITH_INTERVALS and len(WITH_INTERVALS) < len(SHAPES)
    for name in sorted(SHAPES):
        context = SHAPES[name]["result"]["estimation_context"]
        assert context["ci_level"] == CONFIDENCE_LEVEL, name


def test_the_level_is_asked_of_the_run_and_not_of_the_branch():
    """Written first as "a level at or above this block in the envelope",
    this refused twelve honest answers: a causation route records its
    bootstrap interval inside a derivation step, and ``derivation`` is a
    SIBLING of ``numeric_estimate``. Whether an interval was covered would
    have been a fact about which branch its producer wrote it on — the same
    disease one layer up.
    """
    sibling = {
        "estimation_context": {"ci_level": CONFIDENCE_LEVEL},
        "numeric_estimate": {"ci_level": CONFIDENCE_LEVEL, "point": 0.4},
        "derivation": {"steps": [
            {"inputs": {"ci_lower": 0.3, "ci_upper": 0.5}}]},
    }
    verify_confidence_level(sibling)
    del sibling["estimation_context"]["ci_level"]
    with pytest.raises(VerificationError, match="what level this run"):
        verify_confidence_level(sibling)


def test_a_block_is_not_made_to_repeat_what_the_run_already_said():
    """A mediation answer prints four intervals and one level. Requiring
    each block to carry its own would be requiring a producer to write one
    number four times so a rule could compare it with itself."""
    verify_confidence_level({
        "estimation_context": {"ci_level": CONFIDENCE_LEVEL},
        "numeric_estimate": {
            "decomposition": {"nde": {"ci_lower": 0.1, "ci_upper": 0.3},
                              "nie": {"ci_lower": 0.0, "ci_upper": 0.2}},
        },
    })


def test_an_identified_set_does_not_make_a_run_state_a_level():
    """The false positive this rule must not make. At any sample size a
    bounds row's ``[lower, upper]`` is the set the premises leave, so there
    is no coverage for a level to be the level of, and an envelope carrying
    only such pairs is not asked. The prefix is what tells them apart, and
    the same block's ``ci_`` pair — the outer band — IS a confidence
    statement and does put the question."""
    verify_confidence_level({"bounds_results": [
        {"lower_value": 0.2, "upper_value": 0.8},
    ]})
    verify_confidence_level({"numeric_estimate": {
        "counterfactual_cell": {"lower": 0.2, "upper": 0.9},
    }})
    with pytest.raises(VerificationError, match="what level this run"):
        verify_confidence_level({"bounds_results": [
            {"lower_value": 0.2, "upper_value": 0.8,
             "ci_lower": 0.15, "ci_upper": 0.85},
        ]})


def test_the_question_reaches_a_block_nobody_has_written_yet():
    """Both halves are asked of the envelope's shape, so a block added
    under a new name at a new depth arrives at them by being written."""
    with pytest.raises(VerificationError, match="what level this run"):
        verify_confidence_level({"numeric_estimate": {"a_new_block": {
            "rows": [{"ci_lower": 0.1, "ci_upper": 0.4}]}}})
    with pytest.raises(VerificationError, match="every confidence statement"):
        verify_confidence_level({
            "estimation_context": {"ci_level": CONFIDENCE_LEVEL},
            "numeric_estimate": {"a_new_block": {
                "rows": [{"ci_lower": 0.1, "ci_upper": 0.4,
                          "ci_level": 0.9}]}}})


# ------------------------------------------------- and it is drawn once


def test_the_line_is_drawn_in_one_place_and_read_everywhere_else():
    """What made the reader's side checkable at all.

    Forty-seven signature defaults and eight dispatch literals each read as
    a decision, and not one of them was made twice. A fifty-sixth would look
    exactly like an estimator being given a sensible default, so the gate
    says it rather than a reviewer.

    Two literals are allowed and are the point of the arrangement: the
    declaration, and the verifier's restatement of it, which the test above
    holds equal.
    """
    allowed = {
        (PACKAGE / "intervals.py").resolve(),
        (PACKAGE / "verifier" / "confidence_level_rules.py").resolve(),
    }
    offenders = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.resolve() in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            spots = []
            if isinstance(node, ast.keyword) and node.arg == "ci_level":
                spots.append(node.value)
            elif isinstance(node, ast.arguments):
                names = [a.arg for a in node.args + node.kwonlyargs]
                spots.extend(
                    default for name, default in zip(
                        names[len(names) - len(node.defaults):],
                        node.defaults)
                    if name == "ci_level")
                spots.extend(
                    default for arg, default in zip(
                        node.kwonlyargs, node.kw_defaults)
                    if arg.arg == "ci_level" and default is not None)
            elif isinstance(node, ast.Dict):
                spots.extend(
                    value for key, value in zip(node.keys, node.values)
                    if isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and key.value.endswith("ci_level"))
            for spot in spots:
                if isinstance(spot, ast.Constant) and isinstance(
                        spot.value, (int, float)):
                    offenders.append(
                        f"{path.relative_to(PACKAGE)}:{spot.lineno}")
    assert offenders == [], offenders
