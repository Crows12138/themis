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
from themis.types import GapKind
from themis.verifier import VerificationError
from themis.verifier.statement_rules import (
    _CARRIERS,
    _DECLARED_SILENT,
    verify_statements_carry_their_facts,
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
#: line on its ledger.
REACHED = 5089
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


def test_a_kind_from_another_build_is_passed_over_rather_than_refused():
    """The case that looks the same and is not. An unknown token may be a
    member of somebody else's set — which ``language.spelt`` exists to
    allow — and refusing it would make this rule an enum check written in
    the wrong place. Which member a token of OUR sets is, is a schema enum
    and is asked where enums are asked."""
    result = {"data_gap_report": {"gaps": [
        {"kind": "a_species_from_the_future", "said": {"a_fact": "1"}}]}}
    verify_statements_carry_their_facts(result)


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
