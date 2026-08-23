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
from enum import nonmember, unique

from .types import EnvelopeName


@unique
class Lang(EnvelopeName):
    """A language this build can answer a reader in.

    A vocabulary rather than a bare string, so that "which languages does
    this build answer in" has one answer and a surface offering the choice
    has something to enumerate. It is what :func:`themis.output.explainer.explain`
    admits, and nothing else: what has to EXIST is counted by
    :func:`written`, which is the wider set.
    """

    ZH = "zh"


#: What a caller gets who does not say. Chinese because that is the
#: language every word in this build was written in first, and a build
#: that adds a second language does not thereby change what its first was.
DEFAULT = Lang.ZH


#: Languages whose words are being written, and which nothing answers in.
#:
#: :class:`Lang` says which languages a reader may be answered in. This says
#: which ones have words. They were the same fact while there was one
#: language, and the second one is what pulls them apart: a language's words
#: cross four reader surfaces and several thousand strings, which is more
#: than one change — and a build that declares a language it can only half
#: answer in is making a false claim, so the declaration cannot go first
#: either.
#:
#: A tag here is not exempt from anything. :func:`written` is the
#: denominator of every completeness check in this repository, and it counts
#: both sets — so the moment a tag arrives here, every gate that exists
#: starts naming what it lacks, member by member. What :class:`Lang` alone
#: still holds is the surfaces no gate covers yet.
#:
#: **Which is what promoting a tag out of here asserts**: not that its words
#: are written — the gates already say that — but that no reader-facing
#: surface is left where nothing has ever looked.
ARRIVING: frozenset[str] = frozenset({"en"})


def written() -> frozenset[str]:
    """Every language some text in this build is written in.

    The denominator of completeness, which is a different question from
    which languages a reader may ask for: a text keyed by a tag nothing
    answers to is still a text somebody has to finish, and one keyed by a
    tag nothing has heard of is a typo that reaches no reader and reads
    exactly like a text nobody wrote.

    Derived rather than declared, so the two sets cannot come apart from
    the union of themselves.
    """
    return frozenset(str(x) for x in Lang) | ARRIVING


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


#: What each language calls itself.
#:
#: The endonym rather than a name in some fixed language, because this is
#: the one string whose job is to be understood by someone who does not yet
#: know which language to read. Telling a renderer to answer in "Chinese"
#: is telling it in English — the language it was being asked not to use —
#: and a request that has to be understood in the wrong language first is
#: the same shape as a prompt whose examples are all in one language.
ENDONYM: Words = {"zh": "中文", "en": "English"}


def endonym(lang: Lang | str = DEFAULT) -> str:
    """What this language calls itself, for a request that has to name it.

    Falls back to the tag, which is what an unlisted language can honestly
    be called — a tag a renderer has to look up still beats naming a
    different language confidently.
    """
    return say(ENDONYM, lang, unknown=token(lang))


#: What goes between two things named in a row.
#:
#: A language's punctuation is a fact about the language, and neither of the
#: two below was being kept as one. This one lived in
#: ``themis.output.analysis_report`` as ``_AND`` and was reached eleven
#: times from that one module, so a second surface joining a list had
#: nothing to reach for.
BETWEEN_ITEMS: Words = {"zh": "、", "en": ", "}

#: What goes between two sentences in a row.
#:
#: This one lived nowhere, and that is exactly how it was found. Five
#: templates in the report wrote ``...**: {reason}This decides nothing...``
#: — the gap after the filled-in sentence was left to whatever ``reason``
#: happened to end with, which is the payload's business and not the
#: template's. Chinese needs no gap, so in the only language anyone is
#: answered in the five read correctly and nothing looked further; English
#: rendered ``...can be said here.This decides nothing...``.
#:
#: A gap belongs to the language for the same reason the sentence does. Put
#: it in the template instead and every template is free to forget it,
#: which is what happened.
BETWEEN_SENTENCES: Words = {"zh": "", "en": " "}

#: What goes between two clauses of one sentence, and between two loosely
#: joined statements.
#:
#: Separate from :data:`BETWEEN_ITEMS` because Chinese separates a list with
#: ``、`` and a clause with ``，`` while English writes a comma for both. Two
#: facts that coincide in one language are still two, and a single table
#: would make the distinction unavailable the moment a language needs it —
#: which is the language this build was written in first.
BETWEEN_CLAUSES: Words = {"zh": "，", "en": ", "}
BETWEEN_STATEMENTS: Words = {"zh": "；", "en": "; "}

#: What ends a sentence.
#:
#: The gap that FOLLOWS it is :data:`BETWEEN_SENTENCES` and is not part of
#: it. Two rendering modules had this mark under two names — ``_FULL_STOP``
#: spelling English ``". "`` and ``_END_OF_SENTENCE`` spelling ``"."`` —
#: and which of the two a rendering reached for decided whether its next
#: sentence had room. A mark that carries the gap sometimes is a mark
#: nobody can compose with.
FULL_STOP: Words = {"zh": "。", "en": "."}


def listing(items, lang: Lang | str = DEFAULT) -> str:
    """Several things named in a row, in this language's punctuation."""
    return fill(BETWEEN_ITEMS, lang).join(str(item) for item in items)


def sentences(*parts: str, lang: Lang | str = DEFAULT) -> str:
    """Several sentences in a row, with this language's gap between them.

    Empty parts are dropped rather than joined around: a refusal with no
    occasion to report is one sentence followed by another, not one
    followed by a gap followed by another.
    """
    return fill(BETWEEN_SENTENCES, lang).join(part for part in parts if part)


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


