"""An instrument with nothing conditioned is one answer, read by every door.

Balke-Pearl bounds and the response-function polytopes are built on an
instrument that needs nothing conditioned. Which node is one was answered
twice. The scheduler took an edge into the treatment and none into the
outcome, and fed that to the symbolic and numeric Balke-Pearl rows and to the
theta-side polytopes; the data-side reader asked the full criterion. The
verifier split the same way, and its data causation rule asked nothing.

A node that shares a cause w with the outcome has both edges. Measured before
the change on w -> z, w -> y, z -> x, x -> y, x <-> y, with P(y | do(x=1)) =
0.650: the Balke-Pearl interval came back [0.698, 0.855], outside the effect
by nineteen times its own CI margin, and every door took it.

Now one function on each side answers it -- parent of the treatment, not the
outcome, cut off from the outcome once the treatment's outgoing edges are
removed -- and the new names are imported inside each test, so a run before
the change fails test by test rather than at collection.
"""
from __future__ import annotations

import json
import pathlib

import networkx as nx
import numpy as np
import pandas as pd
import pytest

import themis
from tests.answer_corpus import the_door_for
from themis.types import Atom, ConstTerm, CausationQuery
from themis.verifier import VerificationContext
from themis.verifier.bounds_rules import (
    _graph_instrument_candidates, verify_balke_pearl_iv_bounds_result,
)
from themis.verifier.errors import VerificationError

SHAPES = json.loads((pathlib.Path(__file__).parent / "fixtures"
                     / "answer_shapes.json").read_text(encoding="utf-8"))
#: w -> z, w -> y, z -> x, x -> y, x <-> y: z is an instrument only given w.
SHARED = SHAPES["iv_stratified_wald"]["program"]
#: z -> x -> y, x <-> y: z is an instrument with nothing conditioned.
CLEAN = SHAPES["iv_wald"]["program"]


