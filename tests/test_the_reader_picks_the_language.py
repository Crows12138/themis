"""The language is the reader's choice, on every surface a reader reaches.

Everything before this made the choice *possible*: a language a caller can
name, words complete in both, and a browser that carries the axis. None of
it made the choice *reachable*. A reader who is not the developer running
``build_analysis_report(result, lang=...)`` had no way to say which language
they read in — the page answered in whatever ``DEFAULT_LANG`` said, and the
one door an agent reaches the report through had no argument to pass.

So this is about the last hop, and it has three parts.

**The door.** One function turns a tag into a language or refuses it, and
one sentence says why. Two entry points improvising that separately are two
answers to "which languages does this build have", which is what
:class:`themis.language.Lang` replaced.

**The choice.** On the browser it is a real value that changes, kept for the
reader between visits, and asked for by every component through ``useLang``.
The gates here are about what would make it *not* reach somewhere: a
component that imports the default instead of asking, a call into a
rendering function that leaves the language argument off, a cast that lets a
tag nobody answers in through.

**The chooser.** It lists what the build offers rather than what somebody
typed, and labels each option in that option's own language — the one string
in this repository that must not be written in anybody else's, because
telling an English reader that the other choice is "Chinese" tells them in
the language they are choosing to leave.

What is NOT here: that the two sets agree across surfaces, and that every
word exists in both. Those are
``tests/test_the_language_is_a_parameter_not_a_name.py``'s, and they are the
reason a tag could be promoted at all.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re

import pytest

from themis import language
from themis.output import explainer
from tests import web_source
from tests.test_mcp_server import _call_tool

REPO = pathlib.Path(__file__).resolve().parent.parent
WEB = web_source.SRC / "lib" / "language.ts"
APP = web_source.SRC / "App.tsx"

#: The refusal, as one sentence with one author.
_REFUSAL = "is not one this build answers in"

#: Every function a reader-facing text comes out of.
_RENDERERS = ("build_analysis_report", "explain")


# --- the door refuses in one voice -------------------------------------------

@pytest.mark.parametrize("lang", sorted(language.Lang, key=str))
def test_the_door_hands_back_the_member_for_a_language_this_build_has(lang):
    """A member and not a bool.

    What selects among the words is the member; a validator that hands back
    yes leaves every caller to convert the tag a second time, which is a
    second place to get the conversion wrong.
    """
    assert language.answered(str(lang)) is lang
    assert language.answered(lang) is lang


def test_the_door_refuses_a_language_this_build_does_not_answer_in():
    """The counterexample, and what the refusal has to say.

    Both facts, because a reader who asked for a language they cannot have
    needs to know which languages they can: a refusal naming only the tag
    leaves them guessing at the spelling of something that does exist.
    """
    with pytest.raises(NotImplementedError) as raised:
        language.answered("kl")
    assert "'kl'" in str(raised.value)
    for lang in language.Lang:
        assert str(lang) in str(raised.value)


def test_the_refusal_has_one_author():
    """Two doors saying this in their own words is the shape this replaced.

    ``explain`` wrote the sentence inline, and the MCP report tool — the
    second entry point to be handed a reader's choice — had the same job to
    do. A rule about which languages this build has, written twice, is two
    rules that can disagree the moment a build gains one.
    """
    wrote = [
        f"{path.relative_to(REPO).as_posix()}:{i}"
        for path in sorted((REPO / "themis").rglob("*.py"))
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(),
                                 1)
        if _REFUSAL in line
    ]
    assert len(wrote) == 1 and wrote[0].startswith("themis/language.py:"), (
        f"{wrote} each say which languages this build answers in; "
        f"themis.language.answered is where that is decided"
    )


def test_the_explainer_refuses_through_the_same_door():
    """Behaviourally, so the rule above is not satisfied by deleting the
    check rather than by moving it."""
    with pytest.raises(NotImplementedError) as raised:
        explainer.explain(None, "kl")
    assert _REFUSAL in str(raised.value)


# --- every rendering call names a language -----------------------------------

def _renderer_calls(root: pathlib.Path) -> list[tuple[str, bool]]:
    """``(where, was it told which language)`` for every rendering call."""
    out = []
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = (node.func.attr if isinstance(node.func, ast.Attribute)
                    else getattr(node.func, "id", None))
            if name not in _RENDERERS:
                continue
            told = (any(k.arg == "lang" for k in node.keywords)
                    or (name == "explain" and len(node.args) >= 2))
            out.append((f"{path.relative_to(root).as_posix()}:{node.lineno}",
                        told))
    return out


def test_every_rendering_call_in_the_package_names_a_language():
    """Both renderers default to :data:`themis.language.DEFAULT`, and a
    default is right for a library caller who has no reader in front of
    them. It is not right for a caller that DOES — and inside this package
    every caller does, because the only one there is stands between an agent
    and its user.

    One call today. The rule is what makes the second one visible: a
    renderer reached from a new entry point without the argument answers
    every reader in Chinese and reports success, which is the failure this
    whole tier exists to stop being invisible.
    """
    calls = _renderer_calls(REPO / "themis")
    assert calls, "the scan reached no rendering call at all"
    silent = [where for where, told in calls if not told]
    assert not silent, (
        f"{silent} render for a reader without saying which one, out of "
        f"{len(calls)} rendering calls in the package"
    )


def test_a_rendering_call_that_names_no_language_is_refused(tmp_path):
    """The counterexample, spelled the way the MCP door was."""
    (tmp_path / "m.py").write_text(
        "reports.append(build_analysis_report(result, program=prog))\n",
        encoding="utf-8")
    assert _renderer_calls(tmp_path) == [("m.py:1", False)]


# --- the one door an agent reaches a report through --------------------------

@pytest.fixture(scope="module")
def _program():
    return json.loads(
        (REPO / "tests" / "test_e2e" / "fixtures" / "assoc_canonical.json")
        .read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def _app():
    from themis.mcp import build_server
    return build_server()


#: A character that only one of the languages this build answers in is
#: written with. What it settles is which language a report came back in,
#: without pinning any particular sentence — the wording of a heading is
#: somebody's to rewrite, and this rule is not about the wording.
_CJK = re.compile(r"[一-鿿]")


def test_the_report_tool_answers_in_the_language_it_is_asked_for(
        _app, _program):
    """The gap this tier's last cut closed.

    The browser has the reader in front of it and asks. A library caller
    passes ``lang=``. An agent on the other end of this door knows which
    language its user reads and had nowhere to say so — so every report that
    ever left through it was in one language, whoever was reading.
    """
    said = {
        str(lang): _call_tool(
            _app, "themis_report",
            {"program": _program, "lang": str(lang)})["reports"][0]
        for lang in language.Lang
    }
    assert len(set(said.values())) == len(language.Lang), (
        "the door returned the same text for two different languages, so "
        "the argument reached nothing"
    )
    assert _CJK.search(said["zh"])
    assert not _CJK.search(said["en"])


def test_the_report_tool_answers_in_the_default_when_it_is_not_asked(
        _app, _program):
    """A door that suddenly demanded the argument would break every caller
    that has one, for no reader's benefit. What the choice buys is that it
    is reachable, not that it is compulsory."""
    out = _call_tool(_app, "themis_report", {"program": _program})
    asked = _call_tool(_app, "themis_report",
                       {"program": _program, "lang": str(language.DEFAULT)})
    assert out["reports"] == asked["reports"]


def test_the_report_tool_refuses_a_language_this_build_does_not_answer_in(
        _app, _program):
    """Refused by name at the door rather than rendered half-way: a report
    assembled in a language with no words in it comes back as a page of
    stand-ins, which reads like a build that lost its text."""
    with pytest.raises(Exception) as raised:
        _call_tool(_app, "themis_report", {"program": _program, "lang": "kl"})
    assert _REFUSAL in str(raised.value)


def test_the_agent_can_see_that_the_door_takes_a_language(_app):
    """An argument an agent cannot discover is an argument it will not
    pass. The tool schema is the only description it gets."""
    import asyncio

    tools = asyncio.run(_app.list_tools())
    schema = next(t for t in tools if t.name == "themis_report").inputSchema
    assert "lang" in schema.get("properties", {})


# --- the browser: the choice is a value that changes -------------------------

def test_asking_for_the_language_is_not_reading_a_constant():
    """What ``useLang`` was, and the whole reason it existed while it was.

    Seventeen components ask it. Had they imported ``DEFAULT_LANG`` instead,
    making the choice real would have been an edit in each of them — and the
    pressure at that moment is to thread a prop through the ones that render
    nothing, which is how a surface ends up half in one language.
    """
    body = web_source.chunks(web_source.read(WEB))["useLang"]
    assert "useSyncExternalStore" in body, (
        "useLang no longer subscribes to anything, so a reader's choice "
        "cannot reach the components that asked for it"
    )


def _asks_for_the_language() -> list[pathlib.Path]:
    return [path for path in sorted(web_source.SRC.rglob("*.tsx"))
            if re.search(r"\buseLang\(\)", web_source.read(path))]


def test_no_component_imports_the_language_instead_of_asking_for_it():
    """The denominator is the components that ask. A component holding the
    default is one the chooser cannot move."""
    asking = _asks_for_the_language()
    assert len(asking) >= 17, "the scan lost the components that ask"
    holding = [
        path.relative_to(REPO).as_posix() for path in asking
        if re.search(r"\bDEFAULT_LANG\b", web_source.read(path))
    ]
    assert not holding, (
        f"{holding} both ask for the reader's language and hold the default; "
        f"whichever one they render with, the other is dead"
    )


def _params(name: str, text: str) -> list[str] | None:
    """The parameter list of one top-level declaration, in order.

    In order because what a rule about call sites needs is not that the
    language is a parameter but WHICH one it is: an optional argument left
    off is a shorter call, and only the position says whether the caller
    reached it.

    Its own matcher rather than :func:`tests.web_source.balanced`, which
    opens on a bracket and does not count parentheses — starting it on a
    parameter list, the first ``string[]`` closes it, and the parameters
    after that one read as absent. Angle brackets are counted too, because
    ``Record<string, Words>`` carries a comma that is not between
    parameters; the ``>`` of an arrow type is blanked first, since that one
    closes nothing.
    """
    opened = (re.search(rf"^export function {name}\s*(\()", text)
              or re.search(rf"^export const {name}\b[^\n=]*=\s*(\()", text))
    if not opened:
        return None
    reading = text.replace("=>", "  ")
    start, depth, i = opened.start(1) + 1, 0, opened.start(1)
    while i < len(reading):
        char = reading[i]
        if char in "'\"`":
            quote, i = char, i + 1
            while i < len(reading) and reading[i] != quote:
                i += 2 if reading[i] == "\\" else 1
        elif char in "([{<":
            depth += 1
        elif char in ")]}>":
            depth -= 1
            if depth == 0:
                break
        i += 1
    else:
        return None
    out, at, last = [], start, start
    while at < i:
        char = reading[at]
        if char in "([{<":
            depth += 1
        elif char in ")]}>":
            depth -= 1
        elif char == "," and depth == 0:
            out.append(text[last:at])
            last = at + 1
        at += 1
    out.append(text[last:i])
    return [part.strip() for part in out if part.strip()]


#: The two modules a component renders text through.
_DOORS = (web_source.VERDICT, WEB)


def _takes_a_language() -> dict[str, tuple[pathlib.Path, int]]:
    """``name -> (where it is declared, which argument is the language)``."""
    found: dict[str, tuple[pathlib.Path, int]] = {}
    for door in _DOORS:
        for name, text in web_source.chunks(web_source.read(door)).items():
            for i, param in enumerate(_params(name, text) or ()):
                if re.match(r"lang\b", param):
                    found[name] = (door, i)
                    break
    return found


def _called_without_one(text: str, taking) -> list[tuple[str, int]]:
    """``(name, line)`` for every call that left the language off."""
    out = []
    for name, (_door, where) in sorted(taking.items()):
        for line, args in web_source.calls(name, text):
            if len(args) <= where or not args[where].strip():
                out.append((name, line))
    return out


def test_every_call_that_could_be_told_the_readers_language_is_told_it():
    """The defect class this tier made live.

    Every one of these takes ``lang`` with ``DEFAULT_LANG`` as its default,
    which is right for the module's own signature and silent at the call
    site: a forgotten argument was invisible while there was one language,
    and is a Chinese phrase in an English page now. Nothing in the type
    system can see it — the parameter is optional, so leaving it off
    compiles.
    """
    taking = _takes_a_language()
    assert len(taking) >= 39, "the scan lost the functions that take one"
    reached, missing = 0, []
    for path in (sorted(web_source.SRC.rglob("*.tsx"))
                 + sorted(web_source.SRC.rglob("*.ts"))):
        text = web_source.read(path)
        here = {name: (door, where)
                for name, (door, where) in taking.items() if path != door}
        reached += sum(len(web_source.calls(name, text)) for name in here)
        missing += [f"{path.relative_to(REPO).as_posix()}:{line}  {name}"
                    for name, line in _called_without_one(text, here)]
    assert reached >= 549, f"the scan reached only {reached} calls"
    assert not missing, "\n".join(missing) + (
        "\neach falls back to DEFAULT_LANG, which is one language whoever "
        "is reading"
    )


def test_a_call_that_left_the_language_off_is_refused():
    """The counterexample, run through the same predicate."""
    taking = _takes_a_language()
    assert _called_without_one("const said = listing(items)\n", taking) == [
        ("listing", 1)]
    assert not _called_without_one("const said = listing(items, lang)\n",
                                   taking)


def test_only_one_place_turns_an_outside_string_into_a_language():
    """Everything the choice can be built from was written by somebody who
    is not this build: a value stored by a version that offered more
    languages, a browser asking for one nobody here writes. Each has to be
    checked against what this build ANSWERS in — never against the wider set
    the completeness gates count, which is what being written in means.

    A cast is where that check gets skipped, and it is the only construct
    that can skip it, so the rule is that there is one of them.
    """
    cast = [
        f"{path.relative_to(REPO).as_posix()}:{line}"
        for path in (sorted(web_source.SRC.rglob("*.ts"))
                     + sorted(web_source.SRC.rglob("*.tsx")))
        for line, said in enumerate(web_source.read(path).splitlines(), 1)
        if re.search(r"\bas Lang\b", said)
    ]
    assert len(cast) == 1, (
        f"{cast} each assert that some string is a language this build "
        f"answers in; `offered` is where that is decided"
    )
    assert "as Lang" in web_source.chunks(web_source.read(WEB))["offered"]


def test_the_page_says_which_language_it_is_in():
    """``documentElement.lang`` is what a screen reader picks a voice from
    and what the browser hyphenates by. It is a second record of the one
    choice, so it is written where the choice is — one assignment, in the
    module that owns the store."""
    assigned = [
        path.relative_to(REPO).as_posix()
        for path in (sorted(web_source.SRC.rglob("*.ts"))
                     + sorted(web_source.SRC.rglob("*.tsx")))
        if re.search(r"documentElement\.lang\s*=", web_source.read(path))
    ]
    assert assigned == [WEB.relative_to(REPO).as_posix()]


# --- the chooser -------------------------------------------------------------

def test_the_endonyms_are_the_kernels():
    """Generated, not restated. A language's own name is the one string that
    cannot be checked by reading it: whoever reviews the browser's copy reads
    one of the two languages it is about."""
    said = web_source.string_map("ENDONYM",
                                 web_source.read(web_source.GENERATED))
    assert said == dict(language.ENDONYM)


def test_no_surface_writes_a_languages_name_by_hand():
    """The counterexample this table exists to make impossible.

    A chooser labelled from a table of its own is a chooser that goes stale
    silently: the label is still a word, still in a language, and still
    renders — it is just not what the kernel calls that language any more.
    """
    written = [
        f"{path.relative_to(REPO).as_posix()}:{line}"
        for path in (sorted(web_source.SRC.rglob("*.ts"))
                     + sorted(web_source.SRC.rglob("*.tsx")))
        if path != web_source.GENERATED
        for line, said in enumerate(web_source.read(path).splitlines(), 1)
        if any(re.search(rf"'{name}'|\"{name}\"", said)
               for name in language.ENDONYM.values())
    ]
    assert not written, (
        f"{written} name a language in their own words; ENDONYM is generated "
        f"from the kernel so that there is one answer"
    )


def test_the_chooser_offers_what_the_build_offers():
    """Listed by iterating ``LANGS`` rather than by writing the options out.

    A chooser with its options typed in is a third record of which languages
    this build has — after the kernel's ``Lang`` and the browser's ``LANGS``
    — and the one nothing checks, because a missing option is not an error
    anywhere. It is a language the build answers in that no reader can ask
    for.
    """
    said = web_source.read(APP)
    assert "LANGS.map(" in said, (
        "the chooser no longer reads the set of languages; whatever it lists "
        "instead is a third record of which ones this build has"
    )
    assert "ENDONYM" in said
    typed = sorted(set(re.findall(
        r"'(" + "|".join(str(x) for x in language.Lang) + r")'", said)))
    assert not typed, (
        f"{typed} are written into the chooser by hand"
    )
