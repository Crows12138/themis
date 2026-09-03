"""What the public door does with an honest answer, written once.

Every gate built on ``fixtures/answer_shapes.json`` holds the same
sentence somewhere near its head — the rule I just wrote refuses no answer
this repository honestly produces — and each of them held it as three
lines of its own. That is one claim written a dozen times, and the second
writer of a claim is always the last to hear that it changed.

It changed when the corpus widened past the answers that carry a number.
``themis.verify`` requires a derivation, and an answer that took no route
has none, so "the door accepts every honest answer" stopped being true as
stated while remaining true as meant. A dozen copies would have had to be
told that one at a time; there is one here instead.

The corpus itself is deliberately NOT shared. Each gate reads the snapshot
for its own question and says what it found, and a single reader would
make one narrowing narrow everything. What belongs here is the part that
is about the DOOR rather than about any gate's rule.
"""
from __future__ import annotations

import pytest

import themis


def reads(result) -> bool:
    """Whether the CHAIN door will look at this answer at all.

    ``themis.verify`` re-runs the reasoning, so it requires a reasoning
    chain and refuses an answer that has none before reading a word of it.
    A gap diagnosis and a question outside the language are exactly such
    answers: the report IS the answer, and no route was taken to have a
    chain of.

    So a forgery planted on one of them is refused for what the answer is,
    not for the forgery — and a gate that scored that as a catch would be
    counting its own blindness as coverage.
    """
    return result.get("derivation") is not None


def the_door_for(result):
    """The strongest public door that will read this answer.

    Two doors audit an envelope and the difference between them is one
    premise. ``verify`` re-runs the chain as well as everything beside it,
    so it is the stronger, and it needs a chain to do it;
    ``verify_answer_claims`` holds what the answer SAYS and asks for the
    program alone.

    A gate asking whether a claim is held should put its forgery to the
    strongest door that will read the answer carrying it, which is what
    this returns. Choosing by hand is how a gate comes to report its own
    blindness as coverage on one half of the corpus and nothing on the
    other.
    """
    return themis.verify if reads(result) else themis.verify_answer_claims


def verify_honestly(program, result) -> None:
    """What an honest answer is entitled to get back from the doors.

    Acceptance at both, except that the chain door is entitled to one
    refusal — the one about the missing chain — on an answer that has
    none. Any other complaint is a rule refusing an honest answer, which
    is what every caller of this exists to catch.
    """
    themis.verify_answer_claims(program, result)
    if reads(result):
        themis.verify(program, result)
        return
    with pytest.raises(ValueError, match="requires a result with a"):
        themis.verify(program, result)
