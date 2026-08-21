"""A reader's language was part of a name, so it could not be asked for.

Twenty-three glosses spelled it into the function (``scale_zh``), eight
tables into the table (``_PATTERN_ZH``), four vocabularies into the field
(``Layer.zh``), and one artifact into a JSON key (an audit row's ``zh``). A
name takes no argument, which is why
:func:`themis.output.explainer.explain` had carried a ``lang`` since v0.1
that raised for every value but one: the argument was right and had nowhere
to go.

The fix was not a Chinese-to-English table. 427 of the strings a reader
gets are built by interpolation, so the Chinese sentence is not a constant
and cannot be a key — the thing that was missing was **the fact without a
language on it**, which is the token a vocabulary already had.

What this module holds is the shape that makes the next language
mechanical. Not that any English exists — none does yet — but that
:class:`themis.language.Lang` is the one place that says which languages
this build has, that every reader-facing text is reachable per member per
member of it, and that nothing quietly answers in the wrong one. The
completeness of the words themselves is
``tests/test_vocabulary_reach.py::test_the_gloss_answers_for_every_member``,
which is parametrized over this vocabulary: adding a member there is what
names every word that does not exist yet, which is the whole reason the
gate is written first and the member added second.

**Two sets, and they are not one fact twice.**
:class:`themis.language.Lang` is the door — which languages a reader may be
answered in. ``ARRIVING`` is which ones have words being written. They were
the same fact while there was one language, and the second one is what
pulls them apart: a language crosses four surfaces and several thousand
strings, so its words cannot land in one change, and a build declaring a
language it can half answer in is making a false claim, so the declaration
cannot land first either. Everything below counts
:func:`themis.language.written`, the union — a tag in either set is held to
having every word — and what the door alone still guards is the surfaces
no gate covers yet.

**Where this stops.** The browser now carries the axis, so the rule below
reaches it per member per language. What this file does NOT check there is
legality — a table keyed by a tag nothing knows — because the compiler
refuses it first: those tables are typed ``Record<string, Words>`` and
``Words`` is keyed by ``Lang``, which makes a stray tag a build error
rather than a test failure. Said out loud rather than left to look like an
omission.
"""
from __future__ import annotations

import inspect
import pathlib
import re

import pytest

import themis
from themis import audits, language, ledger, risk_provenance
from themis.output import explainer
from tests import web_source
from tests.test_vocabulary_reach import VOCABULARIES, _members, _resolve
from tests.test_web_vocabularies import _declared

REPO = pathlib.Path(__file__).resolve().parent.parent
WEB = REPO / "themis" / "web" / "frontend" / "src" / "lib" / "language.ts"

#: Every spelling a language tag has ever had in this repository's names.
#: Two rather than one so the rule is about the CLASS of name and not about
#: the one that happened to be there; a third language added by spelling it
#: into a name is what this is here to refuse.
TAGS = ("zh", "en")


def _declared_tables() -> dict[str, dict]:
    """Every gloss the registry names that IS the words rather than an
    accessor over them."""
    out = {}
    for name, row in sorted(VOCABULARIES.items()):
        if not row.glossed_by:
            continue
        obj = _resolve(row.glossed_by)
        if isinstance(obj, dict):
            out[name] = obj
    return out


def _strays(tables: dict[str, dict]) -> list[str]:
    """Texts written in a language nothing here has heard of."""
    known = language.written()
    found: list[str] = []
    for name, table in tables.items():
        for member, words in table.items():
            assert isinstance(words, dict), (name, member)
            found += [f"{name}.{member}.{tag}" for tag in words
                      if tag not in known]
    return sorted(found)


def _language_in_the_name(dotted: str) -> bool:
    """A gloss whose spelling fixes which reader it answers."""
    tail = dotted.rsplit(".", 1)[-1].lower()
    return any(tail.endswith(f"_{tag}") for tag in TAGS)


def _browser_set(name: str, source: str) -> set[str]:
    """One of the browser's two language lists."""
    listed = re.search(rf"export const {name} = \[(.*?)\] as const",
                       source, re.S)
    assert listed, f"lib/language.ts declares no {name}"
    return {m.group(1) for m in re.finditer(r"'([^']+)'", listed.group(1))}


def _browser_langs(source: str) -> tuple[set[str], str | None]:
    """What ``lib/language.ts`` says this page can answer in."""
    default = re.search(r"export const DEFAULT_LANG: Lang = '([^']+)'",
                        source)
    return (_browser_set("LANGS", source),
            default.group(1) if default else None)


# --- the vocabulary itself ---------------------------------------------------

def test_the_build_says_which_languages_it_has():
    assert list(language.Lang), "a build answers in at least one language"
    assert language.DEFAULT in set(language.Lang)


def test_a_language_is_either_answered_in_or_arriving():
    """Both at once would be a claim contradicting itself: the words are
    finished and the words are being written."""
    assert not (language.ARRIVING & {str(x) for x in language.Lang})


