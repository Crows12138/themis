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

A HOLE IS ONE FACT WHICHEVER HALF IT TRAVELS IN. Where the record names
nothing, a producer writes the hole as a word, the stand-in its sentence
says instead, and a rule reading only ``said`` read every hole except
those: any of the 996 names below could become a stand-in and pass. And a
population hole is its ROLE'S: read against every population the program
names, a source written as the target was the answer carried backwards.
"""
from __future__ import annotations

import copy
import json
import pathlib
from types import SimpleNamespace

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.kernel import _premises_of
from themis.verifier import VerificationError
from themis import gaps, language
from themis.output import data_gap_report
from themis.types import Atom, ConstTerm, DerivationStep
from themis.verifier.gap_claim_rules import (
    _ABOUT_WHAT_IT_NAMES,
    _COPIED_FROM,
    _SPELT_AGAIN_ON_THE_GAP,
    _STANDS_IN,
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
    _PRINTED_FROM,
    _printed_from,
    _the_question_asked,
    _the_role_the_question_gives,
    _the_transport_formula_as_printed,
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
#: this file used to look at: one of the slots below never sits under
#: ``describes`` at all — the methods already in hand hang off an
#: alternative path — so a walk written to the old roster's shape would
#: have reported it as absent.
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
    # 18 more intervention, 26 more what and 6 more target: the eight rows brought when the
    # identifier began answering a query conditioning on a descendant of the treatment.
    # 2 more assumptions and 4 more intervention: the row brought when a decomposition
    # asked within a stratum was evaluated within it.
    # 4 more intervention: the row brought when a question was refused because the
    # stratum it names holds too few rows to answer it on.
    # 14 count, a slot this roster had no entry for: twelve caveats saying how many
    # intervals bound one quantity, two saying how many instruments the graph offered.
    # 12 fallback, the other slot it had no entry for: the interval a question falls
    # back to, offered by name on its own way past. The roster was one rule over, as
    # the set of kinds that have one, which is what the tier rule asks and a column
    # short of the word.
    assert split == {
        "assumptions": 38, "method": 63, "what": 113,
        "methods": 73, "population": 16, "source": 10,
        "kind": 11, "target": 39, "count": 14,
        "intervention": 592, "treatment": 21, "outcome": 18,
        "latent": 4, "z": 5, "w": 3, "fallback": 12,
    }, split
    assert len(SITES) == 1032, len(SITES)


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
    assert refused == 1032, refused


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
    # 2 more: the row brought when a decomposition asked within a stratum was evaluated
    # within it lists the assumptions of both its branches, the natural effects' and the
    # controlled one's.
    assert checked == 111, checked


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

    Five kinds now, and the fifth is the one this paragraph was written
    against. A NUMBER contains no identifier to be wrong about, which is
    true and is the name rule's answer; it was read as the copy rule's
    answer too. What no roster can hold is a RENDERED number, where a
    formatting step sits between the value and its spelling. A ``count``
    is ``str`` of a length, and the list it is the length OF is on the
    same envelope.
    """
    def kind(statement, key):
        if holds_a_name(statement, key):
            return "name"
        return _IN_ITS_SENTENCE.get((statement, key)) or _NOT_NAMES[key]

    assert {kind(s, k) for s, k in _COPIED_FROM} == {
        "vocabulary", "expression", "domain", "name", "number"}
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
# the record it was read from — asked of a fact about what its sentence
# names, in both halves. The rule that asks it is ``verify_gap_subjects``,
# because the record such a fact is held to is the program's declaration
# and that door is where the program is.


def _about_entry(statement, key):
    """The record for this slot IN THIS STATEMENT, or the general one."""
    return (_ABOUT_WHAT_IT_NAMES.get((statement, key))
            or _ABOUT_WHAT_IT_NAMES.get((None, key)))


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
    if _about_entry(statement, key) is not None
)

