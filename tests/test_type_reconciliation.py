"""Pre-flight data diagnostic (2026-07-11, borrow-list #3).

Themis reconciles each model variable's DECLARED measurement type
(``scale`` / ``domain``) against the ACTUAL supplied column and, on
disagreement, raises a ``declared_type_data_mismatch`` gap plus the
reconciliation evidence in ``extensions.type_reconciliation``. These tests
pin:

- the new ``VariableDeclaration.scale`` field round-trips (parse + serialize);
- the estimate path fires the gap on a real mismatch and stays SILENT on a
  consistent program and on an undeclared variable ("didn't say" ≠ "said
  continuous");
- both verdict shapes (declared_continuous_data_discrete / domain_violated);
- ``verify_type_reconciliation`` independently re-derives the verdict and
  rejects a tampered classification / verdict / severity / phantom / missing
  gap — including through the public ``themis.verify_data_gap_report`` entry;
- the mismatch surfaces in the unified ``build_analysis_report``.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.dispatch import _attach_type_reconciliation
from themis.output.analysis_report import build_analysis_report
from themis.types import VariableDeclaration
from themis.kernel import _statement_to_dict
from themis.input.semantic_validator import _to_statement
from themis.verifier import verify_type_reconciliation
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(x_decl: dict):
    """Backdoor DAG z→x, z→y, x→y with a configurable declaration for x."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", **x_decl},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {"kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True}, "given": []}},
        ],
    }


def _binary_df(n=400, seed=0):
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.3 + 0.4 * z).astype(int)
    y = (rng.random(n) < 0.2 + 0.3 * x + 0.2 * z).astype(int)
    return pd.DataFrame({"x": x.astype(bool), "y": y.astype(bool),
                         "z": z.astype(bool)})


def _df_with_x(x_values, n=400, seed=0):
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n).astype(bool)
    y = rng.integers(0, 2, n).astype(bool)
    return pd.DataFrame({"x": x_values, "y": y, "z": z})


def _reconciled(program, df):
    """Run structural identification, attach reconciliation, return result."""
    out = themis.run(program)
    _attach_type_reconciliation(program, out, df)
    return out["results"][0]


def _first_mismatch_gap(result):
    gaps = (result.get("data_gap_report") or {}).get("gaps") or []
    return [g for g in gaps if g.get("kind") == "declared_type_data_mismatch"]


# ============================================ scale field round-trip


def test_scale_field_round_trips_through_serializer():
    vd = VariableDeclaration(predicate="dose", scale="continuous")
    d = _statement_to_dict(vd)
    assert d["scale"] == "continuous"
    back = _to_statement(d)
    assert back.scale == "continuous"


def test_scale_absent_is_omitted_not_null():
    vd = VariableDeclaration(predicate="dose")
    d = _statement_to_dict(vd)
    assert "scale" not in d


def test_program_with_scale_parses_and_runs():
    # A declared scale is advisory — it must not change structural reasoning.
    prog = _program({"scale": "continuous"})
    out = themis.run(prog)
    assert out["results"]


# ============================================ fires on a real mismatch


def test_declared_continuous_but_binary_data_fires_end_to_end():
    prog = _program({"scale": "continuous"})
    env = themis.estimate(prog, _binary_df(), ci_bootstrap=50)
    res = env["results"][0]
    gaps = _first_mismatch_gap(res)
    assert len(gaps) == 1
    assert gaps[0]["signature"] == "declared_continuous_data_discrete"
    assert gaps[0]["severity"] == "important"
    assert gaps[0]["blocks"] == "interpretation"
    checks = res["extensions"]["type_reconciliation"]["checks"]
    assert checks[0]["predicate"] == "x"
    assert checks[0]["declared_scale"] == "continuous"
    assert checks[0]["observed_scale"] == "binary"


def test_binary_domain_violated_by_multivalue_data():
    prog = _program({"domain": [True, False]})
    df = _df_with_x(np.arange(400) % 5)  # 5 distinct integer values
    res = _reconciled(prog, df)
    gaps = _first_mismatch_gap(res)
    assert len(gaps) == 1
    assert gaps[0]["signature"] == "domain_violated"
    assert gaps[0]["blocks"] == "point_estimate"
    assert res["extensions"]["type_reconciliation"]["checks"][0]["n_unique"] == 5


def test_discrete_domain_out_of_range_value():
    prog = _program({"domain": [0, 1, 2]})
    df = _df_with_x(np.arange(400) % 4)  # values 0..3, 3 is out of domain
    res = _reconciled(prog, df)
    gaps = _first_mismatch_gap(res)
    assert len(gaps) == 1
    assert gaps[0]["signature"] == "domain_violated"
    check = res["extensions"]["type_reconciliation"]["checks"][0]
    assert 3 in check["observed_values"]


