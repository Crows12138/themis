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

:func:`themis.language.describe` is that step, and the cap in
``EstimatorFailure`` is the backstop behind it — a reader never sees the
62,000 characters even from a site that has not been converted. The tests
below hold both, plus the shape that produced the worst case: a sentence
that says how many there are must not also print them.

That last one used to be read off the source, because until #433 a site
wrote its own sentence and could interpolate a column raw. No site writes
one now, so it is read off the mechanism instead — see the third section.
"""
from __future__ import annotations

import numpy as np
import pytest

from themis import language, refusals
from themis.refusals import Refusal


# --- one value, as a sentence should carry it ---------------------------------


def test_a_numpy_scalar_arrives_as_the_value_it_stands_for():
    """``np.False_`` is how a repr of a dataframe cell reads. The reader
    asked about their data, not about our array library."""
    assert language.describe(np.False_) == "False"
    assert language.describe(np.int64(3)) == "3"
    assert language.describe(np.float64(0.5)) == "0.5"


def test_a_column_says_how_many_it_is_and_shows_a_few():
    """The measured failure: the fact the refusal turns on is the count,
    and the levels themselves belong to ``details``."""
    levels = [float(v) for v in np.arange(3000)]
    text = language.describe(levels)
    assert text == "[0, 1, 2, … +2997]"
    assert len(text) < 80


def test_the_count_of_what_was_cut_is_written_in_symbols():
    """This runs inside a sentence that has a language, so the part of it
    that is not the caller's data must not have one either.

    It said ``3000 values (e.g. ...)``, and a Chinese reader got that
    English inside their Chinese sentence whenever a slot held more than
    three values — four treatment levels was enough. The language gate
    cannot see it because the string is composed at run time, which is
    what makes the symbol the fix rather than a translation."""
    text = refusals.sentence(
        "treatment_not_binary", {"treatment": "dose", "levels": [0, 1, 2, 3]})
    assert "values" not in text and "e.g." not in text
    assert "[0, 1, 2, … +1]" in text


def test_a_stratum_reaches_the_sentence_as_the_cell_it_is():
    """The envelope's side of this path names ``{column: level}``; this
    side had no branch for it and rendered the KEYS, so a stratum arrived
    as ``['channel']`` with the level gone — silently, because a list of
    one column name is a perfectly ordinary thing for a sentence to hold."""
    assert language.describe({"channel": 2}) == "channel=2"
    assert language.describe(
        {"channel": 2, "region": "north"}) == "channel=2, region='north'"
    assert language.describe([{"channel": 2}]) == "[channel=2]"


def test_a_cell_with_no_columns_says_so_rather_than_vanishing():
    """The counterexample for the branch above: joining an empty mapping
    gives the empty string, which would leave a hole in the sentence where
    the reader was promised a stratum."""
    assert language.describe({}) == "{}"


def test_a_list_of_names_is_the_answer_and_is_shown_whole():
    """The opposite case, and the reason the cutoff is read off the
    elements rather than fixed: cutting an adjustment set drops the thing
    the reader has to act on."""
    names = [f"cov{i}" for i in range(8)]
    assert language.describe(names) == str(names)


def test_a_short_collection_is_shown_whole():
    """Three levels is the answer to "which levels", not a sample of it."""
    assert language.describe([np.float64(0.0), np.float64(1.0),
                              np.float64(2.0)]) == "[0, 1, 2]"


def test_a_float_loses_the_tail_no_reader_wanted():
    assert language.describe(0.30000000000000004) == "0.3"


def test_a_string_keeps_its_quotes():
    """Sites interpolate column names with ``!r``; routing one through
    ``describe`` must not change what the sentence has always said."""
    assert language.describe("x") == "'x'"


# --- the backstop ---------------------------------------------------------


def test_an_oversized_sentence_is_capped_rather_than_raised():
    """A refusal that crashed on the length of its own explanation would
    turn "no number, and here is why" into no answer at all.

    What can still run away is a SLOT: ``describe`` bounds a collection,
    and a single value said back is as long as the caller's data made it."""
    exc = refusals.EstimatorFailure(
        Refusal.OUTCOME_NOT_BINARY, outcome="y" * 50_000, levels=[0.0, 1.0],
    )
    assert len(str(exc)) < 1200
    assert "truncated" in str(exc)
    assert exc.failure_type == Refusal.OUTCOME_NOT_BINARY


def test_an_ordinary_sentence_passes_through_unchanged():
    occasion = {"outcome": "'y'", "levels": [0.0, 1.0, 2.0]}
    exc = refusals.EstimatorFailure(Refusal.OUTCOME_NOT_BINARY, **occasion)
    assert str(exc) == refusals.sentence(Refusal.OUTCOME_NOT_BINARY, occasion)
    assert "truncated" not in str(exc)


# --- the shape that produced the worst case -----------------------------------


def test_a_collection_in_a_slot_is_described_whichever_site_passed_it():
    """The 62,003-character sentence, held as a property of the mechanism
    rather than as a rule about prose.

    It used to be two scans over the source, because a site wrote its own
    sentence and could interpolate a column raw: one looked for a message
    that counted a collection and then also printed it, the other for a
    collection built inside the f-string. Both asked sites to reach for
    ``describe`` voluntarily, and both went quiet at #433 — there is no
    such message left to read.

    What replaced them is not a rule. Every slot goes through
    :func:`themis.refusals._slot` on its way into the species' sentence,
    and a collection there is described unconditionally, so no site can
    opt out of the thing the scans were asking for.
    """
    levels = [float(v) for v in np.arange(3000)]
    text = refusals.sentence(
        Refusal.OUTCOME_NOT_BINARY, {"outcome": "'y'", "levels": levels})
    assert "[0, 1, 2, … +2997]" in text
    assert len(text) < 300, text[:300]
    assert "truncated" not in str(
        refusals.EstimatorFailure(
            Refusal.OUTCOME_NOT_BINARY, outcome="'y'", levels=levels))


@pytest.mark.parametrize("value", [np.False_, np.True_])
def test_a_stratum_label_reads_as_a_value_not_as_a_dtype(value):
    """``empty stratum (Z=np.True_, X=True)`` reached a reader. Both sides
    of that sentence are the same kind of thing and only one of them had
    been through a coercion."""
    assert language.describe(value) in ("True", "False")
