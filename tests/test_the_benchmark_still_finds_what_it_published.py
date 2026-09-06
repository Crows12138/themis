"""The benchmark's published findings, held to the build that has to make them.

``benchmarks/agent_integration/`` is what the README sends a reviewer to on
the critical path: three NL causal questions, and for each one a written
claim about which ``GapKind`` Themis emits when an agent encodes it well.
That claim is the benchmark's whole argument — the contrast it reports
between an unaided model and one with Themis is a contrast in exactly these
findings — and until now nothing held it to the code. Six hundred rounds of
change had gone past a document nobody could check.

**Where each half comes from, because a gate that authors both halves holds
nothing.** The claim is read out of the question file itself: the
``Expected Themis behavior`` section names its kinds in backticks and this
reads them there rather than restating them, so editing the document is
what changes the assertion. What is authored beside it is only the
ENCODING — the kernel_ast an agent would build from the DAG the question
spells out — and that lives in a ``*.arm_c.json`` next to the question,
where a reader comparing the two can see whether the transcription is
faithful. Themis is the third party, and it is what this puts on trial.

A question naming two encodings (Q2 names both an ObservationStatement and
an ``EffectQuery.given``, with a different finding for each) carries both,
and the claim is read across them: every kind the document names has to be
found by at least one encoding of that question. Attributing each kind to
one encoding would mean writing down here which is which, which is the
restating this file exists to avoid.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

import themis
from themis.types import GapKind

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "benchmarks/agent_integration/questions"

#: Where a question states what Themis is expected to find.
_SECTION = "## Expected Themis behavior"

#: Every backticked identifier. Which of them are claims is decided by the
#: vocabulary, not by a list here: a kind renamed in the enum stops being
#: read out of the document, and the coverage test below then reports a
#: question that claims nothing.
_BACKTICKED = re.compile(r"`([a-z][a-z0-9_]*)`")

_KINDS = {kind.value for kind in GapKind}


def _claimed(question: pathlib.Path) -> frozenset[str]:
    """The kinds this question's own text says Themis emits."""
    text = question.read_text(encoding="utf-8")
    start = text.find(_SECTION)
    if start < 0:
        return frozenset()
    end = text.find("\n## ", start + len(_SECTION))
    section = text[start:end if end > 0 else len(text)]
    return frozenset(_BACKTICKED.findall(section)) & _KINDS


def _encodings(question: pathlib.Path) -> list[dict]:
    beside = question.with_suffix("").with_suffix(".arm_c.json")
    if not beside.exists():
        return []
    return json.loads(beside.read_text(encoding="utf-8"))["encodings"]


QUESTION_FILES = sorted(QUESTIONS.glob("q*.md"))
#: Below this the benchmark has stopped being the three-question contrast
#: its README describes.
_QUESTIONS_PUBLISHED = 3


def test_the_benchmark_still_has_the_questions_it_describes():
    assert len(QUESTION_FILES) >= _QUESTIONS_PUBLISHED, QUESTION_FILES


@pytest.mark.parametrize("question", QUESTION_FILES, ids=lambda p: p.stem)
def test_a_question_states_findings_and_carries_an_encoding(question):
    """Neither half may go missing quietly.

    A question with no claim would pass the trial below by asking nothing
    of it, and a question with no encoding would be skipped — both are the
    shape where a gate reports success because it never looked.
    """
    assert _claimed(question), (
        f"{question.name} names no GapKind in its expected-behavior "
        f"section, so nothing about it is being checked"
    )
    assert _encodings(question), (
        f"{question.name} has no {question.stem}.arm_c.json beside it, so "
        f"its claim cannot be put to the build"
    )


@pytest.mark.parametrize("question", QUESTION_FILES, ids=lambda p: p.stem)
def test_the_build_still_finds_what_the_question_says_it_finds(question):
    claimed = _claimed(question)
    found: set[str] = set()
    for encoding in _encodings(question):
        out = themis.run(encoding["program"])
        results = out.get("results") or []
        assert results, f"{encoding['name']}: no result at all"
        result = results[0]
        report = result.get("data_gap_report") or {}
        found |= {gap.get("kind") for gap in report.get("gaps") or []}
    missing = claimed - found
    assert not missing, (
        f"{question.name} publishes findings this build no longer makes: "
        f"{sorted(missing)}"
    )


@pytest.mark.parametrize("question", QUESTION_FILES, ids=lambda p: p.stem)
def test_no_encoding_of_a_published_question_answers_with_a_number(question):
    """The other half of what the benchmark reports.

    Its contrast is not only that Themis names the trap — it is that the
    answer refuses a point estimate where an unaided model quotes one. A
    build that started returning a number here would keep every claim above
    and lose the argument.
    """
    for encoding in _encodings(question):
        result = (themis.run(encoding["program"]).get("results") or [None])[0]
        assert result["status"] == "needs_investigation", (
            f"{encoding['name']}: {result['status']}")
        assert not result.get("numeric_estimate"), encoding["name"]
