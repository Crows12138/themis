"""``provenance[].ref_kind`` is held to the species that cites it.

A ref is checkable only because its kind says where to look, so the kind
a site writes beside an id is a claim about the species as much as about
the id. A declaration existed before #618 — the verifier's
``_KIND_ACCEPTS_REF`` — and two things were wrong with where it sat and
what was asked of it.

Where: in the verifier, so the producer could not read it. Twenty-three
sites typed a kind beside an id and nothing compared the two.

What: the rule asked whether a gap carried AT LEAST ONE ref of an
acceptable kind. On this corpus every gap carries exactly one, so that
question and "is its ref acceptable" have never given different answers
— and the moment a gap carries two, anything rides along beside one that
is acceptable. Measured before the change: 406 of 406 gaps accepted a
second ref naming a real derivation step their species may not cite, and
every public door said yes. The 4551 refusals that looked like this
rule's work were T10-1 finding an id would not resolve in the space its
kind named, which is a fact about the SPELLING of an id.
"""
import ast
import copy
import json
import pathlib
from collections import Counter

import pytest

import themis
from themis import types
from themis.types import (
    DataGap,
    GapKind,
    GapProvenanceRef,
    GapRefKind,
    RAISED_BY,
    RAISED_BY_TURNS_ON,
    REF_KINDS_OF,
    REF_KIND_TURNS_ON,
    _REF_KINDS_TYPED_AT_SITES,
    _bind_ref_kinds,
    cites,
    ref_kinds_of,
)
from themis.verifier import data_gap_rules
from themis.verifier.errors import VerificationError

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS = json.loads(
    (ROOT / "tests/fixtures/answer_shapes.json").read_text(encoding="utf-8"))


# ------------------------------------------------ the table, as bound


def test_every_species_says_where_its_evidence_lives():
    assert set(REF_KINDS_OF) == set(GapKind)
    assert len(REF_KINDS_OF) == 42
    assert all(REF_KINDS_OF.values()), "an empty row reads as a refusal"


def test_the_ceiling_is_one_space_for_most_species_and_two_at_most():
    """Declared, because an unstated ceiling gets read as a floor.

    Thirty-one species have exactly one space, so for those the ref kind
    is settled outright and two refs of that species are interchangeable
    only with each other. Eleven have two, and no species has three: the
    widest this leaves anything is a choice between a step and one
    fallback.
    """
    widths = Counter(len(row) for row in REF_KINDS_OF.values())
    assert dict(sorted(widths.items())) == {1: 31, 2: 11}


def test_a_species_with_a_choice_is_the_species_that_owes_a_sentence():
    choosing = {kind for kind, row in REF_KINDS_OF.items() if len(row) > 1}
    assert choosing == set(REF_KIND_TURNS_ON)
    assert len(REF_KIND_TURNS_ON) == 11
    assert all(REF_KIND_TURNS_ON.values())


def test_one_question_stands_behind_every_sentence():
    """Nine of the eleven share a sentence because they share a reason.

    Whether the identification attempt had recorded a step by the time
    the gap was filed. The other two ask it too and fall back elsewhere —
    to the program shape, and to the check that classified the query.
    """
    assert len(set(REF_KIND_TURNS_ON.values())) == 3
    assert Counter(REF_KIND_TURNS_ON.values()).most_common(1)[0][1] == 9


# ------------------------------------------------ the fold


def test_who_may_cite_a_check_is_not_written_here_at_all():
    """It is RAISED_BY's, and a second copy is free to drift from it."""
    for row in _REF_KINDS_TYPED_AT_SITES.values():
        assert GapRefKind.VERIFIER_CHECK not in row


def test_the_fold_puts_it_back_exactly_where_it_belongs():
    cite_a_check = {kind for kind, row in REF_KINDS_OF.items()
                    if GapRefKind.VERIFIER_CHECK in row}
    assert cite_a_check == set(RAISED_BY) | set(RAISED_BY_TURNS_ON)
    assert len(cite_a_check) == 14


def test_thirteen_species_have_no_typed_row_because_they_cite_only_a_check():
    absent = set(GapKind) - set(_REF_KINDS_TYPED_AT_SITES)
    assert len(absent) == 13
    assert all(REF_KINDS_OF[kind] == frozenset({GapRefKind.VERIFIER_CHECK})
               for kind in absent)
    assert len(_REF_KINDS_TYPED_AT_SITES) == 29


