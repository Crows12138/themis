"""An instrument is not something the treatment causes.

The IV criterion was read as two m-separation facts: the instrument is
m-connected to the treatment, and m-separated from the outcome once the
treatment's outgoing edges are cut. Cutting those edges removes every path
that starts with one, and a path from a node the treatment causes back to
the treatment starts with one. So a child of the treatment passed both,
while it shares every cause of the treatment with the outcome: a Wald ratio
taken around it is the treatment's confounded contrast. "Not caused by the
treatment" was only in the producer's pool for the conditioning set.

Measured before the change on x -> y, x <-> y, x -> m, where
P(y | do(x=1)) = 0.65 and the contrast is 0.30: the effect question was
numerically solved at 0.604 around m, the identify question structurally
solved through m, the vector search offered a treatment's child as an
instrument for both treatments, and the strongest door took every one.
"""
from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd
import pytest

import themis
from tests.answer_corpus import the_door_for
from themis.runtime import structural_solver
from themis.types import Atom, ConstTerm, EffectQuery, Intervention, ValuedAtom
from themis.verifier import VerificationContext
from themis.verifier.errors import VerificationError
from themis.verifier.rules import _rule_vector_iv_criterion_check, iv_criterion_holds
from themis.verifier.verify import (
    verify_identification_pattern, verify_vector_iv_identification,
)

ME = [{"name": "me", "type": "const"}]


def atom(p):
    return {"args": ME, "predicate": p}


def A(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _query(qid, kind):
    return {"id": qid, "kind": "query", "query": {
        "kind": kind, "given": [],
        "intervention": {"atom": atom("x"), "value": True},
        "target": {"atom": atom("y"), "value": True} if kind == "effect" else atom("y"),
    }}


def _program(nodes, edges, latent):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *({"domain": [True, False], "kind": "variable", "predicate": p}
              for p in nodes),
            *({"kind": "cause", "from": atom(u), "to": atom(v)} for u, v in edges),
            *({"kind": "bidirected", "left": atom(u), "right": atom(v)}
              for u, v in latent),
            _query("q", "effect"), _query("qi", "identify"),
        ],
    }


CHILD_EDGES = [("x", "y"), ("x", "m")]
BOTH_EDGES = [("z", "x"), ("x", "y"), ("x", "m")]
LATENT = [("x", "y")]
#: The only node that moves x is one x causes.
CHILD = _program(["x", "y", "m"], CHILD_EDGES, LATENT)
#: A real instrument beside it.
BOTH = _program(["z", "x", "y", "m"], BOTH_EDGES, LATENT)
VECTOR_EDGES = [("a", "y"), ("b", "y"), ("z1", "a"), ("z2", "b"), ("a", "m")]
VECTOR_LATENT = [("a", "y"), ("b", "y"), ("a", "b")]


def _graph(edges, latent):
    graph = nx.DiGraph()
    graph.add_edges_from((A(u), A(v)) for u, v in edges)
    return graph, frozenset(frozenset({A(u), A(v)}) for u, v in latent)


def _effect(x="x", extra=()):
    return EffectQuery(
        target=ValuedAtom(atom=A("y"), value=True),
        intervention=Intervention(atom=A(x), value=True), given=(),
        extra_interventions=tuple(Intervention(atom=A(e), value=True) for e in extra))


def _results(out):
    return {r["query_id"]: r for r in out["results"]}


# ---------------------------------------------------------------- producer
def test_a_child_of_the_treatment_is_not_offered_as_an_instrument():
    graph, latent = _graph(CHILD_EDGES, LATENT)
    assert structural_solver.iv_sets(graph, A("x"), A("y"), bidirected=latent) == ()


def test_beside_a_real_instrument_only_the_real_one_is_offered():
    graph, latent = _graph(BOTH_EDGES, LATENT)
    offered = structural_solver.iv_sets(graph, A("x"), A("y"), bidirected=latent)
    assert [c.instrument.predicate for c in offered] == ["z"]


def test_no_treatment_of_a_vector_causes_its_instruments():
    graph, latent = _graph(VECTOR_EDGES, VECTOR_LATENT)
    offered = structural_solver.vector_iv_sets(
        graph, (A("a"), A("b")), A("y"), bidirected=latent)
    assert sorted(c.instrument.predicate for c in offered) == ["z1", "z2"]


# ---------------------------------------------------------------- verifier
@pytest.mark.parametrize("z,w", [("m", ()), ("z", ("m",))])
def test_the_criterion_says_when_the_treatment_causes_it(z, w):
    graph, latent = _graph(BOTH_EDGES, LATENT)
    upstream, _, _ = iv_criterion_holds(
        graph, latent, A("x"), A("y"), A(z), frozenset(A(n) for n in w))
    assert upstream is False
    assert iv_criterion_holds(
        graph, latent, A("x"), A("y"), A("z"), frozenset()) == (True, True, True)


