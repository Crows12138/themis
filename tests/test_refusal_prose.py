"""A refusal's sentence is the reader's answer line, so a value in it is
a value shown to the reader.

``_render_answer`` puts ``estimator_failure.reason`` into the answer slot
verbatim. One instrumented suite run raised 581 refusals and measured what
that costs: 78 of them carried something no reader should see, and the
worst was not the one on record. ``outcome_not_binary`` fired 55 times
with a message naming the outcome's observed levels — and rendering all
3000 of them, 62,003 characters, into one sentence. ``treatment_not_binary``
did the same 17 times. The nine numpy reprs (``np.float64(0.0)``,
``Z=np.True_``) were the smaller half of the problem.

Five copies of a numpy coercion already existed, under four names, and
every one of them justifies itself as JSON safety — the value bound for
the envelope. The same value bound for a sentence had no such step, and
its size had no step at all: ``{levels}`` reads the same at two levels
and at three thousand.

:func:`themis.refusals.describe` is that step, and the cap in
``EstimatorFailure`` is the backstop behind it — a reader never sees the
62,000 characters even from a site that has not been converted. The tests
below hold both, plus the shape that produced the worst case: a message
that says how many there are must not also print them.
"""
from __future__ import annotations

import ast
import pathlib

import numpy as np
import pytest

from themis import refusals


# --- one value, as a sentence should carry it ---------------------------------


def test_a_numpy_scalar_arrives_as_the_value_it_stands_for():
    """``np.False_`` is how a repr of a dataframe cell reads. The reader
    asked about their data, not about our array library."""
    assert refusals.describe(np.False_) == "False"
    assert refusals.describe(np.int64(3)) == "3"
    assert refusals.describe(np.float64(0.5)) == "0.5"


def test_a_column_says_how_many_it_is_and_shows_a_few():
    """The measured failure: the fact the refusal turns on is the count,
    and the levels themselves belong to ``details``."""
    levels = [float(v) for v in np.arange(3000)]
    text = refusals.describe(levels)
    assert text.startswith("3000 values (e.g. 0, 1, 2")
    assert len(text) < 80


def test_a_list_of_names_is_the_answer_and_is_shown_whole():
    """The opposite case, and the reason the cutoff is read off the
    elements rather than fixed: cutting an adjustment set drops the thing
    the reader has to act on."""
    names = [f"cov{i}" for i in range(8)]
    assert refusals.describe(names) == str(names)


def test_a_short_collection_is_shown_whole():
    """Three levels is the answer to "which levels", not a sample of it."""
    assert refusals.describe([np.float64(0.0), np.float64(1.0),
                              np.float64(2.0)]) == "[0, 1, 2]"


def test_a_float_loses_the_tail_no_reader_wanted():
    assert refusals.describe(0.30000000000000004) == "0.3"


def test_a_string_keeps_its_quotes():
    """Sites interpolate column names with ``!r``; routing one through
    ``describe`` must not change what the sentence has always said."""
    assert refusals.describe("x") == "'x'"


# --- the backstop ---------------------------------------------------------


def test_an_oversized_message_is_capped_rather_than_raised():
    """A refusal that crashed on the length of its own explanation would
    turn "no number, and here is why" into no answer at all."""
    exc = refusals.EstimatorFailure(
        refusals.OUTCOME_NOT_BINARY, "x" * 50_000,
    )
    assert len(str(exc)) < 1200
    assert "truncated" in str(exc)
    assert exc.failure_type == refusals.OUTCOME_NOT_BINARY


def test_an_ordinary_message_passes_through_unchanged():
    message = "outcome 'y' has 3 observed levels; this one wants two."
    exc = refusals.EstimatorFailure(refusals.OUTCOME_NOT_BINARY, message)
    assert str(exc) == message


# --- the shape that produced the worst case -----------------------------------


_ESTIMATION = pathlib.Path(__file__).resolve().parent.parent / "themis"


def _refusal_messages():
    """Every ``EstimatorFailure(species, message, ...)`` message node."""
    for path in sorted(_ESTIMATION.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "EstimatorFailure"
                    and len(node.args) >= 2
                    and isinstance(node.args[1], ast.JoinedStr)):
                yield path, node.args[1]


def _interpolations(message: ast.JoinedStr):
    return [v.value for v in message.values
            if isinstance(v, ast.FormattedValue)]


def _is_described(expr: ast.AST) -> bool:
    return (isinstance(expr, ast.Call)
            and isinstance(expr.func, ast.Attribute)
            and expr.func.attr == "describe")


_COLLECTION_CALLS = {"sorted", "list", "tuple", "set"}


def test_a_message_that_counts_a_collection_does_not_also_print_it():
    """The 62,000-character sentence, as a rule rather than as a fix. If
    the sentence says how many levels there are, the levels themselves are
    the occasion's — ``details`` carries those."""
    offenders = []
    for path, message in _refusal_messages():
        exprs = _interpolations(message)
        counted = {
            ast.unparse(e.args[0]) for e in exprs
            if isinstance(e, ast.Call) and isinstance(e.func, ast.Name)
            and e.func.id == "len" and e.args
        }
        for expr in exprs:
            if _is_described(expr):
                continue
            if ast.unparse(expr) in counted:
                offenders.append(f"{path.name}:{message.lineno} {ast.unparse(expr)}")
    assert not offenders, (
        f"{offenders} print a collection they also counted; wrap it in "
        f"refusals.describe"
    )


def test_a_message_does_not_interpolate_a_collection_it_just_built():
    """``sorted(vals)`` in a sentence is a column heading for a data dump.
    The call itself says the value is a collection — no name to guess at."""
    offenders = []
    for path, message in _refusal_messages():
        for expr in _interpolations(message):
            if _is_described(expr):
                continue
            if (isinstance(expr, ast.Call)
                    and isinstance(expr.func, ast.Name)
                    and expr.func.id in _COLLECTION_CALLS):
                offenders.append(
                    f"{path.name}:{message.lineno} {ast.unparse(expr)}"
                )
    assert not offenders, (
        f"{offenders} interpolate a freshly built collection; wrap it in "
        f"refusals.describe"
    )


# --- and end to end, on the case that measured 62,003 characters --------------


def test_the_worst_measured_refusal_now_fits_in_a_sentence():
    from themis.estimation.general_id import _sorted_levels

    levels = _sorted_levels(
        __import__("pandas").Series(np.random.default_rng(0).normal(size=3000))
    )
    message = (
        f"outcome 'y' has {len(levels)} observed levels "
        f"({refusals.describe(levels)}); v1 of the general-ID plug-in ATE "
        f"requires a binary outcome."
    )
    assert len(message) < 300, message[:300]
    exc = refusals.EstimatorFailure(refusals.OUTCOME_NOT_BINARY, message)
    assert "truncated" not in str(exc)


@pytest.mark.parametrize("value", [np.False_, np.True_])
def test_a_stratum_label_reads_as_a_value_not_as_a_dtype(value):
    """``empty stratum (Z=np.True_, X=True)`` reached a reader. Both sides
    of that sentence are the same kind of thing and only one of them had
    been through a coercion."""
    assert refusals.describe(value) in ("True", "False")
