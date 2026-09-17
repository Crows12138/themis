"""What a gap tells a reader it IS, held to the gap it is.

``describes[].sentence`` is the field a reader reads FIRST — the statement
naming what went wrong. It was typed at 78 construction sites out of a
closed vocabulary of 88 and declared nowhere: ``gaps.BY_SENTENCE`` names
the members and ``gaps.DESCRIBES`` holds their wording, and neither says
which species may make which statement. Swapping one for another on an
accepted answer, 21 of the 87 foreign statements went through the public
door. The 66 refusals came from ``statement_rules._CARRIERS``, which asks
whether the slots a sentence names are the ones filled in beside it — so
any two statements with the same slot signature were interchangeable, and
a gap about unmeasured confounding could describe itself as a weak first
stage.

Fifth instance of one disease and the same cure: a value written at every
construction site and declared nowhere, split into what the species fixes
and what the occasion fixes, checked at import, obeyed by the producer and
imported rather than restated by the verifier.

The declaration is a CEILING, as :data:`themis.gaps.ROUTES_OF` is: which
of a species' statements THIS occasion makes is the renderer's decision.
Two statements of the same species therefore stay interchangeable — and a
species says between one and ten, against a vocabulary of 88.

Read off the SITES, not off a run. The corpus reaches 70 of the 88, so a
table harvested from answers would refuse the other 18 wherever they are
written, and a gate that closes a hole by refusing honest reports is worse
than the hole.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from tests.answer_corpus import verify_honestly
from themis import gaps
from themis.gaps import Sentence
from themis.output.data_gap_report import GAP_KINDS_WITH_NO_PRODUCER
from themis.types import DataGap, GapKind
from themis.verifier import data_gap_rules
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

ALL_SENTENCES = sorted(str(said) for said in Sentence)


def _results(envelope):
    return envelope.get("results") or [envelope]


def _door(result):
    return (themis.verify if result.get("derivation") is not None
            else themis.verify_answer_claims)


# --------------------------------------------- the declaration is complete


def test_every_species_that_is_ever_built_says_something():
    """The partition, and the half that cannot be asked at import.

    ``gaps._bind_sentences`` cannot ask whether every species has a row:
    a species nothing constructs says nothing, and which species those are
    is declared one layer up. So the two are held together here, where
    both are importable — and both directions are defects. A species with
    a producer and no row is one whose description nothing holds; a
    species with a row and no producer is a row describing a gap that
    cannot exist.
    """
    assert set(gaps.SENTENCES_OF) <= set(GapKind)
    assert (set(GapKind) - set(gaps.SENTENCES_OF)
            == set(GAP_KINDS_WITH_NO_PRODUCER))
    assert all(said for said in gaps.SENTENCES_OF.values())


def test_the_finer_table_is_folded_in_rather_than_copied():
    """``DISPLACED_BECAUSE`` decides a statement per displaced pair, and
    the coarse table does not write those eight a second time. Two tables
    saying the same thing drift, and the one that wins is a lookup order.
    """
    folded = set(gaps.DISPLACED_BECAUSE.values())
    kind = GapKind.UNATTEMPTED_LAYER_DUE_TO_DISPATCH_CONFLICT
    assert folded <= gaps.SENTENCES_OF[kind]
    assert not folded & gaps._SENTENCES_TYPED_AT_SITES[kind]
    assert len(gaps.SENTENCES_OF[kind]) == len(folded) + len(
        gaps._SENTENCES_TYPED_AT_SITES[kind])


def test_every_statement_the_kernel_names_is_some_species():
    """The direction that is easy to leave out, and the one #615 learned
    the expensive way: a statement on no row is one every rule reading
    this table refuses wherever it is written, so the gate itself becomes
    the false positive."""
    spoken = {said for row in gaps.SENTENCES_OF.values() for said in row}
    assert spoken == set(Sentence)


def test_a_species_says_few_of_the_eighty_eight():
    """The reach, measured rather than asserted. A ceiling nobody states
    gets read as a floor, so what this gate does NOT close is written
    down: two statements of the same species stay interchangeable."""
    widths = sorted(len(said) for said in gaps.SENTENCES_OF.values())
    assert widths[0] == 1
    assert widths[-1] == 10
    assert len(list(Sentence)) == 88


# ------------------------------------------------- the producer honours it


def test_a_gap_may_say_what_its_species_declares():
    gap = DataGap(
        kind=GapKind.UNMEASURED_CONFOUNDER_RISK,
        describes=(gaps.sentence(
            Sentence.THE_DAG_DECLARES_NO_LATENT_COMMON_CAUSE),),
        alternative_paths=(),
    )
    assert [str(s.sentence) for s in gap.describes] == [
        "the_dag_declares_no_latent_common_cause"]


def test_a_gap_may_not_say_what_another_species_says():
    """The forgery this gate is about, at the door it is built: a gap
    describing itself as another failure entirely."""
    with pytest.raises(ValueError, match="does not declare as a statement"):
        DataGap(
            kind=GapKind.UNMEASURED_CONFOUNDER_RISK,
            describes=(gaps.sentence(
                Sentence.THE_JOINT_FIRST_STAGE_IS_WEAK,
                instruments="`z`", f="1.0", threshold="10"),),
            alternative_paths=(),
        )


def test_a_species_nothing_builds_is_refused_in_those_terms():
    """The other side of the partition, and it points at the table that
    owns the fact rather than at the one that noticed it."""
    kind = next(iter(GAP_KINDS_WITH_NO_PRODUCER))
    with pytest.raises(ValueError, match="nothing in this kernel builds"):
        DataGap(
            kind=kind,
            describes=(gaps.sentence(
                Sentence.THE_DAG_DECLARES_NO_LATENT_COMMON_CAUSE),),
            alternative_paths=(),
        )


def test_rewriting_a_gap_keeps_the_statements_it_already_had():
    """``dataclasses.replace`` re-enters the constructor, and several
    passes rewrite a gap after it is built."""
    from dataclasses import replace

    gap = DataGap(
        kind=GapKind.WEAK_IV_INSTRUMENT,
        describes=(gaps.sentence(
            Sentence.THE_FIRST_STAGE_IS_WEAK,
            instrument="`z`", f="1.0", threshold="10"),),
        alternative_paths=(),
    )
    again = replace(gap, describes=(gaps.sentence(
        Sentence.THE_SET_CONSTRAINS_NOTHING),))
    assert [str(s.sentence) for s in again.describes] == [
        "the_set_constrains_nothing"]


# ------------------------------------------------- what the corpus carries


def test_no_answer_this_repository_produces_says_a_stray_statement():
    """The honest side, whole. A rule that refuses an answer the kernel
    itself writes is worse than the hole it closes, so this runs before
    the numbers below mean anything.

    Pinned at what it measures, because a sweep that quietly covers less
    each round stops measuring without failing.
    """
    slots = 0
    gap_total = 0
    species: set[str] = set()
    for name in sorted(SHAPES):
        for result in _results(SHAPES[name]["result"]):
            report = result.get("data_gap_report")
            if not isinstance(report, dict):
                continue
            for gap in report.get("gaps") or []:
                gap_total += 1
                species.add(gap["kind"])
                allowed = {str(s) for s in gaps.says_of(gap["kind"])}
                said = [entry["sentence"]
                        for entry in gap.get("describes") or []]
                slots += len(said)
                assert set(said) <= allowed, (name, gap["kind"])
    # 4 fewer slots: the sentence naming a Balke-Pearl interval's method and assumptions went with the
    # interval on four refreshed answers, whose instrument needs something conditioned.
    # 1 more slot and 1 more gap: the refreshed joint general-ID answer carries a gap about its
    # second treatment's definition, which its producer had grown since the row was stored.
    # 56 more slots and 56 more gaps: the eight rows brought when the identifier began
    # answering a query conditioning on a descendant of the treatment.
    assert (slots, gap_total, len(species)) == (1182, 1031, 38)


def test_the_door_still_accepts_every_answer_the_corpus_holds():
    for name in sorted(SHAPES):
        row = SHAPES[name]
        for result in _results(row["result"]):
            verify_honestly(row["program"], result)


# ----------------------------------------------------- what the rule holds


def _report(kind: str, said: str) -> dict:
    return {"gaps": [{"kind": kind, "describes": [{"sentence": said}]}]}


def test_every_species_refuses_every_statement_that_is_not_its_own():
    """Both directions over the whole cross product, so the gate cannot be
    tightened on one species and loosened on another without saying so."""
    refused = 0
    allowed = 0
    for kind in sorted(k.value for k in GapKind):
        own = {str(s) for s in gaps.says_of(kind)}
        for candidate in ALL_SENTENCES:
            report = _report(kind, candidate)
            if candidate in own:
                data_gap_rules._verify_t10_8_what_it_says(report)
                allowed += 1
                continue
            with pytest.raises(VerificationError, match="T10-8"):
                data_gap_rules._verify_t10_8_what_it_says(report)
            refused += 1
    assert (allowed, refused) == (89, 3607)
    assert allowed + refused == len(list(GapKind)) * len(ALL_SENTENCES)


def test_a_species_nothing_builds_is_told_so_by_the_rule_too():
    kind = next(iter(GAP_KINDS_WITH_NO_PRODUCER)).value
    with pytest.raises(VerificationError,
                       match="nothing in this kernel builds"):
        data_gap_rules._verify_t10_8_what_it_says(
            _report(kind, "the_dag_declares_no_latent_common_cause"))


def test_the_rule_declines_a_species_this_build_cannot_name():
    """An unrecognised kind belongs to T10-3, and a rule refusing for a
    reason another authority owns reports that authority's coverage as its
    own."""
    data_gap_rules._verify_t10_8_what_it_says(
        _report("a_species_from_some_other_build",
                "the_dag_declares_no_latent_common_cause"))


def test_the_rule_declines_a_statement_this_build_cannot_name():
    """An unrecognised statement belongs to the contract, which enumerates
    them, and ``verify`` validates against it before any rule runs."""
    data_gap_rules._verify_t10_8_what_it_says(
        _report("unmeasured_confounder_risk", "it_all_went_wrong_somehow"))


# ------------------------------------------ the reader's door, and the gap


def _carrier(kind: str):
    """An accepted answer describing itself, and where it sits."""
    for name in sorted(SHAPES):
        row = SHAPES[name]
        try:
            for one in _results(row["result"]):
                _door(one)(row["program"], one)
        except Exception:                                      # noqa: BLE001
            continue
        for index, result in enumerate(_results(row["result"])):
            report = result.get("data_gap_report")
            if not isinstance(report, dict):
                continue
            for position, gap in enumerate(report.get("gaps") or []):
                if gap.get("kind") == kind and gap.get("describes"):
                    return name, index, position
    raise AssertionError(f"no accepted answer in the corpus is a {kind}")


def _swapped(row, index, position, candidate):
    envelope = copy.deepcopy(_results(row["result"])[index])
    envelope["data_gap_report"]["gaps"][position]["describes"][0][
        "sentence"] = candidate
    return envelope


def test_what_a_gap_says_cannot_be_swapped_for_another_species_statement():
    """The measurement the gate exists for, at the door a reader uses."""
    name, index, position = _carrier("unmeasured_confounder_risk")
    row = SHAPES[name]
    honest = _results(row["result"])[index]["data_gap_report"]["gaps"][
        position]["describes"][0]["sentence"]
    assert honest == "the_dag_declares_no_latent_common_cause"

    through = []
    for candidate in ALL_SENTENCES:
        if candidate == honest:
            continue
        try:
            _door(_swapped(row, index, position, candidate))(
                row["program"], _swapped(row, index, position, candidate))
        except Exception:                                      # noqa: BLE001
            continue
        through.append(candidate)
    assert through == []


def test_without_the_rule_the_same_swap_goes_through(monkeypatch):
    """What the gate is worth, measured rather than asserted. The
    statements that get past without it are not near-misses: 'a joint
    intervention does not transport' on a gap about unmeasured confounding
    describes a dispatch that never happened."""
    name, index, position = _carrier("unmeasured_confounder_risk")
    row = SHAPES[name]
    monkeypatch.setattr(
        data_gap_rules, "_verify_t10_8_what_it_says", lambda report: None)
    through = []
    for candidate in ALL_SENTENCES:
        envelope = _swapped(row, index, position, candidate)
        try:
            _door(envelope)(row["program"], envelope)
        except Exception:                                      # noqa: BLE001
            continue
        through.append(candidate)
    assert len(through) == 22
    assert "a_joint_intervention_does_not_transport" in through


# ---------------------------------------------------------- what it is not


def test_two_statements_of_one_species_are_still_interchangeable():
    """Said out loud, because a ceiling nobody states gets read as a
    floor. Deciding between them means saying which the occasion makes,
    and that is the renderer's branches copied into a table."""
    kind = GapKind.WEAK_IV_INSTRUMENT
    both = {Sentence.THE_FIRST_STAGE_IS_WEAK,
            Sentence.THE_SET_CONSTRAINS_NOTHING}
    assert both <= gaps.SENTENCES_OF[kind]
    for said in both:
        data_gap_rules._verify_t10_8_what_it_says(
            _report(kind.value, str(said)))
