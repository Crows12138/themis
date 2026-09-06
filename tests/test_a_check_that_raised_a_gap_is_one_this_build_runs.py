"""A gap says a check raised it. Whether that check is one this build runs.

Every gap carries provenance, and for fourteen species that provenance is
a ``verifier_check`` ref: a check ran, and this is which one and what it
was about. The check's name and the subject were both f-string literals at
seventeen construction sites and declared nowhere, so an audit had no
second record to hold either half against and asked only that the string
was not empty. From the reader's side a question that cannot be asked and
a question that found nothing wrong are the same thing.

The name belongs to the species — measured before it moved, ten of the
fourteen use one name at every site, and the four that use two have a
reason their producer states in code. The subject belongs to the answer:
it is a variable the gap's own sentence already names, or a column the
estimator stood on. So the tests here come in two halves. One holds the
declaration and the producers to each other, read out of the producers by
AST rather than typed again. The other puts forged refs to the real door.

What this file does NOT assert is what ``program_site`` refs resolve to.
That range is declared in the rule and its reason is the door's shape, not
an omission here.
"""
from __future__ import annotations

import ast
import copy
import json
import pathlib

import pytest

import themis
from themis.types import (
    NO_SUBJECT,
    GapKind,
    RAISED_BY,
    RAISED_BY_TURNS_ON,
    raised_by,
    raised_by_ref,
)
from themis.verifier.data_gap_rules import _verify_t10_1_provenance
from themis.verifier.errors import VerificationError

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: The two modules that build these refs. Named rather than searched, so a
#: third producer is a deliberate edit here and not a silent omission.
PRODUCERS = (
    ROOT / "themis/output/data_gap_report.py",
    ROOT / "themis/estimation/dispatch.py",
)


# ------------------------------------------------ what the producers do


def _literal_head(node: ast.AST) -> str | None:
    """The check name a site writes, when it writes one."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _checks_written_by_producers() -> frozenset[str]:
    """Every check name that appears at a construction site.

    Read from the sites because that is the thing under test: a name the
    table declares and no site writes is a row nothing can reach, and a
    name a site writes and no table declares is the defect this block was.

    ``check`` is the one word a producer says a name under — passed to the
    constructor, or bound a line above where the branch that chooses the
    check is also choosing the sentence. Anything else spelling a check
    name is invisible here, which is what the accepting half of this file
    is for: an unreachable name is caught by the door, not by a scan.
    """
    found: set[str] = set()
    for path in PRODUCERS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            written: list[ast.AST] = []
            if isinstance(node, ast.Call):
                func = node.func
                name = (func.attr if isinstance(func, ast.Attribute)
                        else func.id if isinstance(func, ast.Name) else None)
                if name in ("raised_by_ref", "_verifier_check",
                            "_record_overlap_gap"):
                    written = [kw.value for kw in node.keywords
                               if kw.arg == "check"]
            elif isinstance(node, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == "check"
                       for t in node.targets):
                    written = [node.value]
            for value in written:
                for sub in ast.walk(value):
                    head = _literal_head(sub)
                    if head:
                        found.add(head)
    return frozenset(found)


def test_every_name_a_site_writes_is_one_the_contract_declares():
    """The direction that was the defect.

    A site that spells its own check name is a site whose reach nothing
    can hold, because the only record of what it meant is the site.
    """
    declared = set(RAISED_BY.values())
    for names, _why in RAISED_BY_TURNS_ON.values():
        declared |= set(names)
    stray = _checks_written_by_producers() - declared
    assert not stray, (
        "a producer names a check the contract does not declare: "
        f"{sorted(stray)}"
    )


def test_a_site_only_writes_a_name_where_the_species_has_a_choice():
    """Ten of the fourteen say nothing, which is the point of moving it.

    Where a species has one check, the site passing it again would be the
    old arrangement wearing the new call.
    """
    single = set(RAISED_BY.values())
    branching: set[str] = set()
    for names, _why in RAISED_BY_TURNS_ON.values():
        branching |= set(names)
    written = _checks_written_by_producers()
    assert not (written & single), (
        "a site writes a name its species already declares alone: "
        f"{sorted(written & single)}"
    )
    assert written <= branching


def test_every_declared_check_is_one_some_site_can_write():
    """And the other direction: a row nothing reaches is a row that lies.

    Single-name species reach theirs through the table, so what has to be
    reachable at a site is exactly the branching names.
    """
    branching: set[str] = set()
    for names, _why in RAISED_BY_TURNS_ON.values():
        branching |= set(names)
    assert branching == _checks_written_by_producers()


def test_a_species_has_one_check_or_a_reason_it_has_two():
    """The table's own shape, held rather than trusted."""
    assert not (RAISED_BY.keys() & RAISED_BY_TURNS_ON.keys())
    for kind, (names, why) in RAISED_BY_TURNS_ON.items():
        assert len(names) >= 2, kind
        assert why.strip(), f"{kind} names two checks and no reason"
        assert all(name for name in names)
    for kind, name in RAISED_BY.items():
        assert name, kind
        assert raised_by(kind) == frozenset({name})


