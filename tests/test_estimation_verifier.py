"""Phase 7.1 S.N.4 — verifier rule tests for numeric_backdoor_estimate.

Tests the relaxed-audit rule on:
- accepting a well-formed numeric estimate witness
- rejecting wrong method enum
- rejecting point outside CI
- rejecting malformed data_hash
- rejecting under-minimum sample size
- rejecting adjustment overlap with treatment / outcome
- rejecting mismatched adjustment between structural and numeric steps
- end-to-end: themis.verify round-trips a data-based estimate
- byte-code independence: verifier rule doesn't call sklearn / backdoor
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.types import (
    Atom,
    ConstTerm,
    DerivationStep,
    EffectQuery,
    Intervention,
    StepRef,
    StructuralResult,
    ValuedAtom,
)
from themis.verifier import VerificationContext
from themis.verifier.errors import VerificationError
from themis.verifier.rules import _rule_numeric_backdoor_estimate

import networkx as nx


def _atom(pred):
    return Atom(predicate=pred, args=(ConstTerm(name="me"),))


def _ctx(graph):
    x, y = _atom("x"), _atom("y")
    return VerificationContext(
        graph=graph,
        query=EffectQuery(
            target=ValuedAtom(atom=y, value=True),
            intervention=Intervention(atom=x, value=True),
            given=(),
        ),
    )


def _valid_criterion_step(graph, z_set):
    return DerivationStep(
        rule="backdoor_criterion",
        inputs={
            "graph": graph, "x": _atom("x"), "y": _atom("y"),
            "z": frozenset(z_set), "given": frozenset(),
        },
        output=True, label="s1",
    )


_OK_INPUTS = {
    "criterion": StepRef(label="s1"),
    "treatment": None,        # filled per-test
    "outcome": None,
    "adjustment": None,
    "method": "backdoor_linear",
    "data_hash": "0" * 64,
    "sample_size": 100,
    "point": 0.5,
    "ci_lower": 0.3,
    "ci_upper": 0.7,
    "ci_level": 0.95,
}


def _build_inputs(z_set, **overrides):
    x, y = _atom("x"), _atom("y")
    base = dict(_OK_INPUTS)
    base["treatment"] = x
    base["outcome"] = y
    base["adjustment"] = frozenset(z_set)
    base.update(overrides)
    return base


# ============================================ acceptance


def test_accepts_well_formed_estimate():
    z = _atom("z")
    g = nx.DiGraph()
    g.add_edges_from([(z, _atom("x")), (z, _atom("y")), (_atom("x"), _atom("y"))])
    criterion = _valid_criterion_step(g, {z})

    _rule_numeric_backdoor_estimate(
        ctx=_ctx(g),
        inputs=_build_inputs({z}),
        claimed_output=StructuralResult(value=True),
        step_index=1,
        step_by_id={"s1": criterion},
        step_output_by_id={"s1": True},
    )


def test_accepts_without_ci():
    z = _atom("z")
    g = nx.DiGraph()
    g.add_edges_from([(z, _atom("x")), (z, _atom("y")), (_atom("x"), _atom("y"))])
    criterion = _valid_criterion_step(g, {z})

    _rule_numeric_backdoor_estimate(
        ctx=_ctx(g),
        inputs=_build_inputs(
            {z}, ci_lower=None, ci_upper=None, ci_level=None,
        ),
        claimed_output=StructuralResult(value=True),
        step_index=1,
        step_by_id={"s1": criterion},
        step_output_by_id={"s1": True},
    )


# ============================================ rejections


def test_rejects_unknown_method():
    z = _atom("z")
    g = nx.DiGraph()
    g.add_edges_from([(z, _atom("x")), (z, _atom("y")), (_atom("x"), _atom("y"))])
    criterion = _valid_criterion_step(g, {z})

    with pytest.raises(VerificationError, match="method"):
        _rule_numeric_backdoor_estimate(
            ctx=_ctx(g),
            inputs=_build_inputs({z}, method="random_forest"),
            claimed_output=StructuralResult(value=True),
            step_index=1,
            step_by_id={"s1": criterion},
            step_output_by_id={"s1": True},
        )


def test_rejects_point_outside_ci():
    z = _atom("z")
    g = nx.DiGraph()
    g.add_edges_from([(z, _atom("x")), (z, _atom("y")), (_atom("x"), _atom("y"))])
    criterion = _valid_criterion_step(g, {z})

    with pytest.raises(VerificationError, match="outside"):
        _rule_numeric_backdoor_estimate(
            ctx=_ctx(g),
            inputs=_build_inputs(
                {z}, point=1.5, ci_lower=0.3, ci_upper=0.7,
            ),
            claimed_output=StructuralResult(value=True),
            step_index=1,
            step_by_id={"s1": criterion},
            step_output_by_id={"s1": True},
        )


def test_rejects_malformed_hash():
    z = _atom("z")
    g = nx.DiGraph()
    g.add_edges_from([(z, _atom("x")), (z, _atom("y")), (_atom("x"), _atom("y"))])
    criterion = _valid_criterion_step(g, {z})

    with pytest.raises(VerificationError, match="SHA-256"):
        _rule_numeric_backdoor_estimate(
            ctx=_ctx(g),
            inputs=_build_inputs({z}, data_hash="too_short"),
            claimed_output=StructuralResult(value=True),
            step_index=1,
            step_by_id={"s1": criterion},
            step_output_by_id={"s1": True},
        )


def test_rejects_under_minimum_sample_size():
    z = _atom("z")
    g = nx.DiGraph()
    g.add_edges_from([(z, _atom("x")), (z, _atom("y")), (_atom("x"), _atom("y"))])
    criterion = _valid_criterion_step(g, {z})

    with pytest.raises(VerificationError, match="sample_size"):
        _rule_numeric_backdoor_estimate(
            ctx=_ctx(g),
            inputs=_build_inputs({z}, sample_size=5),
            claimed_output=StructuralResult(value=True),
            step_index=1,
            step_by_id={"s1": criterion},
            step_output_by_id={"s1": True},
        )


def test_rejects_adjustment_overlaps_treatment():
    z = _atom("z")
    g = nx.DiGraph()
    g.add_edges_from([(z, _atom("x")), (z, _atom("y")), (_atom("x"), _atom("y"))])
    criterion = _valid_criterion_step(g, {z, _atom("x")})

    with pytest.raises(VerificationError, match="disjoint"):
        _rule_numeric_backdoor_estimate(
            ctx=_ctx(g),
            inputs=_build_inputs({z, _atom("x")}),  # includes treatment
            claimed_output=StructuralResult(value=True),
            step_index=1,
            step_by_id={"s1": criterion},
            step_output_by_id={"s1": True},
        )


def test_rejects_adjustment_mismatch_with_criterion_step():
    z, w = _atom("z"), _atom("w")
    g = nx.DiGraph()
    g.add_edges_from([(z, _atom("x")), (z, _atom("y")), (_atom("x"), _atom("y"))])
    # Criterion claims {z}, numeric step claims {w} — mismatch
    criterion = _valid_criterion_step(g, {z})

    with pytest.raises(VerificationError, match="equal the z-set"):
        _rule_numeric_backdoor_estimate(
            ctx=_ctx(g),
            inputs=_build_inputs({w}),
            claimed_output=StructuralResult(value=True),
            step_index=1,
            step_by_id={"s1": criterion},
            step_output_by_id={"s1": True},
        )


def test_rejects_structural_result_false():
    z = _atom("z")
    g = nx.DiGraph()
    g.add_edges_from([(z, _atom("x")), (z, _atom("y")), (_atom("x"), _atom("y"))])
    criterion = _valid_criterion_step(g, {z})

    with pytest.raises(VerificationError, match="must be True"):
        _rule_numeric_backdoor_estimate(
            ctx=_ctx(g),
            inputs=_build_inputs({z}),
            claimed_output=StructuralResult(value=False),
            step_index=1,
            step_by_id={"s1": criterion},
            step_output_by_id={"s1": True},
        )


def test_rejects_criterion_referencing_wrong_rule():
    z = _atom("z")
    g = nx.DiGraph()
    g.add_edges_from([(z, _atom("x")), (z, _atom("y")), (_atom("x"), _atom("y"))])
    # Criterion ref points to a graph_is_dag step, not backdoor_criterion
    wrong_step = DerivationStep(
        rule="graph_is_dag",
        inputs={"graph": g},
        output=True, label="s1",
    )

    with pytest.raises(VerificationError, match="backdoor_criterion"):
        _rule_numeric_backdoor_estimate(
            ctx=_ctx(g),
            inputs=_build_inputs({z}),
            claimed_output=StructuralResult(value=True),
            step_index=1,
            step_by_id={"s1": wrong_step},
            step_output_by_id={"s1": True},
        )


# ============================================ end-to-end


def test_themis_verify_accepts_data_based_estimate():
    """themis.estimate output round-trips through themis.verify."""
    def atom(p):
        return {"predicate": p, "args": [{"type": "const", "name": "me"}]}

    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": atom("z"), "to": atom("x")},
            {"kind": "cause", "from": atom("z"), "to": atom("y")},
            {"kind": "cause", "from": atom("x"), "to": atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": atom("x"), "value": True},
                "target": {"atom": atom("y"), "value": True},
                "given": [],
            }},
        ],
    }
    rng = np.random.default_rng(0)
    n = 500
    z = rng.standard_normal(n)
    x_data = rng.random(n) < 0.5
    y_data = 1.0 * z + 2.0 * x_data.astype(float) + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"x": x_data, "z": z, "y": y_data})

    out = themis.estimate(ast, df, ci_bootstrap=0)
    result = out["results"][0]

    assert result["status"] == "numerically_solved"
    # Must not raise
    themis.verify(ast, result)


# ============================================ byte-code independence


def test_verifier_rule_does_not_import_sklearn_or_estimators():
    """V-verifier invariant: the numeric_backdoor_estimate rule must not
    retrain a model — it's an audit layer, not a re-implementer. Scan
    its co_names for forbidden symbols."""
    forbidden = {
        "sklearn",
        "LogisticRegression",
        "LinearRegression",
        "estimate_backdoor_ate",
        "BackdoorEstimate",
        "bootstrap",
    }
    names = set(_rule_numeric_backdoor_estimate.__code__.co_names)
    leaked = names & forbidden
    assert not leaked, f"verifier rule leaked to estimator internals: {leaked}"


def test_verifier_module_does_not_import_estimators():
    import themis.verifier.rules as rules_mod
    assert not hasattr(rules_mod, "sklearn")
    assert not hasattr(rules_mod, "estimate_backdoor_ate")
    assert not hasattr(rules_mod, "BackdoorEstimate")