def test_a_row_that_states_the_check_itself_is_refused_at_import():
    typed = dict(_REF_KINDS_TYPED_AT_SITES)
    typed[GapKind.WEAK_IV_INSTRUMENT] = frozenset(
        {GapRefKind.VERIFIER_CHECK})
    with pytest.raises(ValueError, match="already settle"):
        _bind_ref_kinds(typed)


# ------------------------------------------------ the other import gates


def test_a_species_with_no_row_anywhere_is_refused():
    typed = dict(_REF_KINDS_TYPED_AT_SITES)
    del typed[GapKind.AMBIGUOUS_VARIABLE_DEFINITION]
    with pytest.raises(ValueError, match="has to point somewhere"):
        _bind_ref_kinds(typed)


def test_an_empty_row_is_refused():
    typed = dict(_REF_KINDS_TYPED_AT_SITES)
    typed[GapKind.AMBIGUOUS_VARIABLE_DEFINITION] = frozenset()
    with pytest.raises(ValueError, match="empty row"):
        _bind_ref_kinds(typed)


def test_a_space_no_species_cites_is_refused():
    """The direction that is easy to leave out.

    A member nothing can point at is a word in the vocabulary that no
    envelope can legally carry, and T10-1 would keep an arm alive for it
    for as long as nobody counted.
    """
    typed = dict(_REF_KINDS_TYPED_AT_SITES)
    typed[GapKind.AMBIGUOUS_VARIABLE_DEFINITION] = frozenset(
        {GapRefKind.ENVELOPE_PATH})
    with pytest.raises(ValueError, match="no species cites"):
        _bind_ref_kinds(typed)


def test_a_choice_with_no_sentence_and_a_sentence_with_no_choice():
    """Both sides of the partition, because one side alone rots."""
    typed = dict(_REF_KINDS_TYPED_AT_SITES)
    typed[GapKind.AMBIGUOUS_VARIABLE_DEFINITION] = frozenset(
        {GapRefKind.FRAMING_NOTE, GapRefKind.PROGRAM_SITE})
    with pytest.raises(ValueError, match="have a choice and no sentence"):
        _bind_ref_kinds(typed)

    typed = dict(_REF_KINDS_TYPED_AT_SITES)
    typed[GapKind.MISSING_DISTRIBUTION] = frozenset(
        {GapRefKind.INVESTIGATION_REQUEST})
    with pytest.raises(ValueError, match="have a sentence and no choice"):
        _bind_ref_kinds(typed)


# ------------------------------------------------ the producer's door


def test_a_site_that_cannot_choose_does_not_have_to():
    (ref,) = cites(GapKind.LOW_CONFIDENCE_INPUT_DATA, "confidence")
    assert ref.ref_kind is GapRefKind.ENVELOPE_PATH
    assert ref.ref_id == "confidence"


def test_a_site_with_a_choice_has_to_make_it_and_is_told_what_it_turns_on():
    with pytest.raises(ValueError, match="did not say which"):
        cites(GapKind.MISSING_DISTRIBUTION, "parameter:P(y)")
    with pytest.raises(ValueError, match="recorded a step"):
        cites(GapKind.MISSING_DISTRIBUTION, "parameter:P(y)")


def test_a_site_cannot_cite_a_space_its_species_does_not_declare():
    with pytest.raises(ValueError, match="not a space it declares"):
        cites(GapKind.AMBIGUOUS_VARIABLE_DEFINITION, "s1",
              ref_kind=GapRefKind.DERIVATION_STEP)


def test_a_check_ref_is_refused_here_however_it_arrives():
    """Asked for by name, and filled in by the fold.

    Both on a species that does declare a check, because that is the one
    this guard is for. A species that declares none is refused by the
    declaration instead — a narrower reason, and the right one.
    """
    with pytest.raises(ValueError, match="raised_by_ref is the one way"):
        cites(GapKind.WEAK_IV_INSTRUMENT, "c",
              ref_kind=GapRefKind.VERIFIER_CHECK)
    with pytest.raises(ValueError, match="raised_by_ref is the one way"):
        cites(GapKind.WEAK_IV_INSTRUMENT, "c")
    with pytest.raises(ValueError, match="not a space it declares"):
        cites(GapKind.AMBIGUOUS_VARIABLE_DEFINITION, "c",
              ref_kind=GapRefKind.VERIFIER_CHECK)


