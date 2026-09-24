"""A request's note is what the asks under it share.

``investigation_requests`` groups a reader's asks by the channel that repairs
them, and each request carries a heading written out of its items by one
function, ``summarise``: the target, the priority, and a ``note`` that is the
species and occasion the asks have in common — one ask's own when there is
one, the single mapping every species-carrying ask shares when there are
several, and nothing when they differ.

The verifier held three of those fields to the items and not the note. On an
answer the number path finished, ``missing_information`` is removed, and a
request's note was then a record of what was needed that nothing compared
with anything: the unwitnessed-leaf sweep found an instrument answer's note
could say the reader needed a joint effect identified, and the door took it.

The framing pass wrote its request by hand, and over a single ask it carried
no note where every other channel carries that ask's species. It goes
through ``summarise`` now; its channel keeps the action as its prefix, the
spelling every stored framing request has.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis import gaps, kernel
from themis.runtime.investigation_pusher import summarise
from themis.types import Priority
from themis.verifier.errors import VerificationError
from themis.verifier.investigation_rules import verify_investigation_items

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

CARRIERS = sorted(
    n for n in SHAPES if SHAPES[n]["result"].get("investigation_requests"))

#: Answers the number path finished through an instrument. They carry no
#: ``missing_information``, so the note was the ask's only other record.
INSTRUMENT_ROWS = ("iv_wald", "iv_acr", "iv_2sls_overid", "iv_stratified_wald")

#: The one stored framing request over a single ask.
ONE_FRAMING_ASK = "needs_investigation:probability:none#6bdf54"

#: A stored framing request over two asks about different variables.
TWO_FRAMING_ASKS = "backdoor_linear"


def _pair(name):
    pair = SHAPES[name]
    return pair["program"], copy.deepcopy(pair["result"])


def _typed(program):
    """The program the rule reads: validated, as the doors hand it on."""
    return validate_program(validate_ast(copy.deepcopy(program)))


def _owed(items):
    """What ``summarise`` writes as the note over these items."""
    _, note, _ = summarise(
        "any", [(i["target"], gaps.carried(i), Priority.LOW) for i in items])
    return note


def _request(result, group):
    return next(r for r in result["investigation_requests"]
                if r.get("group") == group)


def _fresh(program, query_id):
    envelope = kernel.run(copy.deepcopy(program))
    fresh = [r for r in envelope.get("results") or ()
             if r.get("query_id") == query_id]
    assert len(fresh) == 1
    return json.loads(json.dumps(fresh[0], ensure_ascii=False))


def test_every_stored_note_is_what_summarise_writes_over_its_items():
    """The claim the rule makes, measured on every stored request."""
    held = 0
    for name in CARRIERS:
        for request in SHAPES[name]["result"]["investigation_requests"]:
            items = request.get("items") or []
            assert items, (name, request.get("target"))
            assert request.get("note") == _owed(items), (
                name, request.get("target"))
            held += 1
    assert held == 216


def test_every_stored_answer_passes_the_rule():
    for name in CARRIERS:
        program, result = _pair(name)
        verify_investigation_items(result, _typed(program))


def test_a_framing_request_over_one_ask_carries_that_asks_species():
    program, stored = _pair(ONE_FRAMING_ASK)
    request = _request(_fresh(program, stored["query_id"]), "framing")
    [item] = request["items"]
    assert request["target"] == item["target"]
    assert request["note"] == gaps.carried(item)
    assert request["note"]["need"] == "framing_fields_unfilled"


def test_a_framing_request_over_several_asks_keeps_its_spelling():
    """Written by ``summarise`` now, and the same bytes the corpus stores."""
    compared = 0
    for name in CARRIERS:
        stored = SHAPES[name]["result"]
        if (stored.get("derivation") is not None
                or stored.get("status") == "numerically_solved"
                or stored.get("numeric_estimate")
                or stored.get("estimator_failure")
                or not any(r.get("group") == "framing"
                           and len(r.get("items") or ()) > 1
                           for r in stored["investigation_requests"])):
            continue
        program, stored = _pair(name)
        fresh = _fresh(program, stored["query_id"])
        # Only where the program alone gives back everything else the row
        # stores: a row another entry point finished is a different run.
        if ({k: v for k, v in fresh.items() if k != "investigation_requests"}
                != {k: v for k, v in stored.items()
                    if k != "investigation_requests"}):
            continue
        request = _request(stored, "framing")
        assert _request(fresh, "framing") == request, name
        assert request["target"] == f"define_variable:{len(request['items'])}_items"
        assert "note" not in request
        compared += 1
    assert compared == 25


@pytest.mark.parametrize("name", INSTRUMENT_ROWS)
def test_a_note_naming_another_need_over_an_instrument_ask(name):
    program, result = _pair(name)
    request = _request(result, "structure")
    assert request["note"] == {"need": "admg_effect_reachable_only_by_instrument"}
    request["note"] = {"need": "joint_effect_not_identifiable"}
    with pytest.raises(VerificationError, match="sums up the asks under it"):
        verify_investigation_items(result, _typed(program))
    with pytest.raises(VerificationError):
        the_door_for(SHAPES[name]["result"])(program, result)


def test_a_note_dropped_from_a_single_ask():
    program, result = _pair("iv_wald")
    del _request(result, "structure")["note"]
    with pytest.raises(VerificationError, match="sums up the asks under it"):
        verify_investigation_items(result, _typed(program))


def test_a_note_over_asks_that_say_different_things():
    program, result = _pair(TWO_FRAMING_ASKS)
    request = _request(result, "framing")
    first, second = request["items"]
    assert gaps.carried(first) != gaps.carried(second)
    request["note"] = gaps.carried(first)
    with pytest.raises(VerificationError, match="sums up the asks under it"):
        verify_investigation_items(result, _typed(program))


def test_the_occasion_on_a_note_is_held_as_well_as_its_species():
    """Every stored note carrying words about its occasion, each value bent."""
    bent = 0
    for name in CARRIERS:
        for ri, request in enumerate(SHAPES[name]["result"]["investigation_requests"]):
            said = (request.get("note") or {}).get("said") or {}
            for key in sorted(said):
                program, result = _pair(name)
                result["investigation_requests"][ri]["note"]["said"][key] = (
                    str(said[key]) + "_elsewhere")
                with pytest.raises(VerificationError,
                                   match="sums up the asks under it"):
                    verify_investigation_items(result, _typed(program))
                bent += 1
    assert bent > 0


def test_the_rule_restates_summarise():
    """Restated in the verifier, so held against the function it restates."""
    a = {"target": "a", "need": "one_need", "said": {"k": "1"}}
    a_again = {"target": "b", "need": "one_need", "said": {"k": "1"}}
    other = {"target": "c", "need": "one_need", "said": {"k": "2"}}
    silent = {"target": "d"}
    groupings = ([a], [silent], [a, a_again], [a, other], [a, silent],
                 [silent, silent], [a, a_again, silent])
    for items in groupings:
        owed = _owed(items)
        request = {"target": "t", "items": items,
                   **({"note": owed} if owed is not None else {})}
        from themis.verifier.investigation_rules import (
            _check_the_note_is_what_the_items_share as rule)
        rule("r", request, items)
        wrong = dict(request)
        if owed is None:
            wrong["note"] = gaps.carried(a)
        else:
            wrong.pop("note")
        with pytest.raises(VerificationError, match="sums up"):
            rule("r", wrong, items)