#: And every ``said`` it speaks for, by the same walk over the other half.
SAID_SITES = sorted(
    (name, where, statement or "", key)
    for name, pair in SHAPES.items()
    for where, statement, said in every_said_mapping(
        (pair["result"] or {}).get("data_gap_report") or {})
    for key in said
    if _about_entry(statement, key) is not None
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

    Counted in both halves, since the table is read in both: the known
    noise a measurement field names, which field, and where a threshold
    cuts travel as ``said``.
    """
    split: dict[str, int] = {}
    for _name, _where, _statement, key in WORD_SITES:
        split[key] = split.get(key, 0) + 1
    assert split == {"scale": 36, "role": 19}, split
    assert len({n for n, _, _, _ in WORD_SITES}) == 40
    said: dict[str, int] = {}
    for _name, _where, _statement, key in SAID_SITES:
        said[key] = said.get(key, 0) + 1
    assert said == {"field": 19, "phrase": 19, "cut": 2}, said
    assert {key for _s, key in _ABOUT_WHAT_IT_NAMES} == set(split) | set(
        said), (sorted(_ABOUT_WHAT_IT_NAMES), sorted(split), sorted(said))


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


# ------------------------------------ and the word a hole holds when nothing names it


def _stand_ins_written(gaps_) -> dict:
    return {(str(line.sentence), slot): word
            for gap in gaps_ for line in gap.describes
            for slot, word in (line.words or {}).items()}


def test_a_stand_in_is_the_word_its_producer_writes_when_nothing_names_the_hole():
    """Asked of the producers with records that name nothing, not read off
    the corpus: the corpus carries one stand-in, and a table held to one
    example is a statement about that example."""
    asks_a_curve = SimpleNamespace(
        statements=(),
        extensions={"ambiguities": [{"kind": "dose_response_query"}]})
    route = {"transportable": True,
             "adjustment_set": [{"predicate": "z", "args": []}]}
    # The two asks are grounded in the formula step, so the chain that
    # carries one comes with the route.
    chain = (DerivationStep(rule="transport_formula", inputs={},
                            output="P*(y | do(x)) = ...", label="formula_0"),)
    written = {
        **_stand_ins_written(data_gap_report._classify_transport_assumptions(
            {"transport_identification": {"sources": [route]}})),
        **_stand_ins_written(data_gap_report._transport_source_data_needs(
            route, chain, chain[0], target_pop=None)),
        **_stand_ins_written(data_gap_report._classify_dose_response_data(
            asks_a_curve, SimpleNamespace(query=None), ())),
    }
    assert written == {hole: language.state(word)
                       for hole, word in _STANDS_IN.items()}


def _a_report_saying(sentence, slot, word):
    return {"data_gap_report": {"gaps": [{"describes": [
        {"sentence": sentence, "words": {slot: word}}]}]}}


def _atom(name):
    return Atom(predicate=name, args=(ConstTerm(name="u"),))


# --- and the third question: the gap's own other sentences --------------------


#: Every (answer, gap, where, statement, slot) the third table speaks for,
#: found by the rule's own walk. A denominator per slot, so that a corpus
#: which stopped carrying one of these families says so here rather than
#: reading as a rule that still has teeth.
SPELT_SITES = sorted(
    (name, index, where, statement or "", key)
    for name, pair in SHAPES.items()
    for index, gap in enumerate(
        ((pair["result"] or {}).get("data_gap_report") or {}).get("gaps")
        or ())
    for where, statement, said in every_said_mapping(gap, ("gaps", str(index)))
    for key in said
    if _SPELT_AGAIN_ON_THE_GAP.get((statement or "", key)) is not None
)

#: How many of those have another sentence on the same gap to be read
#: against. The rest are the silence this rule keeps on purpose.
SPELT_WITH_A_PARTNER = 25


def _partnered():
    for site in SPELT_SITES:
        name, index, where, statement, key = site
        result = SHAPES[name]["result"]
        gap = result["data_gap_report"]["gaps"][index]
        _says, slots = _SPELT_AGAIN_ON_THE_GAP[(statement, key)]
        elsewhere = {
            str(value)
            for w, _s, said in every_said_mapping(gap, ("gaps", str(index)))
            for k, value in said.items()
            if str(k) in slots and (w, str(k)) != (where, key)
        }
        if elsewhere:
            yield site


PARTNERED = sorted(_partnered())


def test_the_second_spellings_this_rule_speaks_for():
    """The denominator, per slot. Four families, each read off the producer
    that writes it rather than off values that happened to agree."""
    split: dict[str, int] = {}
    for _name, _index, _where, _statement, key in PARTNERED:
        split[key] = split.get(key, 0) + 1
    assert sum(split.values()) == SPELT_WITH_A_PARTNER, split
    assert split == {
        "drop": 4, "interval": 2, "k": 5, "level": 2, "levels": 2,
        "lost": 2, "skipped": 2, "wanted": 2, "winner": 2, "won": 2,
    }, split


def test_the_table_is_keyed_on_the_statement_and_never_on_the_slot():
    """A slot's meaning is its sentence's, and here that is not a nicety.

    ``level`` is a confidence level in the sentence about an
    Anderson-Rubin set and a dose in the one about a bridge going
    negative. A table filed by the commoner meaning would not merely miss
    the other; it would refuse it, because the other gap says that number
    once.
    """
    for statement, slot in _SPELT_AGAIN_ON_THE_GAP:
        assert statement, slot
        assert slot
    filed = {slot for _statement, slot in _SPELT_AGAIN_ON_THE_GAP}
    assert "level" in filed
    assert sum(1 for s, k in _SPELT_AGAIN_ON_THE_GAP if k == "level") == 2


@pytest.mark.parametrize("site", PARTNERED,
                         ids=lambda s: f"{s[0]}|{s[3]}|{s[4]}")
def test_an_honest_gap_says_the_same_thing_in_both_sentences(site):
    name, _index, _where, _statement, _key = site
    verify_gap_quotes(SHAPES[name]["result"], CONTEXTS[name])


@pytest.mark.parametrize("site", PARTNERED,
                         ids=lambda s: f"{s[0]}|{s[3]}|{s[4]}")
def test_a_spelling_that_disagrees_with_the_gaps_other_is_refused(site):
    """One sentence edited, and the gap now says two things about one
    occasion. The reader meets whichever sentence they read first."""
    name, _index, where, _statement, key = site
    forged = copy.deepcopy(SHAPES[name]["result"])
    _said(forged, where)[key] = str(_said(forged, where)[key]) + "_forged"
    with pytest.raises(VerificationError,
                       match="another of its own sentences"):
        verify_gap_quotes(forged, CONTEXTS[name])


_ALONE = {"data_gap_report": {"gaps": [{
    "kind": "proxy_coarsening_undeclared",
    "describes": [{"sentence": "which_levels_are_one_state_is_not_in_the_data",
                   "said": {"k": "2"}}],
}]}}


def test_the_rule_is_silent_where_the_gap_says_a_thing_only_once():
    """There is nothing to appeal to, and a rule that spoke here would be
    refusing a sentence for being alone."""
    verify_gap_quotes(copy.deepcopy(_ALONE), _NAMES_NOTHING)


def test_two_gaps_do_not_lend_each_other_their_spellings():
    """The record being appealed to is THIS gap, which is why the question
    is asked of each in turn. Two gaps each saying a thing once are two
    sentences that are alone, not one pair."""
    report = copy.deepcopy(_ALONE)
    second = copy.deepcopy(report["data_gap_report"]["gaps"][0])
    second["describes"][0]["said"]["k"] = "9"
    report["data_gap_report"]["gaps"].append(second)
    verify_gap_quotes(report, _NAMES_NOTHING)


#: A context whose every record this rule reads names nothing, and one
#: whose every record names something.
_NAMES_NOTHING = SimpleNamespace(query=None, selection_nodes=())
_NAMES_ALL = SimpleNamespace(
    query=SimpleNamespace(target_population="clinic",
                          intervention=SimpleNamespace(atom=_atom("x")),
                          target=SimpleNamespace(atom=_atom("y"))),
    selection_nodes=(SimpleNamespace(source_population="trial"),))


@pytest.mark.parametrize("hole", sorted(_STANDS_IN), ids="|".join)
def test_a_stand_in_is_true_only_where_its_record_names_nothing(hole):
    """A stand-in says the record gives this hole no name, which is a
    claim about the record like any name is."""
    forged = _a_report_saying(*hole, language.state(_STANDS_IN[hole]))
    verify_gap_quotes(forged, _NAMES_NOTHING)
    with pytest.raises(VerificationError, match="has no name"):
        verify_gap_quotes(forged, _NAMES_ALL)


def test_a_copied_hole_written_as_any_other_word_is_refused():
    """Every name on the corpus, rewritten as each stand-in and as a word
    of another set. None of those is the stand-in its sentence says where
    its record names something, which on this corpus is every one of
    them."""
    words = [language.state(member) for member in gaps.Unnamed]
    words.append(language.state(
        data_gap_report.Window.BASELINE_AND_TWO_FOLLOW_UPS))
    refused = 0
    for name, where, _statement, key in SITES:
        row = SHAPES[name]
        for word in words:
            forged = dict(row["result"])
            forged["data_gap_report"] = copy.deepcopy(
                row["result"]["data_gap_report"])
            said = _said(forged, where)
            del said[key]
            line = (_said(forged, where.rsplit(".", 1)[0]) if "." in where
                    else forged["data_gap_report"])
            if not said:
                del line["said"]
            line.setdefault("words", {})[key] = dict(word)
            with pytest.raises(VerificationError,
                               match="where it quotes|has no name"):
                verify_gap_quotes(forged, CONTEXTS[name])
            refused += 1
    assert refused == 1032 * 6, refused


def test_the_one_stand_in_the_corpus_carries_is_held_at_the_door():
    """A transport with no difference declared between populations, whose
    one route comes from a source nobody named."""
    sites = [(name, where, statement, key)
             for name, pair in SHAPES.items()
             for where, statement, words, _said in every_word_mapping(
                 (pair["result"] or {}).get("data_gap_report") or {})
             for key in words if _entry(statement, key) is not None]
    assert len(sites) == 1, sites
    name, where, _statement, key = sites[0]
    row = SHAPES[name]
    the_door_for(row["result"])(row["program"], row["result"])
    refused = 0
    for member in gaps.Unnamed:
        forged = copy.deepcopy(row["result"])
        word = _said(forged, where)[key]
        if word["token"] == str(member):
            continue
        word["token"] = str(member)
        with pytest.raises(VerificationError, match="which here is"):
            the_door_for(row["result"])(row["program"], forged)
        refused += 1
    assert refused == 4, refused


def test_a_population_hole_is_read_against_its_own_role():
    """The direction an answer is carried in. Read against every population
    the program names, a source written as the target passed every door."""
    swapped = 0
    for name, where, statement, key in SITES:
        role = _entry(statement, key)[0]
        if "population" not in role or "domains" in role:
            continue
        row = SHAPES[name]
        block = row["result"]["extensions"]["transport_identification"]
        others = ([block.get("target_population")] if "source" in role
                  else [s.get("source_population") for s in block["sources"]])
        for other in others:
            forged = copy.deepcopy(row["result"])
            said = _said(forged, where)
            if other is None or other == said[key]:
                continue
            said[key] = other
            with pytest.raises(VerificationError, match="never did"):
                the_door_for(row["result"])(row["program"], forged)
            swapped += 1
    assert swapped == 42, swapped


_CURVE = "the_question_asks_for_a_dose_response_curve"


def test_a_curve_names_every_role_the_question_is_read_for():
    """Two readings of which field holds the question's intervention and
    target: the producer's, and the one its stand-in is judged against.

    Where the second finds a name the first must write it — a stand-in
    there hands a reader a placeholder where the question had the name,
    and is refused for it. A proximal effect calls the two ``treatment``
    and ``outcome``, and the producer read past them. Asked of a question
    of every class the corpus holds, flagged for a curve, because no answer
    on the corpus carries a curve for most of them.

    What is left is the other direction, and a number: a cause and an
    association name the curve's roles by fields the question's roles are
    not read from, so there the name is written and nothing reads it.
    """
    asks_a_curve = SimpleNamespace(
        statements=(),
        extensions={"ambiguities": [{"kind": "dose_response_query"}]})
    one_of_each = {}
    for name in sorted(CONTEXTS):
        query = getattr(CONTEXTS[name], "query", None)
        if query is not None:
            one_of_each.setdefault(type(query).__name__, CONTEXTS[name])
    unread = set()
    for kind, context in sorted(one_of_each.items()):
        (gap,) = data_gap_report._classify_dose_response_data(
            asks_a_curve, SimpleNamespace(query=context.query), ())
        line = gap.describes[0]
        assert str(line.sentence) == _CURVE, line
        said, words = line.said or {}, line.words or {}
        for slot in ("intervention", "target"):
            known = _COPIED_FROM[(_CURVE, slot)][1]({}, context)
            if known:
                assert said.get(slot) in known, (kind, slot, said, words)
            elif slot in said:
                unread.add((kind, slot))
    assert unread == {("AssocQuery", "intervention"), ("AssocQuery", "target"),
                      ("CauseQuery", "intervention"), ("CauseQuery", "target")}, (
        sorted(unread))
    assert len(one_of_each) == 10, sorted(one_of_each)
# --- and the fourth question: a slot holding a whole printing ---------------


_STRATIFIED = "the_source_populations_stratified_conditional_is_missing"

#: Every (answer, where, statement, slot) the fourth table speaks for,
#: found by the rule's own walk.
PRINTED_SITES = sorted(
    (name, where, statement or "", key)
    for name, pair in SHAPES.items()
    for where, statement, said in every_said_mapping(
        (pair["result"] or {}).get("data_gap_report") or {})
    for key in said
    if _printed_from(statement, key) is not None
)


def _printing_for(site):
    """What the rule's own printer hands back for this sentence."""
    name, where, statement, key = site
    result = SHAPES[name]["result"]
    _says, printer = _printed_from(statement, key)
    return printer(result, CONTEXTS[name], _said(result, where))


def test_an_expression_is_read_by_the_question_membership_cannot_put():
    """The root cause, asserted where it can be argued with.

    ``formula`` is filed as an expression and correctly so: it is not a
    name, and the name rule cannot read it. That classification was doing
    double duty as the reason NOTHING read it — and it holds a whole
    sentence, which the three questions before this one have no word to
    ask about. One statement declares the slot; a second one arriving
    fails here rather than going quietly unread.
    """
    assert _NOT_NAMES["formula"] == "expression"
    assert not holds_a_name(_STRATIFIED, "formula")
    assert _COPIED_FROM.get((_STRATIFIED, "formula")) is None
    assert _SPELT_AGAIN_ON_THE_GAP.get((_STRATIFIED, "formula")) is None
    assert _printed_from(_STRATIFIED, "formula") is not None
    assert {statement
            for statement, slot in statements_and_the_slots_they_declare()
            if slot == "formula"} == {_STRATIFIED}
    for statement, slot in _PRINTED_FROM:
        assert statement and slot


def test_the_printings_this_rule_speaks_for():
    """The denominator, and the one that has to be counted rather than
    described.

    A second hand can stop recognising the first one's work, and when it
    does this rule goes SILENT rather than loud. So what is pinned is not
    that the printer exists but how many of the corpus's sentences it
    still finds a record for.
    """
    split: dict[str, int] = {}
    for _name, _where, _statement, key in PRINTED_SITES:
        split[key] = split.get(key, 0) + 1
    assert split == {"formula": 8}, split
    assert sum(1 for site in PRINTED_SITES if _printing_for(site)) == 8


def test_the_second_hand_prints_what_the_first_one_printed():
    """The two hands, on one record.

    The rule rests on a printing of this package's own making agreeing
    with the one on the envelope, so the agreement is pinned against the
    runtime's printer rather than against a string written out twice.
    """
    from themis.runtime.transport import transport_formula_repr
    y, x = _atom("belly_fat_loss"), _atom("running")
    for z in ((_atom("age"),), (_atom("age"), _atom("sex"))):
        names = ", ".join(a.predicate for a in z)
        assert _the_transport_formula_as_printed(
            y.predicate, x.predicate, names) == transport_formula_repr(y, x, z)


@pytest.mark.parametrize("site", PRINTED_SITES,
                         ids=lambda s: f"{s[0]}|{s[3]}")
def test_an_honest_printing_is_accepted(site):
    name = site[0]
    verify_gap_quotes(SHAPES[name]["result"], CONTEXTS[name])


def test_an_estimand_printed_some_other_way_is_refused():
    """Three gross lies per sentence — a forged spelling, an empty string,
    a set of variables this route never adjusted for."""
    refused = 0
    for site in PRINTED_SITES:
        name, where, _statement, key = site
        honest = str(_said(SHAPES[name]["result"], where)[key])
        for lie in (honest + "_forged", "",
                    honest.replace(", ", ", stranger, ")):
            assert lie != honest
            forged = copy.deepcopy(SHAPES[name]["result"])
            _said(forged, where)[key] = lie
            with pytest.raises(VerificationError,
                               match="sends a reader after"):
                verify_gap_quotes(forged, CONTEXTS[name])
            refused += 1
    assert refused == 24, refused


def test_the_record_is_the_source_this_sentence_names():
    """Two sources adjust for what each was declared to differ in, so the
    estimand a gap about one of them prints is that one's.

    Swapped between the two sentences, every word is still on the
    envelope and both sentences now send a reader after the other
    source's quantity. This is what the population beside the estimand is
    for, and why one roster per answer would have taken the swap.
    """
    by_answer: dict[str, list] = {}
    for name, where, _statement, key in PRINTED_SITES:
        by_answer.setdefault(name, []).append((where, key))
    pairs = sorted((name, sites) for name, sites in by_answer.items()
                   if len(sites) == 2)
    assert pairs, "no answer carrying two of these sentences to swap"
    for name, ((one, key_one), (two, key_two)) in pairs:
        forged = copy.deepcopy(SHAPES[name]["result"])
        first, second = _said(forged, one)[key_one], _said(forged, two)[key_two]
        assert first != second, (name, first)
        _said(forged, one)[key_one] = second
        _said(forged, two)[key_two] = first
        with pytest.raises(VerificationError, match="sends a reader after"):
            verify_gap_quotes(forged, CONTEXTS[name])


def test_the_silence_is_real_where_the_route_prints_something_else():
    """A route whose formula is not the one this package prints is a fault
    in the thing being quoted, and the rule holding a route to the chain
    is the one to speak about it. Refusing here would refuse a gap's
    sentence for somebody else's mistake.
    """
    name, where, _statement, key = PRINTED_SITES[0]
    altered = copy.deepcopy(SHAPES[name]["result"])
    for route in altered["extensions"]["transport_identification"]["sources"]:
        if route.get("formula_repr") is not None:
            route["formula_repr"] = "P*(y | do(x)) = something else entirely"
    _said(altered, where)[key] = "anything at all"
    verify_gap_quotes(altered, CONTEXTS[name])


def test_the_silence_is_real_where_the_question_has_no_two_ends():
    """The two ends are the question's, and a question with none leaves
    the printer nothing to print from."""
    name, where, _statement, key = PRINTED_SITES[0]
    altered = copy.deepcopy(SHAPES[name]["result"])
    _said(altered, where)[key] = "anything at all"
    verify_gap_quotes(altered, _NAMES_NOTHING)
