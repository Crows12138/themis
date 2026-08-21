"""Which language a reader is answered in, and where that is decided.

A vocabulary member's word for the reader is decided data. ``M3`` names a
Pearl condition, and which sentence a reader gets for it is a choice
somebody made once — not a translation anybody may redo, and not something
an LLM should be producing on the way past, or two readers of one answer
would be reading two different judgements. So the words live beside the
vocabulary. What is NOT decided data is which of them a given reader gets,
and that is chosen where the sentence is made.

**Language was not a parameter here; it was part of a name.** Twenty-three
glosses spelled it into the function (``scale_zh``), eight tables into the
table (``_PATTERN_ZH``), four vocabularies into the field (``Layer.zh``). A
name cannot take an argument, so "answer this reader in English" was not an
expressible request — which is why :func:`themis.output.explainer.explain`
has carried a ``lang`` argument since v0.1 that raises for every value but
one. The argument was right and had nowhere to go.

Adding a Chinese-to-English table instead was not available either: 427 of
the strings that reach a reader are built by interpolation, so the Chinese
sentence is not a constant and cannot be a key. What was missing was never
a translation. It was **the thing that is the fact without being in any
language** — below, the token: a member's own spelling, which every
language's word hangs off.

**The envelope never carries a language.** A result is the same result
whoever reads it; two readers of one answer must not need two runs, and an
audit trail must not move because of a display preference. So no schema
states :class:`Lang` and it appears on no envelope path.
"""
from __future__ import annotations

from collections.abc import Mapping
from enum import unique

from .types import EnvelopeName


@unique
class Lang(EnvelopeName):
    """A language this build can answer a reader in.

    A vocabulary rather than a bare string, so that "which languages does
    this build answer in" has one answer and the completeness gate has a
    denominator: every reader-facing text has to exist for every member
    HERE, and adding a member is exactly what names the texts that do not
    exist yet. That ordering is the point — the gate is written while this
    holds one member and passes trivially, and the second member is what
    verifies it.
    """

    ZH = "zh"


#: What a caller gets who does not say. Chinese because that is the
#: language every word in this build was written in first, and a build
#: that adds a second language does not thereby change what its first was.
DEFAULT = Lang.ZH


#: One thing's reader-facing text, by language.
#:
#: Keyed by language INSIDE each member rather than by member inside each
#: language — the translations of one thing sit together, and a table maps
#: a token to one of these. The alternative groups a language into a table
#: of its own, which is what a translator's file looks like and what a
#: reviewer cannot check: two distant records of one fact drift, and this
#: package has already watched that happen where a fact had two records
#: (one assumption id reaches readers as three different sentences).
#: Adjacency is the only structural defence against it.
Words = Mapping[str, str]


def token(value) -> str:
    """The spelling this value has on the envelope.

    :class:`~themis.types.EnvelopeName` makes ``str(member)`` the value,
    which is what a result carries, so on the vocabularies that inherit it
    ``str`` would do. Asking for ``value`` first is what makes a gloss
    answer the same whether it is handed the member, the string an
    envelope carries, or a vocabulary that has not moved onto that base —
    a plain ``(str, Enum)`` answers ``str`` with the member's ADDRESS, and
    a reader's word cannot depend on which side of the boundary, or which
    base, it was asked from.

    This lookup was written twice, in the two packages that gloss, and
    only one of the two did this.
    """
    return str(getattr(value, "value", value))


def say(words: Words, lang: Lang | str = DEFAULT, *, unknown: str) -> str:
    """One thing's text in the reader's language, or ``unknown``.

    For a caller that already holds the thing — a vocabulary member, a
    table row — where there is no lookup left to do and the fallback is
    therefore the caller's to name.

    A text missing in a language this build declares is a hole in this
    repository, which the completeness gate keeps empty. Nothing here
    quietly answers in the other language instead: a report half in a
    language the reader did not ask for is the defect, not the fix.
    """
    text = words.get(token(lang))
    return text if text is not None else unknown


def gloss(table: Mapping[str, Words], value, lang: Lang | str = DEFAULT,
          *, unknown: str | None = None) -> str:
    """The reader's word for a value read back off an envelope.

    An unlisted value renders as its own token rather than as silence or a
    guess: a name the reader has to look up still beats the sentence
    omitting it, and it beats confidently naming the wrong thing. That is
    also the fallback for the hole :func:`say` describes — a value this
    build has never heard of and a value it cannot say in this language
    are different facts, and a reader can act on neither.

    ``unknown`` overrides that where a caller's sentence needs a phrase
    the bare token would not fit into.

    The table may be keyed by a vocabulary's members rather than by their
    values; the two lookups agree, because a member of a ``str`` enum
    hashes and compares as its own value.
    """
    tok = token(value)
    return say(table.get(tok) or {}, lang,
               unknown=f"`{tok}`" if unknown is None else unknown)