def test_the_two_rules_agree_on_who_may_cite_a_check():
    """T10-3 says which ref kinds a species may cite; T10-1 says whether
    the check named is one that species has. A species in one and not the
    other is a promise the sibling rule refuses on sight.

    Found by this direction: two entries listed ``verifier_check`` while
    declaring no check, and they were the only two in that table with no
    reason written beside them — the signature of a row widened to let
    something through rather than because a producer emits it.
    """
    from themis.verifier.data_gap_rules import _KIND_ACCEPTS_REF
    may_cite = {kind for kind, kinds in _KIND_ACCEPTS_REF.items()
                if "verifier_check" in kinds}
    declares = {kind.value for kind in RAISED_BY}
    declares |= {kind.value for kind in RAISED_BY_TURNS_ON}
    assert may_cite == declares, {
        "T10-3 allows a check for a species that declares none":
            sorted(may_cite - declares),
        "a species declares a check T10-3 would refuse":
            sorted(declares - may_cite),
    }


def test_no_producer_builds_one_of_these_refs_by_hand():
    """The declaration binds only if it is the sole way through.

    ``raised_by_ref`` refuses a species with no row, an invented name and
    a silent branch — and all three of those refusals are reachable around
    if a site can write the dataclass itself. Two of the four sites in
    ``data_gap_report`` did exactly that before this block.
    """
    by_hand = []
    for path in PRODUCERS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (func.attr if isinstance(func, ast.Attribute)
                    else func.id if isinstance(func, ast.Name) else None)
            if name != "GapProvenanceRef":
                continue
            for keyword in node.keywords:
                if keyword.arg != "ref_kind":
                    continue
                if (isinstance(keyword.value, ast.Attribute)
                        and keyword.value.attr == "VERIFIER_CHECK"):
                    by_hand.append(f"{path.name}:{node.lineno}")
    assert not by_hand, (
        "a producer spells a verifier_check ref itself instead of asking "
        f"raised_by_ref for one: {by_hand}"
    )


def test_a_species_that_declares_nothing_gets_nothing():
    """Totality without partitioning the enum.

    Being raised by a named check is a property of how a species is found,
    so most kinds have no row — and the empty set has to read as a refusal
    everywhere, not as permission.
    """
    assert raised_by(GapKind.MISSING_DISTRIBUTION) == frozenset()
    with pytest.raises(ValueError, match="declares none"):
        raised_by_ref(GapKind.MISSING_DISTRIBUTION, "x")


def test_a_site_cannot_invent_a_name_for_a_species_that_has_one():
    with pytest.raises(ValueError, match="not one it declares"):
        raised_by_ref(GapKind.OVERIDENTIFICATION_REJECTED, "x",
                      check="whatever")


