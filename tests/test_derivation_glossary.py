"""Every derivation step says what it did, and the report says it.

「怎么算出来的」 was bound to the ROUTE block family, and only the
identification patterns write a block. Instrumented over one suite run, 22
of 72 reports had that section missing — across six query kinds — and 14 of
those had a derivation the section simply never read. The verification
section made the omission plain: it told the reader the chain has N steps
and never said what they were.

So the chain is rendered for every result that has one, and each rule says
what it did once, in :mod:`themis.output.derivation_glossary`. These tests
hold both ends: no producer-written rule without a sentence, and no result
with a derivation whose section comes out empty.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from themis import language
from themis.output import analysis_report, derivation_glossary
from themis.output.derivation_glossary import SAYS

PACKAGE = pathlib.Path(analysis_report.__file__).resolve().parent.parent


def _rules_producers_write() -> dict[str, list[str]]:
    """Every ``DerivationStep(rule=...)`` literal outside the verifier.

    Walked rather than grepped: the rule name is what a producer PUTS on a
    step, and the same string appears in verifier messages, gap heuristics
    and docstrings, so a text search both over- and under-counts. The
    verifier is excluded because it consumes rule names, never writes one.
    """
    found: dict[str, list[str]] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        if "verifier" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", getattr(node.func, "attr", None))
            if name != "DerivationStep":
                continue
            for kw in node.keywords:
                if kw.arg == "rule" and isinstance(kw.value, ast.Constant):
                    found.setdefault(kw.value.value, []).append(
                        f"{path.relative_to(PACKAGE)}:{node.lineno}"
                    )
    return found


WRITTEN = _rules_producers_write()


@pytest.mark.parametrize("rule", sorted(WRITTEN))
def test_every_step_a_producer_writes_says_what_it_did(rule):
    """The default renders an unglossed rule as its own id, which is the
    right behaviour for an envelope from another build and the wrong one
    for a rule in this package: here it would print snake_case at a reader
    who asked how the answer was reached."""
    assert rule in SAYS, (
        f"{rule} is written at {WRITTEN[rule][0]} and has no sentence in "
        f"derivation_glossary.SAYS — the report would print its id"
    )


def test_the_glossary_has_no_entry_for_a_step_nothing_writes():
    """A sentence for a rule no producer emits is prose nobody will read,
    and it hides the opposite mistake: the count looking right while the
    entry that matters is missing."""
    assert set(SAYS) - set(WRITTEN) == set()


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_no_two_steps_are_described_the_same_way(lang):
    """Two steps with one sentence means the reader cannot tell them apart
    in the chain — which is the whole point of printing the chain.

    Per language, because that is per reader: two rules distinguishable in
    one language and merged in another leaves the second reader with the
    same chain twice."""
    said = [words[lang] for words in SAYS.values() if lang in words]
    dupes = sorted({s for s in said if said.count(s) > 1})
    assert not dupes, f"the same {lang} sentence describes several rules: {dupes}"


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_every_step_says_what_it_did_in_every_language(lang):
    """The third door's own completeness check.

    A vocabulary declared by neither a Python enum nor a schema enum — its
    only declaration is this glossary — is invisible to the registry in
    ``tests/test_vocabulary_reach.py``, which is where every other
    vocabulary is counted once per language. So it is counted here, and a
    language arriving with fifty-seven of these written names the
    fifty-eighth rather than reaching a reader as an id."""
    wordless = sorted(rule for rule, words in SAYS.items()
                      if not words.get(lang, "").strip())
    assert not wordless, (
        f"{wordless} have no {lang} sentence — each would reach a reader "
        f"asking how the answer was arrived at as its own snake_case id"
    )


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_a_step_with_no_sentence_here_is_not_answered_in_another_language(lang):
    """The counterexample. A build that fell back would hand a reader one
    step of the chain in a language they did not ask for, which is worse
    than the identifier: the identifier says a word is missing."""
    assert derivation_glossary.describe("a_rule_from_the_future", lang) == (
        "`a_rule_from_the_future`"
    )


def test_a_step_from_another_build_renders_as_its_own_name():
    assert derivation_glossary.describe("a_rule_from_the_future") == (
        "`a_rule_from_the_future`"
    )


# --- the section ---------------------------------------------------------


def _result(steps, **extra):
    return {"derivation": {"steps": [{"rule": r} for r in steps]}, **extra}


@pytest.mark.parametrize("rule", sorted(WRITTEN))
def test_a_result_carrying_a_step_never_gets_an_empty_route_section(rule):
    """The claim the report makes about itself. Six query kinds used to
    fail it because the section read only blocks, and a result whose route
    is its derivation had nothing bound to it."""
    section = analysis_report._render_route(_result([rule]))
    assert section.strip(), rule
    assert SAYS[rule][language.DEFAULT] in section


def test_the_steps_are_said_in_the_order_they_ran():
    section = analysis_report._render_route(
        _result(["backdoor_criterion", "numeric_backdoor_estimate"])
    )
    first = section.index(SAYS["backdoor_criterion"][language.DEFAULT])
    second = section.index(
        SAYS["numeric_backdoor_estimate"][language.DEFAULT])
    assert first < second
    assert "1." in section and "2." in section


def test_a_result_with_no_derivation_leaves_the_section_alone():
    """Empty is right when there is nothing to say: a refused query and one
    still waiting for data carry no chain, and 8 of the 22 empty sections
    measured were exactly that."""
    assert analysis_report._render_route({}) == ""
    assert analysis_report._render_route({"derivation": {"steps": []}}) == ""


def test_the_chain_comes_after_the_pattern_and_the_estimand():
    """Order is a claim about what the reader wants first: which pattern on
    which set, then the expression, then the skeleton."""
    result = _result(
        ["backdoor_criterion"],
        extensions={"identification": {"pattern": "backdoor",
                                       "adjustment_set": ["z"]}},
    )
    section = analysis_report._render_route(result)
    assert section.index("后门") < section.index("推导链")
