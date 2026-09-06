"""How bad a gap is, and what it stands in the way of, belong to the species.

``severity`` ranks the list a reader works down and decides which gap
reaches the headline; ``blocks`` says which of identification, a point, an
interval, a transport or an interpretation filling this one would buy back.
A reader acts on both, and no rule read either: 230 answers carried a
severity nobody had ever checked, and 230 a blocks.

No rule could. Both were typed at all 47 construction sites, and a value
every site writes is declared nowhere — so anything holding them would have
had to restate the producer's layout, which is agreeing with it by
construction. Measured before they moved: of the 42 species, 38 were
written with one severity at every site and 40 with one ``blocks``, and
each of the few that were not has a reason its producer states in code.

So they are declared beside ``GapKind``: ``SEVERITY_OF`` / ``BLOCKS_OF``
for the species whose value is the same on every occasion, and
``SEVERITY_TURNS_ON`` / ``BLOCKS_TURN_ON`` for the few where it is the
occasion's, each naming in a sentence what it turns on.

Three gates hold three different things, and none of them is the others:

- the two rows PARTITION the enum, checked when :mod:`themis.types` is
  imported — so a species added without a row is an ImportError before any
  test runs, which is why nothing here restates that check;
- :class:`~themis.types.DataGap` fills what the species declares and
  refuses a value that contradicts it. That is what holds the one
  construction site whose kind is computed, which no source scan can read;
- T10-5 ``data_gap_species_check`` re-reads both fields off the ENVELOPE at
  the door, which is where a gap that was serialized, edited, or submitted
  by somebody else is read.

A value that AGREES is accepted rather than refused, and that is not a
half-measure: ``dataclasses.replace`` re-enters the constructor with the
gap's own values, and three production sites rewrite a gap's routes that
way. What may not happen is a site holding a different value from the
species — and the source scan below keeps the producers from restating
even the agreeing one.

The scan reads a literal ``GapKind.X``. A kind outside the vocabulary never
reaches T10-5 at all: the schema the door validates against refuses it
first, which ``test_phase10_data_gap_schema.py`` pins.
"""
from __future__ import annotations

import ast
import copy
import json
import pathlib
from dataclasses import replace

import pytest

from themis.output.data_gap_report import data_gap_from_dict
from themis.output.result_orchestrator import data_gap_to_dict
from themis.types import (
    BLOCKS_OF,
    BLOCKS_TURN_ON,
    SEVERITY_OF,
    SEVERITY_TURNS_ON,
    raised_by,
    DataGap,
    GapBlocks,
    GapKind,
    GapProvenanceRef,
    GapRefKind,
    GapSeverity,
)
from themis.verifier import data_gap_rules
from themis.verifier.errors import VerificationError

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests/fixtures/answer_shapes.json").read_text(encoding="utf-8"))

#: What a fixture supplies where the declaration says the value is an
#: occasion's — which is the only place a fixture gets to choose one.
_AN_OCCASION = {"severity": GapSeverity.IMPORTANT,
                "blocks": GapBlocks.INTERPRETATION}


def _gap(kind: GapKind, **kw) -> DataGap:
    """A gap of this species, saying only what the species leaves open."""
    fields = {"kind": kind, "describes": (), "provenance": (
        GapProvenanceRef(ref_kind=GapRefKind.VERIFIER_CHECK, ref_id="x"),)}
    if kind in SEVERITY_TURNS_ON:
        fields["severity"] = _AN_OCCASION["severity"]
    if kind in BLOCKS_TURN_ON:
        fields["blocks"] = _AN_OCCASION["blocks"]
    fields.update(kw)
    return DataGap(**fields)  # type: ignore[arg-type]


def _envelope_gap(kind: GapKind, **kw) -> dict:
    """The same gap, in the shape the envelope carries it.

    The provenance is the check this species declares, named with no
    subject, which is the one ref shape that resolves with no artifact and
    no rest-of-envelope beside it. It used to be spelled ``"x"`` under a
    comment saying a verifier_check ref resolved without one — true at the
    time, and the defect T10-1 closed: a fixture reaching for the member
    nothing checked was choosing not to be checked. Species with no
    declared check are refused here rather than given a placeholder, so
    the next author picks a species instead of picking a hole.
    """
    severity, blocks = SEVERITY_OF.get(kind), BLOCKS_OF.get(kind)
    checks = raised_by(kind)
    assert checks, (
        f"{kind.value} declares no check, so there is no provenance this "
        f"fixture can write that a rule will resolve"
    )
    gap = {
        "kind": kind.value,
        "severity": (severity or _AN_OCCASION["severity"]).value,
        "blocks": (blocks or _AN_OCCASION["blocks"]).value,
        "describes": [],
        "provenance": [{"ref_kind": "verifier_check",
                        "ref_id": sorted(checks)[0]}],
    }
    gap.update(kw)
    return gap