def A(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _graph(edges, latent=(("x", "y"),)):
    graph = nx.DiGraph()
    graph.add_edges_from((A(u), A(v)) for u, v in edges)
    return graph, frozenset(frozenset({A(u), A(v)}) for u, v in latent)


SHARED_EDGES = [("w", "z"), ("w", "y"), ("z", "x"), ("x", "y")]
CLEAN_EDGES = [("z", "x"), ("x", "y")]


def _only_result(program, out):
    qid = next(s["id"] for s in program["statements"] if s.get("kind") == "query")
    return next(r for r in out["results"] if r["query_id"] == qid)


def _row(result, method="balke_pearl_iv"):
    return next((b for b in result.get("bounds_results") or ()
                 if b.get("method") == method), None)


# ---------------------------------------------------------------- producer
@pytest.mark.parametrize("edges,latent,offered", [
    (CLEAN_EDGES, [("x", "y")], ["z"]),
    (SHARED_EDGES, [("x", "y")], []),
    (CLEAN_EDGES + [("z", "y")], [("x", "y")], []),
    (CLEAN_EDGES, [("x", "y"), ("z", "y")], []),
])
def test_one_function_says_which_node_is_an_instrument(edges, latent, offered):
    from themis.runtime.structural_solver import unconditional_instruments

    graph, bidirected = _graph(edges, latent)
    found = unconditional_instruments(graph, A("x"), A("y"), bidirected=bidirected)
    assert [z.predicate for z in found] == offered


class _Theta:
    def domain_of(self, node):
        return (True, False)


@pytest.mark.parametrize("edges,offered", [(CLEAN_EDGES, "z"), (SHARED_EDGES, None)])
def test_the_theta_polytopes_read_it(edges, offered):
    from themis.runtime.scheduler import _instrument_for_theta_cell

    graph, bidirected = _graph(edges)
    found = _instrument_for_theta_cell(
        graph, _Theta(), x_atom=A("x"), y_atom=A("y"), bidirected=bidirected)
    assert (found.predicate if found is not None else None) == offered


@pytest.mark.parametrize("program,instrument", [(CLEAN, "z"), (SHARED, None)])
def test_a_balke_pearl_row_is_fitted_only_around_one(program, instrument):
    result = _only_result(program, themis.run(program))
    row = _row(result)
    assert (row["instrument"] if row is not None else None) == instrument
    assert _row(result, "manski_natural") is not None
    the_door_for(result)(program, result)


def _sample(n, seed, *, shared):
    """P(y | do(x=1)) = mean(base) + 0.25, every probability inside [0, 1]."""
    rng = np.random.default_rng(seed)
    w = rng.random(n) < 0.5
    u = rng.random(n) < 0.5
    z = rng.random(n) < ((0.05 + 0.9 * w) if shared else 0.5)
    x = rng.random(n) < 0.05 + 0.5 * z + 0.4 * u
    base = 0.05 + 0.1 * u + (0.6 * w if shared else 0.0)
    y = rng.random(n) < base + 0.25 * x
    frame = {"z": z, "x": x, "y": y, **({"w": w} if shared else {})}
    return pd.DataFrame(frame), float(np.mean(base + 0.25))


@pytest.mark.parametrize("program,shared", [(CLEAN, False), (SHARED, True)])
def test_on_data_every_interval_holds_the_effect(program, shared):
    df, arm = _sample(100_000, 11, shared=shared)
    result = _only_result(program, themis.estimate(program, df))
    rows = [b for b in result.get("bounds_results") or ()
            if b.get("lower_value") is not None]
    assert rows
    for row in rows:
        assert row["ci_lower"] - 0.01 <= arm <= row["ci_upper"] + 0.01, row["method"]
    assert (_row(result) is not None) == (not shared)
    the_door_for(result)(program, result)


# ---------------------------------------------------------------- verifier
@pytest.mark.parametrize("edges,latent,holds", [
    (CLEAN_EDGES, [("x", "y")], True),
    (SHARED_EDGES, [("x", "y")], False),
    (CLEAN_EDGES + [("z", "y")], [("x", "y")], False),
    ([("z", "m"), ("m", "x"), ("x", "y")], [("x", "y")], False),
])
def test_the_verifier_holds_one_transcription(edges, latent, holds):
    from themis.verifier.rules import unconditional_instrument_holds

    graph, bidirected = _graph(edges, latent)
    assert unconditional_instrument_holds(
        graph, bidirected, A("x"), A("y"), A("z")) is holds


def _bp_row(program, instrument):
    query = next(s["query"] for s in program["statements"] if s.get("kind") == "query")
    row = {
        "method": "balke_pearl_iv", "estimand": "arm_probability",
        "tightness": "sharp", "instrument": instrument,
        "lower_expression":
            f"min of P(y=true | do(x=true)) over the response-function "
            f"polytope fitted to P(y, x | {instrument}) "
            f"(Balke-Pearl LP, 16 response types)",
        "upper_expression":
            f"max of P(y=true | do(x=true)) over the response-function "
            f"polytope fitted to P(y, x | {instrument}) "
            f"(same polytope, same observables as lower)",
        "assumptions": [
            "iv1_relevance",
            "iv2_exclusion_instrument_affects_outcome_only_via_treatment",
            "iv3_independence_instrument_independent_of_unmeasured_confounders",
        ],
    }
    return row, query


def test_a_row_fitted_around_a_node_sharing_a_cause_with_the_outcome_is_refused():
    assert _graph_instrument_candidates(SHARED, treatment="x", outcome="y") == set()
    assert _graph_instrument_candidates(CLEAN, treatment="x", outcome="y") == {"z"}
    row, query = _bp_row(CLEAN, "z")
    verify_balke_pearl_iv_bounds_result(row, program=CLEAN, query_dict=query)
    row, query = _bp_row(SHARED, "z")
    with pytest.raises(VerificationError, match="does not offer"):
        verify_balke_pearl_iv_bounds_result(row, program=SHARED, query_dict=query)


@pytest.mark.parametrize("edges,refused", [(CLEAN_EDGES, False), (SHARED_EDGES, True)])
def test_the_data_polytope_of_a_causation_answer_names_an_instrument(edges, refused):
    """The causation rule re-derived the polytope and never the column."""
    from themis.verifier.rules import _check_the_data_instrument

    graph, bidirected = _graph(edges)
    ctx = VerificationContext(
        graph=graph, bidirected=bidirected,
        query=CausationQuery(cause=A("x"), effect=A("y")))
    inputs = {"instrument": "z"}
    if not refused:
        _check_the_data_instrument(ctx, inputs, A("x"), A("y"),
                                   step_index=0, rule="numeric_causation_estimate")
        return
    with pytest.raises(Exception, match="is not the instrument"):
        _check_the_data_instrument(ctx, inputs, A("x"), A("y"),
                                   step_index=0, rule="numeric_causation_estimate")
