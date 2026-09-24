"""A closed vocabulary's lies are its words, and three is not a number of them.

The remainder sweep tells every leaf three lies. For a leaf with no declared
vocabulary that number is not a budget: a coined spelling, a blank, and a
name from somewhere else are the three KINDS of lie such a value can be
told, and three is how many kinds there are.

When the sweep learned to draw its lies from a leaf's declared vocabulary,
the number came along. The comment beside it said so in as many words --
the domain reading "changed where the three come FROM, not how many there
are" -- and that sentence is the defect. A vocabulary has no kinds. It has
words, and two words are two different claims, so the number of lies it can
be told is the number of words in it.

What that cost, measured through the sweep's own doors: of 2036 leaves with
a vocabulary of ten words or fewer that the sweep called held, 115 survive a
word it never asked about. The clearest is ``status``. On all forty-three
answers that say ``counterfactual_solved`` the word can be rewritten to
``numerically_solved`` and every door says yes; the three words the sample
did ask about sit either side of it in the declared order, so the spread
that was meant to avoid asking only about neighbours asked only about
neighbours of the wrong word.

That clearest case is closed. #735 held the word to the road the answer
came by -- four questions are about more than one world and reach a number
two ways, and the estimating road leaves an estimate behind -- so a
counterfactual point that estimated nothing can no longer call itself
numerically solved. A second closed in #743, one step further in: a
diagnosis whose confidence region did not close was calling itself
numerically solved on the strength of the block's KEY, and the block
records whether it closed. The third closed in #766, and on the other
thing the word is about: an answer that identified and then refused at the
estimator was calling itself one that needs investigating, which says
nothing false about how far the run got and does say the structural
question is still open while the slot beside it says it is settled. The
paragraph above is what this instrument FOUND, and it stays as it was
measured. That distinction is the whole difference between a file about an
instrument and a file about the rules the instrument measured -- and it is
why a closed pair stays on the roster below rather than coming off it.

Asking every word is affordable up to a point and the point is measured
rather than chosen: the vocabularies this contract declares come in two
clumps -- four words or fewer, then five to ten, and then a jump straight
to thirty-eight -- so any ceiling inside that gap buys the same coverage.
Above it the sweep still samples, and what is in that position is now
counted in the gate rather than described in a comment, because "held"
means something weaker there.
"""
from __future__ import annotations

import collections
import copy

import pytest

import tests.test_every_answer_shape_is_asked_the_same_question as gate

#: Every pair the measurement found, as (honest word, word that survives,
#: the frontier that closed it or None). Each is a word the old sample
#: never asked about.
#:
#: All three are closed now: a counterfactual point calling itself
#: numerically solved, in #735; a diagnosis whose region did not close
#: calling itself the same, in #743; and an answer that identified and
#: then refused at the estimator calling itself one that needs
#: investigating, in #766. A pair used to come OFF this list when it
#: closed, and the last one leaving would have left the tests below
#: parametrized over nothing -- green, and asking nothing. So a closed
#: pair stays, with the measurement below reading its entry rather than
#: trusting it: the same discipline that took each of them off the open
#: half in the first place.
FOUND = (
    ("counterfactual_solved", "numerically_solved", "#735"),
    ("needs_investigation", "numerically_solved", "#743"),
    ("structurally_solved", "needs_investigation", "#766"),
)

#: ...and the half this file is about, which is empty by measurement.
SURVIVING = tuple((honest, survives)
                  for honest, survives, closed_by in FOUND
                  if closed_by is None)


# ============================================ what the contract declares


def test_the_vocabularies_come_in_two_clumps_with_a_gap_between_them():
    """The ceiling's justification, asserted rather than asserted ABOUT.

    A ceiling is a cost, so the only thing that makes one number better
    than another is where it can be put without changing what is bought.
    Here nothing has between eleven and thirty-seven words, so every line
    inside that gap buys the same coverage -- and the day something does,
    this fails and somebody prices it again.
    """
    sizes = sorted({len(members) for members in gate._DOMAIN.values()})
    assert sizes == [2, 3, 4, 5, 6, 7, 9, 10, 38, 42, 49, 85, 88, 140]
    assert gate._LARGEST_VOCABULARY_ASKED_IN_FULL in range(10, 38)


def test_the_two_clumps_are_this_many_vocabularies_each():
    counts = collections.Counter(
        len(members) <= gate._LARGEST_VOCABULARY_ASKED_IN_FULL
        for members in gate._DOMAIN.values())
    assert counts[True] == 83
    assert counts[False] == 12
    assert len(gate._DOMAIN) == 95


# ================================================ what the sweep now asks


@pytest.mark.parametrize("shape", sorted(
    s for s, m in gate._DOMAIN.items()
    if len(m) <= gate._LARGEST_VOCABULARY_ASKED_IN_FULL))