def _report(*gaps: dict) -> dict:
    return {"gaps": list(gaps)}


# ------------------------------------------------ what the species fills


@pytest.mark.parametrize("kind", list(GapKind), ids=lambda k: k.value)
def test_a_gap_of_any_species_comes_out_with_both_words(kind):
    """Every species, with nothing typed but what the declaration leaves
    open. A gap reaching a reader with a field unset would be one whose
    severity is whatever sorting makes of ``None``."""
    gap = _gap(kind)
    assert gap.severity is not None and gap.blocks is not None
    if kind in SEVERITY_OF:
        assert gap.severity is SEVERITY_OF[kind]
    if kind in BLOCKS_OF:
        assert gap.blocks is BLOCKS_OF[kind]


@pytest.mark.parametrize("field", ["severity", "blocks"])
def test_a_species_whose_value_is_the_occasions_has_to_say_which(field):
    """Nothing fills it, because there is nothing to fill it from — and the
    refusal hands back the declaration's own sentence, so an author reads
    why this species is different rather than only that it is."""
    varies = SEVERITY_TURNS_ON if field == "severity" else BLOCKS_TURN_ON
    other = "blocks" if field == "severity" else "severity"
    other_varies = BLOCKS_TURN_ON if other == "blocks" else SEVERITY_TURNS_ON
    for kind, why in varies.items():
        supplied = {other: _AN_OCCASION[other]} if kind in other_varies else {}
        with pytest.raises(ValueError) as excinfo:
            DataGap(kind=kind, describes=(), **supplied)
        assert why in str(excinfo.value)


@pytest.mark.parametrize("field,declared,other", [
    ("severity", SEVERITY_OF, GapSeverity.INFORMATIONAL),
    ("blocks", BLOCKS_OF, GapBlocks.BOUNDS),
])
def test_a_site_may_not_hold_a_value_the_species_denies(
        field, declared, other):
    kind = GapKind.MISSING_DISTRIBUTION
    assert declared[kind] is not other
    with pytest.raises(ValueError, match="not a site's to set"):
        _gap(kind, **{field: other})


def test_a_gap_survives_being_rewritten():
    """Why an agreeing value is accepted rather than refused: ``replace``
    re-enters the constructor with everything the gap already holds, and
    three production sites rewrite a gap's routes that way."""
    gap = _gap(GapKind.MISSING_DISTRIBUTION)
    again = replace(gap, signature="conditional")
    assert (again.severity, again.blocks) == (gap.severity, gap.blocks)


def test_the_hydrator_cannot_read_back_a_value_the_species_denies():
    """The one site no source scan reaches: it takes its kind off the
    envelope it is decoding, so the constructor is all that stands there."""
    written = data_gap_to_dict(_gap(GapKind.MISSING_DISTRIBUTION))
    assert data_gap_from_dict(written).severity is GapSeverity.BLOCKING
    written["severity"] = GapSeverity.INFORMATIONAL.value
    with pytest.raises(ValueError, match="not a site's to set"):
        data_gap_from_dict(written)


# --------------------------------------------------- T10-5, at the door


@pytest.mark.parametrize("field,other", [
    ("severity", GapSeverity.INFORMATIONAL.value),
    ("blocks", GapBlocks.BOUNDS.value),
])
def test_the_door_refuses_a_word_the_species_denies(field, other):
    """Through the public entry, so this also says the rule is wired to the
    door rather than only written."""
    kind = GapKind.OVERIDENTIFICATION_REJECTED
    declared = (SEVERITY_OF if field == "severity" else BLOCKS_OF)[kind]
    with pytest.raises(VerificationError) as excinfo:
        data_gap_rules.verify_data_gap_report(
            _report(_envelope_gap(kind, **{field: other})))
    said = str(excinfo.value)
    assert "T10-5" in said and other in said and declared.value in said
    assert excinfo.value.rule == "data_gap_species_check"


@pytest.mark.parametrize("field", ["severity", "blocks"])
def test_the_door_refuses_a_gap_that_says_nothing_about_it(field):
    """Absent is not silent. A reader sorting a list by a field that is not
    there is shown an order nobody chose."""
    gap = _envelope_gap(GapKind.OVERIDENTIFICATION_REJECTED)
    del gap[field]
    with pytest.raises(VerificationError, match="says nothing about its"):
        data_gap_rules.verify_data_gap_report(_report(gap))