def test_a_species_with_a_choice_has_to_make_it():
    """Silence would pick one, and which one would be an accident.

    The refusal hands back the declaration's own sentence, so an author
    reads why this species is different rather than only that it is —
    which is also the sentence's only reader, and a table value nothing
    reads is one nothing keeps honest.
    """
    _names, why = RAISED_BY_TURNS_ON[GapKind.WEAK_IV_INSTRUMENT]
    with pytest.raises(ValueError, match="did not say which") as excinfo:
        raised_by_ref(GapKind.WEAK_IV_INSTRUMENT, "x")
    assert why in str(excinfo.value)


def test_the_spelling_is_the_check_then_what_it_was_about():
    """The one place the two halves are joined."""
    (bare,) = raised_by_ref(GapKind.OVERIDENTIFICATION_REJECTED)
    assert bare.ref_id == "overid"
    (with_subject,) = raised_by_ref(
        GapKind.OVERIDENTIFICATION_REJECTED, "x")
    assert with_subject.ref_id == "overid:x"


# ------------------------------------------------ what the door refuses


def _verifier_check_sites() -> list[tuple[str, int, int, str, str]]:
    """(row, gap index, ref index, species, ref_id) for every recorded one."""
    out = []
    for name in sorted(SHAPES):
        result = SHAPES[name]["result"] or {}
        gaps = (result.get("data_gap_report") or {}).get("gaps") or []
        for gap_index, gap in enumerate(gaps):
            for ref_index, ref in enumerate(gap.get("provenance") or []):
                if ref.get("ref_kind") == "verifier_check":
                    out.append((name, gap_index, ref_index,
                                gap.get("kind"), ref.get("ref_id") or ""))
    return out


SITES = _verifier_check_sites()
#: Below this the corpus stopped being a corpus and the rows below are a
#: sample of nothing. Not the count: a floor, so a harvest that collects
#: fewer rows fails here rather than passing on an empty sweep.
_FLOOR = 200


def test_the_corpus_still_carries_enough_of_these_to_mean_anything():
    assert len(SITES) >= _FLOOR, len(SITES)


def _refused(result) -> bool:
    try:
        themis.verify_data_gap_report(result)
    except VerificationError:
        return True
    return False


def _bend(row: str, gap_index: int, ref_index: int, ref_id: str) -> dict:
    bad = copy.deepcopy(SHAPES[row]["result"])
    bad["data_gap_report"]["gaps"][gap_index]["provenance"][ref_index][
        "ref_id"] = ref_id
    return bad


@pytest.mark.parametrize("row", sorted(SHAPES))
def test_the_honest_answer_is_accepted(row):
    """A false positive is worse than the hole it closes.

    Asked of every row rather than of the ones carrying one of these refs,
    because a rule that refuses an answer for some unrelated reason is the
    same failure and would otherwise be invisible here.
    """
    themis.verify_data_gap_report(SHAPES[row]["result"])


@pytest.mark.parametrize(
    "row,gap_index,ref_index,species,ref_id", SITES,
    ids=[f"{r}-{g}-{i}" for r, g, i, _s, _x in SITES])
def test_a_subject_this_gap_is_not_about_is_refused(
    row, gap_index, ref_index, species, ref_id,
):
    """The half the check name alone cannot reach.

    A suffix on the subject leaves the check name intact, which is exactly
    the edit a rule that stopped at the name would wave through.
    """
    assert _refused(_bend(row, gap_index, ref_index, ref_id + "_forged"))


@pytest.mark.parametrize(
    "row,gap_index,ref_index,species,ref_id", SITES,
    ids=[f"{r}-{g}-{i}" for r, g, i, _s, _x in SITES])
def test_a_check_another_species_owns_is_refused(
    row, gap_index, ref_index, species, ref_id,
):
    _check, _, subject = ref_id.partition(":")
    other = "no_effect_test" if _check != "no_effect_test" else "overid"
    forged = f"{other}:{subject}" if subject else other
    assert _refused(_bend(row, gap_index, ref_index, forged))


