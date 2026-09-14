"""A gap's sentence arrives assembled, and nothing checked what was in it.

The sentence rule holds a statement's slot NAMES to the holes its token
declares — a fact with nowhere to go and a hole with no fact are both
refused. Neither question is about the VALUE, and the value is the whole
of what a reader meets: the sentence reaches them with ``manski_natural``
and ``P(survival=False|treatment=False)`` already substituted in.

Measured before this: of 1386 facts a gap sentence shows, 416 could be
rewritten and pass both public doors.

WHY THEY WENT UNHELD, which is the part worth keeping. This module
already sorted every ``said`` key into "names a variable" and "does not",
and the second roster carried a reason per family — a vocabulary member
"needs a table this package would have to restate". That reason answers
the NAME MEMBERSHIP question, and it was being read as answering a
different one: whether anything at all could hold the value. Three keys
show the two apart. None of them is a variable, and every one of them has
an exact second record on the same envelope:

    method       -> bounds_results[].method / numeric_estimate.method
    what         -> the key missing_information files the parameter under
    assumptions  -> the assumptions that interval records, and the ledger

No table is restated and no membership is tested. These are equalities
between two copies of one fact.

WHAT STAYS OUT, and why it is not an oversight. 41 of the honest values
in this block live nowhere else on the envelope, and they are of two
kinds: a RENDERED number (``36.3%`` for 0.363, ``1.089e-229`` for a
p-value) which is not equal to anything recorded, and a COINED label
(``CDE``) which is not a copy of anything. A rule demanding every quoted
fact be findable would refuse all 41. Holding those needs a comparison
with a tolerance, which is a different authority and a different
frontier.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.kernel import _premises_of
from themis.verifier import VerificationError
from themis.verifier.gap_claim_rules import (
    _COPIED_FROM,
    _IN_ITS_SENTENCE,
    _NOT_NAMES,
    _ROLES,
    every_said,
    every_said_mapping,
    holds_a_name,
    verify_gap_quotes,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

RULE = "gap_names_check"

CONTEXTS = {name: _premises_of(pair["program"], pair["result"])[3]
            for name, pair in SHAPES.items()}


def _entry(statement, key):
    """The roster for this slot IN THIS STATEMENT, or the general one."""
    return _COPIED_FROM.get((statement, key)) or _COPIED_FROM.get((None, key))


#: (answer, path to the ``said``, statement, slot) for every fact this rule
#: speaks for. Found by the rule's own walk rather than at the one depth
#: this file used to look at: two of the slots below never sit under
#: ``describes`` at all — the methods already in hand hang off an
#: alternative path, and the field a framing gap is short of hangs off a
#: ``words`` entry — so a walk written to the old roster's shape would have
#: reported the new ones as absent.
SITES = sorted(
    (name, where, statement or "", key)
    for name, pair in SHAPES.items()
    for where, statement, said in every_said_mapping(
        (pair["result"] or {}).get("data_gap_report") or {})
    for key in said
    if _entry(statement, key) is not None
)


def _said(result, where):
    node = result["data_gap_report"]
    for step in where.split("."):
        node = node[int(step)] if step.isdigit() else node[step]
    return node


def test_the_facts_this_rule_speaks_for():
    """The denominator, per slot, so a narrowing shows as a number."""
    split: dict[str, int] = {}
    for _name, _where, _statement, key in SITES:
        split[key] = split.get(key, 0) + 1
    # 4 fewer each of assumptions and method: the sentence naming a Balke-Pearl interval's method and assumptions went with the
    # interval on four refreshed answers, whose instrument needs something conditioned.
    assert split == {
        "assumptions": 36, "method": 63, "what": 87,
        "methods": 73, "field": 19, "population": 16, "source": 10,
        "kind": 11, "target": 33,
        "intervention": 566, "treatment": 21, "outcome": 18,
        "latent": 4, "z": 5, "w": 3,
    }, split
    assert len(SITES) == 965, len(SITES)


@pytest.mark.parametrize("name", sorted({n for n, _, _, _ in SITES}))
def test_an_honest_gap_is_accepted(name):
    """The half a rule of this kind gets wrong by being too strict."""
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


def test_every_quoted_fact_the_answer_never_did_is_refused():
    """The teeth, counted rather than sampled."""
    refused = 0
    for name, where, _statement, key in SITES:
        row = SHAPES[name]
        forged = copy.deepcopy(row["result"])
        _said(forged, where)[key] = "a_thing_this_answer_never_did"
        with pytest.raises(Exception):                          # noqa: B017
            the_door_for(row["result"])(row["program"], forged)
        refused += 1
    assert refused == 965, refused


def test_a_listed_slot_is_refused_one_member_at_a_time():
    """``assumptions`` spells several at once, and a reader acts on each.

    Appending one the interval does not rest on leaves every other member
    true, which is the shape a whole-string comparison would pass.
    """
    checked = 0
    for name, where, _statement, key in SITES:
        if key not in ("assumptions", "methods"):
            continue
        row = SHAPES[name]
        forged = copy.deepcopy(row["result"])
        said = _said(forged, where)
        said[key] = f"{said[key]}, an_assumption_nothing_here_rests_on"
        with pytest.raises(VerificationError, match="never did"):
            the_door_for(row["result"])(row["program"], forged)
        checked += 1
    # 4 fewer: the sentence naming a Balke-Pearl interval's method and assumptions went with the
    # interval on four refreshed answers, whose instrument needs something conditioned.
    assert checked == 109, checked


def test_the_rule_is_never_asked_without_a_record_to_appeal_to():
    """The silence, measured rather than assumed.

    A rule that goes quiet where its authority is absent reports perfect
    coverage of whatever it could not see, so how often that happens is a
    number this file owns. On this corpus it is zero — every slot that
    appears has its record beside it.

    Asked at the SITES the rule visits, not at the keys the report
    mentions. The two were the same measurement while a roster was chosen
    by a slot's name; keyed on the statement they are not, and the looser
    one says a rule went quiet in a statement it never consults. It read
    15 here, and all fifteen were an answer that mentions ``target``
    somewhere while declaring no domains — which is not a silence, because
    the entry that wants domains is the one under the statement about
    transporting, and those answers carry none.
    """
    blind = 0
    for name, pair in SHAPES.items():
        result = pair["result"]
        report = result.get("data_gap_report") or {}
        for _where, statement, said in every_said_mapping(report):
            for key in said:
                found = _entry(statement, key)
                if found is None:
                    continue
                if not found[1](result, CONTEXTS[name]):
                    blind += 1
    assert blind == 0, blind


def test_the_silence_is_real_where_the_record_is_gone():
    """And that it IS silent, which the corpus cannot show precisely
    because the record is always there.

    Stripping the record leaves a gap quoting a method with nothing to be
    judged against. Refusing then would refuse an answer whose interval
    block simply was not built, so the rule must say nothing.
    """
    name, where, _statement, _key = next(s for s in SITES if s[3] == "method")
    context = CONTEXTS[name]

    lying = copy.deepcopy(SHAPES[name]["result"])
    _said(lying, where)["method"] = "a_method_nobody_ran"
    with pytest.raises(VerificationError, match="never did"):
        verify_gap_quotes(lying, context)

    # The same lie, with the record it would be judged against removed.
    blind = copy.deepcopy(lying)
    blind.pop("bounds_results", None)
    blind.pop("numeric_estimate", None)
    verify_gap_quotes(blind, context)


def test_a_kind_is_not_a_reason_nothing_can_hold_a_value():
    """The root cause, asserted where it can be argued with.

    Every key here is filed as NOT a name, and correctly — none of them
    is a variable of the problem. That classification was doing double
    duty as the reason they went unchecked, and the two questions are
    orthogonal: what sort of word this is, and whether a second record of
    it exists.

    Four kinds now, where three of them once looked like a reason to look
    away. A vocabulary member and an expression were the first two; a
    DOMAIN is a name out of the register the name rule cannot read, and
    the program declares every one of them; and a ``value`` slot joins
    when its statement says which register it is in.

    And a NAME, where its statement copies it from the question. Being a
    name says the name rule asks it, and that rule asks whether a word is
    one of the problem's; a second record says whether it is the one.
    """
    def kind(statement, key):
        if holds_a_name(statement, key):
            return "name"
        return _IN_ITS_SENTENCE.get((statement, key)) or _NOT_NAMES[key]

    assert {kind(s, k) for s, k in _COPIED_FROM} == {
        "vocabulary", "expression", "domain", "name"}
    names = {(s, k) for s, k in _COPIED_FROM if kind(s, k) == "name"}
    assert {k for _s, k in names} == set(_ROLES)
    assert all(s is not None for s, _k in names)


def test_a_rendered_number_is_deliberately_not_in_this_roster():
    """What stays out, exercised rather than described.

    ``share`` is 36.3% where the record holds 0.363, so an equality
    against the record refuses the honest answer. That is why the roster
    is per-key and not "every quoted fact must be findable".
    """
    assert not any(key == "share" for _statement, key in _COPIED_FROM)
    assert _NOT_NAMES["share"] == "number"
    found = [
        (name, value)
        for name, pair in SHAPES.items()
        for _where, key, value in every_said(
            pair["result"].get("data_gap_report") or {})
        if key == "share"
    ]
    assert found, "no share slot in the corpus to speak about"
    name, value = found[0]
    rest = json.dumps({k: v for k, v in SHAPES[name]["result"].items()
                       if k != "data_gap_report"}, ensure_ascii=False)
    assert str(value) not in rest, (name, value)