def test_the_denominator_is_the_two_sets_and_nothing_else():
    """Derived, so the union cannot come apart from the sets it is of."""
    assert language.written() == (
        {str(x) for x in language.Lang} | language.ARRIVING)


@pytest.mark.parametrize("tag", sorted(language.ARRIVING))
def test_nothing_answers_in_a_language_that_is_only_arriving(tag):
    """A language whose words are half written is refused at the door, so
    no reader ever gets the half. It is the door that says so and not the
    tables: the tables are held to being complete either way, which is what
    makes promoting the tag a change of one line."""
    with pytest.raises(NotImplementedError):
        explainer.explain(None, tag)


def test_every_declared_word_is_in_a_language_this_build_declares():
    """A table keyed by a tag nothing answers to is a word nobody reads.

    The sharp end of the whole arrangement: a typo in a language key, or a
    tag left behind by a language that was removed, is a text that exists
    and is unreachable — and it reads exactly like a text that was never
    written, which is the failure this repository keeps finding.

    Only the tables can be walked; a gloss that is a function is asked
    instead, once per language, by ``test_the_gloss_answers_for_every_member``.
    """
    strays = _strays(_declared_tables())
    assert not strays, (
        f"{strays} are texts in a language this build does not answer in, "
        f"which reach no reader and read like texts nobody wrote"
    )


@pytest.mark.parametrize("vocabulary", [ledger.Severity, ledger.Layer,
                                        ledger.Provenance,
                                        risk_provenance.RiskProvenance])
def test_a_member_carries_its_words_and_not_one_language(vocabulary):
    known = language.written()
    for member in vocabulary:
        assert not hasattr(member, "zh"), (
            f"{member} still carries a field named after a language")
        assert set(member.words) <= known, member
        assert member.words[language.DEFAULT].strip(), member


def test_an_audit_row_is_not_keyed_by_a_language():
    """The most literal form of it: a JSON key named after a language.

    A caller holding that row could not ask for the other one, because the
    request had nowhere to go.
    """
    for row in audits.AUDITS:
        assert not hasattr(row, "zh"), row.name
        assert row.words[language.DEFAULT].strip(), row.name


# --- no gloss is named after a language --------------------------------------

def test_no_gloss_the_registry_names_has_a_language_in_its_name():
    """The denominator is the registry, not the package.

    The report's own sentences are still written by functions called
    ``_explain_effect_zh``, and they are not glosses of a closed
    vocabulary — a different denominator and a different job. What can be
    held today is the set with a gate behind it.
    """
    named = sorted(row.glossed_by for row in VOCABULARIES.values()
                   if row.glossed_by
                   and _language_in_the_name(row.glossed_by))
    assert not named, (
        f"{named} spell a language into a name, so a reader of the other "
        f"one cannot be asked for"
    )


@pytest.mark.parametrize("name", sorted(
    n for n, v in VOCABULARIES.items()
    if v.glossed_by and not isinstance(_resolve(v.glossed_by), dict)))
def test_every_gloss_that_is_a_function_takes_the_language(name):
    """So the registry can ask any of them the same way."""
    fn = _resolve(VOCABULARIES[name].glossed_by)
    params = list(inspect.signature(fn).parameters)
    assert len(params) >= 2, (VOCABULARIES[name].glossed_by, params)
    member = sorted(_members(name))[0]
    assert fn(member, language.DEFAULT) == fn(member)


# --- nothing answers in the language that was not asked for ------------------

def test_a_missing_text_is_not_answered_in_another_language():
    """The counterexample the whole shape exists for.

    A build that fell back to its first language would put a Chinese
    sentence into an English report — which is the defect this repository
    has already registered once, not the fix for it.
    """
    only_other = {"xx": "a word in a language nobody asked for"}
    assert language.say(only_other, language.DEFAULT, unknown="!") == "!"
    assert language.gloss({"m": only_other}, "m") == "`m`"


def test_an_unknown_value_and_an_unsayable_one_read_alike():
    """Both hand back the identifier, and only one of them is meant to.

    A value from another build's envelope is expected and permanent; a
    value this build knows with no text is a hole the completeness gate
    keeps empty. A reader can act on neither, so they render the same —
    stated here so that nobody reads the shared fallback as one fact.
    """
    assert language.gloss({}, "never_heard_of_it") == "`never_heard_of_it`"
    assert language.gloss({"known": {}}, "known") == "`known`"


def test_the_words_of_one_thing_sit_together():
    """Keyed by language inside each member, not by member inside each
    language: two distant records of one fact drift, and adjacency is the
    only structural defence. Held on the shape rather than on a comment."""
    for member in ledger.Layer:
        assert set(member.words) & {str(x) for x in language.Lang}


# --- the argument that existed now selects among the vocabulary --------------

def test_explain_refuses_a_language_this_build_does_not_answer_in():
    with pytest.raises(NotImplementedError, match="does not|is not one"):
        explainer.explain(None, "kl")


