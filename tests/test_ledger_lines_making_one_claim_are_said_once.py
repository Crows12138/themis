"""Ledger lines that make one claim of several things are said once.

#812. The assumption ledger holds one line per assumption, which is what
the verifier holds each of to its source. Both reader surfaces printed it
that way too: a reader looking at the result page was shown "the edge ...
is a hypothesis the upstream LLM proposed, not an edge evidence supports.
The answer as it stands restates that hypothesis rather than verifying it",
with the same three tags, once per edge the model had drawn. Across the
answers the live model has produced, a ledger of 3 to 33 lines is 1 to 3
such claims.

The envelope is unchanged. Where they render, both surfaces put together
the lines that differ only in what the claim is about, say the claim once
with a count, and list what it is said of.

What is pinned here: which lines go together and in what order; that the
said-once sentences are declared for real claims and list them in holes
those claims have; that the report prints every assumption exactly once;
and that the browser groups by the same facts over the generated tables.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from themis import language, ledger
from themis.output import analysis_report, reader_words
from tests import web_source

ROOT = pathlib.Path(__file__).resolve().parents[1]
SHAPES = json.loads(
    (ROOT / "tests/fixtures/answer_shapes.json").read_text(encoding="utf-8"))


def _edge(name: str, **over) -> dict:
    line = {"claim": [{"vocabulary": "gap_describes",
                       "token": "the_edge_is_an_llm_proposal",
                       "said": {"edge": name}}],
            "layer": "structural_edge", "provenance": "llm_proposal",
            "severity": "invalidating", "testable": True}
    line.update(over)
    return line


def _prior(key: str, value: str) -> dict:
    return {"claim": [{"vocabulary": "theta_prior_claim",
                       "token": "a_commonsense_prior",
                       "said": {"key": key, "value": value}}],
            "layer": "parameter", "provenance": "llm_prior",
            "severity": "distorting", "testable": True}


_DECLARED = {"claim": [{"vocabulary": "assumption_claim",
                        "token": "no_unmeasured_confounding"}],
             "layer": "identification", "provenance": "inherent",
             "severity": "invalidating", "testable": False}


# --- which lines go together --------------------------------------------------


def test_lines_differing_only_in_what_the_claim_is_about_go_together():
    lines = [_edge("a → b"), _DECLARED, _edge("b → c"), _prior("P(a)", "0.3"),
             _edge("a → c"), _prior("P(b|a)", "0.6")]
    groups = ledger.grouped(lines)
    assert [len(g) for g in groups] == [3, 1, 2]
    # In the order the first of each was met, and nothing lost or repeated.
    assert [g[0] for g in groups] == [lines[0], lines[1], lines[3]]
    assert sorted(map(id, (a for g in groups for a in g))) == sorted(
        map(id, lines))


@pytest.mark.parametrize("change", [
    {"severity": "distorting"},
    {"layer": "identification"},
    {"provenance": "discovery"},
    {"testable": False},
    {"checked": {"verdict": "refuted", "by": "overidentification"}},
], ids=["grade", "layer", "provenance", "testable", "checked"])
def test_a_line_a_reader_is_told_something_else_about_stays_apart(change):
    """Every tag printed beside a group is printed once, off its first
    line; a line that differs in one would be shown wearing another's."""
    groups = ledger.grouped([_edge("a → b"), _edge("b → c", **change)])
    assert [len(g) for g in groups] == [1, 1]


def test_a_claim_with_no_said_once_sentence_is_said_line_by_line():
    twice = [copy.deepcopy(_DECLARED), copy.deepcopy(_DECLARED)]
    assert [len(g) for g in ledger.grouped(twice)] == [1, 1]
    # And so is one made of two statements, whose second differs per line.
    two = _edge("a → b")
    two["claim"].append({"vocabulary": "gap_describes",
                         "token": "the_edge_survived_this_share_of_resamples",
                         "said": {"confidence": "0.8"}})
    assert [len(g) for g in ledger.grouped([two, copy.deepcopy(two)])] == [1, 1]


# --- the sentences ------------------------------------------------------------


def _claim_words(spelling: str) -> language.Words:
    """The sentence a claim's own vocabulary has for this token."""
    found = [words for name in ("gap_describes", "theta_prior_claim",
                                "stated_form_claim")
             for words in [language._words_of(name, spelling)] if words]
    assert len(found) == 1, (spelling, len(found))
    return found[0]


