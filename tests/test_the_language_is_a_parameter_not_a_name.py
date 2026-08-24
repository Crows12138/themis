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

import ast
import inspect
import pathlib
import re
import string
from typing import NamedTuple

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


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_an_audit_says_what_it_re_derives_in_every_language(lang):
    """The rows are a table the registry does not reach.

    Every other vocabulary is counted per member per language in
    ``tests/test_vocabulary_reach.py``, and these are not members of one —
    an audit row is an artifact a caller receives, and its sentence is what
    tells whoever is deciding whether to trust the answer what was
    recomputed. A row with no sentence in the reader's language would say
    only its own snake_case name, which is the developer's handle.
    """
    wordless = sorted(row.name for row in audits.AUDITS
                      if not row.words.get(lang, "").strip())
    assert not wordless, (
        f"{wordless} do not say in {lang} what they re-derive"
    )


# --- no gloss is named after a language --------------------------------------

def test_no_gloss_the_registry_names_has_a_language_in_its_name():
    """The registry's own reading of the rule below.

    Kept beside the package-wide one because it fails differently: this
    names the vocabulary whose other reader cannot be asked for, and the
    wider check names a file and a line.
    """
    named = sorted(row.glossed_by for row in VOCABULARIES.values()
                   if row.glossed_by
                   and _language_in_the_name(row.glossed_by))
    assert not named, (
        f"{named} spell a language into a name, so a reader of the other "
        f"one cannot be asked for"
    )


class _Named(NamedTuple):
    """A name bound in the package, and where."""

    #: ``path:name`` — what the debt list keys on, so that a line moving
    #: is not an edit here.
    where: str
    line: int


def _named_after_a_language(root: pathlib.Path) -> list[_Named]:
    """Every name bound under ``root`` that is written for one reader.

    Every scope, not just the module's: a local holding one language's
    word is the same defect one level down, and it was the last of them.
    A whole underscore-delimited segment rather than a suffix, because
    ``en`` is a substring of half the English in the package.

    A name that is nothing BUT a tag is naming the language itself, which
    is how a reader's choice gets spelled at all — refuse those and the
    parameter has no values left to take. What this is about is a tag
    ATTACHED to something else: a name doing the job of an argument.
    """
    segment = re.compile(r"(^|_)(" + "|".join(TAGS) + r")($|_)")
    found: list[_Named] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                name = node.name
            elif isinstance(node, ast.arg):
                name = node.arg
            elif (isinstance(node, ast.Name)
                  and isinstance(node.ctx, ast.Store)):
                name = node.id
            else:
                continue
            plain = name.lower().strip("_")
            if plain in TAGS or not segment.search(plain):
                continue
            found.append(_Named(
                f"{path.relative_to(root).as_posix()}:{name}", node.lineno))
    return sorted(found)


def test_no_name_in_the_package_is_written_for_one_reader():
    """The rule the registry's version was a slice of.

    A gloss called ``scale_zh`` cannot be asked for the other reader —
    that is the whole of it. The reason the check above could hold only
    the registry was that the report's own sentences were still written
    by ten functions called ``_explain_effect_zh``: a table of
    one-language producers, which is what ``explain(result, lang)`` had
    to hand its argument to. They take the reader's language now, so the
    denominator is the package.

    With no exceptions, which is the state a list of them existed to
    reach: one batch carried a single named row here — the analysis
    report's ``_VERDICT_ZH``, honest while its table really was one
    language — and the row went when the table did.
    """
    named = _named_after_a_language(REPO / "themis")
    assert not named, (
        "these spell a language into a name, and a name takes no "
        "argument:\n" + "\n".join(f"{r.where}:{r.line}" for r in named))


def test_a_name_written_for_one_reader_is_refused(tmp_path):
    """What the rule above says no to, and what it must go on allowing.

    The second file is the vocabulary's own member. A rule that swept it
    up would read as stricter and be unusable: the language a reader
    picks has to be spelled somewhere.
    """
    (tmp_path / "m.py").write_text("def scale_zh(value):\n    return value\n",
                                   encoding="utf-8")
    (tmp_path / "v.py").write_text('ZH = "zh"\n', encoding="utf-8")
    assert _named_after_a_language(tmp_path) == [_Named("m.py:scale_zh", 1)]


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
    assert language.gloss({"m": only_other}, "m") == language.absent(
        "no_word_for_this_token", token="m")


