"""A proposal-edge gap, read against the edge it cites.

A gap of kind ``unverified_proposal_edge_on_query_path`` cites the
annotation that flagged its edge, ``program:cause:<from>-><to>:annotations.source``,
and T10-1's other half finds that annotation in the program. What the gap
tells a reader is that statement read aloud: which edge, whether a language
model proposed it or an algorithm learned it, which algorithm, how often it
survived resampling. The site was found and not read.

The census could not show it. It bends one leaf at a time, and the one
leaf a gap's edge could be bent at is now held by the ledger line that
copies the gap — so a lie told in one place is refused and the same lie
told in both was accepted everywhere. Measured, with the gap and its line
rewritten together: the edge reversed on 19 rows of 19, an LLM proposal told
as learned by discovery on 18 of 18, the reverse on 3 of 3, the algorithm on
3 of 3, the share on 2 of 2. Every forgery here is written that way, and one
test says so, so what refuses them is this rule and not the ledger's.
"""
from __future__ import annotations

import copy
import json
import pathlib
from collections import Counter

import pytest

import themis
from tests.answer_corpus import the_door_for
from themis import language
from themis.verifier.data_gap_rules import (
    _as_read,
    _the_cited_edge,
    _what_the_edge_says,
    verify_gap_edge_statements,
)
from themis.verifier.errors import VerificationError

SHAPES = json.loads((pathlib.Path(__file__).parent / "fixtures" /
                     "answer_shapes.json").read_text(encoding="utf-8"))

EDGE = "unverified_proposal_edge_on_query_path"
REFUSED = "the edge it cites"


def _gaps(result):
    return (result.get("data_gap_report") or {}).get("gaps") or []


def _ledger(result):
    return (((result.get("extensions") or {})
             .get("assumption_ledger") or {}).get("assumptions") or [])


def _site(gap):
    return next(ref["ref_id"] for ref in gap.get("provenance") or ()
                if ref.get("ref_kind") == "program_site")


def _edge_gaps():
    for name in sorted(SHAPES):
        for g, gap in enumerate(_gaps(SHAPES[name]["result"])):
            if gap.get("kind") == EDGE:
                yield name, g, gap


def _first(test):
    return next((name, g) for name, g, gap in _edge_gaps() if test(name, gap))


PROPOSED = _first(lambda _n, gap: gap["describes"][0]["sentence"]
                  == "the_edge_is_an_llm_proposal")
LEARNED = _first(lambda _n, gap: gap["describes"][0]["sentence"]
                 == "the_edge_was_learned_by_discovery")
SHARED = _first(lambda _n, gap: len(gap["describes"]) == 2)
PAIRED = _first(lambda _n, gap: _site(gap).startswith("program:bidirected:"))
NO_CHAIN = _first(lambda name, _g: SHAPES[name]["result"].get(
    "derivation") is None)


def _restated(describes):
    return [dict(language.restate(e, "gap_describes", "sentence"))
            for e in describes]


def _forged(at, rewrite, provenance=None):
    """The gap's statements and the ledger line that copies them, rewritten
    together, so the two copies still agree."""
    name, g = at
    pair = SHAPES[name]
    result = copy.deepcopy(pair["result"])
    gap = _gaps(result)[g]
    before = _restated(gap["describes"])
    gap["describes"] = rewrite(copy.deepcopy(gap["describes"]))
    for line in _ledger(result):
        if not line.get("id") and line.get("claim") == before:
            line["claim"] = _restated(gap["describes"])
            if provenance:
                line["provenance"] = provenance
            return pair["program"], result
    raise AssertionError(f"{name}: no ledger line copies gap[{g}]")


def _refused(program, result):
    with pytest.raises(VerificationError, match=REFUSED):
        the_door_for(result)(program, result)


def _reversed(describes):
    said = describes[0]["said"]
    tail, _, head = said["edge"].partition(" → ")
    said["edge"] = f"{head} → {tail}"
    return describes


def _told_as_learned(describes):
    return [{"sentence": "the_edge_was_learned_by_discovery",
             "said": {"edge": describes[0]["said"]["edge"],
                      "algorithm": "PC"}}]


def _told_as_proposed(describes):
    return [{"sentence": "the_edge_is_an_llm_proposal",
             "said": {"edge": describes[0]["said"]["edge"]}}]


# ------------------------------------------------- the fact this rests on


