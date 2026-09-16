"""A token names a sentence, and the facts beside it are what it needs.

A sentence does not cross the process boundary as text. What crosses is a
token naming a template and the occasion's facts for that template's holes,
and a surface that knows the reader's language assembles the two. So the
pair is one claim in two halves, and until now nothing asked whether the
halves agree.

Neither way of disagreeing shows up as a failure, because
``language.assemble`` is built not to fail: a hole this occasion carried
nothing for is rendered as a stated absence, and a fact the template has no
hole for is dropped without a word. Both were reachable through both public
doors on the corpus this repository really produces.

The question had been asked once — statically, over ``DataGap(...)`` call
sites, for the one table keyed on a gap's KIND
(``test_what_having_it_would_buy_is_the_species_not_the_occasion``). Four
other carriers were never asked, the scan reaches only the sites that name
their species with a literal, and a static scan cannot see an envelope
somebody else wrote. That is the eighth time in this line that coverage
turned out to be a function of where the author was standing, and the
answer is the same one: ask it of the envelope, at every carrier, from the
tables the sentences are actually written in.

What this gate holds, then:

- every statement the corpus carries is accepted, at the strongest door
  that reads its answer
- a fact with no hole, a hole with no fact, and a token swapped for one
  whose sentence wants something else are each refused at the door, and
  each refused by this rule when it is asked on its own — two claims,
  because a forgery can be a lie in more than one way at once and the
  rule a caller hears is then the order the passes run in
- the carrier table names every site in the contract where a property's
  own declared domain is one of these vocabularies — so which sites are
  covered is measured against the schema, not remembered
- a table that is partial on purpose has its other half read as a
  declaration: a kind in ``NOTHING_FILLS`` has no sentence, so it has no
  hole, so a fact beside it goes nowhere
- and the producer side of the same claim: a route offered where there is
  no occasion may not name one.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis import gaps, language
from themis.input.syntactic_validator import SyntacticError
from themis.refusals import REFUSED
from themis.runtime.iv_words import Premise
from themis.types import GapKind
from themis.verifier import VerificationError
from themis.verifier.program_copy_rules import query_of
from themis.verifier.rules import _SIMPLE_RULES, _STEP_REF_RULES
from themis.verifier.statement_rules import (
    _CARRIERS,
    _DECLARED_SILENT,
    _PREMISE_SETTLED_BY,
    _THROUGH_AN_INSTRUMENT,
    _the_premise_the_derivation_ran,
    verify_statements_carry_their_facts,
    verify_statements_repeat_what_decided_them,
)

from . import schema_walk
from .answer_corpus import the_door_for, verify_honestly

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

#: Every statement the corpus carries, and how many of the envelope's
#: sentences each carrier accounts for. Pinned so a narrowing of the walk
#: shows up as a number rather than as a quieter gate. One statement was
#: added by a refresh: the stored framing request over a single ask began
#: carrying that ask's species as its note, a ``gap_says`` statement.
#: 16 went with another: six answers lost a Balke-Pearl
#: interval taken around a node that is not an instrument with nothing
#: conditioned, and what it and its gap sentence said. Four came with a
#: refresh of the joint general-ID answer, from what its producer had grown
#: since the row was stored: a gap about the second treatment's definition
#: (what it describes, what it asks for, what it says) and the bootstrap
#: line on its ledger. Three left when two refusals stopped carrying a copy
#: of the reason the identification layer files on its own block: the two
#: reasons, and the one factor under the missing-data one.
REACHED = 5086
PER_CARRIER = {
    "gap_routes": 1193,
    # These three and the ledger below moved together, by eight and eight
    # and eight and one, when a targeted corpus refresh picked up producer
    # drift the stored rows predated: eight more gaps and one more ledger
    # entry across six rows. Four carriers of the same eight gaps is what
    # a per-carrier pin is for — a narrowing shows up as one of them
    # falling while the others hold. They moved by one each again with the
    # joint general-ID refresh.
    "gap_describes": 1149,
    "gap_if_provided": 975,
    "gap_says": 676,
    "assumption_claim": 509,
    # The two the sweep could not see while its range was the table's own
    # contents. Both were already reached three and thirty-six times as a
    # statement quoted INSIDE another sentence's hole, which is the shape
    # that makes a missing carrier so quiet: the vocabulary was present in
    # the totals all along, and the block that carries it on its own was
    # the part nothing asked.
    "measurement_scale": 72,
    "refusal_sentence": 39,
}


def _statements(result) -> list[tuple[tuple, str, str]]:
    """Every statement on one envelope as ``(where, spelling, vocabulary)``.

    An index path rather than a shape path, because a forgery has to be
    planted at ONE of them. Written here rather than imported from the rule
    for the reason every gate in this repository writes its own walk: a
    gate that finds a rule's statements with the rule's own code agrees
    with it about which statements there are, which is the only thing this
    could get wrong.
    """
    out: list[tuple[tuple, str, str]] = []

    def walk(node, path: list) -> None:
        if isinstance(node, dict):
            shape = ".".join(k for k in path if not isinstance(k, int))
            if isinstance(node.get("vocabulary"), str) and "token" in node:
                out.append((tuple(path), "token", node["vocabulary"]))
            carrier = _CARRIERS.get(shape)
            if carrier is not None and node.get(carrier[0]):
                out.append((tuple(path), carrier[0], carrier[1]))
            for key, value in node.items():
                walk(value, [*path, key])
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, [*path, "[]", index])

    walk(result, [])
    return out


def _at(result, path: tuple):
    node = result
    for key in path:
        if key != "[]":
            node = node[key]
    return node


def _words(vocabulary: str, token: str):
    owner = language.VOCABULARIES[vocabulary]
    if isinstance(owner, dict):
        return owner.get(token)
    return next((m.words for m in owner if str(m) == token), None)


def _members(vocabulary: str) -> list[str]:
    owner = language.VOCABULARIES[vocabulary]
    return [str(m) for m in owner]


def _holes(vocabulary: str, token: str) -> set[str]:
    return language.holes(_words(vocabulary, token) or {})


def _facts(entry) -> set[str]:
    return {str(k) for half in ("said", "words")
            for k in (entry.get(half) or ())}


# --- what the corpus really carries -------------------------------------------


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_honest_answer_says_its_sentences_whole(shape):
    """The denominator. A rule that refused an answer this system produces
    would be worse than the hole it closes."""
    row = SHAPES[shape]
    verify_honestly(row["program"], row["result"])


def test_the_walk_reaches_what_it_claims_to():
    """A walk that quietly stopped early would pass every forgery below by
    never arriving at it, so its own reach is stated first — and stated per
    vocabulary, because a narrowing that lost one entirely would leave the
    total looking much the same. Two of the counts are there because the
    sweep that decides which sites exist used to be bounded by the table it
    checks, and both vocabularies were already in this total as statements
    quoted inside other sentences' holes while the blocks carrying them on
    their own went unread."""
    seen: dict[str, int] = {}
    for shape in sorted(SHAPES):
        for _, _, vocabulary in _statements(SHAPES[shape]["result"]):
            seen[vocabulary] = seen.get(vocabulary, 0) + 1
    assert sum(seen.values()) == REACHED, sum(seen.values())
    assert {k: v for k, v in seen.items() if k in PER_CARRIER} == PER_CARRIER


def test_every_vocabulary_the_corpus_names_is_one_this_build_declares():
    """The rule passes over a token it cannot resolve, which is
    ``language.spelt``'s design and not a hole — a producer may name a
    member of somebody else's set. What would be a hole is the whole
    envelope going unread because nothing registered the tables, and that
    failure is silent: it looks exactly like an envelope with nothing
    wrong."""
    unknown = {vocabulary
               for shape in SHAPES
               for _, _, vocabulary in _statements(SHAPES[shape]["result"])
               if vocabulary not in language.VOCABULARIES}
    assert unknown == set()


# --- the three ways a token and its facts can disagree ------------------------


def _forge(shape, make):
    """Plant one lie per statement and count what comes back.

    A shape the contract will not hold is counted apart from a shape a
    rule refused. One carrier sits on a closed record with no half to
    carry facts in, so the fact-with-no-hole lie cannot be planted there
    at all — and counting the validator's refusal as this rule's would
    report the rule as holding a site it was never asked about.

    Two claims, and each asked where nothing else can answer for it. The
    door says whether the lie gets through, and the rule is called on its
    own to say whether THIS rule is what stops it — because a forgery can
    be a lie in more than one way at once, and which rule a caller hears
    is then the order the kernel runs its passes. Relabelling a gap's
    kind is such a forgery: it makes the sentence promise facts nobody
    supplied, and it also changes whether the envelope says a point is
    still available, so the tier contradicts it too.
    """
    row = SHAPES[shape]
    refused = survived = by_this_rule = unplantable = 0
    for path, spelling, vocabulary in _statements(row["result"]):
        forged = copy.deepcopy(row["result"])
        entry = _at(forged, path)
        if not make(entry, spelling, vocabulary):
            continue
        try:
            the_door_for(row["result"])(row["program"], forged)
        except SyntacticError:
            unplantable += 1
            continue
        except Exception:                       # noqa: BLE001
            refused += 1
        else:
            survived += 1
        try:
            verify_statements_carry_their_facts(forged)
        except VerificationError:
            by_this_rule += 1
    return refused, survived, by_this_rule, unplantable


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_a_fact_the_sentence_has_no_hole_for_is_refused(shape):
    """The direction with no symptom at all. The assembler puts the holes
    it knows about into the template and drops everything else, so a fact
    added here reaches no reader and leaves no trace."""

    def make(entry, _spelling, _vocabulary):
        entry.setdefault("said", {})["a_fact_with_no_hole"] = "7"
        return True

    refused, survived, mine, unplantable = _forge(shape, make)
    assert survived == 0
    assert mine == refused
    # The scale carrier's record has no half to put a fact in, so the
    # contract refuses the shape before any rule reads it. One per check
    # on the row, and pinned so a site quietly becoming unforgeable here
    # shows as a number rather than as a smaller denominator.
    assert unplantable == len(
        ((SHAPES[shape]["result"].get("extensions") or {})
         .get("type_reconciliation") or {}).get("checks") or [])


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_a_hole_this_occasion_did_not_fill_is_refused(shape):
    """The other direction, which does have a symptom and shows it to the
    reader rather than to anyone who could fix it: the hole renders as a
    stated absence in the middle of the sentence."""

    def make(entry, _spelling, _vocabulary):
        carried = _facts(entry)
        if not carried:
            return False
        key = sorted(carried)[0]
        for half in ("said", "words"):
            (entry.get(half) or {}).pop(key, None)
        return True

    refused, survived, mine, unplantable = _forge(shape, make)
    assert survived == 0
    assert mine == refused
    assert unplantable == 0


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_a_sentence_relabelled_to_another_is_refused(shape):
    """The worst of the three, because both halves of it are silent at
    once: the facts this occasion had go nowhere, and the sentence the
    reader is shown promises facts nobody supplied."""

    def make(entry, spelling, vocabulary):
        want = _holes(vocabulary, str(entry[spelling]))
        other = next((m for m in _members(vocabulary)
                      if m != str(entry[spelling])
                      and _holes(vocabulary, m) != want), None)
        if other is None:
            return False
        entry[spelling] = other
        return True

    refused, survived, mine, unplantable = _forge(shape, make)
    assert survived == 0
    assert mine == refused
    assert unplantable == 0


def test_the_reader_is_told_which_half_was_wrong():
    """Two failures with one cause are still two facts, and the sentence a
    reader gets says which of them happened."""
    result = {"data_gap_report": {"gaps": [{
        "kind": str(GapKind.MISSING_DISTRIBUTION),
        "describes": [{"sentence": str(gaps.Sentence.TIAN_FOUND_A_HEDGE),
                       "said": {"nothing_wants_this": "1"}}]}]}}
    with pytest.raises(VerificationError, match="no hole for any of them"):
        verify_statements_carry_their_facts(result)

    holed = next(t for t in gaps.DESCRIBES if language.holes(gaps.DESCRIBES[t]))
    result["data_gap_report"]["gaps"][0]["describes"] = [{"sentence": holed}]
    with pytest.raises(VerificationError, match="promises a fact and does"):
        verify_statements_carry_their_facts(result)


# --- and the list they are handed together ------------------------------------


def _lists_of_statements(result) -> list[tuple[tuple, list]]:
    """Every list whose items are all statements, and where it sits.

    Written here for the same reason ``_statements`` is: the claim under
    test is about a list rather than about any one statement, and a gate
    that finds the rule's lists with the rule's own code agrees with it
    about which lists there are.
    """
    out: list[tuple[tuple, list]] = []

    def walk(node, path: list) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, [*path, key])
        elif isinstance(node, list):
            if node and all(isinstance(item, dict)
                            and isinstance(item.get("vocabulary"), str)
                            and "token" in item for item in node):
                out.append((tuple(path), node))
            for index, value in enumerate(node):
                walk(value, [*path, "[]", index])

    walk(result, [])
    return out


def test_no_list_the_corpus_ships_says_one_sentence_twice():
    """The standing statement of what the rule asks, against what ships.

    The second number is the denominator the case is really about: a list
    of one cannot repeat anything, so only these can carry the forgery a
    reader would meet without any of it being planted by hand.
    """
    lists = [(shape, where, items) for shape in sorted(SHAPES)
             for where, items in _lists_of_statements(SHAPES[shape]["result"])]
    for shape, where, items in lists:
        for index, item in enumerate(items):
            assert item not in items[:index], (shape, where, item)
    assert sum(1 for _, _, items in lists if len(items) > 1) == 21


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_a_sentence_handed_to_a_reader_twice_is_refused(shape):
    """The forgery none of the audits above can see. Each of them is about
    one statement — its sentence, the set it is from, the record its coiner
    filed — and being one of several is not a property any statement has,
    so the pair was nobody's question."""
    row = SHAPES[shape]
    refused = survived = by_this_rule = unplantable = planted = 0
    for path, items in _lists_of_statements(row["result"]):
        planted += 1
        forged = copy.deepcopy(row["result"])
        _at(forged, path).append(copy.deepcopy(items[0]))
        try:
            the_door_for(row["result"])(row["program"], forged)
        except SyntacticError:
            unplantable += 1
            continue
        except Exception:                       # noqa: BLE001
            refused += 1
        else:
            survived += 1
        try:
            verify_statements_carry_their_facts(forged)
        except VerificationError:
            by_this_rule += 1
    assert survived == 0
    assert unplantable == 0
    assert by_this_rule == refused == planted