@pytest.mark.parametrize(
    "row,gap_index,ref_index,species,ref_id", SITES,
    ids=[f"{r}-{g}-{i}" for r, g, i, _s, _x in SITES])
def test_a_ref_that_names_no_check_is_refused(
    row, gap_index, ref_index, species, ref_id,
):
    assert _refused(_bend(row, gap_index, ref_index, ""))


def test_a_subject_cannot_be_checked_without_the_answer():
    """The rule says what it needs, and refuses rather than falls silent.

    Asked of the rule directly: a door has its own reasons to refuse, and
    a door test would pass whether or not this arm ever looked. The same
    posture the envelope-path arm takes, for the same reason.
    """
    report = {"gaps": [{
        "kind": GapKind.OVERIDENTIFICATION_REJECTED.value,
        "provenance": [{"ref_kind": "verifier_check", "ref_id": "overid:x"}],
    }]}
    with pytest.raises(VerificationError, match="no answer to look for it"):
        _verify_t10_1_provenance(
            report, derivation_steps=[], investigation_requests=[],
            framing_notes=[], envelope=None,
        )


def test_a_check_with_no_subject_needs_no_answer():
    """And the arm does not demand one it has no use for.

    The counterfactual branch names a check and nothing else, because what
    raised it was the shape of the query rather than any variable.
    """
    report = {"gaps": [{
        "kind": (GapKind.COUNTERFACTUAL_IDENTIFICATION_ASSUMPTION_REQUIRED
                 .value),
        "provenance": [{"ref_kind": "verifier_check",
                        "ref_id": "counterfactual_status"}],
    }]}
    _verify_t10_1_provenance(
        report, derivation_steps=[], investigation_requests=[],
        framing_notes=[], envelope=None,
    )


def test_a_species_the_contract_does_not_know_is_refused():
    """An unknown species name resolves to no checks, and no checks refuses.

    Reading it as "anything goes" is the arrangement this rule ended.
    """
    report = {"gaps": [{
        "kind": "a_species_that_does_not_exist",
        "provenance": [{"ref_kind": "verifier_check", "ref_id": "overid"}],
    }]}
    with pytest.raises(VerificationError, match="no check at all"):
        _verify_t10_1_provenance(
            report, derivation_steps=[], investigation_requests=[],
            framing_notes=[], envelope={},
        )


def test_a_column_the_answer_stood_on_counts_as_a_subject():
    """The second source, held so it cannot quietly go away.

    Some checks name an adjustment column that the gap's own sentence
    renders as prose rather than as a name, and dropping the estimation
    context from the pool would refuse nine honest refs in this corpus.
    """
    report = {"gaps": [{
        "kind": GapKind.OVERIDENTIFICATION_REJECTED.value,
        "provenance": [{"ref_kind": "verifier_check", "ref_id": "overid:z"}],
    }]}
    _verify_t10_1_provenance(
        report, derivation_steps=[], investigation_requests=[],
        framing_notes=[],
        envelope={"estimation_context": {"data_columns": ["z"]}},
    )
    with pytest.raises(VerificationError, match="not a name this gap"):
        _verify_t10_1_provenance(
            report, derivation_steps=[], investigation_requests=[],
            framing_notes=[],
            envelope={"estimation_context": {"data_columns": ["y"]}},
        )


def test_the_placeholder_for_no_columns_is_not_looked_up_as_one():
    """``<none>`` is what a check writes where a list came out empty.

    Declared once and read by both sides; treating it as a variable name
    would refuse an honest ref for saying there was nothing to name.
    """
    report = {"gaps": [{
        "kind": GapKind.OUTCOME_MODEL_QUASI_SEPARATION.value,
        "provenance": [{"ref_kind": "verifier_check",
                        "ref_id": f"outcome_separation:y|x:{NO_SUBJECT}"}],
    }]}
    _verify_t10_1_provenance(
        report, derivation_steps=[], investigation_requests=[],
        framing_notes=[],
        envelope={"estimation_context": {"data_columns": ["x", "y"]}},
    )
