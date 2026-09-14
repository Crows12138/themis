"""A selection block is about the nodes the premises name.

The producer resolved the atoms a program restricts its sample on to graph
nodes by predicate, and the verifier resolved every name on the block the
same way -- one node per predicate, whichever the graph listed last. On a
program unrolled in time a variable has a node per step, so the
restriction on ``w`` now landed on ``w`` a step back and no block was
written, and an honest block adjusting for ``m`` now was refused because
``m`` read as ``m`` a step back, which the treatment does not reach.

The treatment, outcome and selection nodes are named by the premises -- the
question and the observations -- and are read from there. The adjustment
set is the one part the program does not name, and the block names it by
predicate, so it is held to what those names claim: some reading of them
as distinct nodes satisfies every condition.
"""
from __future__ import annotations

import copy

import networkx as nx
import pytest

import themis
from themis.runtime.scheduler import _serialize_selection_recovery
from themis.runtime.selection_recovery import recover_effect
from themis.types import Atom, ConstTerm, ObservationStatement, RelativeTimeIndex
from themis.verifier import verify_selection_recovery
from themis.verifier.errors import VerificationError
from tests.answer_corpus import the_door_for

_ME = [{"type": "const", "name": "me"}]


def _at(p, t=None):
    atom = {"predicate": p, "args": _ME}
    if t is not None:
        atom["time_index"] = {"kind": "relative", "value": t}
    return atom


def _restricted(edges, x, y, w):
    names = sorted({a["predicate"] for e in edges for a in e})
    st = [{"kind": "variable", "predicate": p, "domain": [True, False]}
          for p in names]
    st += [{"kind": "cause", "from": a, "to": b} for a, b in edges]
    st.append({"kind": "observation", "atom": w, "value": True})
    st.append({"kind": "query", "id": "q", "query": {
        "kind": "effect", "given": [],
        "intervention": {"atom": x, "value": True},
        "target": {"atom": y, "value": True}}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": st}


#: y -> m -> w and x -> w, the sample restricted on w: w is a common effect
#: of the treatment and the outcome, and adjusting for m (a descendant of
#: the treatment) recovers the effect.
_NOW = ((_at("x", -1), _at("y", 0)), (_at("y", 0), _at("m", 0)),
        (_at("m", 0), _at("w", 0)), (_at("x", -1), _at("w", 0)))

HONEST = {
    "no time": _restricted(
        ((_at("x"), _at("y")), (_at("y"), _at("m")), (_at("m"), _at("w")),
         (_at("x"), _at("w"))), _at("x"), _at("y"), _at("w")),
    "one step, no second node": _restricted(
        _NOW, _at("x", -1), _at("y", 0), _at("w", 0)),
    "w a step back": _restricted(
        _NOW + ((_at("y", -1), _at("w", -1)),), _at("x", -1), _at("y", 0),
        _at("w", 0)),
    "m a step back": _restricted(
        _NOW + ((_at("y", -1), _at("m", -1)),), _at("x", -1), _at("y", 0),
        _at("w", 0)),
    "m and w a step back": _restricted(
        _NOW + ((_at("y", -1), _at("m", -1)), (_at("m", -1), _at("w", -1))),
        _at("x", -1), _at("y", 0), _at("w", 0)),
}


def _answer(program):
    return next(r for r in themis.run(program)["results"]
                if r.get("query_id") == "q")


def _refusal(program, result):
    try:
        the_door_for(result)(program, result)
    except VerificationError as exc:
        return str(exc)
    return None


@pytest.mark.parametrize("name", sorted(HONEST))
def test_an_honest_block_is_written_and_accepted(name):
    program = HONEST[name]
    result = _answer(program)
    block = result["extensions"]["selection_recovery"]
    assert block["selection_nodes"] == ["w"]
    assert block["recoverable"] is True
    assert (block["z_plus"], block["z_minus"]) == ([], ["m"])
    assert _refusal(program, result) is None


def test_a_restriction_on_a_node_that_is_no_common_effect_writes_none():
    """The same graph restricted on ``w`` a step back, which only the
    outcome a step back reaches: nothing to recover, so no block."""
    program = _restricted(_NOW + ((_at("y", -1), _at("w", -1)),),
                          _at("x", -1), _at("y", 0), _at("w", -1))
    assert "selection_recovery" not in (_answer(program).get("extensions") or {})


FORGERIES = {
    "the descendant moved into Z+":
        lambda b: b.update(z_plus=b["z_minus"], z_minus=[]),
    "the verdict flipped":
        lambda b: b.update(recoverable=False, criterion=None),
    "another variable named as restricted":
        lambda b: b.update(selection_nodes=["m"]),
    "another variable named as the treatment":
        lambda b: b.update(treatment="w"),
    "the ledger emptied":
        lambda b: b.update(external_data_needed=[]),
    "the outcome's variable adjusted for":
        lambda b: b.update(z_minus=["y"], adjustment_set=["y"]),
}


@pytest.mark.parametrize("forgery", sorted(FORGERIES))
@pytest.mark.parametrize("name", sorted(HONEST))
def test_a_forged_block_is_refused(name, forgery):
    program = HONEST[name]
    result = copy.deepcopy(_answer(program))
    FORGERIES[forgery](result["extensions"]["selection_recovery"])
    assert _refusal(program, result) is not None


def _node(p, t):
    return Atom(predicate=p, args=(ConstTerm(name="me"),),
                time_index=RelativeTimeIndex(value=t))


def _premises(w):
    from types import SimpleNamespace

    return ((ObservationStatement(atom=w, value=True),),
            SimpleNamespace(intervention=SimpleNamespace(atom=_node("x", -1)),
                            target=SimpleNamespace(atom=_node("y", 0))))


def _decoy_m():
    g = nx.DiGraph([
        (_node("x", -1), _node("y", 0)), (_node("y", 0), _node("m", 0)),
        (_node("m", 0), _node("w", 0)), (_node("x", -1), _node("w", 0)),
        (_node("y", -1), _node("m", -1)),
    ])
    rec = recover_effect(g, _node("x", -1), _node("y", 0), (_node("w", 0),))
    return _serialize_selection_recovery(rec, _node("x", -1), _node("y", 0)), g


def test_the_selection_nodes_are_read_off_the_program():
    """A block naming ``w`` as restricted, beside premises restricting on
    ``m``, is about a sample nobody drew. Asked of the verifier rather
    than the door, where the collider caveat's own rule speaks first."""
    block, g = _decoy_m()
    with pytest.raises(VerificationError,
                       match="not the nodes the program restricts"):
        verify_selection_recovery(block, g, *_premises(_node("m", 0)))


def test_an_adjustment_name_is_held_to_some_node_it_can_mean():
    block, g = _decoy_m()
    assert block["z_minus"] == ["m"]
    verify_selection_recovery(block, g, *_premises(_node("w", 0)))


def test_a_name_written_twice_reads_as_two_nodes():
    """``m`` twice is ``m`` now and ``m`` a step back, and the second is no
    descendant of the treatment."""
    block, g = _decoy_m()
    block["z_minus"] = ["m", "m"]
    block["adjustment_set"] = ["m", "m"]
    with pytest.raises(VerificationError, match="not a descendant of X"):
        verify_selection_recovery(block, g, *_premises(_node("w", 0)))


def test_a_witness_larger_than_the_range_searched_is_refused():
    block, g = _decoy_m()
    block["search_budget"] = 0
    with pytest.raises(VerificationError, match="larger than the recorded"):
        verify_selection_recovery(block, g, *_premises(_node("w", 0)))