@pytest.mark.parametrize("word", [s.value for s in GapSeverity])
def test_the_door_says_nothing_where_the_species_left_it_to_the_occasion(
        word):
    """The counterexample this rule has to accept. This species' severity is
    computed per occasion, so every word in the vocabulary is one an honest
    envelope may carry here, and a rule refusing any of them refuses an
    honest answer.

    Which species that is comes from the declaration rather than being
    named here: the one this was written with stopped varying a round
    later, when the two readings of "which predicates the query names"
    became one and the branch that made it vary turned out unreachable.
    """
    kind = next(iter(SEVERITY_TURNS_ON))
    data_gap_rules._verify_t10_5_species_properties(
        _report(_envelope_gap(kind, severity=word)))


def test_the_door_passes_over_a_species_this_build_does_not_have():
    """Nothing to look up, so nothing to refuse on: the schema the door
    validates against has already refused the word."""
    gap = _envelope_gap(GapKind.OVERIDENTIFICATION_REJECTED)
    gap["kind"] = "invented_kind"
    data_gap_rules._verify_t10_5_species_properties(_report(gap))


def test_every_gap_the_corpus_carries_is_one_its_species_would_own():
    """The number that decides whether this rule may exist at all: a rule
    refusing an honest answer is worse than the hole it closes, and these
    are the reports the suite's own runs produced. T10-5 alone, because its
    three siblings need the rest of an envelope this reads nothing of."""
    seen = 0
    for pair in SHAPES.values():
        report = (pair.get("result") or {}).get("data_gap_report")
        if not isinstance(report, dict) or not report.get("gaps"):
            continue
        seen += len(report["gaps"])
        data_gap_rules._verify_t10_5_species_properties(copy.deepcopy(report))
    # A floor rather than the count: the corpus is regenerated, and what
    # this asserts is that the walk above had something to walk.
    assert seen > 900


def test_the_refusal_names_what_a_reader_does_with_the_field():
    assert set(data_gap_rules._WHAT_A_READER_DOES_WITH_IT) == {
        field for field, _fixed, _varies
        in data_gap_rules._A_GAP_SAYS_OF_ITSELF
    }


# ------------------------------------------- and nobody types them again


def _sites_that_restate_the_species(source: str) -> list[str]:
    """Every ``DataGap(...)`` in this source handing the constructor a value
    its species already declares — agreeing or not."""
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "DataGap"):
            continue
        args = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        kind = args.get("kind")
        if not (isinstance(kind, ast.Attribute)
                and isinstance(kind.value, ast.Name)
                and kind.value.id == "GapKind"):
            continue
        species = GapKind[kind.attr]
        for field, table in (("severity", SEVERITY_OF), ("blocks", BLOCKS_OF)):
            if field in args and species in table:
                out.append(f"line {node.lineno}: {field} of {species.value}")
    return out


def _sites_whose_kind_is_computed(source: str) -> list[int]:
    return [node.lineno for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "DataGap"
            and not any(
                kw.arg == "kind" and isinstance(kw.value, ast.Attribute)
                and isinstance(kw.value.value, ast.Name)
                and kw.value.value.id == "GapKind"
                for kw in node.keywords)]


def test_no_producer_restates_a_value_its_species_declares():
    """87 lines came out when the declaration went in. What keeps them out
    is this scan: the constructor accepts an agreeing value, so nothing else
    notices a site quietly acquiring a second author."""
    offenders = {
        str(path.relative_to(ROOT)): rows
        for path in sorted((ROOT / "themis").rglob("*.py"))
        if (rows := _sites_that_restate_the_species(
            path.read_text(encoding="utf-8")))
    }
    assert offenders == {}


def test_the_scan_would_see_a_site_that_did():
    """The counterexample: a gate nobody has watched say no is a gate
    nobody has watched."""
    restated = """
DataGap(kind=GapKind.MISSING_DISTRIBUTION,
        severity=GapSeverity.BLOCKING, describes=())
"""
    assert _sites_that_restate_the_species(restated) == [
        "line 2: severity of missing_distribution"]

    occasion = f"""
DataGap(kind=GapKind.{next(iter(SEVERITY_TURNS_ON)).name},
        severity=GapSeverity.IMPORTANT, describes=())
"""
    assert _sites_that_restate_the_species(occasion) == []


def test_the_one_site_the_scan_cannot_read_is_the_hydrator():
    """Stated rather than left to be found: exactly one gap in this tree is
    built from a kind read off an envelope, and what holds its two fields is
    the constructor."""
    computed = {str(path.relative_to(ROOT)): _sites_whose_kind_is_computed(
        path.read_text(encoding="utf-8"))
        for path in sorted((ROOT / "themis").rglob("*.py"))}
    assert sum(len(v) for v in computed.values()) == 1
    assert [name for name, rows in computed.items() if rows] == [
        str(pathlib.Path("themis/output/data_gap_report.py"))]