def test_two_occasions_of_one_sentence_are_two_sentences():
    """Why the pair is compared whole and not by its tokens.

    One corpus row says ``a_risk_sits_outside_its_bound`` twice in the
    same list, once about each arm of the same query, and a reader needs
    both. Asking for distinct TOKENS would refuse that answer; what makes
    an occasion that occasion is the facts it came with, so it is the
    facts that are compared, and only the pair that is one is refused.
    """
    row = SHAPES["needs_investigation:causation:none#4f0014"]
    where, items = next(
        (w, i) for w, i in _lists_of_statements(row["result"])
        if len(i) > 1 and len({str(s["token"]) for s in i}) == 1)
    assert [s["said"]["quantity"] for s in items] == [
        "P(Y=1|do(X=1))", "P(Y=1|do(X=0))"]
    verify_statements_carry_their_facts(row["result"])

    forged = copy.deepcopy(row["result"])
    twins = _at(forged, where)
    twins[1] = copy.deepcopy(twins[0])
    with pytest.raises(VerificationError, match="twice, with the same facts"):
        verify_statements_carry_their_facts(forged)


def test_the_two_ways_a_design_can_break_are_not_one_way_twice():
    """The leaf this came from, at the door.

    ``sutva_concerns`` names what would have to be true of the units for
    the answer to mean anything, the set has exactly two members, and
    every row that carries the list carries both — so bending either
    member is the same forgery as doubling it, and the reader is warned
    about one thing twice while the other leaves without a word.
    """
    row = SHAPES["needs_investigation:effect:none#03cf75"]
    forged = copy.deepcopy(row["result"])
    concerns = next(
        (gap.get("required_data") or {}).get("sutva_concerns")
        for gap in forged["data_gap_report"]["gaps"]
        if (gap.get("required_data") or {}).get("sutva_concerns"))
    assert len(concerns) == len(_members("sutva_concern")) == 2
    concerns[1]["token"] = concerns[0]["token"]

    with pytest.raises(VerificationError, match="twice, with the same facts"):
        verify_statements_carry_their_facts(forged)
    with pytest.raises(VerificationError):
        the_door_for(row["result"])(row["program"], forged)


