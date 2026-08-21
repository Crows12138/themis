"""General-ID (c-factor plug-in) numeric evaluator — unit tests.

The estimand under test is Pearl's napkin (W→Z→X→Y, W↔X, W↔Y): the
effect of X on Y is NOT identified by any back-door adjustment, front-door
set, or instrument — only by the general ID algorithm's c-factor
factorisation (a nested ratio). estimate_general_id_ate evaluates that
identified formula on discrete data by the non-parametric plug-in.

The DGP has a KNOWN true ATE (computed in closed form from the SCM), and
strong X–Y confounding through the open back-door X←Z←W←U_wy→Y so the
naive P(Y|X) contrast is badly biased — the plug-in must recover truth
where the naive estimate cannot.
"""
from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from themis.input.syntactic_validator import validate_ast
from themis.input.semantic_validator import validate_program
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime import structural_solver
from themis.types import Atom, ConstTerm
from themis.estimation.general_id import (
    GeneralIdEstimate,
    estimate_general_id_ate,
    estimate_joint_general_id_ate,
)
from themis.refusals import EstimatorFailure


def _A(p: str) -> Atom:
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _napkin_graph():
    """Build the napkin (graph, bidirected, x, y) via the AST projection —
    the exact path the dispatch uses, so the atoms match by value."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "w", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("w"), "to": _atom("z")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("w"), "right": _atom("x")},
            {"kind": "bidirected", "left": _atom("w"), "right": _atom("y")},
        ],
    }
    prog = validate_program(validate_ast(ast))
    ground = instantiate(prog)
    graph = project(ground)
    bidirected = structural_solver.bidirected_from_ground(ground)
    x = next(n for n in graph.nodes() if n.predicate == "x")
    y = next(n for n in graph.nodes() if n.predicate == "y")
    return graph, bidirected, x, y


def _sigmoid(t):
    return 1.0 / (1.0 + np.exp(-t))


def _napkin_data(n, seed=0):
    """SCM realising the napkin ADMG. U_wx is the W↔X latent, U_wy the
    W↔Y latent. Strong U_wy→W→Z→X and U_wy→Y makes the X–Y back-door
    (through Z) heavily confounded."""
    rng = np.random.default_rng(seed)
    u_wx = rng.random(n) < 0.5
    u_wy = rng.random(n) < 0.5
    W = rng.random(n) < _sigmoid(2.5 * u_wy + 1.0 * u_wx - 1.75)
    Z = rng.random(n) < _sigmoid(3.0 * W - 1.5)
    X = rng.random(n) < _sigmoid(3.0 * Z + 0.5 * u_wx - 1.75)
    Y = rng.random(n) < _sigmoid(1.2 * X + 2.5 * u_wy - 1.85)
    return pd.DataFrame({"w": W, "z": Z, "x": X, "y": Y})


# True ATE = E_{U_wy}[P(Y=1|X=1,U_wy) - P(Y=1|X=0,U_wy)], U_wy ~ Bern(0.5).
_TRUE_ATE = sum(
    0.5 * (_sigmoid(1.2 * 1.0 + 2.5 * u - 1.85) - _sigmoid(1.2 * 0.0 + 2.5 * u - 1.85))
    for u in (0.0, 1.0)
)


# ============================================ recovery vs truth


def test_plugin_recovers_true_ate_where_only_cfactor_identifies():
    graph, bi, x, y = _napkin_graph()
    # Sanity: this graph is NOT back-door / front-door / IV identifiable —
    # only the general c-factor algorithm identifies it.
    assert not structural_solver.minimal_adjustment_sets(graph, x, y, bidirected=bi)
    assert not structural_solver.front_door_sets(graph, x, y, bidirected=bi)

    df = _napkin_data(6000, seed=0)
    est = estimate_general_id_ate(
        df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
        ci_bootstrap=0,
    )
    assert isinstance(est, GeneralIdEstimate)
    assert est.method == "general_id_plugin"
    assert abs(est.point - _TRUE_ATE) < 0.035, (
        f"plug-in {est.point} vs true {_TRUE_ATE}"
    )


def test_plugin_beats_naive_confounded_contrast():
    graph, bi, x, y = _napkin_graph()
    df = _napkin_data(6000, seed=1)
    est = estimate_general_id_ate(
        df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
        ci_bootstrap=0,
    )
    naive = df.loc[df.x, "y"].mean() - df.loc[~df.x, "y"].mean()
    # naive is badly biased (open back-door through Z); the plug-in is
    # an order of magnitude closer to truth.
    assert abs(naive - _TRUE_ATE) > 0.08
    assert abs(est.point - _TRUE_ATE) < abs(naive - _TRUE_ATE) / 3


def test_bootstrap_ci_brackets_point_and_covers_truth():
    graph, bi, x, y = _napkin_graph()
    df = _napkin_data(8000, seed=2)
    est = estimate_general_id_ate(
        df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
        ci_bootstrap=200, random_state=42,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= est.point <= est.ci_upper
    assert est.ci_lower <= _TRUE_ATE <= est.ci_upper


def test_determinism_same_seed_identical():
    graph, bi, x, y = _napkin_graph()
    df = _napkin_data(3000, seed=3)
    a = estimate_general_id_ate(
        df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
        ci_bootstrap=80, random_state=7,
    )
    b = estimate_general_id_ate(
        df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
        ci_bootstrap=80, random_state=7,
    )
    assert a.point == b.point
    assert a.ci_lower == b.ci_lower and a.ci_upper == b.ci_upper


def test_records_contrast_levels_and_hash():
    graph, bi, x, y = _napkin_graph()
    df = _napkin_data(2000, seed=4)
    est = estimate_general_id_ate(
        df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
        ci_bootstrap=0,
    )
    assert est.treatment_high is True and est.treatment_low is False
    assert est.outcome_high is True
    assert est.treatment == "x" and est.outcome == "y"
    assert len(est.data_hash) == 64
    assert est.form == "nonparametric_plug_in"


# ============================================ honest refusals (guards)


def test_bow_arc_not_identifiable_raises():
    """X → Y, X ↔ Y — the canonical hedge; do(X) is not point-identified,
    so there is no c-factor estimand to evaluate."""
    x, y = _A("x"), _A("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, y)])
    bi = frozenset({frozenset({x, y})})
    df = pd.DataFrame({
        "x": (np.arange(200) % 2).astype(bool),
        "y": (np.arange(200) % 3 == 0),
    })
    with pytest.raises(EstimatorFailure) as exc:
        estimate_general_id_ate(
            df, graph=g, bidirected=bi, treatment_atom=x, outcome_atom=y,
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == "not_identifiable_by_general_id"


def test_non_binary_treatment_raises():
    graph, bi, x, y = _napkin_graph()
    rng = np.random.default_rng(0)
    n = 500
    df = pd.DataFrame({
        "w": rng.random(n) < 0.5, "z": rng.random(n) < 0.5,
        "x": rng.integers(0, 3, n), "y": rng.random(n) < 0.5,
    })
    with pytest.raises(EstimatorFailure) as exc:
        estimate_general_id_ate(
            df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == "treatment_not_binary"


def test_non_binary_outcome_raises():
    graph, bi, x, y = _napkin_graph()
    rng = np.random.default_rng(0)
    n = 500
    df = pd.DataFrame({
        "w": rng.random(n) < 0.5, "z": rng.random(n) < 0.5,
        "x": rng.random(n) < 0.5, "y": rng.integers(0, 3, n),
    })
    with pytest.raises(EstimatorFailure) as exc:
        estimate_general_id_ate(
            df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == "outcome_not_binary"


def _two_treatment_graph():
    """Two treatments and an outcome. The joint corner's guards run before
    identification does, so what the graph identifies does not matter here."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "a", "domain": [True, False]},
            {"kind": "variable", "predicate": "b", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("a")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("b")},
            {"kind": "cause", "from": _atom("a"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("b"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("z"), "right": _atom("y")},
        ],
    }
    prog = validate_program(validate_ast(ast))
    ground = instantiate(prog)
    graph = project(ground)
    bidirected = structural_solver.bidirected_from_ground(ground)
    named = {n.predicate: n for n in graph.nodes()}
    return graph, bidirected, (named["a"], named["b"]), named["y"]


