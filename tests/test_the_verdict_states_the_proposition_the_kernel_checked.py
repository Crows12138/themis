"""#418 — one proposition, two authors, and only the looser one had a reader.

A ``cause`` verdict is ``nx.has_path`` over the edges the caller drew. The
kernel has always said so: :attr:`themis.questions.Question.settles` carried
"a directed path runs from the source to the target in this graph", written
from the verifier that audits the kind, and its docstring stated the
discipline — the proposition a reader is told is the proposition the kernel
checked.

That field had no consumer. The language gate had it registered as UNREAD,
and what a reader actually got came from a second table, hand-written in the
report, which said 存在因果影响 — a claim about the world. Nothing required
the two to agree, and the copy had dropped the scope the original carried.
The ``effect`` pair showed the same asymmetry within one entry: its false
half said "from this graph" and its true half said only 可识别.

So the second author is gone rather than corrected, and the propositions are
the reader's words. What keeps a third from appearing is that the rendered
line must CONTAIN the declared proposition, verbatim, for every kind and both
values: a surface that restates instead of stating stops matching the moment
it rephrases, whether or not the rephrasing is faithful.

The browser is the one restatement that has to exist — it cannot import
Python — and it is held string by string rather than key by key, which is the
axis this defect lived on. Its keys and its ``answersIt`` flags were already
pinned, and the wording drifted underneath both.
"""
from __future__ import annotations

import re

import pytest

from themis import language, questions
from themis.output.analysis_report import _render_answer
from tests import web_source

#: Every language some text in this build is written in — which is the
#: right denominator here rather than ``Lang``: a language whose words are
#: being written is one a copy can drift in, and ``en`` is not yet a member
#: of the enum precisely because not every surface has been looked at.
LANGS = tuple(sorted(language.written()))


def _res(kind: str, value: bool, **extra) -> dict:
    return {"status": "structurally_solved", "query_kind": kind,
            "structural_result": {"value": value}, **extra}


def _proposition(reading: questions.Question, value: bool,
                 lang: language.Lang | str) -> str:
    return language.fill(reading.settles if value else reading.fails, lang)


def _states_it(line: str, reading: questions.Question, value: bool,
               lang: language.Lang | str) -> bool:
    """Whether this line says the proposition rather than a version of it.

    The criterion itself, so the twenty cells below and the artefact this
    defect produced are judged by one rule rather than by a rule and a
    description of it.
    """
    return _proposition(reading, value, lang) in line


# ====================================================== the reader's surface


@pytest.mark.parametrize("lang", LANGS, ids=str)
@pytest.mark.parametrize("value", [True, False], ids=["holds", "fails"])
@pytest.mark.parametrize("kind", [q.kind for q in questions.DECLARED], ids=str)
def test_the_answer_line_states_the_declared_proposition(kind, value, lang):
    """Twenty cells, one author.

    Containment rather than equality: the line carries a verdict word, a
    supporting-path count, a "no number was given" clause. What it may not
    carry is a second version of the proposition, and a rephrasing — however
    faithful — is exactly that.
    """
    reading = questions.reading_of(kind)
    line = _render_answer(_res(kind, value), lang=lang)
    assert _states_it(line, reading, value, lang), (
        f"{kind}/{value}/{lang}: {line!r} does not say "
        f"{_proposition(reading, value, lang)!r}")


def test_the_wording_this_defect_produced_is_refused():
    """The gate shown saying no to the artefact it was built for.

    The old report's cause row, rebuilt: a verdict word and a sentence about
    the world. It is not a wrong answer — the path is there — it is an answer
    to a question about smoking and cancer rather than about the graph, and
    every check that reads the boolean, the kind, or the verdict word passes
    on it.
    """
    was_rendered = "结论：**是** —— 存在因果影响"
    assert not _states_it(
        was_rendered, questions.CAUSE, True, language.DEFAULT)


def test_a_scoped_verdict_still_reads_as_an_answer():
    """The scope is inside the proposition, not appended as a caveat.

    A caveat can be dropped by a surface that shortens; the proposition
    cannot be dropped without dropping the answer. So the line still opens
    with the verdict word for the kinds whose verdict IS the answer.
    """
    line = _render_answer(
        _res("cause", True,
             structural_result={"value": True,
                                "supporting_paths": [["x", "y"]]}),
        lang=language.DEFAULT)
    assert line.startswith("结论：**是**")
    assert _states_it(line, questions.CAUSE, True, language.DEFAULT)


# ====================================================== the browser's copy


def _web_propositions() -> dict[tuple[str, bool, str], str]:
    """(kind, value, language) -> what the browser's chip says.

    Parsed through :mod:`tests.web_source`, which is where the brace matcher
    lives; a regex written here would be the fifth of its kind and would go
    quietly empty the next time the table grows an axis.
    """
    source = web_source.read(web_source.VERDICT)
    entries = web_source.members("QUESTION_READINGS", source)
    assert entries, "verdict.ts declares no QUESTION_READINGS"
    out = {}
    for kind, said in entries.items():
        words = web_source.entry(said, "words")
        for tag in ("zh", "en"):
            per_lang = web_source.entry(words, tag)
            for value, side in ((True, "holds"), (False, "failsTo")):
                text = web_source.entry(per_lang, side)
                found = re.search(r"gloss:\s*'((?:[^'\\]|\\.)*)'", text)
                assert found, f"{kind}/{tag}/{side} has no gloss"
                out[(kind, value, tag)] = web_source.unquoted(found.group(1))
    return out


def _kernel_propositions() -> dict[tuple[str, bool, str], str]:
    return {
        (q.kind, value, lang): _proposition(q, value, lang)
        for q in questions.DECLARED
        for value in (True, False)
        for lang in LANGS
    }


def test_the_browser_says_the_propositions_and_not_its_own_version():
    """String by string, both languages, both values.

    The keys and the ``answersIt`` flags were already held equal and the
    wording drifted underneath them: this table special-cased three kinds,
    then covered ten, and by then ``identify`` had a shorter sentence of its
    own and two entries had absorbed a remark about the render into the
    proposition.
    """
    assert _web_propositions() == _kernel_propositions()


def test_a_paraphrase_in_the_browser_would_be_caught():
    """The same refusal, on the surface that has to keep a copy.

    A generator will write this table one day (#399). Until then the copy is
    free to be edited by hand, which is how the report's copy came to say
    something the kernel never checked — so what stands in for the generator
    is that a hand edit which changes the words fails here.
    """
    drifted = dict(_web_propositions())
    drifted[("cause", True, "zh")] = "存在因果影响"
    assert drifted != _kernel_propositions()


def test_the_render_note_is_not_part_of_the_proposition():
    """The "no number yet" remark is about this render, not about the question.

    It sat inside two of the ten entries, true of all eight kinds whose
    boolean is a precondition. Inside the table it is a second record of the
    surface's own state; outside it, the table can be held equal to the
    kernel's words at all.
    """
    source = web_source.read(web_source.VERDICT)
    table = web_source.literal("QUESTION_READINGS", source)
    assert "数值还没算出来" not in table
    assert "no number has been computed yet" not in table
    assert "NO_NUMBER_YET" in source