def test_an_unknown_value_and_an_unsayable_one_read_alike():
    """Both say the same thing, and only one of them is meant to.

    A value from another build's envelope is expected and permanent; a
    value this build knows with no text is a hole the completeness gate
    keeps empty. A reader can act on neither, so they render the same —
    stated here so that nobody reads the shared marker as one fact.
    Separating them would need this surface's twin to carry a second copy
    of the language-name table for a case the completeness gate already
    keeps empty; what the marker does buy is that neither of them can be
    read as a NAME any more.
    """
    unsayable = language.absent("no_word_for_this_token",
                                token="never_heard_of_it")
    assert language.gloss({}, "never_heard_of_it") == unsayable
    assert language.gloss({"known": {}}, "known") == language.absent(
        "no_word_for_this_token", token="known")


# --- an absence does not wear the notation of a presence ---------------------
#
# Backticks mean "a name" everywhere else a reader looks, and both stand-ins
# were spelled that way, so three different things arrived identical: the
# thing the sentence is ABOUT, a fact this occasion did not carry, and a
# value this build has no word for. The rule is not which bracket they wear
# — it is that a reader can tell an absence from a presence.
#
# Their texts, their per-language completeness and their hole parity are
# already counted by the scan above: ``ABSENT`` and ``ABSENCE_WORDS`` are
# ``Words`` literals like any other, on both surfaces. What is left is what
# no scan over literals can see — that the two tables are the same table,
# and that neither of them renders as a name.

def _absence_reads_as_a_name(said: str) -> bool:
    """A rendering a reader would take for the thing being talked about."""
    return re.fullmatch(r"`[^`]*`", said.strip()) is not None


@pytest.mark.parametrize("lang", sorted(language.written()))
@pytest.mark.parametrize("kind", sorted(language.ABSENT))
def test_an_absence_does_not_render_as_a_name(kind, lang):
    """What the defect was, per marker per language.

    A slot nothing filled came out ``\\`column\\``` and a token with no word
    came out ``\\`sideways\\```, which is exactly how the sentence around
    them writes a column that IS there. The stand-in has to say that
    something is missing, and a bare backticked identifier says the
    opposite.
    """
    said = language.absent(kind, lang, name="a_slot", token="a_token")
    assert not _absence_reads_as_a_name(said), (
        f"ABSENT[{kind!r}][{lang!r}] renders as {said!r}, which is how this "
        f"repository writes a name that is present"
    )


def test_a_marker_spelled_the_old_way_is_refused():
    """The counterexample, spelled the way both of them were."""
    assert _absence_reads_as_a_name("`column`")
    assert _absence_reads_as_a_name("  `sideways`  ")
    assert not _absence_reads_as_a_name("（未提供 column）")
    assert not _absence_reads_as_a_name("`sideways`（本版本没有它的说法）")


def test_both_surfaces_put_the_same_thing_where_a_fact_is_missing():
    """The one table this surface restates by hand rather than generates.

    Twenty vocabularies reach it from ``kernelWords.generated.ts``, and
    these two rows cannot: that generator anchors every row on what an
    ENVELOPE may carry, and a marker is what a renderer puts where nothing
    was carried. So they sit with the mechanism that uses them — ``say``,
    ``fill`` and ``holes`` are hand-written twins on that surface too — and
    what generating would have bought for four strings is this.
    """
    web = web_source.words_map("ABSENCE_WORDS", web_source.read(WEB))
    assert web == {kind: dict(words)
                   for kind, words in language.ABSENT.items()}


