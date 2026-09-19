"""The heading a shortfall is filed under belongs to its species.

A ``missing_information`` row's ``name`` is two halves — the channel that
repairs the shortfall, and what in particular is short — and it is not a
label. The envelope indexes rows by it, and an ask resolves its target
against it, silently: a name that moves takes its row out of reach of the
list a reader is handed, and switches off the checks on the ask pointing
at it without anything saying so.

Thirty-seven sites spelled one. The consequences were all three of the
ones a free field buys. ``ATOM_NOT_IN_GRAPH`` was filed under ``atom`` at
six of them and under ``longitudinal`` at a seventh, and no stored answer
could show it because the seventh is the only one a stored answer reaches.
Three sites in the longitudinal block wrote the species' own token into
the subject, which the ``need`` field beside the name already carries. And
nothing anywhere said what a name had to be, so twenty-six of these leaves
stood in the declared remainder: bend one to a stranger, to the empty
string or to itself with a suffix, and every public door accepted it.

What replaces the spelling is a declaration beside the species —
:data:`themis.gaps.FILED_WHOLE`, :data:`~themis.gaps.FILED_UNDER`,
:data:`~themis.gaps.FILED_ABOUT` and :data:`~themis.gaps.FILES_NO_ROW` —
saying which half of the name the species settles and which the occasion
does. ``gaps.missing`` builds the name from that, so a site hands over the
half it owns and cannot hand over the other. The return door recomputes
the channel the same way and asks the rest of the envelope for the
subject, which is where this file starts.
"""
from __future__ import annotations

import ast
import collections
import copy
import json
import pathlib

import pytest

import themis
from themis import gaps
from themis.input.syntactic_validator import SyntacticError
from themis.runtime import scheduler
from themis.verifier.errors import VerificationError
from themis.verifier.investigation_rules import verify_investigation_items

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json").read_text("utf-8"))
UNWITNESSED = json.loads(
    (ROOT / "tests" / "fixtures" / "unwitnessed_leaves.json").read_text("utf-8"))

#: Every stored row, as ``(answer, index, need, name)``. The roster is read
#: off the corpus rather than off the declaration this frontier empties:
#: keyed on the file it empties, it would parametrize nothing and a suite
#: reporting no tests reports green.
CARRYING = [
    (name, i, str(row.get("need")), str(row.get("name")))
    for name, pair in sorted(SHAPES.items())
    for i, row in enumerate(pair["result"].get("missing_information") or ())
    if isinstance(row, dict)
]

#: The answers whose rows this file bends. One per row species is what the
#: gate asks; every row is what a corpus fact is asked of.
BENDING = sorted({name for name, _, _, _ in CARRYING})


# --------------------------------------------------------- the declaration

def test_every_species_says_where_its_rows_are_filed():
    """Exactly one of the four, for all of them.

    The binder runs at import, so this is what it already proved; it is
    restated here because a binder that stopped being called would leave
    nothing behind that said so.
    """
    tables = (gaps.FILED_WHOLE, gaps.FILED_UNDER,
              gaps.FILED_ABOUT, gaps.FILES_NO_ROW)
    placed = collections.Counter(
        sum(need in table for table in tables) for need in gaps.Need)
    assert placed == {1: len(list(gaps.Need))}, dict(placed)


def test_a_species_on_no_table_is_refused():
    """And the binder is what refuses it, rather than a reader noticing."""
    victim = next(iter(gaps.FILED_WHOLE))
    kept = gaps.FILED_WHOLE.pop(victim)
    try:
        with pytest.raises(ValueError, match="no filing declared"):
            gaps._bind_filings()
    finally:
        gaps.FILED_WHOLE[victim] = kept
    gaps._bind_filings()


def test_a_species_on_two_tables_is_refused():
    victim = next(iter(gaps.FILED_UNDER))
    gaps.FILED_ABOUT[victim] = "somewhere"
    try:
        with pytest.raises(ValueError, match="two ways"):
            gaps._bind_filings()
    finally:
        del gaps.FILED_ABOUT[victim]
    gaps._bind_filings()


def test_a_whole_name_is_a_channel_and_a_subject():
    """Both halves, because the reader's index is split on that colon."""
    for need, whole in gaps.FILED_WHOLE.items():
        head, colon, subject = whole.partition(":")
        assert head and colon and subject, (need, whole)


def test_a_half_the_site_completes_carries_no_separator():
    """A half with a colon in it would decide where the split falls."""
    for table in (gaps.FILED_UNDER, gaps.FILED_ABOUT):
        for need, half in table.items():
            assert half and ":" not in half, (need, half)


def test_a_species_that_files_no_row_says_why():
    for need, why in gaps.FILES_NO_ROW.items():
        assert why and why.strip(), need


# ------------------------------------------------------------- the door

