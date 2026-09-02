"""Not whether a gap's words are names, but whether they are ITS names.

The frontier before last asked a question about VOCABULARY: is this word
one the problem is written in. Every honest gap passes it — and so does a
forgery that swaps one real variable for another. A gap about ``y``
rewritten to be about ``x`` sends a reader to fill in a variable that is
missing nothing, in words that are all real.

The bounds frontier met the same thing one step earlier, on a row
claiming its width was ``x``: holding a value to "is a real name" is not
holding it to "is THIS one".

The answer was already on the gap. A gap carries ``provenance``, T10-1
holds every ref in it to something that exists, and across the corpus the
variable a gap is about appears in its own refs 102 times out of 102. The
skeleton was verified, the contents were verified, and nothing had joined
them. ``missing`` is anchored on the other side entirely — the fields a
gap says are unset are fields the PROGRAM does not set — which is the
asked side and not the answer's to arrange.

Both questions ride the report's own ``said`` walk rather than a container
list of their own, because the first version of this rule read
``gap["describes"]`` and left the same key in ``alternative_paths``
standing — the frontier's disease, on the gate written to cure it.
"""
from __future__ import annotations

import copy
import json
import pathlib
import re

import pytest

import themis
from themis.types import VariableDeclaration
from themis.verifier.errors import VerificationError
from themis.verifier.gap_claim_rules import (
    every_said_mapping,
    verify_gap_subjects,
)

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

CARRIERS = sorted(n for n in SHAPES
                  if (SHAPES[n]["result"].get("data_gap_report") or {})
                  .get("gaps"))


def _pair(method):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _described(result, key):
    for gap in (result.get("data_gap_report") or {}).get("gaps") or []:
        for d in gap.get("describes") or []:
            if key in (d.get("said") or {}):
                return gap, d
    raise AssertionError(f"no describes carrying {key!r}")


def _with(name, key, mutate):
    program, result = _pair(name)
    mutate(*_described(result, key))
    themis.verify(program, result)


WITH_VARIABLE = sorted(
    n for n in CARRIERS
    if any("variable" in (d.get("said") or {})
           for g in SHAPES[n]["result"]["data_gap_report"]["gaps"]
           for d in g.get("describes") or []))


# ------------------------------------------------- the facts this rests on


def _declared_names(method):
    return [str(s.get("predicate")) for s in SHAPES[method]["program"]["statements"]
            if s.get("kind") == "variable"]


def _subjects():
    """Every ``(variable, ref tokens)`` pair anywhere under a gap."""
    for name in CARRIERS:
        for gap in SHAPES[name]["result"]["data_gap_report"]["gaps"]:
            refs = [str(r.get("ref_id")) for r in gap.get("provenance") or []]
            tokens = {t for r in refs for t in IDENT.findall(r)}
            for _, said in every_said_mapping(gap):
                if isinstance(said.get("variable"), str):
                    yield name, said["variable"], refs, tokens


def test_the_variable_a_gap_is_about_is_named_by_its_own_provenance():
    """The measurement the rule rests on, kept where it can go stale.

    Counted over the whole walk, not over ``describes``: three containers
    carry the key today and all three answer the same way.
    """
    pairs = list(_subjects())
    inside = sum(1 for _, v, _, tokens in pairs if v in tokens)
    assert (inside, len(pairs)) == (102, 102)


def _riders():
    """``(shape, gap index, name)`` a substring anchor would have let by.

    A real variable of the problem that occurs inside one of the gap's
    ref ids without being a name that ref mentions.
    """
    for name in CARRIERS:
        gaps = SHAPES[name]["result"]["data_gap_report"]["gaps"]
        for i, gap in enumerate(gaps):
            refs = [str(r.get("ref_id")) for r in gap.get("provenance") or []]
            tokens = {t for r in refs for t in IDENT.findall(r)}
            for v in _declared_names(name):
                if any(v in r for r in refs) and v not in tokens:
                    yield name, i, v


def test_a_ref_that_merely_contains_the_name_is_not_the_name():
    """Why the anchor is a whole token and not a substring.

    A ref id is a structured string with names inside it, so "occurs in"
    accepts names the ref never mentions: a gap about ``m`` rides on
    ``program:front_door_pattern``, and one about ``y`` on
    ``propensity_overlap:x|z``. The tighter relation costs nothing on the
    honest side — 102 of 102 either way — and this corpus offers 48 rides
    it refuses.
    """
    assert sum(1 for _, v, refs, _ in _subjects()
               if any(v in r for r in refs)) == 102
    assert len(list(_riders())) == 48


