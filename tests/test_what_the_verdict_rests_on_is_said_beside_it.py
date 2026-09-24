"""What the verdict rests on, where it has not been established, is said
beside the verdict.

A cause question asked on an edge the upstream model proposed came back
headed ``✅ 已解决（结构层）`` and ``结论：是`` in the report, and ``已识别
(结构上)`` over "the causal structure itself holds" in the browser. Every
fact under those heads was right — the verdict's own words are scoped to
"in the graph", the ledger graded the edge invalidating and said the
answer only replays the proposal — and the reader met none of it first:
the report printed the ledger five sections down and the browser folded
it into "how it was computed". The heads read ``status`` and the verdict's
boolean, and neither says whether the graph's load-bearing lines stand.

Which lines a reader has to meet beside the verdict is
:func:`themis.ledger.goes_with_the_verdict`: a proposal nobody took on, or a
premise this run's own data refused. What is pinned here:

- the two facts it reads are facts about the vocabularies — a producer
  either relays a proposal or takes a premise on, never both — and the
  browser tests the same two sets, generated rather than restated;
- every stored answer's report says exactly those lines under its status,
  as the ledger below prints them, in both languages;
- the browser reads them through the same test, outside the foldout.
"""
from __future__ import annotations

import json
import pathlib

import pytest

import themis
from themis import language, ledger
from themis.output import analysis_report
from tests import web_source

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHAPES = json.loads(
    (ROOT / "tests/fixtures/answer_shapes.json").read_text(encoding="utf-8"))

#: Restated rather than imported, so the corpus walk below selects by what
#: the vocabularies are pinned to say and not by the function under test.
_PROPOSALS = {"llm_proposal", "discovery", "llm_prior"}
_LEADS = {"refuted"}


def _beside_the_verdict(entry: dict) -> bool:
    return (entry.get("provenance") in _PROPOSALS
            or (entry.get("checked") or {}).get("verdict") in _LEADS)


def _entries(result: dict) -> list[dict]:
    return list((((result.get("extensions") or {}).get("assumption_ledger")
                  or {}).get("assumptions")) or ())


def _head(report: str) -> list[str]:
    """What the report says between its status line and its first section."""
    lead = report.split("\n## ", 1)[0].splitlines()
    status = next(i for i, line in enumerate(lead)
                  if line.startswith(("**状态**", "**Status**")))
    return [line for line in lead[status + 1:] if line.strip()]


# --- the two facts are facts about the vocabularies --------------------------

def test_the_sets_are_what_the_members_say():
    assert ledger.PROPOSED == _PROPOSALS
    assert ledger.LEADING == _LEADS


def test_a_producer_either_relays_a_proposal_or_takes_a_premise_on():
    """A row mixing the two would let one channel write a line that is a
    guess and a line somebody owns under one name, and whether the verdict
    has to carry it would then depend on which of the two it wrote."""
    relays = set()
    for producer, (_, provenances) in ledger.ADMISSIBLE.items():
        kinds = {p.proposed for p in provenances}
        assert len(kinds) == 1, (producer, sorted(map(str, provenances)))
        if kinds == {True}:
            relays.add(producer)
    assert relays == {"proposal_edge", "theta_prior"}


def test_the_browser_tests_the_same_two_sets():
    generated = web_source.read(web_source.GENERATED)
    assert web_source.string_list("PROPOSED_PROVENANCES", generated) \
        == ledger.PROPOSED
    assert web_source.string_list("LEADING_VERDICTS", generated) \
        == ledger.LEADING


def test_the_browser_asks_the_kernels_question_before_the_foldout():
    """Through the generated sets, and above the fold: the reader who never
    opens "how it was computed" is the one the verdict would mislead."""
    test = web_source.chunks(web_source.read(web_source.VERDICT))[
        "goesWithTheVerdict"]
    assert "generated.PROPOSED_PROVENANCES" in test
    assert "generated.LEADING_VERDICTS" in test
    component = web_source.without_comments(
        web_source.read(web_source.COMPONENT))
    assert "filter(goesWithTheVerdict)" in component
    assert component.index("verdict__premises") < component.index("<Foldout")


# --- the report says them under its status ----------------------------------

#: Stored answers with at least one such line: nineteen resting on a proposal,
#: five on a premise their own data refused, none on both.
_WITH_PREMISES = 24


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_every_stored_answer_heads_with_exactly_those_lines(lang):
    with_premises = 0
    for name, row in sorted(SHAPES.items()):
        result = row["result"]
        report = analysis_report.build_analysis_report(
            result, program=row.get("program"), lang=lang)
        chosen = [a for a in _entries(result) if _beside_the_verdict(a)]
        head = _head(report)
        if not chosen:
            assert head == [], (name, head)
            continue
        with_premises += 1
        expected = [line for a in chosen
                    for line in analysis_report._ledger_rows([a], lang=lang)]
        assert head[0] == language.fill(analysis_report._WITH_THE_VERDICT,
                                        lang), name
        assert head[1:] == expected, name
        # The same rows the ledger prints, not a second telling of them.
        ledger_section = report.split("\n## ", 1)[1]
        for line in expected:
            assert line in ledger_section, (name, line)
    assert with_premises == _WITH_PREMISES, with_premises


# --- the occasion that found it ---------------------------------------------

def _cause_program(annotated: bool) -> dict:
    def atom(p):
        return {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    edge = {"kind": "cause", "from": atom("smoking"), "to": atom("cancer")}
    if annotated:
        edge["annotations"] = {"source": "llm_proposal"}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "smoking",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "cancer",
             "domain": [True, False]},
            edge,
            {"kind": "query", "id": "q",
             "query": {"kind": "cause", "from": atom("smoking"),
                       "to": atom("cancer")}},
        ],
    }


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_a_yes_read_off_a_proposed_edge_says_so_under_its_status(lang):
    program = _cause_program(annotated=True)
    result = themis.run(program)["results"][0]
    assert result["status"] == "structurally_solved"
    assert result["structural_result"]["value"] is True
    head = _head(analysis_report.build_analysis_report(
        result, program=program, lang=lang))
    assert head[0] == language.fill(analysis_report._WITH_THE_VERDICT, lang)
    assert len(head) == 2 and "smoking → cancer" in head[1], head


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_the_same_yes_on_an_edge_the_caller_drew_heads_with_nothing(lang):
    program = _cause_program(annotated=False)
    result = themis.run(program)["results"][0]
    assert result["structural_result"]["value"] is True
    assert _head(analysis_report.build_analysis_report(
        result, program=program, lang=lang)) == []