def test_the_door_settles_the_half_the_species_owns():
    """A site that names it is refused rather than obeyed: two authors for
    one field is the state this declaration replaces."""
    whole = next(iter(gaps.FILED_WHOLE))
    with pytest.raises(ValueError, match="settles its own"):
        gaps.filed(whole, subject="anything")
    under = next(iter(gaps.FILED_UNDER))
    with pytest.raises(ValueError, match="settles its own channel"):
        gaps.filed(under, channel="elsewhere", subject="x")
    about = next(iter(gaps.FILED_ABOUT))
    with pytest.raises(ValueError, match="settles its own subject"):
        gaps.filed(about, channel="mediation", subject="x")


def test_the_door_requires_the_half_it_leaves():
    under = next(iter(gaps.FILED_UNDER))
    for nothing in (None, ""):
        with pytest.raises(ValueError, match="named by the site"):
            gaps.filed(under, subject=nothing)
    about = next(iter(gaps.FILED_ABOUT))
    for nothing in (None, ""):
        with pytest.raises(ValueError, match="named by the site"):
            gaps.filed(about, channel=nothing)


def test_a_species_that_files_no_row_cannot_be_filed():
    need = next(iter(gaps.FILES_NO_ROW))
    with pytest.raises(ValueError, match="files no missing_information row"):
        gaps.filed(need)


def test_a_stray_name_does_not_ride_in_as_a_fact():
    """``name`` was the keyword this door took, and a caller that kept
    passing it would have had it flattened onto the envelope as a rendered
    fact rather than refused."""
    with pytest.raises(ValueError, match="was passed name="):
        gaps.missing(
            kind=gaps.MissingKind.STRUCTURE,
            need=gaps.Need.NO_BACKDOOR_OR_FRONTDOOR,
            name="identification:not_identifiable",
        )


# -------------------------------------------------------------- the sites

