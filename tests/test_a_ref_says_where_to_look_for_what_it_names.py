"""A gap's provenance ref, and the space its id lives in.

A gap tells a reader what raised it by naming something: a derivation step,
an investigation request, a framing note, a place in this answer, a place in
the program, a check this build ran. T10-1's whole job is that the named
thing is there — and it can only ask that if it knows WHERE to look, which is
what ``ref_kind`` is for.

Three of the six members named a space from the start. The other two did not
exist, and what stood where they belonged was ``verifier_check``: measured
over the corpus, 479 of 966 refs wore it while addressing three different
things, so the arm that read them accepted any non-empty string. A kind that
names no space is a ref nothing can ask about, and from the outside that is
indistinguishable from a ref nothing found wrong with.

What it cost is on the envelope. ``graph_learned_from_data`` cited
``extensions.discovery_metadata`` — spelled as a path into the answer, while
the function producing it says two lines above the site that it reads
``program.extensions`` because discovery is a program-shape signal. It named
a block that was not there, on every answer that carried it, and nothing
said so.

**Why this file replays programs instead of reading the fixture.** The corpus
was recorded before this change, so its refs still wear the old kind and
would exercise none of it. Which species cite a path is derived from the
producer rather than listed here — a list would be this file's own guess at
the producer's layout, and the point of the change is that a guess is what a
catch-all forces.
"""
from __future__ import annotations

import ast
import copy
import json
import pathlib

import pytest

import themis
from themis.types import GapRefKind
from themis.verifier.data_gap_rules import (
    _at_path,
    _verify_t10_1_provenance as _t10_1,
)
from themis.verifier.errors import VerificationError

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

PRODUCERS = ("themis/output/data_gap_report.py", "themis/estimation/dispatch.py")


def _named(node):
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _species_by_ref_kind() -> dict[str, set[str]]:
    """Which gap species cite under each ref kind.

    Read from the declaration since #618. It used to be read off the
    construction sites, and the reason written here was that a list in
    this file would be this file's own guess at the producer's layout.
    That reason stopped holding the moment the producer began filling the
    kind FROM the declaration instead of typing it beside the id: reading
    :data:`themis.types.REF_KINDS_OF` is reading what the sites read, and
    an AST scan would now be reading the shape of a call.

    Wider than the sites by exactly the species whose row leaves a
    choice, which is the right direction for this file to be wrong in —
    it replays programs and asserts on the refs that actually come out.
    """
    from themis.types import REF_KINDS_OF
    out: dict[str, set[str]] = {}
    for species, spaces in REF_KINDS_OF.items():
        for space in spaces:
            out.setdefault(space.name, set()).add(species.name)
    return out


BY_KIND = _species_by_ref_kind()


def _species_values(attr_names: set[str]) -> frozenset[str]:
    """``GapKind.X`` as the string an envelope carries."""
    from themis.types import GapKind
    return frozenset(getattr(GapKind, n.split(".")[-1]).value
                     for n in attr_names)


PATHS = _species_values(BY_KIND.get("ENVELOPE_PATH", set()))
SITES = _species_values(BY_KIND.get("PROGRAM_SITE", set()))


def _rows_citing(species: frozenset[str]) -> list[str]:
    """Corpus rows whose recorded report carries one of these species.

    Taken by the property. Which rows those are is a fact about the
    collection; that a row of this species exists is what the test needs.
    """
    rows = []
    for name in sorted(SHAPES):
        report = ((SHAPES[name]["result"] or {}).get("data_gap_report") or {})
        if any(gap.get("kind") in species
               for gap in report.get("gaps") or []):
            rows.append(name)
    return rows


PATH_ROWS = _rows_citing(PATHS)
SITE_ROWS = _rows_citing(SITES)


def _fresh(name: str) -> list[dict]:
    """This build's own answers to that row's program."""
    return themis.run(SHAPES[name]["program"]).get("results") or []


def _refs(result: dict, kind: str) -> list[tuple[int, int, dict]]:
    out = []
    report = result.get("data_gap_report") or {}
    for i, gap in enumerate(report.get("gaps") or []):
        for j, ref in enumerate(gap.get("provenance") or []):
            if ref.get("ref_kind") == kind:
                out.append((i, j, ref))
    return out


# ------------------------------------------------ the vocabulary itself


def test_every_kind_this_build_has_is_a_kind_the_envelope_allows():
    """Both directions, because either alone hides half of a drift.

    A member with no schema entry cannot reach a reader; a schema entry
    with no member is a word nothing can produce, and a rule keyed on it
    would be silently unreachable.
    """
    schema = json.loads(
        (ROOT / "themis/schemas/query_result.schema.json").read_text(
            encoding="utf-8"))
    found = None
    stack = [schema]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            props = node.get("properties") or {}
            if "ref_kind" in props and "ref_id" in props:
                found = frozenset(props["ref_kind"]["enum"])
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    assert found is not None, "the schema no longer states a provenance ref"
    assert found == frozenset(k.value for k in GapRefKind)


def test_no_member_stands_for_no_space():
    """The defect this frontier was, stated as the thing not to reintroduce.

    Each member has to answer "where do I look", because T10-1's question
    is only askable once it is answered. A member added tomorrow with no
    arm in that rule is a place refs will collect, exactly as one did.
    """
    from themis.verifier import data_gap_rules

    source = pathlib.Path(data_gap_rules.__file__).read_text(encoding="utf-8")
    for kind in GapRefKind:
        assert f'"{kind.value}"' in source, (
            f"{kind.value!r} is a ref kind T10-1 does not name; refs wearing "
            f"it reach the else-branch, which is where the catch-all was")


