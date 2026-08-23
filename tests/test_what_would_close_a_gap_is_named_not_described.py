"""A gap says what would close it in a NAME, and it says it for every kind.

The report used to carry a next-steps tail, and the tail was assembled from
a chain in ``data_gap_report`` that named twelve of the thirty-six gap kinds
and fell through to ``_gaps.described(gap)`` for the other twenty-four. A
description is a complete sentence, so the fall-through put a sentence where
a noun phrase goes — which is the wall of text the chain's own docstring said
it existed to prevent, and it produced one seventeen times on the corpus, at
worst out of a description with a median length of 1518 characters.

The chain is now :data:`themis.gaps.WANTED`, total over
:class:`~themis.types.GapKind`. Totality is the whole repair: what let two
thirds of the kinds be silent was a fallback, so the gate here is that there
is nothing left to fall back to, in every language this build writes.
"""
from __future__ import annotations

import pytest

from themis import gaps, language
from themis.types import GapKind, GapRefKind, GapSeverity
from themis import gaps as _gaps

#: Longer than any phrase that fits inside "supply {}". Generous — the
#: point is not to police wording but to keep a SENTENCE out of a slot a
#: reader reads as a name, and the shortest description the old chain fell
#: through to was already twice this.
LONGEST = 140


@pytest.mark.parametrize("kind", sorted(GapKind), ids=str)
def test_every_gap_kind_says_what_would_close_it(kind):
    """No fall-through, so no kind reaches a reader as somebody else's
    sentence — or, once the fall-through is gone, as a bare token."""
    assert str(kind) in gaps.WANTED, (
        f"{kind} has no phrase in themis.gaps.WANTED; a reader shown this "
        f"gap would be told to supply its snake_case name"
    )


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_the_phrase_is_written_in_every_language(lang):
    """A hole in one language is the reader of that language being handed
    a hole, and it is invisible from the language that has the word."""
    wordless = sorted(kind for kind, words in gaps.WANTED.items()
                      if not words.get(lang, "").strip())
    assert not wordless, f"{wordless} have no {lang} phrase"


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_a_phrase_is_not_a_sentence(lang):
    """What goes in the hole is read as the object of "supply", and the
    defect this cut removed was a paragraph arriving there."""
    long = sorted((len(words[lang]), kind) for kind, words in
                  gaps.WANTED.items() if len(words.get(lang, "")) > LONGEST)
    assert not long, (
        f"these {lang} phrases are sentence-length and are read inside "
        f"'supply {{}}': {long}"
    )


def test_a_kind_with_no_phrase_is_refused(monkeypatch):
    """The counterexample, and the state it refuses is the one this build
    was in: twenty-four of the thirty-six kinds had no phrase, and each was
    silently answered with its own description. Nothing distinguishes that
    state from coverage except a gate that looks for it."""
    monkeypatch.delitem(gaps.WANTED, str(GapKind.MISSING_IV_CANDIDATE))
    with pytest.raises(AssertionError, match="no phrase"):
        test_every_gap_kind_says_what_would_close_it(
            GapKind.MISSING_IV_CANDIDATE)


def test_a_sentence_in_the_phrase_slot_is_refused(monkeypatch):
    """The other counterexample, built out of the thing that used to arrive
    here: a gap description. The kind that produced the worst of them is
    the one whose phrase is replaced."""
    monkeypatch.setitem(
        gaps.WANTED, str(GapKind.MEASUREMENT_ERROR_CONCERN),
        {lang: "。" * (LONGEST + 1) for lang in language.written()})
    with pytest.raises(AssertionError, match="sentence-length"):
        test_a_phrase_is_not_a_sentence(str(language.DEFAULT))


def test_the_named_variant_refines_a_kind_that_already_has_a_phrase():
    """It is a refinement for the occasions that can name the variables,
    not a second table free to cover a different set of kinds."""
    assert set(gaps.WANTED_NAMED) <= set(gaps.WANTED)


def test_a_kind_this_build_never_heard_of_is_said_by_its_token():
    """The one fallback that stays, and what it is for: an envelope another
    build wrote. It is not reachable from a kind declared here, which is
    what the totality gate above is holding."""
    said = gaps.wanted({"kind": "a_kind_from_some_later_build"})
    assert said == "`a_kind_from_some_later_build`"


def test_the_phrase_names_the_variables_when_the_occasion_carries_them():
    """The refinement, doing its job: naming what is wanted beats naming
    the role of what is wanted, and the gap does not always know it."""
    gap = {
        "kind": str(GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN),
        "required_data": {"variables": ["age", "sex"]},
    }
    said = gaps.wanted(gap, "en")
    assert "age, sex" in said and "target population" in said
    bare = gaps.wanted({"kind": gap["kind"]}, "en")
    assert bare == "P*(Z) on the target population"


def test_the_distribution_name_comes_off_the_provenance_not_the_prose():
    """The one kind whose phrase IS a name this run produced. It is read
    off the channel that carries it, and the pusher's prefix is the
    pusher's — a reader asked to supply ``parameter:P(y|x)`` is being shown
    an internal spelling."""
    gap = {
        "kind": str(GapKind.MISSING_DISTRIBUTION),
        "provenance": [{"ref_kind": str(GapRefKind.INVESTIGATION_REQUEST),
                        "ref_id": "parameter:P(y|x)"}],
    }
    assert gaps.wanted(gap) == "P(y|x)"


def test_the_tail_is_one_line_per_gap_worth_acting_on():
    """Informational gaps are caveats, not errands, and a gap with nowhere
    to go has no line — the two conditions the field carried before it
    left the envelope, now both read off the gap itself.

    The middle entry is the severity condition and the LAST is the other
    one: ``missing_iv_candidate`` is a species nothing supplied unblocks,
    so it is named in :data:`themis.gaps.NOTHING_FILLS` and gets no line
    however blocking it is."""
    entries = [
        {"kind": str(GapKind.MISSING_STRUCTURAL_INPUT),
         "severity": str(GapSeverity.BLOCKING)},
        {"kind": str(GapKind.UNMEASURED_CONFOUNDER_RISK),
         "severity": str(GapSeverity.INFORMATIONAL)},
        {"kind": str(GapKind.MISSING_IV_CANDIDATE),
         "severity": str(GapSeverity.BLOCKING)},
    ]
    assert gaps.next_steps(entries, "en") == ["supply a structural input"]
