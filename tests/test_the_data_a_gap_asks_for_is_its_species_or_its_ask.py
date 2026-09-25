"""What a gap tells a reader to go and collect, and who decides it.

``required_data.data_type`` is the difference between "someone has to
publish one number" and "someone has to obtain records", and it was typed
at every construction site that has one — six of them — and declared
nowhere. That is the arrangement :data:`themis.types.SEVERITY_OF` was
written to end, twice already: a value every site writes is not declared
anywhere, so the only thing a rule could hold it against is the producer's
layout, and a verifier restating a producer's layout agrees with it by
construction.

So the word is on the species now. Five species ask for one shape whichever
occasion raises them; one asks for either, and its row says what the choice
turns on.

THE OCCASION IS READ, not taken from either word the gap wrote. A
``missing_distribution`` gap cites the investigation item it was filed for,
and that item carries the statement the distribution is missing FROM —
whether it conditions on anything is a fact about the answer rather than
about the gap's own spelling of it. Which is what makes this more than two
fields agreed with each other: the ``signature`` naming the shape and the
``data_type`` naming what would supply it are one fact spelled twice, and
both are held to the statement.

Measured before any of it was believed: 974 gaps across 38 species pass
untouched, and 1494 forgeries — every other shape on every gap that states
one, a shape invented for a species that asks for none, and each signature
flipped — are refused, none of them by the schema.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.types import (
    DATA_TYPE_OF,
    DATA_TYPE_TURNS_ON,
    DataGap,
    GapKind,
    GapProvenanceRef,
    GapRefKind,
    GapRequiredData,
    GapSeverity,
    RequiredDataType,
    required_data_type,
)
from themis.gaps import Sentence, sentence
from themis.verifier.data_gap_rules import _verify_t10_6_shape_of_data
from themis.verifier.errors import VerificationError

CORPUS = pathlib.Path(__file__).resolve().parent / "fixtures" / (
    "answer_shapes.json")
SHAPES = tuple(shape.value for shape in RequiredDataType)


@pytest.fixture(scope="module")
def corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def _results(envelope):
    return envelope.get("results") or [envelope]


def _read(result) -> None:
    _verify_t10_6_shape_of_data(
        result.get("data_gap_report") or {},
        investigation_requests=list(result.get("investigation_requests") or []),
    )


def _refuses(result) -> str | None:
    try:
        _read(result)
    except VerificationError as exc:
        return str(exc)
    return None


# --- the declaration, read from the contract rather than the corpus -------


def test_a_species_asks_for_one_shape_or_chooses_between_shapes():
    """The premise. Two rows that cannot overlap, and a species in neither
    asks for no particular shape — which is a declaration too, and the one
    that makes the table total without partitioning the enum."""
    assert not DATA_TYPE_OF.keys() & DATA_TYPE_TURNS_ON.keys()
    for kind, shape in DATA_TYPE_OF.items():
        assert isinstance(kind, GapKind)
        assert isinstance(shape, RequiredDataType)
        assert required_data_type(kind) == frozenset({shape})
    for kind, (shapes, turns_on) in DATA_TYPE_TURNS_ON.items():
        assert len(shapes) >= 2, kind
        assert turns_on.strip() and not turns_on.endswith("."), kind
        assert required_data_type(kind) == shapes
    assert required_data_type(GapKind.AMBIGUOUS_VARIABLE_DEFINITION) == (
        frozenset())


def test_the_one_species_whose_shape_is_the_occasions_is_the_one_with_an_ask():
    """Why exactly one row is a choice: a species asks for a shape it can
    name in advance unless what it is missing is a statement the caller
    wrote, and only one species is filed against a statement."""
    assert set(DATA_TYPE_TURNS_ON) == {GapKind.MISSING_DISTRIBUTION}
    shapes, _turns_on = DATA_TYPE_TURNS_ON[GapKind.MISSING_DISTRIBUTION]
    assert shapes == frozenset({RequiredDataType.IPD,
                                RequiredDataType.MARGINAL})


def test_a_species_no_producer_builds_still_declares_what_it_would_ask_for():
    """``missing_population_distribution`` is declared on the terms its
    severity row is declared on: nothing in this tree builds one, and the
    alternative is a hole in a table whose whole point is having none. A
    producer that disagrees has to change the declaration."""
    assert DATA_TYPE_OF[GapKind.MISSING_POPULATION_DISTRIBUTION] == (
        RequiredDataType.MARGINAL)


# --- the producer fills from it, and refuses a site's own word ------------


def test_a_gap_of_a_fixed_species_has_its_shape_filled_in():
    """The site does not type it, so there is no site left to type it
    wrong."""
    gap = DataGap(
        kind=GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN,
        describes=(sentence(
            Sentence.THE_TARGET_POPULATIONS_COVARIATE_DISTRIBUTION_IS_MISSING,
            population="user", variables="age"),),
        required_data=GapRequiredData(variables=("age",)),
    )
    assert gap.required_data.data_type is RequiredDataType.MARGINAL


def test_a_site_contradicting_its_species_is_refused():
    with pytest.raises(ValueError) as caught:
        DataGap(
            kind=GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN,
            describes=(sentence(
                Sentence
                .THE_TARGET_POPULATIONS_COVARIATE_DISTRIBUTION_IS_MISSING,
                population="user", variables="age"),),
            required_data=GapRequiredData(data_type=RequiredDataType.IPD),
        )
    assert "DATA_TYPE_TURNS_ON" in str(caught.value)


def test_the_occasions_species_has_to_say_which_and_is_told_what_it_turns_on():
    """No filling in for the one species whose shape is an occasion's:
    there is nothing to fill it in FROM, and the sentence the site is
    handed is the question it has to answer."""
    with pytest.raises(ValueError) as caught:
        DataGap(
            kind=GapKind.MISSING_DISTRIBUTION,
            describes=(sentence(Sentence.A_DISTRIBUTION_IS_MISSING,
                                what="P(x)"),),
            required_data=GapRequiredData(),
        )
    assert DATA_TYPE_TURNS_ON[GapKind.MISSING_DISTRIBUTION][1] in str(
        caught.value)


def test_a_species_that_asks_for_no_data_may_not_be_handed_a_shape():
    """The other direction, and the one that keeps the table honest: a
    site cannot invent a shape by being the only place that says it."""
    with pytest.raises(ValueError) as caught:
        DataGap(
            kind=GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
            describes=(sentence(Sentence.THE_IDENTIFICATION_ROUTE_FAILED,
                                why="no admissible set"),),
            required_data=GapRequiredData(data_type=RequiredDataType.IPD),
        )
    assert "declares no shape it asks for" in str(caught.value)


def test_a_gap_with_no_required_data_block_is_not_asked_the_question():
    """Silence where a gap asks for nothing. Most gaps qualify an answer
    rather than ask for data, and demanding a shape of them would be this
    rule inventing an ask."""
    gap = DataGap(
        kind=GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        describes=(sentence(Sentence.THE_IDENTIFICATION_ROUTE_FAILED,
                            why="no admissible set"),),
    )
    assert gap.required_data is None
    assert gap.severity is GapSeverity.BLOCKING


# --- the honest side, on every gap the corpus carries ---------------------


def test_every_gap_in_the_corpus_asks_for_what_its_species_asks_for(corpus):
    """What a refusing rule has to earn first, and read through the report
    door rather than through ``verify`` — most rows carrying a gap report
    have no derivation for ``verify`` to re-run, so a sweep through the
    full door would reach six of the eighty-four asks and report the rest
    as covered."""
    seen = 0
    species = set()
    for name, row in sorted(corpus.items()):
        for result in _results(row["result"]):
            report = result.get("data_gap_report")
            if not isinstance(report, dict):
                continue
            complaint = _refuses(result)
            assert complaint is None, (name, complaint)
            for gap in report.get("gaps") or []:
                seen += 1
                species.add(gap.get("kind"))
    # 26 fewer: the gaps that went when the last value of a variable under one
    # condition stopped being asked for (#776).
    assert (seen, len(species)) == (1011, 38), (seen, len(species))


# --- and every shape the corpus does not say ------------------------------


def test_no_gap_may_ask_for_a_shape_its_species_does_not(corpus):
    """Every other shape, on every gap that states one, the shape dropped
    from a gap that asks for data, and a shape invented for each species
    that asks for none. Counted, because a sweep that reports a number
    nobody can compare is a sweep that can quietly stop reaching
    anything."""
    bent = {"stated": 0, "dropped": 0, "invented": 0}
    for name, row in sorted(corpus.items()):
        for result in _results(row["result"]):
            report = result.get("data_gap_report")
            if not isinstance(report, dict):
                continue
            for index, gap in enumerate(report.get("gaps") or []):
                wanted = gap.get("required_data")
                if isinstance(wanted, dict) and wanted.get("data_type"):
                    for other in SHAPES:
                        if other == wanted["data_type"]:
                            continue
                        forged = copy.deepcopy(result)
                        (forged["data_gap_report"]["gaps"][index]
                         ["required_data"])["data_type"] = other
                        assert _refuses(forged), (name, index, other)
                        bent["stated"] += 1
                    forged = copy.deepcopy(result)
                    (forged["data_gap_report"]["gaps"][index]
                     ["required_data"]).pop("data_type")
                    assert _refuses(forged), (name, index, "dropped")
                    bent["dropped"] += 1
                elif not isinstance(wanted, dict):
                    forged = copy.deepcopy(result)
                    (forged["data_gap_report"]["gaps"][index]
                     )["required_data"] = {"data_type": "ipd"}
                    assert _refuses(forged), (name, index, "invented")
                    bent["invented"] += 1
    # 130 fewer stated and 26 fewer dropped: the gaps that went when
    # the last value of a variable under one condition stopped being asked for (#776).
    assert bent == {"stated": 545, "dropped": 109, "invented": 902}, bent


def test_the_shape_a_missing_distribution_asks_for_is_read_off_its_ask(corpus):
    """Both halves of the one occasion, both directions, on every ask the
    corpus carries: the shape flipped and the signature flipped, each
    refused by the statement rather than by the other word."""
    flipped = {"conditional": 0, "marginal": 0}
    for name, row in sorted(corpus.items()):
        for result in _results(row["result"]):
            report = result.get("data_gap_report")
            if not isinstance(report, dict):
                continue
            for index, gap in enumerate(report.get("gaps") or []):
                shape = gap.get("signature")
                if shape not in ("conditional", "marginal"):
                    continue
                other = "marginal" if shape == "conditional" else "conditional"
                forged = copy.deepcopy(result)
                forged["data_gap_report"]["gaps"][index]["signature"] = other
                complaint = _refuses(forged)
                assert complaint and "one fact spelled twice" in complaint, (
                    name, index)
                flipped[shape] += 1
    # 14 fewer conditional and 12 fewer marginal: the gaps that went when
    # the last value of a variable under one condition stopped being asked for (#776).
    assert flipped == {"conditional": 71, "marginal": 13}, flipped


def test_a_conditional_ask_answered_with_a_marginal_demand_is_refused(corpus):
    """Named rather than swept, because this is the sentence a reader
    acts on: the gap says one published number closes it, and the
    statement it was filed for conditions on something."""
    row = next(row for row in corpus.values()
               if any(gap.get("signature") == "conditional"
                      for result in _results(row["result"])
                      for gap in ((result.get("data_gap_report") or {}
                                   ).get("gaps") or [])))
    forged = copy.deepcopy(row["result"])
    for result in _results(forged):
        for gap in (result.get("data_gap_report") or {}).get("gaps") or []:
            if gap.get("signature") != "conditional":
                continue
            gap["signature"] = "marginal"
            gap["required_data"]["data_type"] = "marginal"
            break
        break
    complaint = _refuses(_results(forged)[0])
    assert complaint and "which needs 'ipd'" in complaint


def test_a_program_and_answer_carry_this_to_the_public_door(corpus):
    """The rule where a caller stands, not only where it was written."""
    row = next(
        row for name, row in sorted(corpus.items())
        if _reaches_verify(row)
    )
    forged = copy.deepcopy(row["result"])
    for result in _results(forged):
        for gap in (result.get("data_gap_report") or {}).get("gaps") or []:
            wanted = gap.get("required_data")
            if isinstance(wanted, dict) and wanted.get("data_type"):
                wanted["data_type"] = "cohort"
                break
        else:
            continue
        break
    with pytest.raises(VerificationError) as caught:
        themis.verify(row["program"], forged)
    assert "T10-6" in str(caught.value)


def _reaches_verify(row) -> bool:
    try:
        themis.verify(row["program"], row["result"])
    except Exception:
        return False
    return any(
        isinstance((result.get("data_gap_report") or {}), dict)
        and any(isinstance(gap.get("required_data"), dict)
                and gap["required_data"].get("data_type")
                for gap in (result.get("data_gap_report") or {}
                            ).get("gaps") or [])
        for result in _results(row["result"])
    )


# --- and silence where there is no ask to read ----------------------------


def test_an_ask_this_rule_cannot_find_leaves_the_occasion_unjudged():
    """A ``missing_distribution`` gap whose item is not in hand: the shape
    is still held to the species' two words, and nothing pretends to know
    which of them this occasion is. Inventing one here would refuse honest
    answers whose investigation requests travelled separately."""
    report = {"gaps": [{
        "kind": "missing_distribution",
        "signature": "conditional",
        "required_data": {"data_type": "marginal"},
        "provenance": [{"ref_kind": "investigation_request",
                        "ref_id": "parameter:P(y)"}],
    }]}
    _verify_t10_6_shape_of_data(report, investigation_requests=[])
    report["gaps"][0]["required_data"]["data_type"] = "cohort"
    with pytest.raises(VerificationError):
        _verify_t10_6_shape_of_data(report, investigation_requests=[])


def test_an_item_that_filed_no_statement_is_not_a_statement_to_read():
    """An item with no probability behind it says nothing about shape, and
    reading ``given`` off it would make an absent target a marginal."""
    report = {"gaps": [{
        "kind": "missing_distribution",
        "signature": "conditional",
        "required_data": {"data_type": "ipd"},
        "provenance": [{"ref_kind": "investigation_request",
                        "ref_id": "parameter:P(y)"}],
    }]}
    requests = [{"items": [{"target": "parameter:P(y)", "skeleton": {}}]}]
    _verify_t10_6_shape_of_data(report, investigation_requests=requests)
    requests[0]["items"][0]["skeleton"] = {"target": {"value": True}}
    with pytest.raises(VerificationError) as caught:
        _verify_t10_6_shape_of_data(report, investigation_requests=requests)
    assert "is marginal" in str(caught.value)