def test_every_proposal_edge_gap_says_what_its_cited_edge_says():
    """Stated as the measurement the rule is built on."""
    kinds = Counter()
    for name, _g, gap in _edge_gaps():
        edge = _the_cited_edge(SHAPES[name]["program"], _site(gap))
        assert edge is not None, (name, _site(gap))
        assert _as_read(gap["describes"]) == _as_read(
            _what_the_edge_says(*edge)), name
        kinds["gaps"] += 1
        kinds[gap["describes"][0]["sentence"]] += 1
        kinds["with a share"] += len(gap["describes"]) == 2
        kinds["bidirected"] += edge[0] == "bidirected"
    assert dict(kinds) == {
        "gaps": 21, "the_edge_is_an_llm_proposal": 18,
        "the_edge_was_learned_by_discovery": 3, "with a share": 2,
        "bidirected": 2}, dict(kinds)


def test_the_forgeries_start_from_answers_their_door_reads():
    for name, _g in {PROPOSED, LEARNED, SHARED, PAIRED, NO_CHAIN}:
        pair = SHAPES[name]
        the_door_for(pair["result"])(pair["program"],
                                     copy.deepcopy(pair["result"]))


def test_the_ledger_cannot_see_these_forgeries():
    """Why each is written in both places: the ledger's own door accepts
    them, so a refusal below is not the copy disagreeing."""
    for at, rewrite, provenance in (
            (PROPOSED, _reversed, None),
            (PROPOSED, _told_as_learned, "discovery"),
            (LEARNED, _told_as_proposed, "llm_proposal")):
        _program, result = _forged(at, rewrite, provenance)
        themis.verify_assumption_ledger(result)


# ------------------------------------------------ what the gap may not say


@pytest.mark.parametrize("at", [PROPOSED, LEARNED, NO_CHAIN],
                         ids=["proposed", "learned", "no_chain"])
def test_a_directed_edge_may_not_be_told_the_other_way_round(at):
    """``NO_CHAIN`` is a diagnosis with no derivation, read by the door that
    asks for the program alone."""
    _refused(*_forged(at, _reversed))


def test_an_edge_a_language_model_proposed_may_not_be_told_as_learned():
    _refused(*_forged(PROPOSED, _told_as_learned, "discovery"))


def test_an_edge_an_algorithm_learned_may_not_be_told_as_proposed():
    _refused(*_forged(LEARNED, _told_as_proposed, "llm_proposal"))


def test_the_algorithm_is_the_one_its_source_names():
    def other_algorithm(describes):
        said = describes[0]["said"]
        said["algorithm"] = "GES" if said["algorithm"] != "GES" else "PC"
        return describes
    _refused(*_forged(LEARNED, other_algorithm))


def test_the_share_is_the_one_the_run_recorded():
    def other_share(describes):
        describes[1]["said"]["confidence"] = "99%"
        return describes
    _refused(*_forged(SHARED, other_share))


def test_a_bidirected_edge_may_not_be_told_as_directed():
    def directed(describes):
        said = describes[0]["said"]
        said["edge"] = said["edge"].replace("↔", "→")
        return describes
    _refused(*_forged(PAIRED, directed))


def test_a_bidirected_edge_is_the_same_edge_named_either_way_round():
    """A pair, as T10-1 reads a bidirected site: refusing this would refuse
    a report that is true."""
    def swapped(describes):
        said = describes[0]["said"]
        left, _, right = said["edge"].partition(" ↔ ")
        said["edge"] = f"{right} ↔ {left}"
        return describes
    program, result = _forged(PAIRED, swapped)
    the_door_for(result)(program, result)


# ------------------------------------------------------- the rule's range


def test_a_gap_whose_site_names_no_edge_of_the_program_is_refused():
    """Asked of the rule alone: at a door, the site half of T10-1 refuses a
    site the program does not have before this rule is reached."""
    name, _g = PROPOSED
    program = copy.deepcopy(SHAPES[name]["program"])
    program["statements"] = [s for s in program["statements"]
                             if s.get("kind") != "cause"]
    with pytest.raises(VerificationError, match=REFUSED):
        verify_gap_edge_statements(SHAPES[name]["result"], program)


def test_the_rule_needs_the_program_document():
    name, _g = PROPOSED
    with pytest.raises(TypeError, match="program document"):
        verify_gap_edge_statements(SHAPES[name]["result"], "not a program")
