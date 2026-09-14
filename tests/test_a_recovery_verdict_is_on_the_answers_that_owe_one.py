"""A verdict on a biased sample is on the answers that owe one.

Two blocks tell a reader whether an effect survives the sample it was
estimated on: whether a restriction on a common effect of the treatment and
the outcome can be undone, and whether a declared missingness leaves the
effect recoverable from the rows that were observed. Each was audited for
what it says, and only where it was. Removed, all ten on the corpus passed
every door; added to an answer whose sample is restricted on no common
effect, a selection verdict passed too, telling a reader of a bias the
sample does not carry and how to undo it.

Which answers owe one is a fact about the program, the question and the
ground graph, and is held both ways.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.kernel import _premises_of
from themis.runtime.scheduler import _serialize_selection_recovery
from themis.runtime.selection_recovery import recover_effect
from themis.types import ObservationStatement
from themis.verifier.errors import VerificationError
from tests.answer_corpus import the_door_for

_ME = [{"type": "const", "name": "me"}]
_SHAPES = pathlib.Path(__file__).parent / "fixtures" / "answer_shapes.json"


def _at(p, t=None):
    atom = {"predicate": p, "args": _ME}
    if t is not None:
        atom["time_index"] = {"kind": "relative", "value": t}
    return atom


def _program(edges, x, y, *, observe=(), indicators=()):
    names = sorted({a["predicate"] for e in edges for a in e}
                   | {a["predicate"] for a in observe}
                   | {a["predicate"] for m, c in indicators for a in (m, *c)})
    st = [{"kind": "variable", "predicate": p, "domain": [True, False]}
          for p in names]
    st += [{"kind": "cause", "from": a, "to": b} for a, b in edges]
    st += [{"kind": "observation", "atom": w, "value": True} for w in observe]
    for i, (missing, caused_by) in enumerate(indicators):
        st.append({"kind": "missingness_indicator", "id": f"R{i}",
                   "missing_var": missing, "caused_by": list(caused_by)})
    st.append({"kind": "query", "id": "q", "query": {
        "kind": "effect", "given": [],
        "intervention": {"atom": x, "value": True},
        "target": {"atom": y, "value": True}}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": st}


_CONFOUNDED = ((_at("z"), _at("x")), (_at("z"), _at("y")), (_at("x"), _at("y")))

#: Answers owing a selection verdict: the sample is restricted on a common
#: effect of the treatment and the outcome -- in the second, the treatment's
#: own next step, which shares the treatment's name.
SELECTION_OWED = {
    "a common effect": _program(
        ((_at("x"), _at("y")), (_at("x"), _at("w")), (_at("y"), _at("w"))),
        _at("x"), _at("y"), observe=[_at("w")]),
    "the treatment a step on": _program(
        ((_at("x", -1), _at("y", 0)), (_at("x", -1), _at("x", 0)),
         (_at("y", 0), _at("x", 0))),
        _at("x", -1), _at("y", 0), observe=[_at("x", 0)]),
}

#: Answers owing none: the sample is restricted, and on no common effect.
SELECTION_NOT_OWED = {
    "a descendant of the treatment only": _program(
        ((_at("x"), _at("y")), (_at("x"), _at("w"))),
        _at("x"), _at("y"), observe=[_at("w")]),
    "a cause of the treatment": _program(
        ((_at("x"), _at("y")), (_at("w"), _at("x"))),
        _at("x"), _at("y"), observe=[_at("w")]),
    "a step back no path from the treatment reaches": _program(
        ((_at("x", -1), _at("y", 0)), (_at("x", -1), _at("w", 0)),
         (_at("y", -1), _at("w", -1))),
        _at("x", -1), _at("y", 0), observe=[_at("w", -1)]),
}

MISSING_OWED = _program(_CONFOUNDED, _at("x"), _at("y"),
                        indicators=[(_at("y"), [_at("z")])])
MISSING_NOT_OWED = _program(_CONFOUNDED, _at("x"), _at("y"))

_BLOCK_OF = {"selection": "selection_recovery", "missing": "missing_data_recovery"}


def _answer(program):
    return next(r for r in themis.run(program)["results"]
                if r.get("query_id") == "q")


def _without(result, block):
    bare = copy.deepcopy(result)
    del bare["extensions"][block]
    return bare


def _owed_cases():
    for name, program in SELECTION_OWED.items():
        yield pytest.param(program, "selection_recovery", id=f"selection: {name}")
    yield pytest.param(MISSING_OWED, "missing_data_recovery", id="missing data")


@pytest.mark.parametrize(("program", "block"), list(_owed_cases()))
def test_an_answer_owing_a_verdict_carries_it_and_passes(program, block):
    result = _answer(program)
    assert block in (result.get("extensions") or {})
    the_door_for(result)(program, result)


@pytest.mark.parametrize(("program", "block"), list(_owed_cases()))
def test_a_verdict_owed_and_removed_is_refused(program, block):
    bare = _without(_answer(program), block)
    with pytest.raises(VerificationError, match=f"carries no {block} block"):
        the_door_for(bare)(program, bare)


@pytest.mark.parametrize("program", list(SELECTION_NOT_OWED.values()),
                         ids=list(SELECTION_NOT_OWED))
def test_a_selection_verdict_nobody_owes_is_refused(program):
    """The block added is the one the producer's own recovery writes for the
    restriction, so everything it says holds of the graph; it is only not
    owed."""
    result = _answer(program)
    assert "selection_recovery" not in (result.get("extensions") or {})
    the_door_for(result)(program, result)
    _, prog, _, ctx = _premises_of(program, result)
    x, y = ctx.query.intervention.atom, ctx.query.target.atom
    restricted = tuple(st.atom for st in prog.statements
                       if isinstance(st, ObservationStatement))
    forged = copy.deepcopy(result)
    forged.setdefault("extensions", {})["selection_recovery"] = (
        _serialize_selection_recovery(
            recover_effect(ctx.graph, x, y, restricted), x, y))
    with pytest.raises(VerificationError, match=(
            "no atom the program restricts the sample on is a common effect")):
        the_door_for(forged)(program, forged)


def test_a_missing_data_verdict_nobody_owes_is_refused():
    """The verdict of the same graph with an indicator declared, carried by
    the answer of the graph without one."""
    result = _answer(MISSING_NOT_OWED)
    assert "missing_data_recovery" not in (result.get("extensions") or {})
    the_door_for(result)(MISSING_NOT_OWED, result)
    forged = copy.deepcopy(result)
    forged.setdefault("extensions", {})["missing_data_recovery"] = (
        _answer(MISSING_OWED)["extensions"]["missing_data_recovery"])
    with pytest.raises(VerificationError, match="owes none"):
        the_door_for(forged)(MISSING_NOT_OWED, forged)


def test_no_verdict_on_the_corpus_can_be_taken_off_its_answer():
    shapes = json.loads(_SHAPES.read_text(encoding="utf-8"))
    carried = [(name, block) for name, row in sorted(shapes.items())
               for block in _BLOCK_OF.values()
               if block in (row["result"].get("extensions") or {})]
    assert len(carried) == 10
    for name, block in carried:
        program, result = shapes[name]["program"], shapes[name]["result"]
        bare = _without(result, block)
        with pytest.raises(VerificationError, match=f"carries no {block} block"):
            the_door_for(bare)(program, bare)