def _joint_refusal(df):
    graph, bi, treatments, y = _two_treatment_graph()
    with pytest.raises(EstimatorFailure) as exc:
        estimate_joint_general_id_ate(
            df, graph=graph, bidirected=bi, treatment_atoms=treatments,
            outcome_atom=y, ci_bootstrap=0,
        )
    return exc.value


def test_treatments_binary_on_different_pairs_is_not_non_binary():
    """Two binary treatments, two different pairs — the corner is undefined
    and neither column is the reason.

    "All treatments at the same level" needs a level they share. Each of
    these has exactly two, which is what the binary guard asks and why it
    cannot be the one that answers here: reading its sentence, the caller
    would go looking for a column with three values and find none.
    """
    rng = np.random.default_rng(0)
    n = 400
    failure = _joint_refusal(pd.DataFrame({
        "z": rng.random(n) < 0.5,
        "a": rng.integers(0, 2, n),        # {0, 1}
        "b": rng.integers(0, 2, n) * 2,    # {0, 2} — binary, and not the same
        "y": rng.random(n) < 0.5,
    }))
    assert failure.failure_type == "treatment_levels_differ"
    assert sorted(failure.details["treatments"]) == ["a", "b"]
    assert len(failure.details["level_sets"]) == 2
    assert "a" in str(failure) and "b" in str(failure)


