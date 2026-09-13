"""A line that names no assumption, held to the record it was written from.

Two channels put lines on the ledger without an id. Each load-bearing
proposal edge becomes the statements of its gap, with whoever proposed the
edge; each prior the language model supplied becomes a sentence of its key
and its value. A line with no id has no name to look up, so neither the
declaration of what an assumption is nor the rule holding a claim to its id
can say anything about one — and the audit counted them instead: at least as
many lines of that layer as the answer owed.

A count is what a record reduced to its length can check. Measured before
this changed, over the 19 answer shapes that carry such lines, every public
door said yes to each of these: an edge a language model proposed told as
learned by discovery, and the other way; a supplied prior told as inherent or
as a default; the line naming a different edge from its gap; ``testable``
saying the data cannot answer it; the line written twice; a real line copied
onto an answer that proposed nothing. The comment explaining the gap said
these lines went unheld "for want of a second record".

The record was on the same answer the whole time, and the line is a copy of
it: the gap's statements verbatim, who proposed the edge read off the first
of them, a prior's key and value. On 19 shapes of 19 every such line is
exactly the line its record owes, and none is anything else. So that is
what the ledger is held to — the lines naming no assumption, taken together,
are the lines this answer's records owe, one each.
"""
from __future__ import annotations

import copy
import json
import pathlib
from collections import Counter

import pytest

from tests.answer_corpus import the_door_for
from themis.verifier.assumption_ledger_rules import (
    _owed_proposal_edges,
    _owed_theta_priors,
)
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

REFUSED = "not the lines this answer's records owe"
_RANK = {"invalidating": 0, "distorting": 1, "confidence_only": 2}


def _ledger(result):
    return (((result.get("extensions") or {})
             .get("assumption_ledger") or {}).get("assumptions") or [])


def _unnamed(result):
    return [i for i, e in enumerate(_ledger(result))
            if isinstance(e, dict) and not e.get("id")]


def _owed(result):
    return (_owed_proposal_edges(result)
            + _owed_theta_priors(result.get("extensions") or {}))


#: The four things a line naming no assumption tells a reader, in the order
#: the rule writes what a record owes.
_TOLD = ("claim", "layer", "provenance", "testable")


def _as_a_reader_meets_it(values):
    return json.dumps(list(values), sort_keys=True, ensure_ascii=False)


def _first_from(provenance, *, in_company=False):
    """The first corpus line of this provenance naming no assumption — on a
    ledger with other lines too, when the forgery removes it."""
    for name in sorted(SHAPES):
        result = SHAPES[name]["result"]
        if in_company and len(_ledger(result)) < 2:
            continue
        for i in _unnamed(result):
            if _ledger(result)[i].get("provenance") == provenance:
                return name, i
    raise AssertionError(f"no corpus line names no assumption and came from "
                         f"{provenance}")


SOURCES = ("llm_proposal", "discovery", "llm_prior")
PROPOSED, LEARNED, SUPPLIED = (_first_from(p) for p in SOURCES)
EDGES = [pytest.param(PROPOSED, id="llm_proposal"),
         pytest.param(LEARNED, id="discovery")]
EVERY_SOURCE = EDGES + [pytest.param(SUPPLIED, id="llm_prior")]

#: The sources with a corpus line that shares its ledger. The one supplied
#: prior is the only line on its ledger, so taking it away leaves a ledger
#: with nothing on it — which is refused for being empty, before any rule
#: reads a line, and would witness that rule rather than this one.
IN_COMPANY = ("llm_proposal", "discovery")

#: An answer whose records owe no such line, read by the door that re-runs
#: the derivation, and whose ledger is all named lines.
OWES_NONE = next(
    name for name in sorted(SHAPES)
    if _ledger(SHAPES[name]["result"])
    and not _unnamed(SHAPES[name]["result"])
    and not _owed(SHAPES[name]["result"])
    and SHAPES[name]["result"].get("derivation") is not None)


def _bent(at):
    name, i = at
    pair = SHAPES[name]
    return pair["program"], copy.deepcopy(pair["result"]), i


def _refused(program, result):
    with pytest.raises(VerificationError, match=REFUSED):
        the_door_for(result)(program, result)


# ------------------------------------------------- the fact this rests on