# --- which sites the table names ----------------------------------------------


def _domains() -> dict[frozenset, str]:
    """Vocabulary name, by the exact token set a schema enum can declare.

    A carrier is found by what its property is allowed to hold rather than
    by what it is called: three unrelated blocks spell something ``kind``,
    and a table keyed on names would either miss a site or claim one.

    A vocabulary's domain includes its declared silent half. ``IF_PROVIDED``
    is partial on purpose and the field that carries its token is a gap's
    kind, whose enum is every kind there is — so reading the table alone
    would leave that carrier looking like a site the contract does not
    have.
    """
    out: dict[frozenset, str] = {}
    for name, owner in language.VOCABULARIES.items():
        tokens = {str(t) for t in owner} | set(_DECLARED_SILENT.get(name, ()))
        out.setdefault(frozenset(tokens), name)
    return out


def _sites_the_contract_declares() -> dict[str, tuple[str, str]]:
    """Every property in the contract whose enum IS a declared vocabulary.

    Asked of all of them. This used to keep only the hits whose vocabulary
    the carrier table already named, which made the instrument that decides
    what is covered a function of what was already covered: it could find a
    new SITE of a known set and never a new SET. Two sites were invisible
    for exactly that reason — a refusal's species and a variable's declared
    scale — and both carried their occasion's facts on every corpus row
    while nothing asked them anything.
    """
    by_domain = _domains()
    found: dict[str, tuple[str, str]] = {}
    for path, sub, _container in schema_walk.RESULT.walk():
        members = schema_walk.RESULT.resolve(sub).get("enum")
        if not isinstance(members, list):
            continue
        named = by_domain.get(frozenset(str(m) for m in members))
        if named is None:
            continue
        found[".".join(path[:-1])] = (path[-1], named)
    return found