# --- the stand-in is the door's answer, not each caller's ---------------------
#
# Changing what the two markers say changed nothing anybody read, because
# twenty-five call sites had already written the old answer out by hand: six
# passed ``unknown=`` the very value they were glossing, two spelled the
# backticked identifier the marker replaced, and seventeen more did one or
# the other on the browser. A default that every caller overrides is not a
# default, and each copy is a place the reader's word can go back to being
# a name.
#
# So the door answers all three cases — a value with a word, a value with no
# word, and NO value — and what a caller may still say is a phrase neither
# of those would fit into. Two rules say that exactly: a fallback may not be
# built out of the value it stands in for, and it may not wear the notation
# of a name. The first is what the six were; the second is what the other
# two were, and it catches the shape the first cannot see, where the
# fallback is a template rather than the value itself.
#
# ``say`` on the browser is out of the first rule's reach on purpose. Its
# subject is a ``Words`` with no token in it, so its callers' fallback is a
# different question — one about 165 component sites that hand back the
# key's own name — which is registered rather than folded in here.

def _handed_to_absent_only(subject: ast.AST, fallback: ast.AST) -> set[str]:
    """What a fallback takes from the value other than to name it.

    Passing the value to :func:`themis.language.absent` is the one thing a
    caller may do with it: that is what turns it from a name into a
    stand-in that says it is one.
    """
    class _Strip(ast.NodeTransformer):
        def visit_Call(self, node):
            called = (node.func.attr if isinstance(node.func, ast.Attribute)
                      else getattr(node.func, "id", None))
            return None if called == "absent" else self.generic_visit(node)

    def roots(node):
        return ({n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
                | {n.attr for n in ast.walk(node)
                   if isinstance(n, ast.Attribute)})

    left = _Strip().visit(ast.parse(ast.unparse(fallback)))
    return roots(subject) & roots(left)


#: A stand-in spelled the way this repository spells a name that is there.
_A_NAME = re.compile(r"^`\{[^{}]*\}`$")


def _fallbacks() -> list[tuple[str, str, ast.AST, ast.AST]]:
    """Every ``(where, which door, value, fallback)`` in the package."""
    out = []
    for path in sorted((REPO / "themis").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = (node.func.attr if isinstance(node.func, ast.Attribute)
                    else getattr(node.func, "id", None))
            if name not in ("say", "gloss"):
                continue
            named = next((k for k in node.keywords if k.arg == "unknown"),
                         None)
            if named is None:
                continue
            out.append((f"{path.relative_to(REPO).as_posix()}:{node.lineno}",
                        name, node.args[1 if name == "gloss" else 0],
                        named.value))
    return out


def test_no_caller_hands_back_the_value_it_was_glossing():
    """The six, and what makes a seventh visible."""
    offenders = [
        f"{where}  {name}({ast.unparse(subject)}) fell back on "
        f"{ast.unparse(fallback)}"
        for where, name, subject, fallback in _fallbacks()
        if _handed_to_absent_only(subject, fallback)
    ]
    assert not offenders, "\n".join(offenders) + (
        "\n`gloss` already answers an unlisted value, and says that it is "
        "standing in; a fallback built out of the value is that answer "
        "written out again without the part that says so"
    )


def test_the_scan_reaches_every_fallback_a_caller_names():
    """A denominator, so the rule above is not green by seeing nothing.

    Counted the other way round: every ``unknown=`` written anywhere in the
    package, which is one per fallback named and is not the reading the
    scan makes. A fallback passed through a door the scan does not know the
    name of arrives here as a keyword nothing reached."""
    written = [
        f"{path.relative_to(REPO).as_posix()}:{i}"
        for path in sorted((REPO / "themis").rglob("*.py"))
        for i, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"(?<![\w.])unknown=", line)
    ]
    reached = {where for where, _, _, _ in _fallbacks()}
    assert len(written) == len(reached), (
        f"{len(written)} `unknown=` written, {len(reached)} reached: "
        f"{sorted(set(written) - reached)}"
    )


@pytest.mark.parametrize("surface", ["kernel", "browser"])
def test_no_stand_in_is_spelled_as_a_name(surface):
    """What both markers used to be, on whichever surface writes it.

    Backticks mean "a name" in every sentence this repository writes, so a
    fallback that is nothing but a backticked hole hands the reader a
    presence where an absence happened — which is what
    :func:`themis.language.absent` exists to stop being possible.
    """
    offenders = []
    if surface == "kernel":
        for where, name, _subject, fallback in _fallbacks():
            if isinstance(fallback, ast.JoinedStr) and _A_NAME.match(
                    "".join(p.value if isinstance(p, ast.Constant) else "{}"
                            for p in fallback.values)):
                offenders.append(f"{where}  {ast.unparse(fallback)}")
    else:
        for path in (sorted(web_source.SRC.rglob("*.ts"))
                     + sorted(web_source.SRC.rglob("*.tsx"))):
            text = web_source.read(path)
            for door, wanted in (("gloss", 4), ("say", 3)):
                for line, args in web_source.calls(door, text):
                    if len(args) < wanted:
                        continue
                    said = args[wanted - 1].strip()
                    if re.fullmatch(r"`\\`\$\{[^{}]*\}\\``", said):
                        offenders.append(
                            f"{path.relative_to(REPO).as_posix()}:{line}"
                            f"  {said}")
    assert not offenders, "\n".join(offenders)


#: A `say` fallback with its `absent(...)` taken out — what is left is what
#: the call site invented for itself.
_ABSENT_CALL = re.compile(r"\babsent\([^()]*(\([^()]*\))?[^()]*\)")
#: Every string in it, empty ones included — matched left to right, because
#: a pattern that skips the empty ones reads two adjacent ones as a single
#: long string with the code between them inside it.
_A_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")


def test_no_call_site_writes_the_text_a_missing_word_is_replaced_by():
    """153 sites wrote the key's own name, and it is not a reader's word.

    ``say`` demands a fallback because its subject may be a ``Words`` that
    came from outside this build. A component's own ``SAYS.title`` is not
    that: it is a literal in the same file, and the completeness rule above
    keeps it whole in every language — so its fallback stood for a case
    that cannot happen, and what 153 authors put there was the key. To a
    reader `ledeMid1` is not a name of anything; it is not even a token
    they could look up, which is the whole argument for keeping one.

    So a text this build wrote goes through ``fill``, where absence throws
    rather than degrading — that being what absence means for a text this
    build wrote — and ``say`` is left to the subjects that really did
    arrive from elsewhere, where the stand-in is
    :func:`themis.language.absent`'s to write. The empty string stays: it
    is not reader-facing text, it is a caller saying print nothing.
    """
    offenders = []
    for path in (sorted(web_source.SRC.rglob("*.ts"))
                 + sorted(web_source.SRC.rglob("*.tsx"))):
        text = web_source.read(path)
        for line, args in web_source.calls("say", text):
            if len(args) < 3:
                continue
            said = _ABSENT_CALL.sub("", args[2])
            if any(len(m) > 2 for m in _A_LITERAL.findall(said)):
                offenders.append(
                    f"{path.relative_to(REPO).as_posix()}:{line}"
                    f"  fell back on {args[2].strip()}")
    assert not offenders, "\n".join(offenders) + (
        "\na text this build wrote is complete in every language, so a "
        "fallback invented at the call site stands for nothing; `fill` is "
        "the door for it, and `absent` writes the stand-in for the texts "
        "that really did come from elsewhere"
    )


def test_the_browser_gloss_does_not_hand_back_its_token_either():
    """The same rule where the same door is written a second time."""
    offenders = []
    for path in (sorted(web_source.SRC.rglob("*.ts"))
                 + sorted(web_source.SRC.rglob("*.tsx"))):
        text = web_source.read(path)
        for line, args in web_source.calls("gloss", text):
            if len(args) < 4:
                continue
            value, said = args[1].strip(), args[3].strip()
            said = re.sub(r"absent\([^()]*(\([^()]*\))?[^()]*\)", "", said)
            if set(re.findall(r"\w+", value)) & set(re.findall(r"\w+", said)):
                offenders.append(
                    f"{path.relative_to(REPO).as_posix()}:{line}"
                    f"  gloss({value}) fell back on {said}")
    assert not offenders, "\n".join(offenders)


def test_the_words_of_one_thing_sit_together():
    """Keyed by language inside each member, not by member inside each
    language: two distant records of one fact drift, and adjacency is the
    only structural defence. Held on the shape rather than on a comment."""
    for member in ledger.Layer:
        assert set(member.words) & {str(x) for x in language.Lang}


# --- a sentence asks for the same things in whichever language it is in ------
#
# A word is finished when it exists. A SENTENCE is not: it has holes, and a
# translation of it has to have the same ones. Two languages putting the
# facts in different places is the whole reason
# :func:`themis.language.fill` exists rather than an f-string, and it is
# also why nothing downstream can notice the mismatch — ``format`` fills
# what it is given and drops what it is not, so a translation that lost a
# slot renders as a shorter sentence rather than as an error. The parity is
# checkable exactly, so it is checked here rather than trusted.


def _holes(text: str) -> set[str] | None:
    """The names this sentence asks to be filled, or None if it cannot be.

    A name is taken at its root, because ``{x.y}`` and ``{x[0]}`` are one
    argument read two ways, and it is the argument the caller has to pass.
    """
    try:
        parsed = list(string.Formatter().parse(text))
    except ValueError:
        return None
    names = set()
    for _, field, _, _ in parsed:
        if field is None:
            continue
        root = re.split(r"[.\[]", field, maxsplit=1)[0]
        if root == "" or root.isdigit():
            return None            # a hole whose name is its position
        names.add(root)
    return names


def _words_in(tree: ast.AST) -> list[tuple[int, dict[str, str]]]:
    """Every ``Words`` literal, recognised by its own keys.

    A dict whose every key names a language IS the words, whatever it is
    bound to — the same reading the language gate makes, and available
    here without the gate's slot machinery, because the keys are the whole
    evidence.
    """
    known, found = language.written(), []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict) or not node.keys:
            continue
        pairs = {}
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant)
                    and isinstance(key.value, str)):
                break
            text = _joined(value)
            if text is None:
                break
            pairs[key.value] = text
        else:
            if pairs and set(pairs) <= known:
                found.append((node.lineno, pairs))
    return found


