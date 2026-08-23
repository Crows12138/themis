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

import string
from collections.abc import Mapping
from enum import nonmember, unique

from .types import EnvelopeName, envelope_scalar


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


# ---------------------------------------------------------------- occasions
#
# A sentence with holes, and the facts of one occasion to put in them. It
# lived in ``themis.refusals`` while a refusal was the only thing shaped that
# way. A gap is the second — ``missing_information[].reason`` is a sentence
# rendered at the site out of a closed kind and this occasion's facts, which
# is the shape ``estimator_failure`` had before it was taken apart — and a
# gap is not a refusal, so a module that had to import ``refusals`` for the
# machinery would be naming the first user rather than the thing.
#
# The names are the same and so are the rules. What each one is FOR is in its
# own docstring; what they share is the split this section is about — a slot
# holds either a value, which reads the same to every reader and so travels
# rendered, or a word, whose text IS the language and so travels as a token.

MESSAGE_CAP = 1000
"""Where a sentence is cut off.

A backstop for the reader, not a fix. The measured case was a message naming
an outcome's observed levels: 3000 floats interpolated into one sentence,
62,003 characters of it, 55 times. Nothing was wrong with the sentence; the
value put into it was a column. The fix is :func:`describe`, which is bounded
by construction, so a truncated message means a site is still interpolating a
value raw — and a test asserts this never fires in the suite, so that site is
found here rather than by whoever reads the answer.
"""

# How many of a collection a sentence shows before it says how many more.
# Names are short and a reader can hold a dozen; values are what a count is
# evidence for, and the measured case had no ceiling — 3000 floats. So the
# cutoff is read off the elements, not fixed.
_NAME_SAMPLE = 12
_VALUE_SAMPLE = 3


def describe(value, *, sample: int | None = None) -> str:
    """One value, as a sentence should carry it.

    Numpy scalars come back as their Python equivalents — ``np.False_`` and
    ``np.float64(0.0)`` are how a repr of a dataframe cell reads, and the
    reader did not ask about our array library. Collections say how many
    they are and show a few, because "how many levels" is the fact a refusal
    turns on and the levels themselves are the occasion's, which belong in
    ``details`` — and they say it in symbols, because this runs inside a
    sentence that HAS a language, and a count written in words arrives in
    English however that sentence was written. Four levels under
    ``treatment_not_binary`` was enough to reach a Chinese reader.

    A stratum arrives as ``{column: level}``, which :func:`occasion` names on
    the envelope's side of this same path. This side had no branch for it, so
    a mapping fell through to the length test and rendered its KEYS:
    ``{'channel': 2}`` reached a reader as ``['channel']`` with the level
    silently gone. Three estimators wrote a cell rendering of their own
    rather than use this one, and that they had to is the same fact.

    Five copies of a numpy coercion already exist across the estimators,
    under four names, and every one of them justifies itself as JSON
    safety — a value bound for the envelope. They are not this function
    and this function does not replace them: they hand back a value, this
    hands back prose. The point is that the envelope's path had a step
    and the sentence's path had none.
    """
    scalar = getattr(value, "item", None)
    if scalar is not None and hasattr(value, "dtype") and getattr(
        value, "ndim", 1
    ) == 0:
        value = scalar()
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, Mapping):
        return ", ".join(
            f"{k}={describe(v)}" for k, v in value.items()) or "{}"
    if isinstance(value, (str, bytes)) or not hasattr(value, "__len__"):
        return repr(value)
    items = list(value)
    if sample is None:
        sample = (
            _NAME_SAMPLE
            if items and all(isinstance(v, str) for v in items)
            else _VALUE_SAMPLE
        )
    if len(items) <= sample:
        return "[" + ", ".join(describe(v) for v in items) + "]"
    shown = ", ".join(describe(v) for v in items[:sample])
    return f"[{shown}, … +{len(items) - sample}]"


def capped(message) -> str:
    """The message, bounded. Never raises: a sentence that crashed on its own
    length would turn "no number, and here is why" into no answer at all."""
    message = str(message)
    if len(message) <= MESSAGE_CAP:
        return message
    return (
        message[:MESSAGE_CAP]
        + f"… (truncated at {MESSAGE_CAP} characters — a value was "
        f"interpolated raw; see themis.language.describe)"
    )