def test_the_carrier_table_names_every_site_the_contract_has():
    """The measured half of the walk. A site the contract declares and this
    table does not name is a statement nothing asks about — the shape of
    every hole this line of work keeps finding — so which sites exist is
    read off the schema rather than remembered."""
    assert _sites_the_contract_declares() == _CARRIERS


def test_the_sweep_is_not_bounded_by_the_table_it_checks():
    """The range of the instrument, held open.

    A sweep that keeps only the vocabularies its table already names
    reports full coverage of the sets it knows and stays silent about the
    ones it does not — the defect this whole file exists to catch, in the
    file itself. So the range is every vocabulary this build declares, and
    that is asserted at the two sets which were invisible while the range
    was the table's own contents.
    """
    reached = {named for _, named in _sites_the_contract_declares().values()}
    assert reached <= set(language.VOCABULARIES)
    assert {REFUSED, "measurement_scale"} <= reached, sorted(reached)


def test_the_carrier_that_can_never_speak_says_why():
    """One of the twelve sites is silent by construction, and silence that
    is not written down reads as coverage.

    ``measurement_scale`` has four members and not one of them has a hole,
    and the record its token sits on is closed with no half to carry facts
    in. So the rule reaches that site and has nothing to compare, always.
    Naming it in the table is still right — the contract declares the site
    — but what it buys today is zero, and this is where that is stated.
    The day a Scale sentence grows a hole, this fails, and somebody has to
    give the record somewhere to put the fact.
    """
    owner = language.VOCABULARIES["measurement_scale"]
    assert [str(m) for m in owner], "the vocabulary is empty"
    for member in owner:
        assert not _holes("measurement_scale", str(member)), str(member)

    shape, spelling = "extensions.type_reconciliation.checks.[]", \
        _CARRIERS["extensions.type_reconciliation.checks.[]"][0]
    record = next(
        schema_walk.RESULT.resolve(container)
        for path, _sub, container in schema_walk.RESULT.walk()
        if ".".join(path) == f"{shape}.{spelling}")
    assert record.get("additionalProperties") is False
    assert not {"said", "words"} & set(record.get("properties") or {})

    # And the other one is not silent: this is the reach the widening buys.
    holed = sum(bool(_holes(REFUSED, str(m)))
                for m in language.VOCABULARIES[REFUSED])
    assert holed == 131, holed