def test_citing_nothing_is_refused_where_it_happens():
    with pytest.raises(ValueError, match="cited nothing"):
        cites(GapKind.LOW_CONFIDENCE_INPUT_DATA)


def test_several_ids_give_several_refs():
    refs = cites(GapKind.MEASUREMENT_ERROR_CONCERN, "program:a", "program:b")
    assert [ref.ref_id for ref in refs] == ["program:a", "program:b"]
    assert {ref.ref_kind for ref in refs} == {GapRefKind.PROGRAM_SITE}


# ------------------------------------------------ the gap refuses it too


def _gap(kind, refs):
    return DataGap(
        kind=kind,
        describes=(),
        provenance=tuple(refs),
    )


def test_a_gap_may_carry_the_space_its_species_declares():
    gap = _gap(GapKind.AMBIGUOUS_VARIABLE_DEFINITION,
               cites(GapKind.AMBIGUOUS_VARIABLE_DEFINITION, "pred"))
    assert gap.provenance[0].ref_kind is GapRefKind.FRAMING_NOTE


def test_a_gap_may_not_carry_a_space_its_species_does_not():
    with pytest.raises(ValueError, match="does not declare as a space"):
        _gap(GapKind.AMBIGUOUS_VARIABLE_DEFINITION,
             (GapProvenanceRef(ref_kind=GapRefKind.DERIVATION_STEP,
                               ref_id="s1"),))


def test_a_gap_outside_the_vocabulary_is_left_to_the_door_that_owns_it():
    """Silent, not lenient.

    Which species exist is the contract's question, answered where they
    are serialised. A check refusing for a reason another authority owns
    reports that authority's coverage as its own.
    """
    with pytest.raises(AttributeError):
        _gap("not_a_species_at_all",
             (GapProvenanceRef(ref_kind=GapRefKind.DERIVATION_STEP,
                               ref_id="s1"),))


# ------------------------------------------------ the rule


def _report(kind, *ref_kinds):
    return {"gaps": [{"kind": kind.value, "provenance": [
        {"ref_kind": str(one), "ref_id": "whatever"} for one in ref_kinds]}]}


def test_the_rule_takes_exactly_what_the_species_declares():
    accepted, refused, wrong = 0, 0, []
    for kind in GapKind:
        for member in GapRefKind:
            try:
                data_gap_rules._verify_t10_3_kind_consistency(
                    _report(kind, member), derivation_steps=[])
            except VerificationError:
                refused += 1
                continue
            accepted += 1
            if member not in REF_KINDS_OF[kind]:
                wrong.append((kind.value, str(member)))
    assert not wrong
    assert (refused, accepted) == (201, 51)


def test_a_foreign_ref_beside_an_honest_one_is_the_case_nobody_asked():
    """199 pairs, all of which used to go through.

    The old question was whether SOME ref was acceptable, and an honest
    ref answers it whatever stands next to it.
    """
    pairs = through = old_question_let_past = 0
    for kind, allowed in REF_KINDS_OF.items():
        honest = sorted(allowed, key=str)[0]
        for member in GapRefKind:
            if member in allowed:
                continue
            pairs += 1
            if {honest, member} & allowed:
                old_question_let_past += 1
            try:
                data_gap_rules._verify_t10_3_kind_consistency(
                    _report(kind, honest, member), derivation_steps=[])
            except VerificationError:
                continue
            through += 1
    assert (pairs, old_question_let_past, through) == (199, 199, 0)


def test_a_gap_still_has_to_cite_something():
    with pytest.raises(VerificationError, match="at least one"):
        data_gap_rules._verify_t10_3_kind_consistency(
            _report(GapKind.LOW_CONFIDENCE_INPUT_DATA), derivation_steps=[])


# ------------------------------------------------ the corpus, honestly


def _gaps_in(envelope):
    report = envelope.get("data_gap_report")
    if isinstance(report, dict):
        yield from report.get("gaps") or []