# ------------------------------------------------ the honest half


@pytest.mark.parametrize("name", PATH_ROWS)
def test_every_path_this_build_writes_lands_on_the_answer(name):
    """The half a rule of this kind gets wrong by being too strict.

    Asked of what this build produces rather than of the recording,
    because the recording predates the kinds.
    """
    for result in _fresh(name):
        for _, _, ref in _refs(result, "envelope_path"):
            found, why = _at_path(result, ref["ref_id"])
            assert found, f"{name}: {ref['ref_id']!r} — {why}"
        if result.get("data_gap_report"):
            themis.verify_data_gap_report(result)


def test_the_build_writes_paths_at_all():
    """A floor under the test above, which passes vacuously if nothing is
    produced. Not an equality: what matters is that the arm is reached."""
    total = sum(len(_refs(r, "envelope_path"))
                for name in PATH_ROWS[:12] for r in _fresh(name))
    assert total >= 5, total


# ------------------------------------------------ the counterexamples


def _a_path_ref():
    for name in PATH_ROWS:
        for result in _fresh(name):
            hits = _refs(result, "envelope_path")
            if hits:
                return name, result, hits[0]
    return None


def test_a_path_this_answer_does_not_carry_is_refused():
    """The point of the arm. A gap that cites a block the answer does not
    have sends a reader looking for the reason it exists in a place where
    there is none."""
    picked = _a_path_ref()
    assert picked is not None, "no answer in this sample cites a path"
    _name, result, (_, _, ref) = picked
    forged = copy.deepcopy(result)
    _refs(forged, "envelope_path")[0][2]["ref_id"] = ref["ref_id"] + "_forged"
    with pytest.raises(VerificationError, match="envelope_path"):
        themis.verify_data_gap_report(forged)


def test_a_path_cannot_be_checked_without_the_answer():
    """The strictness, made explicit rather than left to a default.

    Handed no envelope, this arm refuses instead of passing. An audit
    that cannot look is not an audit that saw nothing wrong, and the
    derivation arm already answers this way when handed no chain.

    Asked of the rule rather than through the entry point: withholding the
    envelope withholds the other three inputs too, and which arm speaks
    first is not something this test is about.
    """
    picked = _a_path_ref()
    assert picked is not None
    _name, result, _ref = picked
    with pytest.raises(VerificationError, match="handed no answer"):
        _t10_1(
            result["data_gap_report"],
            derivation_steps=list(
                (result.get("derivation") or {}).get("steps") or []),
            investigation_requests=list(
                result.get("investigation_requests") or []),
            framing_notes=list(result.get("framing_notes") or []),
            envelope=None,
        )


# ------------------------------------------------ the declared range


def test_a_place_in_the_program_is_outside_this():
    """The range, exercised rather than described.

    This door is result-only by contract — it exists so that answers with
    no derivation can still be audited — so the program a site would be
    found in is not here. Naming the space is still what stops a program
    site from being spelled as a path into the answer.
    """
    for name in SITE_ROWS:
        for result in _fresh(name):
            hits = _refs(result, "program_site")
            if not hits or not result.get("data_gap_report"):
                continue
            forged = copy.deepcopy(result)
            i, j, _ = hits[0]
            forged["data_gap_report"]["gaps"][i]["provenance"][j][
                "ref_id"] += "_forged"
            themis.verify_data_gap_report(forged)
            return
    pytest.fail("no answer in this sample cites a place in the program")


def test_a_site_that_names_nothing_is_still_refused():
    """Empty is not the third state here either."""
    for name in SITE_ROWS:
        for result in _fresh(name):
            hits = _refs(result, "program_site")
            if not hits or not result.get("data_gap_report"):
                continue
            forged = copy.deepcopy(result)
            i, j, _ = hits[0]
            forged["data_gap_report"]["gaps"][i]["provenance"][j][
                "ref_id"] = ""
            with pytest.raises(VerificationError, match="program_site"):
                themis.verify_data_gap_report(forged)
            return
    pytest.fail("no answer in this sample cites a place in the program")


# ------------------------------------------------ the defect it found


def test_the_learned_graph_signal_says_it_is_in_the_program():
    """The one this frontier found, pinned where it was wrong.

    The producer's own docstring says it reads ``program.extensions``
    because discovery is a program-shape signal. The ref said
    ``extensions.discovery_metadata``, which reads as a path into the
    answer and was not one on any row that carried it.
    """
    from themis.types import GapKind

    species = GapKind.GRAPH_LEARNED_FROM_DATA.value
    rows = _rows_citing(frozenset({species}))
    assert rows, "no corpus row records a learned graph"
    checked = 0
    for name in rows:
        for result in _fresh(name):
            for gap in ((result.get("data_gap_report") or {}).get("gaps")
                        or []):
                if gap.get("kind") != species:
                    continue
                for ref in gap.get("provenance") or []:
                    assert ref["ref_kind"] == GapRefKind.PROGRAM_SITE.value, (
                        f"{name}: a program-shape signal cited as "
                        f"{ref['ref_kind']!r}")
                    checked += 1
    assert checked, "the species is recorded but this build raises no gap"