def test_every_carrier_is_a_vocabulary_this_build_declares():
    """The other half: a table entry naming a vocabulary nothing registers
    would read as a site with nothing to check."""
    for shape, (_spelling, vocabulary) in _CARRIERS.items():
        assert vocabulary in language.VOCABULARIES, shape


# --- a table that is partial on purpose ---------------------------------------


def test_a_kind_declared_to_have_no_sentence_carries_no_facts():
    """``IF_PROVIDED`` and ``NOTHING_FILLS`` partition the kinds, and that
    partition is what makes the difference readable: a kind on the second
    half has no sentence BY DECLARATION, so its holes are none rather than
    unknown, and a fact beside it is a fact with nowhere to go.

    Without this the 215 gaps in the corpus whose kind is on that half
    would take any fact at all, which is where the first pass of this rule
    left them."""
    silent = sorted(_DECLARED_SILENT[gaps.PROVIDED])
    assert set(silent) == set(gaps.NOTHING_FILLS)
    result = {"data_gap_report": {"gaps": [
        {"kind": silent[0], "said": {"a_fact": "1"}}]}}
    with pytest.raises(VerificationError, match="no sentence at all"):
        verify_statements_carry_their_facts(result)


def test_a_kind_this_build_does_not_declare_is_a_word_from_nowhere():
    """The case that looked like somebody else's set and was ours.

    An unknown token may be a member of a set another layer coins, which
    ``language.spelt`` exists to allow, and refusing that would refuse
    every assumption id an estimator adds. A gap's kind is not that: it
    comes from a set THIS build declares, so a kind from the future is a
    word the reader is sent to look up and will not find.

    The reason recorded for passing it over was that which member a token
    of our sets is, is a schema enum asked where enums are asked. Enums
    are asked by PATH, and a statement carries its set beside its token —
    so the same set one level in, inside ``words``, was asked by nobody.
    See ``test_a_word_slot_is_held_to_the_set_beside_it``.
    """
    result = {"data_gap_report": {"gaps": [
        {"kind": "a_species_from_the_future", "said": {"a_fact": "1"}}]}}
    with pytest.raises(VerificationError, match="has no such word"):
        verify_statements_carry_their_facts(result)


def test_a_token_from_a_set_another_layer_coins_is_passed_over():
    """And the case that reason was describing, on a set where it holds.

    ``assumption_claim`` is keyed on ids an estimator declares, so a token
    outside the table is the door working and not a forgery: this build
    has no wording for it, which is a fact about this build. What it is
    NOT is unheld — the record its coiner filed beside it says the id was
    declared, and the token is its head.
    """
    result = {"extensions": {"assumption_ledger": {"assumptions": [
        {"id": "an_id_an_estimator_coined_on_618",
         "claim": [{"vocabulary": "assumption_claim",
                    "token": "an_id_an_estimator_coined"}]}]}}}
    verify_statements_carry_their_facts(result)


def test_a_borrowed_token_with_no_record_beside_it_is_refused():
    """And the same token where nothing coined it.

    Passing this over was reading "the tokens are somebody else's" as
    "nobody holds them". The set is open about WHO coins a word, not
    about whether anything says it exists, and with no record beside it
    the label is the only thing behind the word.
    """
    result = {"extensions": {"assumption_ledger": {"assumptions": [
        {"claim": [{"vocabulary": "assumption_claim",
                    "token": "an_id_an_estimator_coined"}]}]}}}
    with pytest.raises(VerificationError, match="record of one"):
        verify_statements_carry_their_facts(result)


def test_a_borrowed_token_is_not_asked_to_agree_with_that_record_here():
    """Existence is this rule's question; agreement is not.

    Whether the two copies are of one fact belongs to the rule that
    audits the record they both sit in, which reads the id's remainder
    for the values as well. Asked in both places, this one runs first
    and the other stops being reachable — so what is pinned here is
    that it is NOT asked.
    """
    result = {"extensions": {"assumption_ledger": {"assumptions": [
        {"id": "another_assumption_entirely_on_618",
         "claim": [{"vocabulary": "assumption_claim",
                    "token": "an_id_an_estimator_coined"}]}]}}}
    verify_statements_carry_their_facts(result)


# --- and the word the question spelt ------------------------------------------


def _spelt_by_a_question() -> dict[str, str]:
    """Every place the PROGRAM spells a word from one of this build's sets.

    :func:`_sites_the_contract_declares` asked this of the answer; this
    asks it of the other document. Two of them, and they are two different
    facts: a word about a NAMED THING, which is the scale a column is
    declared at, and a word about the QUESTION, which is the direction a
    monotonicity assumption runs in. The first is keyed on the name and the
    audit that holds it is keyed on the name too; the second is one word
    for the whole answer, so no name-keyed audit can reach it.
    """
    by_members = _domains()
    document = schema_walk.named("kernel_ast.schema.json")
    found: dict[str, str] = {}
    for path, sub, _container in document.walk():
        members = document.resolve(sub).get("enum")
        if not isinstance(members, list):
            continue
        named = by_members.get(frozenset(str(m) for m in members))
        if named is not None:
            found[".".join(path)] = named
    return found