def occasion(value):
    """One of the occasion's numbers, as the envelope is able to hold it.

    The facts reach a reader through a field of the envelope, so they answer
    to :func:`themis.types.envelope_scalar` like everything else on that
    path — and they answer here, once, rather than at each of the sites,
    which is the arrangement that let five of them ship a numpy scalar into
    a dict on its way to ``json.dumps``.

    Containers recurse. A stratum arrives as ``{column: level}`` and a set
    of missing columns as a list, and JSON writes both down — coercing only
    the scalars would leave a Python repr standing where the structure was,
    which is the failure this half exists to prevent, one level in.

    A value that refuses the coercion is written down rather than raised
    over. That is the one place this departs from the envelope's rule, and
    the reason is the rule :func:`capped` already follows: a refusal that
    crashed while recording why it refused would turn "no number, and here
    is why" into no answer at all. The rule's own justification does not
    reach here either — a printed value is indistinguishable from a string
    value to whatever re-derives from it, and nothing re-derives from these
    fields; the schema types them ``object`` and names no key.
    """
    if isinstance(value, Mapping):
        return {str(k): occasion(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        value = sorted(value, key=str)
    if isinstance(value, (list, tuple)):
        return [occasion(v) for v in value]
    try:
        return envelope_scalar(value)
    except TypeError:
        return repr(value)


def symbols(value) -> str:
    """One of the occasion's VALUES, as a sentence carries it.

    Split from :func:`slot` because the split is the finding: this half
    answers the same way whoever is reading. A count, a column name, a
    stratum, six significant figures — brackets and quotation marks and the
    ``… +N`` of a sampled collection are symbols, and symbols are what a
    sentence in any language puts around them.

    That is what lets a slot leave the process already rendered. A surface
    that cannot run :func:`describe` — the browser cannot, and a TypeScript
    twin of it would be a second implementation with no test on this side
    able to reach it — is handed the result instead of the rule.
    """
    if isinstance(value, (float, list, tuple, Mapping)):
        return describe(value)
    return str(value)


def slot(value, lang: Lang | str = DEFAULT) -> str:
    """One of the occasion's facts, as a sentence carries it.

    A collection says how many it is and shows a few, and a float says six
    significant figures — both by way of :func:`describe`, which is where
    that judgement already lived. Everything else says itself: brackets and
    quotation marks are the SENTENCE's, and the sentence is in a table where
    one author can see both languages of it at once. Reading them off ``!r``
    at the site is what made them the site's, and it is why a column name
    arrived quoted in some refusals and bare in others.

    A WORD is the one that is not a value said back. Which matrix was
    singular, which channel was mismeasured — a member of a closed
    vocabulary, whose token is what the envelope carries and is in no
    language at all. Stringifying it would put that token into whichever
    language the sentence is in, which is the defect the tables exist to
    remove; several species could not be folded at all while this channel
    could only carry numbers, because the one thing that differed between
    their sites was exactly this.
    """
    if isinstance(value, Word):
        return type(value).said(value, lang)
    return symbols(value)


def halve(details: Mapping) -> tuple[dict[str, str], dict[str, dict]]:
    """The occasion's facts as the sentence carries them, split by kind.

    A slot holds one of two things and they leave the process differently.
    A VALUE renders the same in every language, so it travels rendered —
    once, by the one implementation of that rule. A WORD is a member of a
    closed set whose text IS the language, so it travels as the set and the
    token, and the surface that knows the reader's language looks it up in
    the table it already holds.

    Which is which is read off the value rather than declared per species:
    :class:`Word` is the type that says "my text depends on who is reading",
    and it is the only branch of :func:`slot` that does.
    """
    said: dict[str, str] = {}
    words: dict[str, dict] = {}
    for key, value in details.items():
        if isinstance(value, Word):
            words[key] = {"vocabulary": type(value).vocabulary,
                          "token": str(value)}
        else:
            said[key] = capped(symbols(value))
    return said, words


def holes(template: Words) -> set[str]:
    """Every slot name this sentence has, in any language it is written in.

    The union rather than one language's: a hole one language names and
    another does not is a hole, and which languages have it is not the
    reader's problem.
    """
    return {
        name
        for text in template.values()
        for _, name, _, _ in string.Formatter().parse(text) if name
    }


def assemble(template: Words, said: Mapping | None = None,
             words: Mapping | None = None, lang: Lang | str = DEFAULT) -> str:
    """The sentence, here, where the reader's language is known.

    The two halves :func:`halve` produced, put back. A hole this occasion
    carried nothing for is said by its own name rather than thrown over: the
    identification layer has no exception to raise and often files a refusal
    with no facts at all, and a reader there has already been told there is
    no number.
    """
    slots = {hole: f"`{hole}`" for hole in holes(template)}
    slots.update({k: str(v) for k, v in (said or {}).items()})
    for key, word in (words or {}).items():
        slots[key] = spoken(str(word.get("vocabulary") or ""),
                            str(word.get("token") or ""), lang)
    return capped(fill(template, lang, **slots))