def test_treatments_sharing_one_set_that_is_not_a_pair_is_non_binary():
    """One shared level set of three: every treatment is the same non-binary
    column, and that is the plain fact the other guard states."""
    rng = np.random.default_rng(0)
    n = 400
    levels = rng.integers(0, 3, n)
    failure = _joint_refusal(pd.DataFrame({
        "z": rng.random(n) < 0.5,
        "a": levels, "b": levels,          # one set, shared, three deep
        "y": rng.random(n) < 0.5,
    }))
    assert failure.failure_type == "treatment_not_binary"
    assert sorted(failure.details["treatment"]) == ["a", "b"]
    assert failure.details["levels"] == [0, 1, 2]


def test_insufficient_support_positivity_raises():
    """When a conditioning stratum the identified formula needs has zero
    support (here Z is perfectly collinear with W, so the (w=False, z=True)
    cell is empty), the plug-in refuses rather than fabricating a value."""
    graph, bi, x, y = _napkin_graph()
    rng = np.random.default_rng(0)
    n = 400
    W = rng.random(n) < 0.5
    df = pd.DataFrame({
        "w": W,
        "z": W.copy(),                 # z == w — off-diagonal strata empty
        "x": rng.random(n) < 0.5,
        "y": rng.random(n) < 0.5,
    })
    with pytest.raises(EstimatorFailure) as exc:
        estimate_general_id_ate(
            df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == "insufficient_support"


def test_missing_column_raises():
    graph, bi, x, y = _napkin_graph()
    df = pd.DataFrame({
        "w": [True, False] * 50, "z": [True, False] * 50,
        "x": [True, False] * 50,   # no 'y' column
    })
    with pytest.raises(EstimatorFailure) as exc:
        estimate_general_id_ate(
            df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == "missing_column"


def test_cluster_bootstrap_runs_and_is_deterministic():
    graph, bi, x, y = _napkin_graph()
    df = _napkin_data(3000, seed=5)
    df["site"] = (np.arange(len(df)) // 10)      # 300 clusters of 10
    est = estimate_general_id_ate(
        df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
        ci_bootstrap=100, random_state=1, cluster="site",
    )
    assert est.cluster == "site"
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= est.point <= est.ci_upper
    # 'site' is not part of the causal model — not in the data hash inputs
    assert est.treatment == "x" and est.outcome == "y"