def _sets_a_question_spells() -> set[str]:
    """Of those, the ones a QUESTION spells rather than a declaration."""
    return {named for where, named in _spelt_by_a_question().items()
            if ".query.assumptions." in where}


def _repeats(result, sets) -> list[tuple]:
    """Every statement on this envelope from a set a question may spell."""
    out: list[tuple] = []

    def walk(node, path: list) -> None:
        if isinstance(node, dict):
            if node.get("vocabulary") in sets and "token" in node:
                out.append(tuple(path))
            for key, value in node.items():
                walk(value, [*path, key])
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, [*path, "[]", index])

    walk(result, [])
    return out


def test_the_contract_says_where_a_program_spells_one_of_our_words():
    """What a question can put in a reader's sentence, and what it cannot.

    Measured against the schema rather than remembered, for the reason the
    carrier table is: a third place would otherwise arrive unasked. The
    assumption is named after its own SET, which is what lets the rule read
    the pairing instead of keeping a copy of it.
    """
    found = _spelt_by_a_question()
    assert found == {
        "statements.[].query.assumptions.monotonicity": "monotonicity",
        "statements.[].scale": "measurement_scale",
    }
    key = "statements.[].query.assumptions.monotonicity".rsplit(".", 1)[1]
    assert key == found["statements.[].query.assumptions.monotonicity"]


def test_no_carrier_site_spells_a_word_a_record_decides():
    """Why the second walk may look for statements that carry their set.

    A carrier site writes its token under a field of its own and its
    vocabulary is fixed by the table, so a word there could never be found
    by ``vocabulary``. Nothing is lost by that while this holds, and when
    it stops holding it stops here rather than in silence. The scale is
    the other program-spelt word and it IS a carrier — which is why the
    set this asks about is the question's half rather than both, beside
    the set the derivation decides.
    """
    carried = {named for _spelling, named in _CARRIERS.values()}
    assert not (_sets_a_question_spells() | {Premise.vocabulary}) & carried
    assert _spelt_by_a_question()["statements.[].scale"] in carried


def test_every_sentence_that_repeats_the_question_repeats_it():
    """The standing statement, and the population it is about.

    Thirteen answers are for a question that spells the direction; ten
    sentences on those envelopes repeat it, in four blocks that are not a
    list anyone chose — a ledger claim, what an IV answer says it rests
    on, the gap that tells a reader so, and the note beside the bound the
    assumption tightened. Every one of the ten says what the question
    said.
    """
    sets = _sets_a_question_spells()
    asking = sites = agreeing = 0
    where = set()
    for shape in sorted(SHAPES):
        row = SHAPES[shape]
        query = query_of(row["program"], row["result"].get("query_id")) or {}
        spelt = query.get("assumptions") or {}
        found = _repeats(row["result"], sets)
        if spelt:
            asking += 1
        else:
            assert not found, (shape, found)
        for path in found:
            sites += 1
            statement = _at(row["result"], path)
            where.add(".".join(k for k in path if not isinstance(k, int)))
            agreeing += str(statement["token"]) == spelt[
                statement["vocabulary"]]
    assert (asking, sites, agreeing) == (13, 10, 10)
    assert where == {
        "bounds_results.[].notes.[].words.direction",
        "data_gap_report.gaps.[].describes.[].words.assumption.words.direction",
        "extensions.assumption_ledger.assumptions.[].claim.[].words.direction",
        "extensions.iv_identification.required_assumption.words.direction",
    }


def test_a_sentence_naming_a_direction_the_question_did_not_is_refused():
    """The forgery, at every one of the ten.

    Which way the assumption runs decides which side of the interval
    tightens, so the other word hands a reader the opposite conclusion in
    words that are all real. Its second record is not on the envelope at
    all: the question spelt it, and the question is not the answer's to
    write.
    """
    sets = _sets_a_question_spells()
    planted = refused = survived = mine = 0
    for shape in sorted(SHAPES):
        row = SHAPES[shape]
        for path in _repeats(row["result"], sets):
            was = str(_at(row["result"], path)["token"])
            for other in _members(_at(row["result"], path)["vocabulary"]):
                if other == was:
                    continue
                planted += 1
                forged = copy.deepcopy(row["result"])
                _at(forged, path)["token"] = other
                try:
                    the_door_for(row["result"])(row["program"], forged)
                except Exception:                       # noqa: BLE001
                    refused += 1
                else:
                    survived += 1
                try:
                    verify_statements_repeat_what_decided_them(
                        forged, row["program"])
                except VerificationError:
                    mine += 1
    assert survived == 0
    assert mine == refused == planted == 10


