"""A missingness indicator is about the node it names, and names a node.

Both m-graph builders -- the producer's and the verifier's independent
transcription -- used to look an indicator's atoms up by predicate, keeping
one node per predicate. On a program unrolled in time, or about several
people, ``y`` now and ``y`` a step back were one indicator, landed on
whichever of them the graph listed last, and every separation read off it
was about that one. They now use the atoms as nodes, so each partially
observed node has its own indicator carrying its own arguments and time.

The other half is what happens to an atom that is not a node. Both builders
passed over it: a cause of missingness the graph does not have left the
indicator without that parent, and the verdict came back about a program
with the edge taken out. A cause spelt without the time index its node
carries is the ordinary way to write one, and it came back MCAR with the
door agreeing. The program is refused at input now, the verifier refuses on
its own side, and the producer treats one reaching it as a broken invariant.
"""
from __future__ import annotations

import pytest

import themis
from themis.input.semantic_validator import Malformed, SemanticError
from themis.runtime.missing_data import build_m_graph
from themis.types import Atom, ConstTerm, MissingnessIndicator, RelativeTimeIndex
from themis.verifier.errors import VerificationError
from tests.answer_corpus import the_door_for


def _at(p, t=None, who="me"):
    atom = {"predicate": p, "args": [{"type": "const", "name": who}]}
    if t is not None:
        atom["time_index"] = {"kind": "relative", "value": t}
    return atom


def _program(edges, x, y, indicators, objects=("me",)):
    names = sorted({a["predicate"] for e in edges for a in e}
                   | {a["predicate"] for m, c in indicators for a in (m, *c)})
    st = [{"kind": "variable", "predicate": p, "domain": [True, False]}
          for p in names]
    st += [{"kind": "cause", "from": a, "to": b} for a, b in edges]
    for i, (missing, caused_by) in enumerate(indicators):
        st.append({"kind": "missingness_indicator", "id": f"R{i}",
                   "missing_var": missing, "caused_by": list(caused_by)})
    st.append({"kind": "query", "id": "q", "query": {
        "kind": "effect", "given": [],
        "intervention": {"atom": x, "value": True},
        "target": {"atom": y, "value": True}}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": o}
                                   for o in objects]},
            "statements": st}


_NOW = ((_at("z", 0), _at("x", 0)), (_at("z", 0), _at("y", 0)),
        (_at("x", 0), _at("y", 0)))

#: The outcome is missing for a reason the confounder gives, so the verdict
#: is MAR; each program adds a node of one of the query's own variables at
#: another time or for another person, which a lookup by predicate could
#: land the indicator on instead.
HONEST = {
    "a step back of the outcome": _program(
        _NOW + ((_at("w", -1), _at("y", -1)),), _at("x", 0), _at("y", 0),
        [(_at("y", 0), [_at("z", 0)])]),
    "a step back of the treatment": _program(
        _NOW + ((_at("x", -1), _at("w", -1)),), _at("x", 0), _at("y", 0),
        [(_at("y", 0), [_at("z", 0)])]),
    "the outcome missing at both times": _program(
        _NOW + ((_at("w", -1), _at("y", -1)),), _at("x", 0), _at("y", 0),
        [(_at("y", 0), [_at("z", 0)]), (_at("y", -1), [_at("w", -1)])]),
    "another person": _program(
        tuple((_at(a, who=o), _at(b, who=o)) for o in ("p", "q")
              for a, b in (("z", "x"), ("z", "y"), ("x", "y"))),
        _at("x", who="p"), _at("y", who="p"),
        [(_at("y", who="p"), [_at("z", who="p")])], objects=("p", "q")),
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
def test_an_honest_verdict_is_about_the_node_the_indicator_names(name):
    program = HONEST[name]
    result = _answer(program)
    block = result["extensions"]["missing_data_recovery"]
    assert block["mechanism"] == "MAR"
    assert block["recoverable"] is True
    assert _refusal(program, result) is None


@pytest.mark.parametrize("name", sorted(HONEST))
def test_a_forged_mechanism_is_still_refused(name):
    program = HONEST[name]
    result = _answer(program)
    result["extensions"]["missing_data_recovery"]["mechanism"] = "MCAR"
    said = _refusal(program, result)
    assert said is not None and "mechanism" in said


def _node(p, t):
    return Atom(predicate=p, args=(ConstTerm(name="me"),),
                time_index=RelativeTimeIndex(value=t))


def test_two_times_of_one_variable_have_two_indicators():
    import networkx as nx

    g = nx.DiGraph([(_node("z", 0), _node("y", 0)),
                    (_node("w", -1), _node("y", -1))])
    m, r_of_var = build_m_graph(g, [
        MissingnessIndicator(id="R0", missing_var=_node("y", 0),
                             caused_by=(_node("z", 0),)),
        MissingnessIndicator(id="R1", missing_var=_node("y", -1),
                             caused_by=(_node("w", -1),)),
    ])
    assert set(r_of_var) == {_node("y", 0), _node("y", -1)}
    now, before = r_of_var[_node("y", 0)], r_of_var[_node("y", -1)]
    assert now != before
    assert set(m.predecessors(now)) == {_node("z", 0)}
    assert set(m.predecessors(before)) == {_node("w", -1)}


#: Indicators whose atoms are not nodes as written, and how each is named
#: back: as an envelope spells it, since the predicate is the half that
#: matched.
STRAYS = {
    "the missing variable written without its time": (
        _program(_NOW, _at("x", 0), _at("y", 0), [(_at("y"), [_at("z", 0)])]),
        ["y(me)"]),
    "a cause written without its time": (
        _program(_NOW, _at("x", 0), _at("y", 0), [(_at("y", 0), [_at("z")])]),
        ["z(me)"]),
    "a missing variable the graph does not have": (
        _program(_NOW, _at("x", 0), _at("y", 0),
                 [(_at("v", 0), [_at("z", 0)])]),
        ["v(me)@t"]),
}


@pytest.mark.parametrize("name", sorted(STRAYS))
def test_an_atom_that_is_not_a_node_refuses_the_program(name):
    program, atoms = STRAYS[name]
    with pytest.raises(SemanticError) as raised:
        themis.run(program)
    assert raised.value.species is Malformed.MISSINGNESS_ATOM_NOT_IN_GRAPH
    assert raised.value.details["atoms"] == atoms


def test_the_verifier_refuses_an_indicator_that_names_no_node():
    """The verifier does not run the input check, so an answer handed to it
    beside such a program has to be refused there too -- here the verdict
    passing over the cause would have re-derived, beside a program whose
    cause lost its time index."""
    honest = _program(_NOW, _at("x", 0), _at("y", 0),
                      [(_at("y", 0), [_at("z", 0)])])
    result = _answer(honest)
    assert result["extensions"]["missing_data_recovery"]["mechanism"] == "MAR"
    result["extensions"]["missing_data_recovery"]["mechanism"] = "MCAR"
    loose = _program(_NOW, _at("x", 0), _at("y", 0),
                     [(_at("y", 0), [_at("z")])])
    said = _refusal(loose, result)
    assert said is not None and "z(me) is not a node of the graph" in said


def test_the_producer_does_not_pass_over_a_stray_atom():
    import networkx as nx

    g = nx.DiGraph([(_node("z", 0), _node("y", 0))])
    stray = Atom(predicate="z", args=(ConstTerm(name="me"),))
    with pytest.raises(ValueError, match="not nodes of the graph"):
        build_m_graph(g, [MissingnessIndicator(
            id="R0", missing_var=_node("y", 0), caused_by=(stray,))])