@pytest.mark.parametrize("lang", sorted(language.Lang, key=str))
def test_explain_accepts_every_language_the_build_declares(lang):
    """Reaches the vocabulary check and fails afterwards on the ``None``
    result, which is what says the language was accepted."""
    with pytest.raises(AttributeError):
        explainer.explain(None, lang)


# --- the browser knows the same set ------------------------------------------

def test_the_browser_answers_in_the_same_languages():
    """A language the kernel has and the browser does not is a page that
    cannot show what the answer holds; one the browser has alone is a
    choice with nothing behind it.

    Which set, not which words: see the module docstring for why the second
    question cannot be asked of that surface yet."""
    web, default = _browser_langs(web_source.read(WEB))
    assert web == {str(x) for x in language.Lang}
    assert default == str(language.DEFAULT)


def test_the_browser_declares_the_same_two_sets():
    """Not only which languages are answered in but which are on the way.

    The two lists mean different things on this surface as well — one is
    what a chooser may offer, the other is what its tables are held to
    hold — and a browser whose ARRIVING disagreed with the kernel's would
    be held to a different denominator than the kernel it renders."""
    source = web_source.read(WEB)
    assert _browser_set("ARRIVING", source) == language.ARRIVING


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_the_browser_has_a_word_for_every_member_in_every_language(lang):
    """What the previous tier could not ask.

    Its tables had no language axis, so "LANGS says English and the page is
    Chinese" was a failure nothing caught. They have one now, and the
    denominator is the same union the kernel counts — which is what makes
    the second language arrive on both surfaces or on neither.
    """
    source = web_source.read(web_source.VERDICT)
    holes = [
        f"{table}.{member}"
        for table in sorted(set(_declared().values()))
        for member, said in web_source.members(table, source).items()
        if not re.search(rf"\b{lang}:", said)
    ]
    assert not holes, (
        f"{holes} have no {lang} text — each reaches a reader of that "
        f"language as its own identifier"
    )


def test_the_package_exposes_the_vocabulary():
    """A caller choosing a language has to be able to name the choices."""
    assert themis.language.Lang is language.Lang


# --- what each of those refuses ----------------------------------------------
#
# A rule nobody has watched say no is a rule about the corpus that happened
# to be there. Each below runs the SAME predicate the rule above runs, on a
# table doctored one way.

def test_a_word_in_a_language_nobody_answers_in_is_refused():
    doctored = {name: dict(table) for name, table in _declared_tables().items()}
    name, table = sorted(doctored.items())[0]
    member = sorted(table)[0]
    table[member] = {**table[member], "kl": "a text no reader can reach"}
    assert _strays(doctored) == [f"{name}.{member}.kl"]


def test_a_member_whose_words_are_a_bare_string_is_refused():
    """The shape before this item: one text, and no way to ask for another."""
    doctored = {"made_up": {"m": "a sentence with no language on it"}}
    with pytest.raises(AssertionError):
        _strays(doctored)


@pytest.mark.parametrize("spelled", [
    "themis.ledger.layer_zh",
    "themis.output.envelope_glossary.scale_en",
    "themis.output.analysis_report._PATTERN_ZH",
])
def test_a_gloss_named_after_a_language_is_refused(spelled):
    assert _language_in_the_name(spelled)


@pytest.mark.parametrize("kept", [
    "themis.ledger.layer_word",
    "themis.output.analysis_report._PATTERN_WORDS",
    "themis.risk_provenance.describe",
])
def test_a_gloss_named_after_what_it_glosses_is_kept(kept):
    assert not _language_in_the_name(kept)


def test_a_language_in_both_sets_is_refused():
    """Answered in and still being written is not a state a language can be
    in; it is two records of one language disagreeing about whether it is
    finished. Run against a doctored ARRIVING holding a tag the build
    already answers in."""
    doctored = frozenset({str(language.DEFAULT)})
    assert doctored & {str(x) for x in language.Lang}


def test_a_browser_missing_a_member_in_one_language_is_refused():
    """The doctored table the rule above has to say no to: a member with a
    word in one language and nothing in the other, which is precisely what
    a half-finished translation looks like."""
    said = {"half": "{ zh: '有词' }", "whole": "{ zh: '有词', kl: 'a word' }"}
    assert [m for m, s in said.items() if not re.search(r"\bkl:", s)] == \
        ["half"]


def test_a_browser_offering_a_language_the_kernel_lacks_is_refused():
    web, _ = _browser_langs(
        "export const LANGS = ['zh', 'kl'] as const\n"
        "export const DEFAULT_LANG: Lang = 'zh'\n")
    assert web != {str(x) for x in language.Lang}


def test_a_browser_defaulting_to_another_language_is_refused():
    langs = ", ".join(f"'{x}'" for x in sorted(str(x) for x in language.Lang))
    _, default = _browser_langs(
        f"export const LANGS = [{langs}] as const\n"
        "export const DEFAULT_LANG: Lang = 'kl'\n")
    assert default != str(language.DEFAULT)