def test_a_question_that_spells_nothing_leaves_the_sentence_alone():
    """Silence where there is nothing to appeal to.

    An assumption block is optional, and an answer for a question without
    one carries no second record of the word anywhere. Refusing there
    would be this rule inventing the declaration it is supposed to be
    reading.
    """
    sets = _sets_a_question_spells()
    shape = next(s for s in sorted(SHAPES)
                 if _repeats(SHAPES[s]["result"], sets))
    row = SHAPES[shape]
    program = copy.deepcopy(row["program"])
    for statement in program["statements"]:
        (statement.get("query") or {}).pop("assumptions", None)
    path = _repeats(row["result"], sets)[0]
    forged = copy.deepcopy(row["result"])
    was = str(_at(forged, path)["token"])
    _at(forged, path)["token"] = next(
        m for m in _members(_at(forged, path)["vocabulary"]) if m != was)
    verify_statements_repeat_what_decided_them(forged, program)

    # And with the question back, the same forgery is refused — so the
    # silence above is the missing declaration and not the missing walk.
    with pytest.raises(VerificationError, match="the question it answers"):
        verify_statements_repeat_what_decided_them(forged, row["program"])


def test_a_query_id_that_names_no_statement_is_not_guessed_at():
    """Which question an answer is for is another rule's claim.

    A program carries as many statements as the caller wrote. Reading the
    word off one this answer is not for would hold its sentences to a
    declaration nobody made about them, so where the id lands on nothing
    this says nothing at all.
    """
    sets = _sets_a_question_spells()
    shape = next(s for s in sorted(SHAPES)
                 if _repeats(SHAPES[s]["result"], sets))
    row = SHAPES[shape]
    path = _repeats(row["result"], sets)[0]
    forged = copy.deepcopy(row["result"])
    was = str(_at(forged, path)["token"])
    _at(forged, path)["token"] = next(
        m for m in _members(_at(forged, path)["vocabulary"]) if m != was)
    forged["query_id"] = "a_question_this_program_does_not_carry"
    verify_statements_repeat_what_decided_them(forged, row["program"])


# --- and the premise the derivation ran ---------------------------------------


def _premises(result) -> list[tuple]:
    """Every statement naming which premise an instrument's answer rests on."""
    return _repeats(result, {Premise.vocabulary})


def _owed_by_the_route(result) -> str:
    """The same fact read off the blocks each route leaves, not off the chain.

    Written here so the standing test is not the rule agreeing with
    itself: a loop reduced to simultaneous equations, a Wald table under
    the instrument's block, or neither. Two records agreeing on every
    honest answer is what makes the chain the right one to read rather
    than merely a convenient one.
    """
    extensions = result.get("extensions") or {}
    loop = extensions.get("feedback_loop") or {}
    if loop.get("reduction") == "simultaneous_equations":
        return str(Premise.LINEAR_SIMULTANEOUS_SYSTEM)
    if (extensions.get("iv_identification") or {}).get("numeric"):
        return str(Premise.MONOTONICITY_AS_DECLARED)
    return str(Premise.MONOTONICITY_OR_LINEARITY)


def _bent(statement, other):
    """The statement naming ``other`` instead, with the holes its sentence has.

    The premises' sentences do not share holes — only the one quoting the
    declared direction has a place for it — so a bend keeping the old
    facts would be refused by the rule holding a sentence to its holes,
    and would say nothing about this one.
    """
    wanted = _holes(statement["vocabulary"], other)
    assert wanted <= {"direction"}, wanted
    bent = {"vocabulary": statement["vocabulary"], "token": other}
    if wanted:
        bent["words"] = {"direction": {"vocabulary": "monotonicity",
                                       "token": "non_decreasing"}}
    return bent


def test_the_records_that_decide_a_word_decide_different_sets():
    """Two records, no set both of them speak for, and no row asking nothing.

    Were one set decided twice, which record a sentence answered to would
    be a fact about the order the table lists them in. Each step the chain
    is read by is one the verifier really replays, so a misspelt row
    cannot sit in the table unread; and the steps and the chain's default
    between them name every member of the set, so no premise is one the
    reading can never owe.
    """
    assert Premise.vocabulary not in _sets_a_question_spells()
    for rule in (*_PREMISE_SETTLED_BY, _THROUGH_AN_INSTRUMENT):
        assert rule in _SIMPLE_RULES or rule in _STEP_REF_RULES, rule
    reachable = {*_PREMISE_SETTLED_BY.values(),
                 str(Premise.MONOTONICITY_OR_LINEARITY)}
    assert reachable == set(_members(Premise.vocabulary))


def test_every_premise_an_instrument_names_is_the_one_its_derivation_ran():
    """The standing statement, and the population it is about.

    Four answers name a premise, in nine sentences across three blocks —
    the two identification blocks, and the gap that tells a reader — and
    every member of the set is said by one of them, so each branch of the
    reading is answered for by an honest answer rather than by a fixture.
    """
    rows = sites = by_the_chain = by_the_route = 0
    where, said = set(), set()
    for shape in sorted(SHAPES):
        row = SHAPES[shape]
        found = _premises(row["result"])
        if not found:
            continue
        rows += 1
        chain = _the_premise_the_derivation_ran(row["result"], row["program"])
        for path in found:
            sites += 1
            token = str(_at(row["result"], path)["token"])
            said.add(token)
            where.add(".".join(k for k in path if not isinstance(k, int)))
            by_the_chain += token == chain.get(Premise.vocabulary)
            by_the_route += token == _owed_by_the_route(row["result"])
    assert (rows, sites, by_the_chain, by_the_route) == (4, 9, 9, 9)
    assert said == set(_members(Premise.vocabulary))
    assert where == {
        "data_gap_report.gaps.[].describes.[].words.assumption",
        "extensions.identification.required_assumption",
        "extensions.iv_identification.required_assumption",
    }