def test_no_answer_this_build_produces_cites_a_space_it_may_not():
    slots, species, stray = 0, set(), []
    for name in sorted(CORPUS):
        result = CORPUS[name]["result"]
        for one in (result.get("results") or [result]):
            for gap in _gaps_in(one):
                species.add(gap.get("kind"))
                allowed = {str(m) for m in ref_kinds_of(gap.get("kind"))}
                for ref in gap.get("provenance") or []:
                    slots += 1
                    if ref.get("ref_kind") not in allowed:
                        stray.append((name, gap.get("kind"),
                                      ref.get("ref_kind")))
    assert not stray
    assert (slots, len(species)) == (1038, 38)


def test_every_gap_in_the_corpus_carries_exactly_one_ref():
    """Which is why the missing direction stayed invisible for so long.

    Pinned so that the first producer to file a gap over two signals
    lands here, where the reason is written down, rather than nowhere.
    """
    widths = Counter(len(gap.get("provenance") or [])
                     for name in CORPUS
                     for one in (CORPUS[name]["result"].get("results")
                                 or [CORPUS[name]["result"]])
                     for gap in _gaps_in(one))
    assert dict(widths) == {1: 1038}


def _door(envelope):
    return (themis.verify if envelope.get("derivation") is not None
            else themis.verify_answer_claims)


def _an_accepted_row():
    for name in sorted(CORPUS):
        row = CORPUS[name]
        envelopes = row["result"].get("results") or [row["result"]]
        try:
            for one in envelopes:
                _door(one)(row["program"], one)
        except Exception:                                      # noqa: BLE001
            continue
        for index, one in enumerate(envelopes):
            for pos, gap in enumerate(_gaps_in(one)):
                if gap.get("provenance"):
                    return row, index, pos
    raise AssertionError("no accepted row carries a gap with provenance")


def test_the_public_door_refuses_the_second_ref_it_used_to_take():
    """End to end, on an answer this build produced and a door accepts."""
    row, index, pos = _an_accepted_row()
    envelopes = row["result"].get("results") or [row["result"]]
    kind = envelopes[index]["data_gap_report"]["gaps"][pos]["kind"]
    foreign = sorted(set(GapRefKind) - ref_kinds_of(kind), key=str)[0]

    env = copy.deepcopy(envelopes[index])
    env["data_gap_report"]["gaps"][pos]["provenance"].append(
        {"ref_kind": str(foreign), "ref_id": "s1"})
    with pytest.raises(VerificationError, match="T10-3"):
        _door(env)(row["program"], env)


# ------------------------------------------------ nothing goes round it


def test_only_one_place_still_builds_one_of_these_by_hand():
    """The declaration binds only if it is the sole way through.

    ``cites`` refuses a space the species does not declare, an empty
    call and a check — and all three are reachable around if a site can
    write the dataclass itself, which twenty-three of them did. The
    deserialiser keeps the raw constructor because it is reading a ref
    back rather than authoring one, and a check ref has to survive that
    round trip.
    """
    by_hand = []
    for path in sorted((ROOT / "themis").rglob("*.py")):
        if path.name == "types.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (func.attr if isinstance(func, ast.Attribute)
                    else func.id if isinstance(func, ast.Name) else None)
            if name == "GapProvenanceRef":
                rel = path.relative_to(ROOT).as_posix()
                by_hand.append(f"{rel}:{node.lineno}")
    assert len(by_hand) == 1, by_hand
    assert by_hand[0].startswith("themis/output/data_gap_report.py")


def test_the_verifier_reads_the_declaration_rather_than_restating_it():
    source = (ROOT / "themis/verifier/data_gap_rules.py").read_text(
        encoding="utf-8")
    assert "_KIND_ACCEPTS_REF" not in source
    assert "REF_KINDS_OF" in source


def test_the_declaration_is_not_the_producer_read_back():
    """The kernel owns it, and the producer may not be its author.

    Read off the sites, not off the corpus — the corpus reaches 38 of 42
    species, so a table harvested from answers would refuse four species
    wherever they are written.
    """
    assert types.__name__ == "themis.types"
    assert set(REF_KINDS_OF) == set(GapKind)
    reached = {gap.get("kind") for name in CORPUS
               for one in (CORPUS[name]["result"].get("results")
                           or [CORPUS[name]["result"]])
               for gap in _gaps_in(one)}
    assert len(set(GapKind) - {GapKind(k) for k in reached}) == 4
