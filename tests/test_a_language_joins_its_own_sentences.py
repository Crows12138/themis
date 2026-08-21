"""Punctuation between two things is the language's, not the template's.

Five templates in ``analysis_report`` framed a refusal as one string with a
``{reason}`` hole in it: ``**No number — ...**: {reason}This decides nothing
about the question.`` Whatever went into the hole was expected to bring its
own trailing gap, which is the payload's business and not the template's, and
nothing said so anywhere. Chinese needs no gap between sentences, so in the
one language anyone is answered in all five read correctly; English rendered
``...can be said here.This decides nothing...``.

The fix is not five spaces. A gap left to a template is a gap every template
is free to forget, and the same fact had already gone missing once in the
other direction: ``_AND`` — how this language separates items in a list —
lived in the report and was reached eleven times from that one module, so a
second surface joining a list had nothing to reach for. Both now live in
:mod:`themis.language`, beside ``ENDONYM``, which is the other table of facts
about a language rather than in one.

This module holds what that buys: the seam cannot come back, and the report's
refusal frame is now the same three parts the browser has had all along.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

from themis import language, refusals
from themis.output import analysis_report

REPO = pathlib.Path(__file__).resolve().parent.parent

#: A full stop with a capital letter against it. The defect's exact shape,
#: and narrow on purpose: ``e.g.`` and ``P(y|do(x))`` are full stops that
#: are not sentence ends, and both are followed by lower case. Chinese needs
#: no rule here — ``。`` abuts the next sentence by design, which is why the
#: five templates read correctly in the only language with readers.
GLUED = re.compile(r"\.(?=[A-Z])")

#: A reason that ends the way a composed refusal sentence ends. Every entry
#: in ``refusals.SAYS`` is a sentence, and this is what one looks like when
#: it reaches the frame.
ENDED = {"zh": "这一次的原因。", "en": "the reason this time."}


@pytest.mark.parametrize("kind", sorted(str(k) for k in refusals.Kind))
def test_no_kind_glues_the_occasion_to_what_follows(kind):
    """Every kind, every language, with an occasion that ends a sentence."""
    words = analysis_report._kind_words(kind)
    assert words, f"no words for kind {kind!r}"
    for lang in sorted(language.written()):
        said = language.fill(words, lang, reason=ENDED[lang])
        assert not GLUED.search(said), (
            f"the {lang} sentence for a {kind} refusal runs two sentences "
            f"together: {said!r}"
        )


def test_the_check_sees_the_seam_it_was_built_for():
    """The counterexample, spelled the way all five were.

    Composed by hand rather than by doctoring the source, because what was
    wrong was the shape of the template — one string with the hole in it —
    and that shape no longer exists to doctor.
    """
    glued = ("**No number — this is a conclusion about the causal graph**: "
             "{reason}More of the same data will not change it.")
    assert GLUED.search(glued.format(reason=ENDED["en"]))
    assert not GLUED.search(
        glued.replace("{reason}", "{reason} ").format(reason=ENDED["en"]))


def test_chinese_needs_no_gap_and_gets_none():
    """What the language table says, said out loud.

    A gap inserted where the language does not want one is the same defect
    facing the other way, and it would be just as invisible: a stray space
    before 再多同样的数据 reads as a typo rather than as a rule nobody wrote.
    """
    assert language.fill(language.BETWEEN_SENTENCES, "zh") == ""
    assert language.fill(language.BETWEEN_SENTENCES, "en") == " "
    assert language.sentences("甲。", "乙。", lang="zh") == "甲。乙。"
    assert language.sentences("One.", "Two.", lang="en") == "One. Two."


def test_an_absent_part_is_dropped_rather_than_joined_around():
    """A refusal with no occasion is two sentences, not two and a gap."""
    assert language.sentences("One.", "", "Two.", lang="en") == "One. Two."
    assert language.sentences("", lang="en") == ""


def test_a_list_is_joined_where_the_punctuation_lives():
    assert language.listing(["a", "b"], "zh") == "a、b"
    assert language.listing(["a", "b"], "en") == "a, b"
    assert language.listing([], "en") == ""


#: The marks a language joins meaning with: items, clauses, statements,
#: sentences, and the stop that ends one. Chinese and English forms both,
#: plus the space either may pad with.
#:
#: Narrower than "punctuation", and the line is where the fact stops being
#: the language's. ``／`` between two meta fields and ``·`` in the footer
#: are marks this REPORT chose; another surface would choose others and be
#: no less correct. What is the language's about them is only their width —
#: ``／`` against ``  /  ``, an ideographic space against two ASCII ones —
#: and that is one level further in than this module goes.
GRAMMAR = set("、，；。,;. ")


def _punctuation_only_tables(path: pathlib.Path) -> list[str]:
    """Module-level ``Words`` built entirely out of :data:`GRAMMAR`.

    A table of grammatical separators is a table about the language, and
    one sitting in a rendering module is reachable only from there — which
    is how a second surface came to have nothing to join a list with, how
    ``；`` came to be declared in three modules, and how the gap between
    two sentences came to have no home at all.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign) or node.value is None:
            continue
        if "Words" not in ast.unparse(node.annotation):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        values = [v.value for v in node.value.values
                  if isinstance(v, ast.Constant) and isinstance(v.value, str)]
        if values and all(set(v) <= GRAMMAR for v in values):
            found.append(ast.unparse(node.target))
    return found


def test_no_rendering_module_keeps_its_own_punctuation():
    """Where a separator lives decides who can reach it.

    Eight tables were found here on this gate's first run, ``；`` declared
    in three modules apiece and ``。`` under two names that disagreed about
    whether it carried a following space.
    """
    offenders = {
        path.relative_to(REPO).as_posix(): names
        for path in sorted((REPO / "themis" / "output").rglob("*.py"))
        if (names := _punctuation_only_tables(path))
    }
    assert not offenders, (
        f"{offenders} keep a table of separators of their own; a language's "
        f"punctuation belongs in themis.language, where every surface can "
        f"reach it"
    )


def test_the_check_sees_a_separator_table_in_a_rendering_module(tmp_path):
    """The counterexample, spelled the way ``_AND`` was."""
    doctored = tmp_path / "doctored.py"
    doctored.write_text(
        '_AND: language.Words = {"zh": "、", "en": ", "}\n'
        '_HEAD: language.Words = {"zh": "答案", "en": "Answer"}\n',
        encoding="utf-8")
    assert _punctuation_only_tables(doctored) == ["_AND"]