def test_every_line_naming_no_assumption_is_the_line_its_record_owes():
    """Stated as the measurement the rule is built on, over every shape.

    Both directions, as a multiset: no shape carries such a line its records
    do not owe, none owes one it does not carry, and where two records owe
    the same line the ledger carries it twice.
    """
    shapes = lines = 0
    sources = Counter()
    for pair in SHAPES.values():
        result = pair["result"]
        got = sorted(_as_a_reader_meets_it(_ledger(result)[i].get(k)
                                           for k in _TOLD)
                     for i in _unnamed(result))
        want = sorted(_as_a_reader_meets_it(o) for o in _owed(result))
        assert got == want
        if got:
            shapes += 1
            lines += len(got)
            sources.update(_ledger(result)[i]["provenance"]
                           for i in _unnamed(result))
    assert (shapes, lines, dict(sources)) == (
        19, 22, {"llm_proposal": 18, "discovery": 3, "llm_prior": 1}), (
        shapes, lines, dict(sources))


def test_the_honest_answers_these_forgeries_start_from_are_read():
    """A forgery refused by a door that refuses the honest answer too
    witnesses nothing."""
    starts = {at[0] for at in (PROPOSED, LEARNED, SUPPLIED)}
    starts |= {_first_from(p, in_company=True)[0] for p in IN_COMPANY}
    for name in starts | {OWES_NONE}:
        pair = SHAPES[name]
        the_door_for(pair["result"])(pair["program"],
                                     copy.deepcopy(pair["result"]))


# ------------------------------------------------ what the line may not say


@pytest.mark.parametrize("at", EDGES)
def test_an_edge_may_not_change_who_proposed_it(at):
    """Both words are ones a proposal-edge line may carry, so the table of
    which producer writes which pair has nothing to object to."""
    program, result, i = _bent(at)
    line = _ledger(result)[i]
    line["provenance"] = {"llm_proposal": "discovery",
                          "discovery": "llm_proposal"}[line["provenance"]]
    _refused(program, result)


@pytest.mark.parametrize("word", ["inherent", "default"])
def test_a_supplied_prior_may_not_be_told_as_nobody_s_to_overrule(word):
    """``(parameter, inherent)`` and ``(parameter, default)`` are pairs an
    estimator writes, so the same table admits them here."""
    program, result, i = _bent(SUPPLIED)
    _ledger(result)[i]["provenance"] = word
    _refused(program, result)


@pytest.mark.parametrize("at", EVERY_SOURCE)
def test_a_line_may_not_say_the_data_cannot_answer_it(at):
    program, result, i = _bent(at)
    _ledger(result)[i]["testable"] = not _ledger(result)[i]["testable"]
    _refused(program, result)


@pytest.mark.parametrize("at", EDGES)
def test_an_edge_line_may_not_name_an_edge_its_gap_does_not(at):
    program, result, i = _bent(at)
    said = _ledger(result)[i]["claim"][0]["said"]
    tail, _, head = str(said["edge"]).partition(" → ")
    said["edge"] = f"{head} → {tail}"
    _refused(program, result)


@pytest.mark.parametrize("fact", ["key", "value"])
def test_a_prior_line_may_not_state_another_prior(fact):
    """Both facts travel as strings, and the forgery keeps them strings: a
    number here is refused by the contract before this rule reads it."""
    program, result, i = _bent(SUPPLIED)
    said = _ledger(result)[i]["claim"][0]["said"]
    said[fact] = "forged" if fact == "key" else str(said[fact]) + "1"
    _refused(program, result)


# ------------------------------------------- how many lines, and on what


@pytest.mark.parametrize("at", EVERY_SOURCE)
def test_a_line_may_not_be_written_twice(at):
    """A count asked for at least as many lines as records, and this is the
    other direction of the same fact: the reader is told of two proposals
    where one was made."""
    program, result, i = _bent(at)
    _ledger(result).insert(i, copy.deepcopy(_ledger(result)[i]))
    _refused(program, result)


@pytest.mark.parametrize("at", EVERY_SOURCE)
def test_a_line_may_not_arrive_where_no_record_owes_it(at):
    """A real line, copied whole, onto an answer that proposed nothing and
    was supplied nothing. The count returned before looking, because
    nothing was owed."""
    name, i = at
    line = copy.deepcopy(_ledger(SHAPES[name]["result"])[i])
    pair = SHAPES[OWES_NONE]
    program, result = pair["program"], copy.deepcopy(pair["result"])
    lines = _ledger(result)
    lines.insert(sum(1 for e in lines
                     if _RANK[e["severity"]] <= _RANK[line["severity"]]), line)
    _refused(program, result)


@pytest.mark.parametrize("provenance", IN_COMPANY)
def test_a_line_may_not_be_dropped(provenance):
    """The one direction the count did hold, still held, now by the rule
    that holds the rest — see :data:`IN_COMPANY` for why not the prior."""
    program, result, i = _bent(_first_from(provenance, in_company=True))
    del _ledger(result)[i]
    _refused(program, result)