def test_a_small_vocabulary_is_asked_word_by_word(shape):
    """Every word, from every word: a vocabulary of six is five lies, not
    three of them."""
    members = gate._DOMAIN[shape]
    for value in members:
        asked = gate._from_domain(value, members)
        assert set(asked) == set(members) - {value}
        assert len(asked) == len(members) - 1


@pytest.mark.parametrize("shape", sorted(
    s for s, m in gate._DOMAIN.items()
    if len(m) > gate._LARGEST_VOCABULARY_ASKED_IN_FULL))
def test_a_large_vocabulary_is_still_sampled_and_still_spread(shape):
    """Above the ceiling nothing changed, including the reason the three
    are spread across the declared order rather than taken from beside the
    value."""
    members = gate._DOMAIN[shape]
    for value in members:
        asked = gate._from_domain(value, members)
        assert len(asked) == gate._PER_LEAF
        assert set(asked) <= set(members) - {value}
        assert len(set(asked)) == gate._PER_LEAF
    # Spread: the three are not three consecutive words.
    first = gate._from_domain(members[0], members)
    positions = [members.index(one) for one in first]
    assert max(positions) - min(positions) > gate._PER_LEAF


def test_three_is_still_what_a_value_with_no_vocabulary_is_told():
    """The number kept its meaning where it had one. These are kinds -- a
    coined spelling, a blank, a name from elsewhere -- and there are three
    of them."""
    assert gate._PER_LEAF == 3
    told = gate._bends("clinic", None, "a_stranger")
    assert told == ["clinic_forged", "", "a_stranger"]


def test_a_word_outside_the_vocabulary_is_not_a_lie_this_sweep_tells():
    """And why the two cannot be added together: a coined spelling of a
    word with a vocabulary is refused by validation before a rule reads
    it, which is the sweep measuring the validator and reporting it as
    coverage."""
    members = gate._DOMAIN["status"]
    told = gate._bends("numerically_solved", members, "a_stranger")
    assert "a_stranger" not in told
    assert "numerically_solved_forged" not in told
    assert "" not in told


# ==================================================== the defect, measured


def _answers_saying(word):
    return [name for name in sorted(gate.SHAPES)
            if gate.SHAPES[name]["result"].get("status") == word]


def test_the_pairs_this_file_still_finds_a_hole_for():
    """Named and counted, because the test below is parametrized over the
    roster and a roster gone empty is a green test asking nothing at all.

    Which is why the open half is derived and the roster is not: three
    pairs were found, all three are closed, and both halves of that
    sentence are asserted rather than one of them being an absence."""
    assert len(FOUND) == 3
    assert SURVIVING == ()


@pytest.mark.parametrize("honest,survives,closed_by", FOUND)
def test_the_word_that_survives_is_one_the_sweep_now_asks_about(
        honest, survives, closed_by):
    """First, because a test that a forgery passes proves nothing about
    an instrument that never put it. Asked of the closed pairs too: what
    closed them was a rule, and an instrument that stopped asking would
    report the same green."""
    assert survives in gate._from_domain(honest, gate._DOMAIN["status"])


@pytest.mark.parametrize("honest,survives,closed_by", FOUND)
def test_each_pair_is_on_the_side_of_the_line_this_file_files_it_on(
        honest, survives, closed_by):
    """The measurement itself, through the doors the sweep uses, and then
    the file that has to say so.

    Not every answer saying the honest word is one a bend passes on --
    what a rule holds depends on what else the answer carries -- so this
    finds the first that it does and stops. For a pair still open, finding
    none would mean it was never a hole; for a closed one, finding any
    means the frontier named beside it did not close what it says it did.

    This file is about the instrument, not about the rules that read
    ``status``: the point is that a coverage number said held while these
    were true.
    """
    found = None
    for name in _answers_saying(honest):
        program = gate.SHAPES[name]["program"]
        result = gate.SHAPES[name]["result"]
        doors = gate._reading_doors(program, result)
        if not doors:
            continue
        forged = copy.deepcopy(result)
        forged["status"] = survives
        if not any(gate._refuses(door, program, forged) for door in doors):
            found = name
            break
    if closed_by is None:
        assert found is not None, (honest, survives)
        assert "status" in gate.UNWITNESSED.get(found, ()), found
    else:
        assert found is None, (honest, survives, closed_by, found)


# ======================================== what is still measured by sample


def test_the_sampled_leaves_outnumber_the_declared_remainder():
    """Said out loud once, because it is the fact that decides how the
    remainder should be read: more leaves are measured by three words than
    there are leaves in the whole declared remainder."""
    sampled = sum(gate._the_vocabularies_only_sampled().values())
    remainder = sum(len(v) for v in gate.UNWITNESSED.values())
    assert sampled > remainder
