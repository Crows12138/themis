"""A table that says "this one is the occasion's" is not an exemption.

``SEVERITY_OF`` and ``SEVERITY_TURNS_ON`` partition ``GapKind``, and the
partition is checked at import, so every species either declares one
severity for all its occasions or declares, in a sentence, what its
severity turns on. The first half is held by T10-5 against the table. The
second half was held by nothing at all: a species moved into
``SEVERITY_TURNS_ON`` left the only rule that read its severity, and
nothing replaced it — so the table read as a declaration and worked as an
exemption.

MEASURED BEFORE IT WAS WRITTEN, on the corpus's own answers.
``iv_identification_assumption_required`` carries ``important`` on the row
where a feedback loop was reduced to one equation and ``informational``
where the assumption only conditions the reading. Swap those two, and
``verify``, ``verify_answer_claims`` and ``verify_data_gap_report`` all
passed — in both directions, on real envelopes.

WHY THE OCCASION IS READABLE. Two producers build this species, one per
occasion, and they are mutually exclusive by construction: the one that
writes ``informational`` returns as soon as a feedback loop is on the
envelope, and the one that writes ``important`` returns unless that loop
was reduced. So "which occasion" is the identification layer's record of
what happened to the estimand, and that record is on the envelope beside
the gap.

WHAT CLOSES THE SET, and it is not a table of readers. A species declared
occasion-dependent with no reader anywhere has a field nothing can refuse,
and a registry naming its reader would be one more name to keep true. The
sweep below asks each member for a counterexample instead: every species
in ``SEVERITY_TURNS_ON`` must appear on a real answer, and its severity on
that answer must not be bendable. Where the reader lives is then nobody's
business — ``declared_type_data_mismatch`` is read in
:mod:`themis.verifier.type_reconciliation_rules`, against the columns the
answer stands on, and passes this sweep without being registered anywhere.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.blocks import Block
from themis.types import GapKind, GapSeverity, SEVERITY_OF, SEVERITY_TURNS_ON
from themis.verifier.data_gap_rules import (
    _A_LOOP_REDUCED_TO_ONE_EQUATION,
    _the_occasion_for_an_iv_assumption,
    verify_data_gap_report,
)
from themis.verifier.errors import VerificationError

CORPUS = pathlib.Path(__file__).resolve().parent / "fixtures" / (
    "answer_shapes.json")


@pytest.fixture(scope="module")
def corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def _results(envelope):
    return envelope.get("results") or [envelope]


def _gaps(result):
    return (result.get("data_gap_report") or {}).get("gaps") or []


def _rows_carrying(corpus, kind: str):
    """Every (row name, result index, gap index) carrying this species."""
    for name, row in sorted(corpus.items()):
        for result_index, result in enumerate(_results(row["result"])):
            for gap_index, gap in enumerate(_gaps(result)):
                if gap.get("kind") == kind:
                    yield name, result_index, gap_index


# --- the sentence the rule reads is the envelope's own word ----------------


def test_the_path_this_reader_walks_is_the_blocks_vocabulary():
    """Restated, like every envelope word in that module, and pinned here
    to the block the identification layer actually writes."""
    assert _A_LOOP_REDUCED_TO_ONE_EQUATION[0] == "extensions"
    assert _A_LOOP_REDUCED_TO_ONE_EQUATION[1] == Block.FEEDBACK_LOOP.value
    assert _A_LOOP_REDUCED_TO_ONE_EQUATION[2] == "reduction"


@pytest.mark.parametrize("envelope,expected", [
    ({}, "informational"),
    ({"extensions": {}}, "informational"),
    ({"extensions": {"feedback_loop": {}}}, "informational"),
    ({"extensions": {"feedback_loop": {"reduction": None}}}, "informational"),
    ({"extensions": {"feedback_loop": {"reduction": "simultaneous_equations"}}},
     "important"),
])
def test_the_occasion_is_read_off_what_happened_to_the_estimand(
        envelope, expected):
    """Including the corner neither producer builds — a loop on the
    envelope that was not reduced. The gap does not arise there, and a
    reader asked about it answers the weaker of the two rather than
    inventing a third."""
    assert _the_occasion_for_an_iv_assumption(envelope) == expected


# --- the hole, at the size it was measured ---------------------------------


@pytest.mark.parametrize("row_name,expected", [
    ("iv_2sls", "important"),
    ("structurally_solved:identify:identify_via_iv", "informational"),
])
def test_the_two_occasions_are_the_two_the_producers_build(
        corpus, row_name, expected):
    """The shape before anything is bent, on both sides. One answer had
    its estimand replaced by a single equation's coefficient; the other
    carries an assumption that conditions how its number is read."""
    row = corpus[row_name]
    result = _results(row["result"])[0]
    carried = [gap for gap in _gaps(result)
               if gap.get("kind")
               == GapKind.IV_IDENTIFICATION_ASSUMPTION_REQUIRED.value]
    assert [gap["severity"] for gap in carried] == [expected]
    themis.verify_data_gap_report(row["result"])
    themis.verify(row["program"], row["result"])


# --- and the set, closed by counterexample rather than by a roster ---------


@pytest.mark.parametrize("species", sorted(SEVERITY_TURNS_ON,
                                           key=lambda k: k.value))
def test_a_species_that_declares_its_weight_an_occasions_has_a_reader(
        corpus, species):
    """The gate this file exists for. For every species whose severity is
    an occasion's, a real answer carrying it must exist and its severity
    must not be bendable — in EVERY direction, since a rule that refuses
    one wrong word and accepts the other reads no occasion at all.

    A species with no row here fails rather than passing quietly: the
    sweep would otherwise report a closed set on the strength of a corpus
    that never met the member.
    """
    rows = list(_rows_carrying(corpus, species.value))
    assert rows, (
        f"{species.value} declares its severity an occasion's and no answer "
        f"in the corpus carries it, so nothing here can tell whether "
        f"anything reads that occasion; harvest a row that carries it")

    for row_name, result_index, gap_index in rows:
        row = corpus[row_name]
        honest = _gaps(_results(row["result"])[result_index])[gap_index]
        for word in (member.value for member in GapSeverity):
            if word == honest.get("severity"):
                continue
            forged = copy.deepcopy(row["result"])
            _gaps(_results(forged)[result_index])[gap_index]["severity"] = word
            with pytest.raises(VerificationError) as caught:
                themis.verify_data_gap_report(forged)
            complaint = str(caught.value)
            assert "severity" in complaint, (
                f"{row_name} gap[{gap_index}] bent to {word!r} was refused "
                f"by something that is not about its severity: {complaint}")
            assert species.value in complaint


def test_an_audit_handed_no_answer_refuses_rather_than_skipping(corpus):
    """The one way past this reader, closed elsewhere and checked here.

    The occasion is a fact about the answer, so the reader is silent when
    the report is audited on its own — and silence there would be exactly
    the acceptance this file exists to end. It is not reachable: a species
    whose weight turns on the answer cites an ``envelope_path``, and T10-1
    refuses a report audited without the answer that path lands on. Asked
    of the rule rather than trusted to the comment beside it.
    """
    row = corpus["iv_2sls"]
    gap = next(
        g for g in _gaps(_results(row["result"])[0])
        if g.get("kind")
        == GapKind.IV_IDENTIFICATION_ASSUMPTION_REQUIRED.value)
    alone = {"gaps": [copy.deepcopy(gap)]}
    alone["gaps"][0]["severity"] = "informational"
    with pytest.raises(VerificationError) as caught:
        verify_data_gap_report(alone)
    assert caught.value.rule == "data_gap_provenance_check"
    assert "no answer" in str(caught.value)


def test_the_two_tables_still_partition_the_species():
    """What makes the sweep above a statement about all of them: a kind
    absent from both tables would be held by neither this file nor T10-5,
    and there would be nothing to notice it."""
    assert set(SEVERITY_OF) | set(SEVERITY_TURNS_ON) == set(GapKind)
    assert not set(SEVERITY_OF) & set(SEVERITY_TURNS_ON)
