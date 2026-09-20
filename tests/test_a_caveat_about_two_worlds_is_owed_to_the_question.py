"""A caveat about two worlds is owed to the question, not to the answer.

Identifying a counterfactual quantity rests on premises no data can check,
and the gap that says so reached only some of the questions that ask for
one. It read the ANSWER: a status word, plus a three-name list of
derivation rules, plus one spelling of the query kind. Four questions ask
across worlds and only ``counterfactual`` was named, so the other three
arrived through whichever of the other two disjuncts happened to catch
them -- and the caveat came to turn on what came out.

Measured before the repair, on the 252-answer corpus: 56 of the 69
across-world answers carried it. A ``causation`` query answered with
Tian-Pearl bounds carried it, because ``counterfactual_bounded`` is a
counterfactual status; the same query answered with points did not,
because ``numerically_solved`` is not. One question, two stories about its
own premises, and the difference was whether the caller had declared
monotonicity. Every ``counterfactual_conjunction`` answer lost it -- the
conjunction of counterfactual events being, of the ten, the question whose
quantity is most plainly defined over more than one world. So did the
linear-SCM counterfactual that came back through the estimator, while its
forty-three siblings from the solver kept it, the two differing only in
which machine produced the number.

Thirteen answers were left with a bare ``missing_assumption`` gap, which
is what the classifier's own docstring says must not happen: "a stalled
counterfactual surfaces only as a generic 'missing assumption' gap and the
L3 vs L2 distinction is lost in rendering."

``Question.asks_across_worlds`` is the fact it needed. The trap it has to
survive is that the four are not the kinds whose NAME says counterfactual:
``causation`` is PN/PS/PNS, which condition on the factual world and ask
about another one, and nothing in the string says so.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for
from themis import questions
from themis.output.data_gap_report import (
    _classify_counterfactual_assumptions,
)
from themis.types import (
    RAISED_BY_TURNS_ON,
    GapKind,
    QueryKind,
    ResultStatus,
)

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

SPECIES = GapKind.COUNTERFACTUAL_IDENTIFICATION_ASSUMPTION_REQUIRED
CAVEAT = SPECIES.value

#: The four, and why each one's quantity needs two worlds to be stated.
ACROSS_WORLDS = {
    "counterfactual": "one cell of the counterfactual joint distribution",
    "causation": "PN/PS/PNS condition on the factual world and ask about "
                 "another",
    "scm_counterfactual": "abduction reads the unit's world, action leaves it",
    "counterfactual_conjunction": "several counterfactual events at once",
}

#: The answers the producer now writes this caveat onto and the snapshot
#: does not carry it for. Not a tolerance: a roll-call of what one
#: re-collection settles. A structural row's name is a digest over the
#: shapes it brought in the run that filed it, so these rows cannot be
#: refreshed one at a time -- and the day the corpus is collected again
#: this list empties and this test says so by failing.
NOT_COLLECTED_SINCE = {
    "causation_plugin",
    "ctf_conjunction_plugin",
    "needs_investigation:causation:none",
    "needs_investigation:causation:none#4f0014",
    "needs_investigation:scm_counterfactual:none",
    "needs_investigation:scm_counterfactual:none#f2b812",
    "numerically_solved:causation:numeric_causation_estimate",
    "numerically_solved:causation:numeric_causation_estimate#6f97c5",
    "outside_language:causation:none",
    "scm_counterfactual_linear_fit",
    "structurally_solved:counterfactual_conjunction:id_star_identification",
    "structurally_solved:counterfactual_conjunction:"
    "id_star_identification#bc863b",
    "structurally_solved:counterfactual_conjunction:"
    "id_star_identification#c17338",
}


def _caveats(result) -> list:
    return [gap for gap in
            ((result.get("data_gap_report") or {}).get("gaps") or ())
            if gap.get("kind") == CAVEAT]


def _fired(kind: str, status: ResultStatus) -> list:
    return list(_classify_counterfactual_assumptions(
        derivation=(), status=status, query_kind=QueryKind(kind),
    ))


# ------------------------------------------------- what is declared


def test_four_of_the_ten_questions_ask_across_worlds():
    declared = {q.kind for q in questions.DECLARED if q.asks_across_worlds}
    assert declared == set(ACROSS_WORLDS)
    assert len(questions.DECLARED) == 10


def test_the_four_are_not_the_ones_whose_name_says_counterfactual():
    """The trap. A name is not a declaration."""
    by_name = {q.kind for q in questions.DECLARED
               if "counterfactual" in q.kind}
    assert by_name < set(ACROSS_WORLDS)
    assert set(ACROSS_WORLDS) - by_name == {"causation"}


def test_a_question_added_without_an_answer_to_this_does_not_import():
    """No default, for the reason every field beside it has none: an
    absence cannot be told from an oversight once it reads as False."""
    for question in questions.DECLARED:
        assert isinstance(question.asks_across_worlds, bool), question.kind
    field = questions.Question.__dataclass_fields__["asks_across_worlds"]
    assert field.default is dataclasses.MISSING
    assert field.default_factory is dataclasses.MISSING


# ------------------------------------------------- what the classifier does


@pytest.mark.parametrize("kind", sorted(ACROSS_WORLDS))
@pytest.mark.parametrize("status", sorted(ResultStatus, key=str))
def test_a_question_that_asks_across_worlds_is_owed_it_whatever_came_out(
        kind, status):
    """Across every word an answer can lead with, including the four that
    say a quantity arrived and the three that say none did."""
    fired = _fired(kind, status)
    assert len(fired) == 1
    assert fired[0].kind is SPECIES


@pytest.mark.parametrize(
    "kind",
    sorted(q.kind for q in questions.DECLARED if not q.asks_across_worlds))
@pytest.mark.parametrize("status", sorted(ResultStatus, key=str))
def test_a_question_that_does_not_is_never_owed_it(kind, status):
    """The other half, and the one that used to leak: an answer reaching
    a counterfactual status on a question that asked for an
    interventional contrast does not make the question a counterfactual
    one."""
    assert _fired(kind, status) == []


def test_the_name_on_the_ref_is_one_the_species_declares():
    """The pair is kept for a reason the declaration states; what this
    holds is that both halves are reachable, so neither row is a name
    nothing writes."""
    names, why = RAISED_BY_TURNS_ON[SPECIES]
    assert names == {"counterfactual_status", "counterfactual_query_kind"}
    assert "asks_across_worlds" in why
    seen = set()
    for kind in ACROSS_WORLDS:
        for status in ResultStatus:
            fired = _fired(kind, status)
            seen.add(fired[0].provenance[0].ref_id)
    assert seen == names


# ------------------------------------------------- what the corpus shows


def test_every_across_world_answer_the_corpus_has_re_collected_carries_it():
    missing = {name for name in SHAPES
               if SHAPES[name]["result"].get("query_kind") in ACROSS_WORLDS
               and not _caveats(SHAPES[name]["result"])}
    assert missing == NOT_COLLECTED_SINCE


def test_no_other_answer_carries_it():
    stray = [name for name in sorted(SHAPES)
             if SHAPES[name]["result"].get("query_kind") not in ACROSS_WORLDS
             and _caveats(SHAPES[name]["result"])]
    assert stray == []


def test_the_answer_says_it_once():
    """One caveat per answer, not one per disjunct that noticed."""
    for name in sorted(SHAPES):
        assert len(_caveats(SHAPES[name]["result"])) <= 1, name


def test_the_corpus_still_holds_all_four_kinds():
    """A roll-call rather than a total: a kind that stops appearing is a
    kind this gate stops asking about, and that is worth failing on."""
    counts: dict[str, int] = {}
    for name in sorted(SHAPES):
        kind = SHAPES[name]["result"].get("query_kind")
        if kind in ACROSS_WORLDS:
            counts[kind] = counts.get(kind, 0) + 1
    assert set(counts) == set(ACROSS_WORLDS), sorted(counts)
    assert sum(counts.values()) == 69, counts


# ------------------------------------------------- and the door still opens


def test_the_door_still_reads_every_across_world_answer():
    """The caveat is added to answers the public door already accepted, so
    the change must not make any of them refusable."""
    for name in sorted(SHAPES):
        row = SHAPES[name]
        if row["result"].get("query_kind") not in ACROSS_WORLDS:
            continue
        door = the_door_for(row["result"])
        door(json.loads(json.dumps(row["program"])),
             json.loads(json.dumps(row["result"])))