def test_each_said_once_sentence_is_of_a_claim_and_lists_its_own_holes():
    assert set(ledger.SEVERAL_LEAD) == set(ledger.SEVERAL_ITEM)
    assert len(ledger.SEVERAL_LEAD) == 3
    for spelling, lead in ledger.SEVERAL_LEAD.items():
        single = _claim_words(spelling)
        assert language.holes(lead) == {"n"}, spelling
        # What is listed under the sentence is everything the single
        # sentence said of its one thing, so a group loses no fact.
        assert language.holes(ledger.SEVERAL_ITEM[spelling]) == language.holes(
            single), spelling
        assert set(lead) == set(single) == set(ledger.SEVERAL_ITEM[spelling])


def test_the_browser_holds_both_tables_from_the_kernel():
    built = reader_words.tables()
    assert set(built["LEDGER_SEVERAL_LEAD"]) == set(ledger.SEVERAL_LEAD)
    assert set(built["LEDGER_SEVERAL_ITEM"]) == set(ledger.SEVERAL_ITEM)


# --- the report ---------------------------------------------------------------


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_the_report_says_the_claim_once_and_lists_what_it_is_said_of(lang):
    lines = [_edge("a → b"), _edge("b → c"), _edge("a → c"),
             _prior("P(a)", "0.3")]
    rows = analysis_report._ledger_rows(lines, lang=lang)
    lead = language.fill(ledger.SEVERAL_LEAD["the_edge_is_an_llm_proposal"],
                         lang, n=3)
    assert sum(lead in row for row in rows) == 1
    assert rows[1:4] == ["  - `a → b`", "  - `b → c`", "  - `a → c`"]
    # A group of one is the line it always was.
    assert rows[4:] == analysis_report._ledger_rows([lines[3]], lang=lang)
    assert len(rows) == 5


@pytest.mark.parametrize("lang", sorted(language.written()))
def test_every_stored_assumption_is_still_printed_exactly_once(lang):
    """Over the corpus: a row per group, an item per grouped line, and the
    lines said alone unchanged."""
    grouped_somewhere = 0
    for name, row in sorted(SHAPES.items()):
        lines = (((row["result"].get("extensions") or {})
                  .get("assumption_ledger") or {}).get("assumptions")) or []
        if not lines:
            continue
        groups = ledger.grouped(lines)
        assert sum(len(g) for g in groups) == len(lines), name
        rows = analysis_report._ledger_rows(lines, lang=lang)
        heads = [r for r in rows if r.startswith("- ")]
        assert len(heads) == len(groups), name
        several = [g for g in groups if len(g) > 1]
        grouped_somewhere += bool(several)
        for group in several:
            spelling = group[0]["claim"][0]["token"]
            for one in group:
                listed = "  - " + language.assemble(
                    ledger.SEVERAL_ITEM[spelling], one["claim"][0]["said"],
                    lang=lang)
                assert rows.count(listed) >= 1, (name, listed)
        for group in groups:
            if len(group) == 1:
                alone = analysis_report._ledger_rows(group, lang=lang)
                assert alone[0] in rows, name
    # The corpus is mostly answers from data, whose ledgers are an
    # estimator's declared assumptions; two stored answers rest on several
    # proposed edges.
    assert grouped_somewhere == 2, grouped_somewhere


# --- the browser --------------------------------------------------------------


def test_the_browser_groups_by_the_same_facts_at_both_places_it_prints_a_line():
    source = web_source.read(web_source.VERDICT)
    key = web_source.chunks(source)["saidWith"]
    for fact in ("a.severity", "a.layer", "a.provenance", "a.testable",
                 "a.checked?.verdict", "a.checked?.by", "one.vocabulary",
                 "LEDGER_SEVERAL_LEAD"):
        assert fact in key, fact
    assert "claim.length !== 1" in key and "one.words" in key
    component = web_source.without_comments(
        web_source.read(web_source.COMPONENT))
    assert component.count("ledgerGrouped(") == 2
    assert "ledgerGrouped(premises)" in component
    assert "ledgerGrouped(ledger.assumptions)" in component
    assert "ledgerSeveralLead(group, lang)" in component
    assert "ledgerSeveralItem(one, lang)" in component