def test_discrete_declared_but_continuous_data():
    prog = _program({"scale": "discrete"})
    df = _df_with_x(np.linspace(0.0, 1.0, 400))  # 400 distinct floats
    res = _reconciled(prog, df)
    gaps = _first_mismatch_gap(res)
    assert len(gaps) == 1
    assert gaps[0]["signature"] == "domain_violated"
    assert res["extensions"]["type_reconciliation"]["checks"][0][
        "observed_scale"] == "continuous"


# ============================================ silence on consistent / undeclared


def test_consistent_binary_declaration_is_silent():
    prog = _program({"domain": [True, False]})
    res = _reconciled(prog, _binary_df())
    assert _first_mismatch_gap(res) == []
    assert "type_reconciliation" not in (res.get("extensions") or {})


def test_undeclared_variable_is_silent():
    # No scale, no domain on x → "didn't say", never reconciled.
    prog = _program({})
    res = _reconciled(prog, _binary_df())
    assert _first_mismatch_gap(res) == []


def test_declared_continuous_with_continuous_data_is_silent():
    prog = _program({"scale": "continuous"})
    df = _df_with_x(np.linspace(0.0, 5.0, 400))
    res = _reconciled(prog, df)
    assert _first_mismatch_gap(res) == []


# ============================================ verifier: accept honest output


def test_verifier_accepts_honest_reconciliation():
    res = _reconciled(_program({"scale": "continuous"}), _binary_df())
    verify_type_reconciliation(res)  # must not raise


def test_verify_data_gap_report_runs_reconciliation_end_to_end():
    res = _reconciled(_program({"scale": "continuous"}), _binary_df())
    themis.verify_data_gap_report(res)  # honest → ok


def test_verifier_noop_when_no_reconciliation_block():
    # A plain structural result carries no reconciliation → accept.
    res = themis.run(_program({"domain": [True, False]}))["results"][0]
    verify_type_reconciliation(res)


# ============================================ verifier: reject tampering


def _tampered(mutate):
    res = _reconciled(_program({"scale": "continuous"}), _binary_df())
    res = copy.deepcopy(res)
    mutate(res)
    return res


def test_verifier_rejects_flipped_verdict():
    def mutate(r):
        r["extensions"]["type_reconciliation"]["checks"][0]["verdict"] = \
            "domain_violated"
    with pytest.raises(VerificationError):
        verify_type_reconciliation(_tampered(mutate))


def test_verifier_rejects_wrong_observed_scale():
    def mutate(r):
        r["extensions"]["type_reconciliation"]["checks"][0][
            "observed_scale"] = "continuous"
    with pytest.raises(VerificationError):
        verify_type_reconciliation(_tampered(mutate))


def test_verifier_rejects_inconsistent_n_unique():
    def mutate(r):
        r["extensions"]["type_reconciliation"]["checks"][0]["n_unique"] = 9
    with pytest.raises(VerificationError):
        verify_type_reconciliation(_tampered(mutate))


def test_verifier_rejects_wrong_severity():
    def mutate(r):
        for g in r["data_gap_report"]["gaps"]:
            if g.get("kind") == "declared_type_data_mismatch":
                g["severity"] = "informational"
    with pytest.raises(VerificationError):
        verify_type_reconciliation(_tampered(mutate))


def test_verifier_rejects_wrong_blocks():
    def mutate(r):
        for g in r["data_gap_report"]["gaps"]:
            if g.get("kind") == "declared_type_data_mismatch":
                g["blocks"] = "point_estimate"  # verdict maps to interpretation
    with pytest.raises(VerificationError):
        verify_type_reconciliation(_tampered(mutate))


def test_verifier_rejects_phantom_gap():
    def mutate(r):
        r["data_gap_report"]["gaps"].append({
            "kind": "declared_type_data_mismatch",
            "signature": "domain_violated",
            "severity": "important",
            "blocks": "point_estimate",
            "describes": [{"sentence": "tian_found_a_hedge"}],
            "provenance": [{"ref_kind": "verifier_check",
                            "ref_id": "type_reconciliation:ghost"}],
        })
    with pytest.raises(VerificationError):
        verify_type_reconciliation(_tampered(mutate))


def test_verifier_rejects_missing_gap():
    def mutate(r):
        r["data_gap_report"]["gaps"] = [
            g for g in r["data_gap_report"]["gaps"]
            if g.get("kind") != "declared_type_data_mismatch"
        ]
    with pytest.raises(VerificationError):
        verify_type_reconciliation(_tampered(mutate))


# ============================================ report integration


def test_mismatch_surfaces_in_analysis_report():
    prog = _program({"scale": "continuous"})
    env = themis.estimate(prog, _binary_df(), ci_bootstrap=50)
    md = build_analysis_report(env["results"][0], program=prog)
    assert "数据缺口" in md
    assert "重要" in md
    # The declared scale, in the words the rest of the report is in. This
    # gap's description was the one English paragraph the package produced.
    assert "声明为连续" in md