def _calls(path: pathlib.Path, label: str):
    tree = ast.parse(path.read_text("utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        called = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        if called == label:
            yield node


def test_no_site_spells_the_name_it_files_under():
    """The measurement that made this frontier, kept as the rule.

    Read off the product tree rather than the corpus: six of the seven
    sites raising one species are reached by no stored answer, so the
    corpus could not have shown the channel drifting between them.
    """
    spelling = [
        f"{path.relative_to(ROOT).as_posix()}:{node.lineno}"
        for path in sorted((ROOT / "themis").rglob("*.py"))
        for node in _calls(path, "missing")
        if any(kw.arg == "name" for kw in node.keywords)
    ]
    assert spelling == [], spelling


def test_the_escape_a_second_reader_compares_against_is_the_species_own():
    """One name, read from the table by both the site that raises the row
    and the pass that later appends to it."""
    assert scheduler.CAUSATION_RISK_ESCAPE == gaps.filed(
        gaps.Need.INTERVENTIONAL_RISK_NOT_IDENTIFIABLE)
    assert scheduler.CAUSATION_RISK_ESCAPE == gaps.filed(
        gaps.Need.INTERVENTIONAL_RISK_NEEDS_DISTRIBUTIONS)


# ------------------------------------------------------------- the corpus

@pytest.mark.parametrize("answer,index,need,name", CARRYING,
                         ids=[f"{a}[{i}]" for a, i, _, _ in CARRYING])
def test_a_stored_row_is_filed_where_its_species_says(answer, index, need, name):
    species = gaps.BY_NAME[need]
    head, _, subject = name.partition(":")
    if species in gaps.FILED_WHOLE:
        assert name == gaps.FILED_WHOLE[species]
    elif species in gaps.FILED_UNDER:
        assert head == gaps.FILED_UNDER[species] and subject
    else:
        assert subject == gaps.FILED_ABOUT[species] and head


@pytest.mark.parametrize("answer,index,need,name", CARRYING,
                         ids=[f"{a}[{i}]" for a, i, _, _ in CARRYING])
def test_a_stored_row_does_not_repeat_its_species_in_its_subject(
    answer, index, need, name,
):
    """The field beside the name carries the species, and a second copy is
    a second thing to keep in agreement. Three sites wrote one."""
    subject = name.partition(":")[2]
    assert not subject.startswith(f"{need}:"), name


@pytest.mark.parametrize("answer", BENDING)
def test_every_stored_row_is_named_by_an_ask(answer):
    """The invariant the return door leans on for the half it cannot
    recompute. The pusher builds an ask from every row and carries the name
    over as its target; the framing channel writes its own and puts the
    subject there without the channel."""
    result = SHAPES[answer]["result"]
    asked = {
        item.get("target")
        for request in result.get("investigation_requests") or ()
        for item in request.get("items") or ()
    }
    for row in result.get("missing_information") or ():
        name = str(row.get("name"))
        assert name in asked or name.partition(":")[2] in asked, (answer, name)


# ------------------------------------------------------------- the bends

#: A suffix, and a name of the right shape whose channel belongs to a
#: different species. The second is the lie the declaration exists to
#: refuse, and the one a check shaped like the corpus would have missed.
BENDS = ("forged", "channel")


@pytest.mark.parametrize("answer", BENDING)
@pytest.mark.parametrize("bend", BENDS)
def test_a_name_that_is_not_the_one_its_species_files_under_is_refused(
    answer, bend,
):
    pair = SHAPES[answer]
    bad = copy.deepcopy(pair["result"])
    rows = bad.get("missing_information") or []
    was = str(rows[0].get("name"))
    if bend == "forged":
        rows[0]["name"] = f"{was}_forged"
    else:
        other = next(
            value for need, value in gaps.FILED_WHOLE.items()
            if value.partition(":")[0] != was.partition(":")[0]
        )
        rows[0]["name"] = f"{other.partition(':')[0]}:{was.partition(':')[2]}"
    with pytest.raises(VerificationError):
        themis.verify_answer_claims(
            copy.deepcopy(pair["program"]), bad)


@pytest.mark.parametrize("answer", BENDING)
def test_an_empty_name_is_the_contracts_refusal_not_this_rules(answer):
    """The division of labour, stated where it can be read.

    The contract says a name is non-empty, so an emptied one never reaches
    a rule: the door validates before it reads. Both refuse it and only
    one of them gets to. Writing that down is what stops this file from
    claiming a rule holds something the schema was already holding.
    """
    pair = SHAPES[answer]
    bad = copy.deepcopy(pair["result"])
    (bad.get("missing_information") or [])[0]["name"] = ""
    with pytest.raises(SyntacticError, match="should be non-empty"):
        themis.verify_answer_claims(copy.deepcopy(pair["program"]), bad)


# ---------------------------------------- the four tables, one at a time

def _one_row(need, name, target=None):
    """The smallest envelope this rule reads: one row, one ask naming it.

    Built rather than borrowed, because a corpus row carries the facts its
    own sentence needs and several rules read those first — a bend made on
    one is refused, but not always here, and a test that cannot say which
    rule refused is not a test of this one.
    """
    target = name if target is None else target
    return {
        "missing_information": [
            {"kind": "structure", "name": name, "priority": "high",
             "gap": "unidentifiable_no_admissible_set", "need": str(need)},
        ],
        "investigation_requests": [
            {"action": "run_experiment", "target": target, "priority": "high",
             "group": "structure", "items": [{"target": target}]},
        ],
    }


def test_a_row_of_a_species_that_files_none_is_refused():
    """The fourth table is not decoration: a row wearing that species is a
    shortfall raised where the declaration says none is raised."""
    need = next(iter(gaps.FILES_NO_ROW))
    with pytest.raises(VerificationError, match="files none"):
        verify_investigation_items(_one_row(need, "anywhere:at_all"), {})


def test_a_whole_filed_row_under_another_name_is_refused():
    need, whole = next(iter(gaps.FILED_WHOLE.items()))
    verify_investigation_items(_one_row(need, whole), {})
    with pytest.raises(VerificationError, match="filed whole under"):
        verify_investigation_items(_one_row(need, f"{whole}_elsewhere"), {})


def test_a_row_under_a_channel_its_species_does_not_use_is_refused():
    need, channel = next(iter(gaps.FILED_UNDER.items()))
    verify_investigation_items(_one_row(need, f"{channel}:thing"), {})
    with pytest.raises(VerificationError, match="repaired through"):
        verify_investigation_items(_one_row(need, "elsewhere:thing"), {})
    with pytest.raises(VerificationError, match="repaired through"):
        verify_investigation_items(_one_row(need, f"{channel}:"), {})


def test_a_row_about_something_its_species_cannot_be_about_is_refused():
    need, about = next(iter(gaps.FILED_ABOUT.items()))
    verify_investigation_items(_one_row(need, f"mediation:{about}"), {})
    with pytest.raises(VerificationError, match="the species' own"):
        verify_investigation_items(_one_row(need, "mediation:something"), {})


def test_a_row_no_ask_names_is_refused():
    """The half no declaration can hold, held by the ask it became."""
    need, whole = next(iter(gaps.FILED_WHOLE.items()))
    with pytest.raises(VerificationError, match="no ask on this envelope"):
        verify_investigation_items(
            _one_row(need, whole, target="something_else"), {})


@pytest.mark.parametrize("answer", BENDING)
def test_an_honest_answer_is_still_accepted(answer):
    """Both directions, because a rule that refuses everything refuses
    nothing in particular."""
    pair = SHAPES[answer]
    themis.verify_answer_claims(
        copy.deepcopy(pair["program"]), copy.deepcopy(pair["result"]))


# ------------------------------------------------------------ the census

def test_the_census_no_longer_names_this_leaf_anywhere():
    """What the frontier is FOR, stated where a reader of this file is."""
    still = sorted(
        answer for answer, paths in UNWITNESSED.items()
        if "missing_information.[].name" in paths)
    assert still == [], still