def fill(words: Words, lang: Lang | str = DEFAULT, **slots) -> str:
    """One thing's sentence in the reader's language, with its holes filled.

    What :func:`say` is for a word, this is for a sentence — and a sentence
    is where the second language stops being a lookup: the Chinese and the
    English put the same facts in different places, so the text cannot be
    an f-string. An f-string interpolates where it is written, which makes
    it a value rather than a template and leaves nothing for another
    language to be written beside.

    Named slots only. ``{}`` is a hole whose meaning is its position, and
    two languages do not agree about position — the whole reason this
    exists — so a slot that cannot be reordered is a slot that cannot be
    translated.

    A sentence missing in the reader's language raises rather than falling
    back: unlike a word, there is no identifier to hand over instead, and
    the completeness gate keeps this from happening.
    """
    text = words.get(token(lang))
    if text is None:
        raise KeyError(
            f"no {token(lang)} text for this sentence; it exists in "
            f"{', '.join(sorted(words)) or 'no language'}"
        )
    return text.format(**slots)


#: Every interpolated vocabulary this build declares, by the name it answers
#: to on an envelope.
#:
#: Filled by :meth:`Word.__init_subclass__` rather than typed out, for the
#: reason a vocabulary's words live beside its members: a list kept here
#: would be a second record of which sets exist, and it would go stale on
#: the day somebody declares the next one. A set missing from it is a set
#: nothing imported, and a token from a set nothing imported is a token
#: nothing could have produced.
VOCABULARIES: dict[str, type["Word"]] = {}


class Word(EnvelopeName):
    """A vocabulary whose members are read INSIDE a sentence.

    An ordinary vocabulary is CARRIED: it reaches the envelope as its token
    and a reader meets it through a gloss table some surface keeps. This one
    is INTERPOLATED — a sentence has a hole where a member goes — and that is
    a different requirement. The hole is in the reader's language and the
    token is in none, so a slot that can only stringify puts an English token
    into a Chinese sentence, which is the defect the sentence tables exist to
    remove, one level in.

    That gap is why several refusal species could not be folded. Each was one
    fact plus a word — WHICH matrix is singular, WHICH channel is mismeasured
    — and a channel that carries only numbers left every raise site to hard
    -code the word into prose of its own, which made it another author of the
    species' sentence.

    A member carries its own text, so there is no table to look up and
    nothing to keep in step: the vocabulary IS the table. Its token is still
    what reaches the envelope, because the envelope carries no language.
    """

    words: Words
    """This member's text, by language. Adjacent to the member for the reason
    :data:`Words` gives: two distant records of one fact drift."""

    vocabulary: str
    """What this vocabulary answers to on an envelope.

    A member's token is the fact and it is in no language, but a token on
    its own does not say WHICH closed set it came from — and two vocabularies
    are free to spell a member the same way. A reader handed the token and
    not the set has to guess, and a reader that guesses right today is a
    reader that guesses wrong the day the second set gains that spelling.

    Declared rather than derived from the class name, because the two are
    not the same fact: ``Refutation`` answers to ``monotonicity_refutation``
    and ``Design`` to ``singular_matrix``. Declared HERE rather than in the
    gloss registry, because this is the side that has to be right when a
    sentence's slot leaves the process — the registry reads it.

    It arrives as a class keyword rather than as an assignment in the body,
    because in an enum an assignment in the body is a MEMBER — the name
    would join the very set it is supposed to name.
    """

    def __init_subclass__(cls, vocabulary: str = "", **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if not vocabulary:
            raise TypeError(
                f"{cls.__name__} is interpolated into sentences, so its "
                f"token leaves the process inside one; declare it as "
                f"`class {cls.__name__}(Word, vocabulary=\"...\")`, naming "
                f"the closed set a reader is to look the token up in"
            )
        cls.vocabulary = vocabulary
        first = VOCABULARIES.setdefault(vocabulary, cls)
        if first is not cls:
            raise TypeError(
                f"{cls.__name__} and {first.__name__} both answer to "
                f"{vocabulary!r}; a name that reaches an envelope has to "
                f"pick one set out of all of them"
            )

    def __new__(cls, value: str, words: Words) -> "Word":
        member = str.__new__(cls, value)
        member._value_ = value
        member.words = words
        return member

    @classmethod
    def said(cls, value, lang: Lang | str = DEFAULT) -> str:
        """The reader's word for one of ours.

        Answers from the token as readily as from the member, which is not
        a convenience: a token is what comes back off an envelope, and a
        gloss that could only be asked with a live member would be one no
        consumer of a result could use. It is also the shape every other
        gloss in this package has — ``(value, lang) -> str`` — so the
        completeness gates can ask this one the same way.

        The table is built from the members rather than kept beside them,
        because a table kept beside them is a second record of the same
        fact and this package has watched those drift.
        """
        return gloss({m.value: m.words for m in cls}, value, lang)


def spoken(vocabulary: str, tok: str, lang: Lang | str = DEFAULT) -> str:
    """One word off an envelope, in the reader's language.

    The reader's half of what :data:`VOCABULARIES` exists for: a sentence
    that left the process with a hole in it comes back as a template plus,
    for that hole, the set and the token. This turns the pair into a word.

    A set this build has never heard of falls back to the token for the
    reason :func:`gloss` gives — a name the reader has to look up beats
    silence where the sentence promised a word.
    """
    known = VOCABULARIES.get(vocabulary)
    return (gloss({}, tok, lang) if known is None
            else known.said(tok, lang))


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
