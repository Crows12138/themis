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
from themis import gaps, language
from themis.verifier.gap_claim_rules import (
    _A_WORD_COPIES,
    _COPIED_FROM,
    _IN_ITS_SENTENCE,
    _NOT_NAMES,
    _ROLES,
    every_said,
    every_said_mapping,
    every_word_mapping,
    holds_a_name,
    statements_and_the_slots_they_declare,
    verify_gap_quotes,
    verify_gap_subjects,
)
from themis.verifier.gap_claim_rules import (
    _the_question_asked,
    _the_role_the_question_gives,
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


# ------------------------------------------- and the half a fact travels in
#
# Same question as the rest of this file — a fact a gap quotes, against
# the record it was read from — asked of the other half. The rule that
# asks it is ``verify_gap_subjects``, because the record a word is held
# to is the program's declaration and that door is where the program is.


def _word_entry(statement, key):
    """The word roster for this slot IN THIS STATEMENT, or the general one."""
    return (_A_WORD_COPIES.get((statement, key))
            or _A_WORD_COPIES.get((None, key)))


#: (answer, path to the ``words``, statement, slot) for every WORD this rule
#: speaks for. Found by the same walk, which is the point: which half a fact
#: travels in is decided by whether the value needs translating, and this
#: rule's question — is there a second record of it — does not turn on that.
WORD_SITES = sorted(
    (name, where, statement or "", key)
    for name, pair in SHAPES.items()
    for where, statement, words, _said in every_word_mapping(
        (pair["result"] or {}).get("data_gap_report") or {})
    for key in words
    if _word_entry(statement, key) is not None
)


def _members_of(vocabulary: str) -> list[str]:
    return sorted(str(member) for member in language.VOCABULARIES[vocabulary])


def _a_site(slot: str):
    """One site of this slot, for the tests about a single one."""
    return next(site for site in WORD_SITES if site[3] == slot)


def test_the_words_this_rule_speaks_for():
    """The denominator, per slot, so a narrowing shows as a number.

    And the gate the roster has instead of an import-time one. A row was
    held against the slots ``_bind`` knows, which keeps the vocabularies
    whose words live in ``themis.gaps`` — where the WORDS are, not what
    decides whether a report carries the statement. A gap report carries
    seventeen vocabularies and that space sees four, so the check said
    "no statement this build can write has that slot" of a slot nineteen
    answers carry. Reached-or-not is asked of the answers, here.
    """
    split: dict[str, int] = {}
    for _name, _where, _statement, key in WORD_SITES:
        split[key] = split.get(key, 0) + 1
    assert split == {"scale": 36, "role": 19}, split
    assert len({n for n, _, _, _ in WORD_SITES}) == 40
    assert {key for _s, key in _A_WORD_COPIES} == set(split), (
        sorted(_A_WORD_COPIES), sorted(split))


@pytest.mark.parametrize("name", sorted({n for n, _, _, _ in WORD_SITES}))
def test_an_honest_word_is_accepted(name):
    """The half a rule of this kind gets wrong by being too strict."""
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


def test_a_word_bent_to_another_member_of_its_own_set_is_refused():
    """The teeth, and the forgery the membership rule cannot see.

    A token bent to a word the set does not have is refused before any rule
    runs. Bent to another real member it is a sentence a reader is handed
    assembled — "measure that column as continuous" where the answer's own
    reconciliation says it was declared binary — and nothing was asking.
    """
    refused = 0
    for name, where, _statement, key in WORD_SITES:
        row = SHAPES[name]
        was = _said(row["result"], where)[key]
        for member in _members_of(was["vocabulary"]):
            if member == was["token"]:
                continue
            forged = copy.deepcopy(row["result"])
            _said(forged, where)[key]["token"] = member
            with pytest.raises(Exception):                      # noqa: B017
                the_door_for(row["result"])(row["program"], forged)
            refused += 1
    assert refused == 165, refused


def test_the_record_a_word_is_read_against_is_the_one_it_names():
    """Indexed by the name its own sentence gives.

    Every program here declares its columns at a single scale, so a rule
    reading "any scale this problem declares" would refuse all of the
    above and be refusing because of the corpus. Given a second column
    declared at another scale, the two rules part company.
    """
    name, where, _statement, key = _a_site("scale")
    row = SHAPES[name]
    forged = copy.deepcopy(row["result"])
    program = copy.deepcopy(row["program"])
    word = _said(forged, where)[key]
    other = next(m for m in _members_of(word["vocabulary"])
                 if m != word["token"])
    program["statements"].append(
        {"kind": "variable", "predicate": "a_column_this_gap_is_not_about",
         "scale": other})
    word["token"] = other
    with pytest.raises(VerificationError):
        verify_gap_subjects(forged, program)


def test_the_record_a_word_is_read_against_is_not_the_answers_own():
    """The block records the same fact, and is not what is read.

    A way past is written FROM the reconciliation check, so the check is
    where the copy came from — and reading it there made this rule speak
    whenever the CHECK was the forgery: pointing at a gap that is honest,
    and standing in front of the reason a reader needs, which is that the
    record is not what the program declared. Every answer carrying a check
    carries a gap quoting it, so that reason had nothing left to speak
    for. The program is the copy no answer can edit.
    """
    name, where, _statement, key = _a_site("scale")
    row = SHAPES[name]
    forged = copy.deepcopy(row["result"])
    word = _said(forged, where)[key]
    other = next(m for m in _members_of(word["vocabulary"])
                 if m != word["token"])
    for check in forged["extensions"]["type_reconciliation"]["checks"]:
        check["declared_scale"] = other
    verify_gap_subjects(forged, row["program"])


def test_the_silence_is_real_where_the_word_has_no_record():
    """Silent where there is nothing to appeal to, as the said half is.

    A report can name a scale for a column the program declares no
    measurement type for, and inventing the roster out of the gap would be
    reading the authority off the thing being judged.
    """
    name, where, _statement, key = _a_site("scale")
    row = SHAPES[name]
    forged = copy.deepcopy(row["result"])
    program = copy.deepcopy(row["program"])
    word = _said(forged, where)[key]
    word["token"] = next(m for m in _members_of(word["vocabulary"])
                         if m != word["token"])
    for statement in program["statements"]:
        statement.pop("scale", None)
        statement.pop("domain", None)
    verify_gap_subjects(forged, program)


def test_the_space_that_gate_used_to_ask_sees_four_of_seventeen():
    """Why the gate above is a measurement, said as one.

    ``_bind``'s space keeps a vocabulary when its words live in
    ``themis.gaps``. That is a fact about the layering: ``measurement_note``
    and ``query_role`` are spoken by a gap report and their words live in
    the output layer, which no verifier may import. The space is still the
    right one for what ``_bind`` does — every slot this package can WRITE
    is classified — and the wrong one for whether a roster row is reached.
    Counted so the difference is a number and not a remark.
    """
    space = {slot for _statement, slot in
             statements_and_the_slots_they_declare()}
    carried = {statement["vocabulary"]
               for name in SHAPES
               for _w, statement in _statements_in(
                   (SHAPES[name]["result"] or {}).get("data_gap_report") or {})}
    inside = {name for name, owner in language.VOCABULARIES.items()
              if any(owner is held for held in vars(gaps).values())}
    assert len(carried) == 17, sorted(carried)
    assert len(carried & inside) == 4, sorted(carried & inside)
    assert "scale" in space and "role" not in space


def _statements_in(node, path=()):
    """Every statement under a node, for the counting above."""
    if isinstance(node, dict):
        if isinstance(node.get("vocabulary"), str) and "token" in node:
            yield path, node
        for key, value in node.items():
            yield from _statements_in(value, (*path, str(key)))
    elif isinstance(node, list):
        for item in node:
            yield from _statements_in(item, (*path, "[]"))


def test_the_role_a_gap_gives_is_the_side_of_the_question_it_names():
    """What the question decides, and what it does not.

    The predicate intervened on IS the exposure and the one asked
    about IS the outcome, so either of them called anything else
    sends a reader to a variable that is missing nothing. The set's
    other two words are properties of the GRAPH, so about any other
    name what the question says is that it is neither of its own two
    — which is a positive answer and not a silence.
    """
    name, _where, _statement, _key = _a_site("role")
    program = SHAPES[name]["program"]
    intervention, target = _the_question_asked(program)
    assert intervention and target
    assert _the_role_the_question_gives(program, intervention) == {
        "exposure"}
    assert _the_role_the_question_gives(program, target) == {"outcome"}
    others = _the_role_the_question_gives(program, "a_third_column")
    assert others == set(_members_of("query_role")) - {"exposure",
                                                       "outcome"}
    assert others


def test_a_question_that_spells_only_half_of_itself_is_not_appealed_to():
    """Both sides or neither, which is not a convenience.

    Reading a question that names an intervention and no target would
    make every variable that is not that intervention one the question
    gives no role — a claim, and the wrong one, since what it actually
    says about them is nothing.
    """
    name, where, _statement, key = next(
        (site for site in WORD_SITES if site[3] == "role"))
    row = SHAPES[name]
    forged = copy.deepcopy(row["result"])
    program = copy.deepcopy(row["program"])
    word = _said(forged, where)[key]
    word["token"] = next(m for m in _members_of(word["vocabulary"])
                         if m != word["token"])
    for statement in program["statements"]:
        if isinstance(statement.get("query"), dict):
            statement["query"].pop("target", None)
    verify_gap_subjects(forged, program)