def test_one_of_those_rides_is_actually_refused():
    """The counted claim above, taken through the public door once."""
    for name, index, rider in _riders():
        program, result = _pair(name)
        gap = result["data_gap_report"]["gaps"][index]
        described = next(
            (d for d in gap.get("describes") or []
             if (d.get("said") or {}).get("variable")), None)
        if described is None:
            continue
        described["said"]["variable"] = rider
        with pytest.raises(VerificationError, match="never mentions"):
            themis.verify(program, result)
        return
    raise AssertionError("no ride lands on a gap that names a variable")


def test_every_honest_answer_shape_is_still_accepted():
    for name in sorted(SHAPES):
        program, result = _pair(name)
        themis.verify(program, result)


# ------------------------------------------------------------- the gate


def test_a_gap_about_another_real_variable_of_the_same_problem():
    """The counter-example the vocabulary rule cannot see.

    ``x`` is a name this problem has, so every word in the gap stays
    real. What changes is which variable a reader is sent to fill in.
    """
    def swap(gap, described):
        described["said"]["variable"] = "x"

    with pytest.raises(VerificationError, match="not about"):
        _with("backdoor_linear", "variable", swap)


def test_the_same_key_in_a_second_container_is_asked_too():
    """The first version of this rule walked ``describes`` and stopped.

    ``alternative_paths`` carries the same key with the same meaning and
    the same anchor available, and it stood untouched — the frontier's own
    disease, on the gate written to cure it. So the scope is the report's
    ``said`` walk, and this pins that a container the rule does not name
    is reached anyway.
    """
    program, result = _pair("iv_wald")
    for gap in result["data_gap_report"]["gaps"]:
        for alt in gap.get("alternative_paths") or []:
            if (alt.get("said") or {}).get("variable"):
                alt["said"]["variable"] = "x"
                with pytest.raises(VerificationError, match="not about"):
                    themis.verify(program, result)
                return
    raise AssertionError("iv_wald no longer carries the second container")


def test_a_gap_that_names_no_variable_at_all():
    with pytest.raises(VerificationError, match="does not name|hole where"):
        _with("backdoor_linear", "variable",
              lambda g, d: d["said"].update(variable=""))


def test_a_gap_asking_for_a_field_a_declaration_has_no_place_for():
    """An absent key in a raw statement reads as "unset", so the type is
    what says which fields exist at all."""
    def invent(gap, described):
        described["said"]["missing"] = "time_window, enthusiasm"

    with pytest.raises(VerificationError, match="not something a variable"):
        _with("backdoor_linear", "missing", invent)


def test_a_gap_asking_for_a_field_the_program_already_gave():
    """The other way to be wrong, and the one the program settles."""
    for name in CARRIERS:
        program, result = _pair(name)
        try:
            gap, described = _described(result, "missing")
        except AssertionError:
            continue
        subject = described["said"]["variable"]
        declaration = next(
            (s for s in program["statements"]
             if s.get("kind") == "variable" and s.get("predicate") == subject),
            None)
        given = [f for f in ("domain", "measurement", "time_window", "unit",
                             "observability", "direction", "baseline")
                 if (declaration or {}).get(f) is not None]
        if not given:
            continue
        described["said"]["missing"] = given[0]
        with pytest.raises(VerificationError, match="already gave"):
            themis.verify(program, result)
        return
    raise AssertionError("no shape declares a field its gap could re-ask")


def test_a_gap_that_says_nothing_is_missing():
    with pytest.raises(VerificationError, match="names none"):
        _with("backdoor_linear", "missing",
              lambda g, d: d["said"].update(missing="   "))


def test_the_fields_a_gap_may_name_are_the_declaration_type_s_own():
    """Stated so that a renamed framing field is a failure here rather
    than a rule that quietly stops reaching."""
    for field in ("time_window", "measurement", "observability",
                  "direction", "baseline", "state_vs_event", "domain"):
        assert hasattr(VariableDeclaration, field)
    assert not hasattr(VariableDeclaration, "enthusiasm")


# ------------------------------------------- what the rule does not reach


def test_the_other_said_kinds_are_declared_not_held():
    """Counted, so that "we closed the gap report" cannot be said.

    What remains is the two kinds the vocabulary frontier already
    declared — a glossary member needing a table this side cannot have,
    and a number with no second record — plus ``subject``, which names a
    mediator SET (``{m1(me), m2(me)}``) that no provenance ref spells.
    """
    unanchored = 0
    for name in CARRIERS:
        for gap in SHAPES[name]["result"]["data_gap_report"]["gaps"]:
            refs = [str(r.get("ref_id")) for r in gap.get("provenance") or []]
            for d in gap.get("describes") or []:
                said = d.get("said") or {}
                if "subject" not in said:
                    continue
                assert not any(str(said["subject"]) in r for r in refs)
                unanchored += 1
    assert unanchored == 9


def test_the_rule_is_silent_where_there_is_no_report():
    for name in sorted(set(SHAPES) - set(CARRIERS)):
        program, result = _pair(name)
        verify_gap_subjects(result, program)
