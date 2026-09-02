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
    """Whether the public door will look at this answer at all.

    It requires a derivation and refuses an answer that has none before
    reading a word of it. A gap diagnosis and a question outside the
    language are exactly such answers: the report IS the answer, and no
    route was taken to have a chain of.

    So a forgery planted on one of them is refused for what the answer is,
    not for the forgery — and a gate that scored that as a catch would be
    counting its own blindness as coverage.
    """
    return result.get("derivation") is not None


def verify_honestly(program, result) -> None:
    """What an honest answer is entitled to get back from the public door.

    Acceptance — unless the door will not read it, and then the single
    refusal it is allowed to make is the one about the missing derivation.
    Any other complaint is a rule refusing an honest answer, which is what
    every caller of this exists to catch.
    """
    if reads(result):
        themis.verify(program, result)
        return
    with pytest.raises(ValueError, match="requires a result with a"):
        themis.verify(program, result)