def test_the_vector_criterion_says_when_a_treatment_causes_it():
    graph, latent = _graph(VECTOR_EDGES, VECTOR_LATENT)
    ctx = VerificationContext(graph=graph, query=_effect("a", ("b",)),
                              bidirected=latent)

    def step(instrument):
        return {"graph": graph, "y": A("y"), "instrument": A(instrument),
                "treatments": frozenset({A("a"), A("b")}),
                "conditioning": frozenset()}

    _rule_vector_iv_criterion_check(ctx, step("z1"), True, 0)
    _rule_vector_iv_criterion_check(ctx, step("m"), False, 0)
    with pytest.raises(Exception, match="claimed True, recomputed False"):
        _rule_vector_iv_criterion_check(ctx, step("m"), True, 0)


def test_a_block_naming_a_child_as_the_instrument_is_refused():
    graph, latent = _graph(BOTH_EDGES, LATENT)

    def block(name):
        return {"pattern": "instrumental_variable", "instrument": name,
                "conditioning": []}

    verify_identification_pattern(block("z(me)"), graph, latent, _effect())
    with pytest.raises(VerificationError, match="not caused by the treatment=False"):
        verify_identification_pattern(block("m(me)"), graph, latent, _effect())


def test_a_vector_block_naming_a_treatment_s_child_is_refused():
    graph, latent = _graph(VECTOR_EDGES, VECTOR_LATENT)

    def block(*instruments):
        return {"treatments": ["a", "b"], "outcome": "y",
                "instruments": list(instruments), "conditioning": []}

    verify_vector_iv_identification(
        block("z1", "z2"), graph, latent, _effect("a", ("b",)))
    with pytest.raises(VerificationError, match="which a treatment causes"):
        verify_vector_iv_identification(
            block("m", "z1", "z2"), graph, latent, _effect("a", ("b",)))


# -------------------------------------------------------------- end to end
def test_the_effect_question_is_not_answered_around_a_child():
    result = _results(themis.run(CHILD))["q"]
    assert result["missing_information"][0]["need"] == "admg_effect_not_identifiable"
    the_door_for(result)(CHILD, result)


def test_the_identify_question_is_not_answered_around_a_child():
    result = _results(themis.run(CHILD))["qi"]
    assert "iv_identification" not in (result.get("extensions") or {})
    the_door_for(result)(CHILD, result)


def _sample(with_instrument, n=100_000, seed=7):
    """P(y | do(x=1)) = 0.65, contrast 0.30, the same in every unit."""
    rng = np.random.default_rng(seed)
    u = rng.random(n) < 0.5
    z = rng.random(n) < 0.5
    x = rng.random(n) < 0.1 + 0.3 * u + (0.5 * z if with_instrument else 0.3)
    y = rng.random(n) < 0.1 + 0.3 * x + 0.5 * u
    m = rng.random(n) < 0.1 + 0.8 * x
    frame = {"x": x, "y": y, "m": m, **({"z": z} if with_instrument else {})}
    return pd.DataFrame(frame)


def test_on_data_no_number_is_taken_around_a_child():
    result = _results(themis.estimate(CHILD, _sample(False)))["q"]
    assert (result.get("numeric_estimate") or {}).get("instrument") is None
    the_door_for(result)(CHILD, result)


def test_beside_a_real_instrument_the_number_is_the_effect():
    result = _results(themis.estimate(BOTH, _sample(True)))["q"]
    estimate = result["numeric_estimate"]
    assert estimate["instrument"] == "z"
    assert abs(estimate["point"] - 0.30) < 0.03
    the_door_for(result)(BOTH, result)


def _moved_onto(node, name):
    """Every place an answer names its instrument, naming ``name``."""
    if isinstance(node, list):
        return [_moved_onto(v, name) for v in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for key, value in node.items():
        if key == "instrument" and isinstance(value, dict) and value.get("predicate") == "z":
            out[key] = {**value, "predicate": name}
        elif key == "instrument" and value in ("z", "z(me)"):
            out[key] = value.replace("z", name)
        else:
            out[key] = _moved_onto(value, name)
    return out


def test_an_identification_moved_onto_a_child_is_refused():
    honest = _results(themis.run(BOTH))["qi"]
    assert honest["extensions"]["iv_identification"]["instrument"] == "z(me)"
    the_door_for(honest)(BOTH, honest)
    forged = _moved_onto(honest, "m")
    assert forged != honest
    with pytest.raises(VerificationError, match="caused"):
        the_door_for(forged)(BOTH, forged)