def test_a_premise_naming_an_estimator_that_did_not_run_is_refused():
    """The forgery, at every one of the nine and to every other member.

    Which premise it is decides what the number IS — a LATE among
    compliers, or one equation's coefficient rather than a total effect —
    so the other word hands a reader a different estimand in words that
    are all real.
    """
    planted = refused = survived = mine = 0
    for shape in sorted(SHAPES):
        row = SHAPES[shape]
        for path in _premises(row["result"]):
            statement = _at(row["result"], path)
            for other in _members(Premise.vocabulary):
                if other == statement["token"]:
                    continue
                planted += 1
                forged = copy.deepcopy(row["result"])
                target = _at(forged, path)
                target.clear()
                target.update(_bent(statement, other))
                try:
                    the_door_for(row["result"])(row["program"], forged)
                except Exception:                       # noqa: BLE001
                    refused += 1
                else:
                    survived += 1
                try:
                    verify_statements_repeat_what_decided_them(
                        forged, row["program"])
                except VerificationError:
                    mine += 1
    assert survived == 0
    assert mine == refused == planted == 18


def test_every_copy_agreeing_on_the_wrong_premise_is_still_refused():
    """The case holding copies to each other cannot see.

    The two identification blocks were already held equal, so a premise
    swapped in one of them was refused — and the same swap made in every
    copy on the envelope was one consistent sentence, and taken. Copies
    agreeing is not the copies agreeing with what ran.
    """
    planted = 0
    for shape in sorted(SHAPES):
        row = SHAPES[shape]
        paths = _premises(row["result"])
        if not paths:
            continue
        was = _at(row["result"], paths[0])
        for other in _members(Premise.vocabulary):
            if other == was["token"]:
                continue
            planted += 1
            forged = copy.deepcopy(row["result"])
            for path in paths:
                target = _at(forged, path)
                target.clear()
                target.update(_bent(was, other))
            with pytest.raises(VerificationError,
                               match="the derivation it ran settles"):
                the_door_for(row["result"])(row["program"], forged)
    assert planted == 8


def test_a_chain_that_settles_nothing_about_an_instrument_is_not_read_into():
    """Silence where the derivation does not say, and a word where it does.

    A chain with no step touching an instrument owes no premise; a chain
    naming two estimators does not say which of them this answer's
    premise belongs to, and picking one would be refusing on a guess. A
    chain that identified through an instrument and ran neither estimator
    owes the member saying it has not chosen one.
    """
    def chain(*rules):
        return {"derivation": {"steps": [{"rule": r} for r in rules]}}

    read = _the_premise_the_derivation_ran
    assert read({}, {}) == {}
    assert read(chain("iv_criterion_check", "numeric_iv_estimate"), {}) == {}
    assert read(chain(*_PREMISE_SETTLED_BY, _THROUGH_AN_INSTRUMENT), {}) == {}
    assert read(chain(_THROUGH_AN_INSTRUMENT), {}) == {
        Premise.vocabulary: str(Premise.MONOTONICITY_OR_LINEARITY)}
    for step, premise in _PREMISE_SETTLED_BY.items():
        assert read(chain(step, _THROUGH_AN_INSTRUMENT), {}) == {
            Premise.vocabulary: premise}


# --- the producer's half ------------------------------------------------------


def test_an_escape_may_not_promise_a_fact_it_has_no_occasion_for():
    """``gaps.escapes`` builds every route it offers BARE — the species is
    all it knows — so a route whose sentence names a variable arrives with
    the name missing. The table's own docstring already said such a route
    belongs elsewhere; nothing had made it true, and three species were
    shipping one."""
    holed = next(r for r in gaps.Route
                 if language.holes(gaps.ROUTES[str(r)]))
    was = dict(gaps.ESCAPES)
    try:
        gaps.ESCAPES[gaps.Need.IV_FIRST_STAGE_DEGENERATE] = (holed,)
        with pytest.raises(ValueError, match="offered bare"):
            gaps._bind_escapes()
    finally:
        gaps.ESCAPES.clear()
        gaps.ESCAPES.update(was)
    gaps._bind_escapes()


def test_no_route_a_species_settles_names_this_occasion():
    """The standing statement of the same thing: what ships satisfies it."""
    for need, routes in gaps.ESCAPES.items():
        for route in routes:
            assert not language.holes(gaps.ROUTES[str(route)]), (need, route)


def test_the_route_beside_a_declared_loop_names_the_loop():
    """The one site where the facts were on the stack two lines above the
    call that did not pass them. The sentence built just before it is about
    the same two variables."""
    program = SHAPES["iv_2sls"]["program"]
    result = SHAPES["iv_2sls"]["result"]
    routes = [route
              for gap in (result["data_gap_report"] or {}).get("gaps") or ()
              for route in gap.get("alternative_paths") or ()
              if route.get("route") == str(gaps.Route.RESOLVE_THE_LOOP_IN_TIME)]
    assert routes, "the corpus row no longer carries this route"
    for route in routes:
        assert set(route.get("said") or ()) == {"treatment", "outcome"}
    themis.verify(program, result)