def _joined(node: ast.AST) -> str | None:
    """A string literal, including one written across adjacent pieces.

    An f-string reads as its constant parts with ``{}`` where each
    interpolation was, which is what it is: a sentence whose holes are
    named by their position. Nothing special happens to it here — the
    parity rule below already refuses that, and refusing it in one place
    is why a ``Words`` built at its point of use has to become a template
    with names and a :func:`themis.language.fill`.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value if isinstance(part, ast.Constant) else "{}"
            for part in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _joined(node.left), _joined(node.right)
        return None if left is None or right is None else left + right
    return None


def _every_words_literal():
    """(file, line, words) for both surfaces that hold sentences.

    One scan over two languages of source, because the rule is about the
    sentence rather than about where it is stored — and the browser is
    where a mismatch would be least visible: it fills its holes with
    ``replace``, which leaves an unfilled one printed on the page.
    """
    for path in sorted((REPO / "themis").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, pairs in _words_in(tree):
            yield path.relative_to(REPO).as_posix(), line, pairs
    for path in (sorted(web_source.SRC.rglob("*.ts"))
                 + sorted(web_source.SRC.rglob("*.tsx"))):
        text = web_source.read(path)
        for line, pairs in web_source.words_literals(text, language.written()):
            yield path.relative_to(REPO).as_posix(), line, pairs


#: A language tag written as a key. One per language per ``Words``, which
#: makes it the denominator of the scan above without being a number
#: anybody had to count.
_PY_TAG_KEY = re.compile(r"[\"'](" + "|".join(TAGS) + r")[\"']\s*:")
_TS_TAG_KEY = re.compile(r"(?<![\w'\"`])(" + "|".join(TAGS) + r")\s*:")


def test_the_scan_reaches_every_words_that_is_written():
    """A scan that finds nothing passes every rule built on it.

    Which is this repository's registered failure, once: a gate whose
    denominator was whatever it happened to be looking at. So the rules
    below are worth their green only if the scan reaches every ``Words``
    there is — and what says it does is not a count anybody wrote down. It
    is every place a language tag is used as a key, which is exactly one
    per language per ``Words``. A ``Words`` written in a shape the scan
    cannot read arrives here as a tag nothing reached, which is how the
    browser's 50 structured ones were found.
    """
    short = []
    for path in sorted((REPO / "themis").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        keys = len(_PY_TAG_KEY.findall(text))
        reached = sum(len(p) for _, p in _words_in(ast.parse(text)))
        if keys != reached:
            short.append(f"{path.name}: {keys} tag keys, {reached} reached")
    for path in (sorted(web_source.SRC.rglob("*.ts"))
                 + sorted(web_source.SRC.rglob("*.tsx"))):
        text = web_source.read(path)
        keys = len(_TS_TAG_KEY.findall(text))
        reached = sum(len(p) for _, p in
                      web_source.words_literals(text, language.written()))
        if keys != reached:
            short.append(f"{path.name}: {keys} tag keys, {reached} reached")
    assert not short, "\n".join(short)


def test_every_words_is_written_in_every_language_this_build_writes():
    """Not only that the two languages agree — that both are there.

    The rule beside this one compares the languages a ``Words`` HAS. It
    says nothing about a ``Words`` that has one, and one is what a text
    written during the second language's arrival looks like. This is the
    completeness half, over the same scan, and it is what makes the
    fallback in :func:`themis.language.say` unreachable for a text this
    build wrote — which is the difference between "absence is a fact about
    the reader's language" and "absence is a defect in this build".

    ``ARRIVING`` is what a half-written language is for. A language is
    declared there while its texts land, and every ``Words`` is held to it
    from the moment it is declared — so the intermediate state is a
    language nobody may be answered in yet, never a text with a hole.
    """
    short = [
        f"{module}:{line}  has {sorted(pairs)}"
        for module, line, pairs in _every_words_literal()
        if set(pairs) != language.written()
    ]
    assert not short, "\n".join(short) + (
        f"\neach is missing one of {sorted(language.written())}; a reader of "
        f"that language reaches this text through a fallback instead"
    )


def test_a_sentence_asks_for_the_same_things_in_every_language():
    """Whatever one language interpolates, the others interpolate too."""
    apart = []
    for module, line, pairs in _every_words_literal():
        asked = {tag: _holes(text) for tag, text in pairs.items()}
        if None in asked.values() or len(set(map(frozenset, asked.values()))) > 1:
            apart.append(f"{module}:{line}  " + "  ".join(
                f"{tag}={'unnamed' if h is None else sorted(h)}"
                for tag, h in sorted(asked.items())))
    assert not apart, "\n".join(apart)


def test_a_translation_that_lost_a_slot_is_refused():
    """The counterexample. ``format`` would render this without complaint,
    one language short of a fact, which is why the check is on the pair."""
    line, pairs = _words_in(ast.parse(
        '{"zh": "区间宽 {factor} 倍", "en": "the interval is wider"}'))[0]
    assert _holes(pairs["zh"]) != _holes(pairs["en"])


def test_a_hole_with_no_name_is_refused():
    """``{}`` means "whatever comes next", and two languages disagree about
    what comes next — which is the reason ``fill`` takes names only."""
    _, pairs = _words_in(ast.parse('{"zh": "宽 {} 倍", "en": "{} times"}'))[0]
    assert _holes(pairs["zh"]) is None


def _formatting_by_hand() -> list[str]:
    """Every ``.format(`` in the package that is not ``fill``'s own.

    There is no exception list. There was one for as long as it took the
    assumption glossary's 138 claims to become ``Words`` with named holes —
    one line, which the rule beside it then asked to have deleted. An empty
    exception list guarded by an always-skipped test says less than the rule
    saying itself, so what is left is the rule.
    """
    found = []
    for path in sorted((REPO / "themis").rglob("*.py")):
        module = path.relative_to(REPO).as_posix()
        if module == "themis/language.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "format"):
                found.append(f"{module}:{node.lineno}")
    return found


def test_filling_a_sentences_holes_is_fills_alone():
    """``say`` and ``fill`` differ in what they do when the language is
    missing, and the difference only counts if ``fill`` is the way through.

    ``say`` hands back the caller's fallback, which for a sentence is the
    empty string — so ``say(...).format(...)`` gives the reader nothing and
    reports success. ``fill`` raises, because a sentence has no identifier
    to hand over the way a word does. Two call sites did it by hand, and
    one of them was a refusal: the reader would have been told nothing at
    all about why there was no number.
    """
    assert not _formatting_by_hand(), (
        "these fill a template themselves: " + ", ".join(_formatting_by_hand())
        + ". Make it a Words and call language.fill — or, if what is being "
        "filled is not a sentence a reader gets, say so here and excuse it.")


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


#: What the kernel's language module offers a caller, and therefore what
#: the browser's half has to offer too. Read off the kernel rather than
#: listed, so a fourth lookup written there is a fourth the browser is
#: asked for — the gap this catches is the one that was here: the browser
#: had the word half and not the sentence half.
_LOOKUPS = ("say", "gloss", "fill")


def test_both_surfaces_offer_the_same_lookups():
    """A surface missing one does not fail — it improvises.

    ``fill`` was absent here, and the one sentence in ``verdict.ts`` that
    had a hole was filled with a hand-written ``String.replace``: the slot
    name at the call site and the slot name in the text were two literals
    that had to happen to agree, and when they did not the reader got
    ``{factor}`` printed on the page. Nothing was broken enough to notice,
    which is what an improvised half of a contract looks like.
    """
    source = web_source.read(WEB)
    for name in _LOOKUPS:
        assert callable(getattr(language, name, None)), (
            f"themis.language no longer offers {name}; this list is read off "
            f"the kernel and has to be corrected there first"
        )
        assert re.search(rf"^export function {name}\b", source, re.M), (
            f"the kernel offers {name} and the browser's language.ts does "
            f"not, so this surface has to improvise a {name} of its own "
            f"wherever it needs one"
        )


#: A named hole filled by hand. The mechanism is ``fill``, which throws on a
#: slot nothing was given for; ``replace`` prints the hole instead, and a
#: hole printed on the page is indistinguishable to a reader from a word
#: nobody wrote.
_HAND_FILLED = re.compile(r"\.replace\(\s*['\"`]\{")


def _filled_by_hand(text: str) -> list[int]:
    return [i for i, line in enumerate(text.splitlines(), 1)
            if _HAND_FILLED.search(line)]


def test_no_sentence_has_its_hole_filled_by_hand():
    """One call site is a convention; the rule is what makes it one.

    82 more sentences with holes are on their way onto this surface, and
    each would otherwise be free to grow its own ``replace`` — which is how
    the one that was here came about. A slot is a name in a contract or it
    is two literals that agree by luck, and this is the difference.
    """
    offenders = [
        f"{path.relative_to(REPO).as_posix()}:{line}"
        for path in (sorted(web_source.SRC.rglob("*.ts"))
                     + sorted(web_source.SRC.rglob("*.tsx")))
        for line in _filled_by_hand(web_source.read(path))
    ]
    assert not offenders, (
        f"{offenders} fill a named hole with String.replace; `fill` is where "
        f"a slot nothing was given for throws instead of reaching the reader"
    )


def test_the_check_sees_a_hole_filled_by_hand():
    """The counterexample, spelled the way the real one was."""
    assert _filled_by_hand(
        "  value: said.replace('{factor}', fmtNum(x)),") == [1]
    assert _filled_by_hand(
        "  return s.replace(/_/g, ' ')\n  x.replace('a', 'b')") == []


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_the_browser_has_a_word_for_every_member_in_every_language(lang):
    """What the previous tier could not ask.

    Its tables had no language axis, so "LANGS says English and the page is
    Chinese" was a failure nothing caught. They have one now, and the
    denominator is the same union the kernel counts — which is what makes
    the second language arrive on both surfaces or on neither.
    """
    source = web_source.vocabularies()
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
