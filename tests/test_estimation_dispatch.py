"""Phase 7.1 S.N.3 — end-to-end themis.estimate integration tests.

Validates that:
- effect query + data → numeric_estimate attached, status flips to
  numerically_solved
- adjustment set is recovered from the graph (not the data)
- point estimate is in the expected range for a known DGP
- mediation queries pass through untouched (7.4 territory)
- unidentifiable queries skip the estimator cleanly
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _linear_confounded_dgp(n=1000, seed=0, true_ate=2.0):
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)
    # Z confounds X and Y
    x = rng.random(n) < (1 / (1 + np.exp(-0.8 * z)))
    y = 1.0 * z + true_ate * x.astype(float) + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"x": x, "z": z, "y": y})


def _confounded_ast():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }


# ============================================ happy path


def test_effect_query_with_data_returns_numeric_estimate():
    df = _linear_confounded_dgp(n=1000, seed=0, true_ate=2.0)
    out = themis.estimate(_confounded_ast(), df, ci_bootstrap=0)
    result = out["results"][0]

    assert result["status"] == "numerically_solved"
    est = result["numeric_estimate"]
    assert est["method"] == "backdoor_linear"
    assert est["adjustment"] == ["z"]
    assert abs(est["point"] - 2.0) < 0.25
    assert est["treatment"] == "x"
    assert est["outcome"] == "y"
    assert est["sample_size"] == 1000


def test_backdoor_estimate_attaches_assumption_ledger():
    """Binary/linear backdoor estimate surfaces the same assumption ledger
    as dose-response: identification assumptions (invalidating) + the
    outcome-model functional form (distorting), severity-sorted. (The
    user's point: binary has an applicable version too — it was just not
    wired before.)"""
    df = _linear_confounded_dgp(n=1000, seed=0, true_ate=2.0)
    out = themis.estimate(_confounded_ast(), df, ci_bootstrap=0)
    ext = out["results"][0]["extensions"]
    # mechanism_audit: the outcome regression form
    assert ext["mechanism_audit"]["mechanisms"][0]["form"] == "linear"
    # assumption_ledger: identification + functional_form, severity-sorted
    entries = ext["assumption_ledger"]["assumptions"]
    layers = [e["layer"] for e in entries]
    assert "identification" in layers
    assert "functional_form" in layers
    idx_id = min(i for i, e in enumerate(entries) if e["layer"] == "identification")
    idx_form = next(i for i, e in enumerate(entries) if e["layer"] == "functional_form")
    assert entries[idx_id]["severity"] == "invalidating"
    assert entries[idx_form]["severity"] == "distorting"
    assert idx_id < idx_form


def test_bootstrap_ci_populated_when_enabled():
    df = _linear_confounded_dgp(n=500, seed=0, true_ate=2.0)
    out = themis.estimate(_confounded_ast(), df, ci_bootstrap=100, random_state=1)
    est = out["results"][0]["numeric_estimate"]
    assert est["ci_lower"] is not None
    assert est["ci_upper"] is not None
    assert est["ci_lower"] <= est["point"] <= est["ci_upper"]


def test_precision_budget_attached_when_ci_present():
    """Iter 152: backdoor numeric_estimate carries a precision_budget
    field with N-to-halve-CI hint. SE ∝ 1/√N → halving needs 4× N."""
    df = _linear_confounded_dgp(n=500, seed=0, true_ate=2.0)
    out = themis.estimate(_confounded_ast(), df, ci_bootstrap=100, random_state=1)
    est = out["results"][0]["numeric_estimate"]
    assert "precision_budget" in est
    pb = est["precision_budget"]
    assert "current_ci_half_width" in pb
    assert "n_to_halve_ci" in pb
    assert "hint" in pb
    # Halving needs ≈4× N; current N=500 → expect n_to_halve in ~[1900, 2050]
    # (round-up-50 grain). Loose bracket — exact integer depends on bootstrap.
    assert 1900 <= pb["n_to_halve_ci"] <= 2050, (
        f"n_to_halve_ci={pb['n_to_halve_ci']} out of expected ~4×N range"
    )


def test_precision_budget_carries_relative_width_for_mechanical_surfacing():
    """Iter 160: precision_budget.relative_width = half_width / |point|
    lets the renderer's '>30% of point' heuristic be mechanical instead
    of LLM judgment. true_ate=2.0 with N=500 → expect relative_width
    well below 0.3 (CI tight relative to point of magnitude 2)."""
    df = _linear_confounded_dgp(n=500, seed=0, true_ate=2.0)
    out = themis.estimate(_confounded_ast(), df, ci_bootstrap=100, random_state=1)
    pb = out["results"][0]["numeric_estimate"]["precision_budget"]
    assert "relative_width" in pb, (
        "relative_width missing — iter 160 mechanical-surface field "
        "not wired"
    )
    # Sanity: with N=500 and a 2.0 ATE, bootstrap CI should be much
    # tighter than 30% of point. Loose bracket, just confirm finiteness
    # and order-of-magnitude correctness.
    assert 0 < pb["relative_width"] < 1.0


def test_empty_adjustment_when_no_confounder():
    """X → Y with no backdoor: ATE identifiable with empty adjustment."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "x": rng.random(200) < 0.5,
        "y": rng.random(200) < 0.5,
    })
    out = themis.estimate(ast, df, ci_bootstrap=0)
    est = out["results"][0]["numeric_estimate"]
    assert est["adjustment"] == []


# ============================================ mediation passthrough


def test_mediation_query_now_runs_imai_estimator():
    """Phase 7.4: mediation queries get a numeric NDE/NIE/TE block via
    the Imai-via-statsmodels estimator. Status stays structurally_solved
    because the identification is the primary answer; numeric is detail."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
                "mediator": _atom("m"),
            }},
        ],
    }
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "x": rng.random(100) < 0.5,
        "m": rng.random(100) < 0.5,
        "y": rng.random(100) < 0.5,
    })
    out = themis.estimate(ast, df, ci_bootstrap=0)
    result = out["results"][0]
    # Status stays structurally_solved — identification is primary answer
    assert result["status"] == "structurally_solved"
    # Mediation identification preserved
    assert "mediation_decomposition" in result["extensions"]
    # Numeric attached with a decomposition sub-block
    assert "numeric_estimate" in result
    est = result["numeric_estimate"]
    assert est["method"] in ("mediation_linear_imai", "mediation_logit_imai")
    assert "decomposition" in est
    for branch in ("nde", "nie", "te"):
        assert "point" in est["decomposition"][branch]
        assert "ci_lower" in est["decomposition"][branch]


# ============================================ unidentifiable passthrough


def test_unidentifiable_query_skips_numeric():
    """X ↔ Y latent confounder, no IV. Backdoor fails, front-door
    unavailable. 7.1 must not attempt numerical estimation — result
    stays as-is from identification layer."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "bidirected",
             "left": _atom("x"), "right": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "x": rng.random(100) < 0.5,
        "y": rng.random(100) < 0.5,
    })
    out = themis.estimate(ast, df, ci_bootstrap=0)
    result = out["results"][0]
    # Identification says needs_investigation — no numeric estimate
    assert "numeric_estimate" not in result


# ============================================ determinism


def test_themis_estimate_is_deterministic():
    df = _linear_confounded_dgp(n=300, seed=0)
    o1 = themis.estimate(_confounded_ast(), df, ci_bootstrap=50, random_state=42)
    o2 = themis.estimate(_confounded_ast(), df, ci_bootstrap=50, random_state=42)
    e1 = o1["results"][0]["numeric_estimate"]
    e2 = o2["results"][0]["numeric_estimate"]
    assert e1["point"] == e2["point"]
    assert e1["ci_lower"] == e2["ci_lower"]
    assert e1["ci_upper"] == e2["ci_upper"]
    assert e1["data_hash"] == e2["data_hash"]


# ============================================ identify query untouched


def test_identify_query_returns_unchanged():
    """identify query results should NOT get a numeric_estimate — they
    answer the structural question and have no data semantics."""
    ast = _confounded_ast()
    # Flip the query kind to identify
    ast["statements"][-1] = {
        "kind": "query", "id": "q", "query": {
            "kind": "identify",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": _atom("y"),
            "given": [],
        },
    }
    df = _linear_confounded_dgp(n=100, seed=0)
    out = themis.estimate(ast, df, ci_bootstrap=0)
    result = out["results"][0]
    assert result["status"] == "structurally_solved"
    assert "numeric_estimate" not in result


# ============================================ positivity / honesty


def test_single_arm_treatment_refuses_rather_than_fabricates():
    """VISION red line: data with a single observed treatment level has
    ZERO treatment contrast. The g-formula would extrapolate the absent
    arm and return a falsely-precise number. The estimator must refuse —
    EstimatorFailure(overlap_insufficient) — not fabricate. Real-usage
    probe 2026-06-16."""
    from themis.refusals import EstimatorFailure

    rng = np.random.default_rng(22)
    n = 2000
    df = pd.DataFrame({
        "x": np.ones(n, dtype=bool),   # single arm — never False
        "z": rng.standard_normal(n),
        "y": rng.random(n) < 0.6,
    })
    with pytest.raises(EstimatorFailure) as exc:
        themis.estimate(_confounded_ast(), df, ci_bootstrap=0)
    assert exc.value.failure_type == "overlap_insufficient"
    assert "single observed level" in str(exc.value)


def test_numerically_solved_gap_report_is_reconciled_and_self_consistent():
    """After a point estimate is computed from the supplied data, the gap
    report must not still advertise the data as missing. The
    ``missing_distribution: blocking`` and ``answer_is_bounds_not_point_
    estimate`` gaps are dropped, the parameter investigation_requests they
    cite are dropped (so the kernel's own T10 auditor stays satisfied),
    answer_tier becomes 'point', and the summary is recomputed. Real-usage
    probe 2026-06-16.

    ``actionable_next_steps`` is derived from the gaps too, and was left
    behind by the first version of this reconciliation: a report with no
    distribution gap in it went on opening its next-steps with
    "补 P(y=True|w=True,x=True)". Both derived surfaces are checked here
    because both are read, and because one of them being right proves
    nothing about the other."""
    import json

    df = _linear_confounded_dgp(n=1500, seed=3, true_ate=2.0)
    result = json.loads(
        json.dumps(themis.estimate(_confounded_ast(), df, ci_bootstrap=0)["results"][0])
    )
    assert result["status"] == "numerically_solved"
    report = result["data_gap_report"]
    kinds = {g["kind"] for g in report["gaps"]}
    # The two gaps that contradict a computed point are gone.
    assert "missing_distribution" not in kinds
    assert "answer_is_bounds_not_point_estimate" not in kinds
    # Tier reflects the computed point; summary no longer says "missing P(...)".
    assert report["answer_tier"] == "point"
    assert "缺概率分布" not in report["summary"]
    # …and neither does the tail derived from the same gaps.
    assert not [
        step for step in report.get("actionable_next_steps", [])
        if step.startswith("补 P(")
    ], report.get("actionable_next_steps")
    # No leftover parameter investigation_requests citing satisfied θ.
    assert all(
        ir.get("group") != "parameter"
        for ir in result.get("investigation_requests", [])
    )
    # Dual-surface: the kernel's own auditor accepts the reconciled report.
    themis.verify_data_gap_report(result)


def test_iv_estimate_keeps_interval_tier_not_point():
    """The post-numeric-solve reconciliation must NOT claim answer_tier=
    'point' for an IV estimate: non-parametric point ID failed (the
    unidentifiable gap is retained), the IV Wald number rests on
    monotonicity, and the honest non-parametric answer is the interval.
    Setting tier='point' here would contradict the retained unidentifiable
    gap. Regression for the gate added after the reconciliation landed."""
    import json

    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }
    rng = np.random.default_rng(5)
    n = 4000
    z = rng.random(n) < 0.5
    u = rng.random(n) < 0.5  # latent confounder behind x<->y
    x = rng.random(n) < np.clip(0.2 + 0.5 * z + 0.3 * u, 0, 1)
    y = rng.random(n) < np.clip(0.2 + 0.4 * x + 0.3 * u, 0, 1)
    df = pd.DataFrame({"z": z, "x": x, "y": y})
    result = json.loads(
        json.dumps(themis.estimate(ast, df, ci_bootstrap=0)["results"][0])
    )
    assert result["status"] == "numerically_solved"
    assert result["numeric_estimate"]["method"] == "iv_wald"
    report = result["data_gap_report"]
    kinds = {g["kind"] for g in report["gaps"]}
    # Non-parametric point ID failed → gap retained, tier honest.
    assert "unidentifiable_no_admissible_set" in kinds
    assert report["answer_tier"] == "interval"
    # The bounds-framing caveat stays (the non-parametric answer is bounds).
    assert "answer_is_bounds_not_point_estimate" in kinds
    themis.verify_data_gap_report(result)


# ============================================ transport numeric path


def _transport_program(marginal):
    """z->x->y with a selection node on z between trial and user, and the
    target marginal P*(z) in program.extensions (bool keys)."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {"target_marginal": {"predicate": "z", "marginal": marginal}},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "selection_node", "id": "s_z", "affects": _atom("z"),
             "source_population": "trial", "target_population": "user"},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
                "target_population": "user",
            }},
        ],
    }


def _transport_source(n=4000, seed=0, ate_z_true=0.5, ate_z_false=0.2):
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.5
    x = rng.random(n) < 0.5
    y = (0.3 + x.astype(float) * np.where(z, ate_z_true, ate_z_false)
         + rng.normal(scale=0.1, size=n))
    return pd.DataFrame({"z": z, "x": x, "y": y})


def test_transport_numeric_result_passes_own_verifier():
    """A numerically_solved transport result must NOT crash themis.verify.
    Its derivation legitimately ends in the structural identify_via_transport
    terminal (post-stratification adds a number, not a new terminal); the
    numeric verifier now accepts that terminal. Real-usage probe 2026-06-16."""
    prog = _transport_program({True: 0.7, False: 0.3})
    out = themis.estimate(prog, _transport_source(seed=0), ci_bootstrap=0)
    res = out["results"][0]
    assert res["status"] == "numerically_solved"
    assert res["numeric_estimate"]["point"] == pytest.approx(0.41, abs=0.05)
    themis.verify(prog, res)  # was VerificationError before


def test_transport_numeric_reconciles_gap_report():
    """Transport must run the post-numeric reconciliation like backdoor:
    after a point is computed, the structural-pass transport data-need gaps
    (missing_distribution / transport_source_conditional_unknown /
    transport_target_distribution_unknown) are no longer true and must not
    ship as blocking next to the number."""
    import json

    prog = _transport_program({True: 0.7, False: 0.3})
    res = json.loads(json.dumps(
        themis.estimate(prog, _transport_source(seed=1), ci_bootstrap=0)["results"][0]
    ))
    assert res["status"] == "numerically_solved"
    report = res["data_gap_report"]
    blocking = {g["kind"] for g in report["gaps"] if g["severity"] == "blocking"}
    assert blocking == set()
    assert report["answer_tier"] == "point"
    themis.verify_data_gap_report(res)


def test_a_study_sample_does_not_settle_an_ask_about_another_population():
    """Holding every variable an ask names is not holding the ask.

    A transport query wants P_trial(y|x,z), and the supplied DataFrame has
    columns for x, y and z — so a rule reading only the variables would
    settle it. It is a sample of the source, and what is being asked for
    is a conditional in the trial population; nothing about this sample
    stands in for that. The reconciliation reads the population the ask
    carries, which is why the ask survives here and the study-population
    ones do not.
    """
    rng = np.random.default_rng(0)
    n = 4000
    z = rng.random(n) < 0.5
    x = rng.random(n) < 0.5
    df = pd.DataFrame({
        "z": z, "x": x,
        "y": (0.3 + x.astype(float) * np.where(z, 0.5, 0.2)
              + rng.normal(scale=0.1, size=n)),
    })
    # A target marginal that does not sum to 1 — the estimator refuses, so
    # no number arrives to settle the ask on the stronger warrant.
    prog = _transport_program({True: 0.3, False: 0.3})
    result = themis.estimate(prog, df, ci_bootstrap=0)["results"][0]

    assert result["estimator_failure"]["failure_type"] == "invalid_input"
    kept = [
        m for m in result["missing_information"]
        if m["gap"] == "missing_distribution"
    ]
    assert kept, "the transport parameter ask was dropped by the study sample"
    assert kept[0]["observable"]["population"] == "trial"
    assert set(kept[0]["observable"]["variables"]) <= set(df.columns)
    themis.verify_data_gap_report(result)


def test_transport_positivity_violation_surfaces_structured_failure():
    """Target marginal demands a stratum the source has zero support for.
    The estimator's refusal must surface as a structured estimator_failure,
    NOT be silently swallowed (which is indistinguishable from 'no target
    supplied'). VISION red line: pathological data must be disclosed."""
    import json

    rng = np.random.default_rng(0)
    n = 4000
    # Source has ONLY z=False; target demands z=True with weight 0.5.
    df = pd.DataFrame({
        "z": np.zeros(n, dtype=bool),
        "x": rng.random(n) < 0.5,
        "y": 0.3 + (rng.random(n) < 0.5).astype(float) * 0.2 + rng.normal(scale=0.1, size=n),
    })
    res = json.loads(json.dumps(
        themis.estimate(_transport_program({True: 0.5, False: 0.5}), df,
                        ci_bootstrap=0)["results"][0]
    ))
    assert res.get("numeric_estimate") is None
    failure = res.get("estimator_failure")
    assert failure is not None
    assert failure["estimator"] == "transport_post_stratification"
    assert failure["failure_type"] == "overlap_insufficient"
    assert "no observations" in failure["reason"]


def test_transport_one_armed_stratum_is_a_positivity_finding_not_a_bad_request():
    """The stratum exists and is one-armed, so there is no contrast in it to
    transport. That is a fact about the data, and the species has to say so:
    it once arrived as `invalid_input`, which tells the caller to go fix a
    request that was never wrong.

    Its sibling — a stratum with no rows at all — was the branch that had a
    test, and it is the branch the old message-matching happened to catch."""
    import json

    rng = np.random.default_rng(0)
    n = 4000
    z = rng.random(n) < 0.5
    df = pd.DataFrame({
        "z": z,
        "x": np.where(z, True, rng.random(n) < 0.5),   # z=True: treated only
        "y": rng.normal(size=n),
    })
    res = json.loads(json.dumps(
        themis.estimate(_transport_program({True: 0.5, False: 0.5}), df,
                        ci_bootstrap=0)["results"][0]
    ))
    failure = res["estimator_failure"]
    assert failure["failure_type"] == "overlap_insufficient"
    assert failure["kind"] == "data"
    assert failure["details"]["n_control"] == 0


def test_transport_malformed_target_marginal_stays_a_bad_request():
    """The other side of the same distinction: when the request really is
    malformed the species must not drift into a data finding, or the caller
    goes looking for data that would not have helped."""
    import json

    res = json.loads(json.dumps(
        themis.estimate(_transport_program({True: 0.3, False: 0.3}),   # ≠ 1
                        _transport_source(seed=0), ci_bootstrap=0)["results"][0]
    ))
    failure = res["estimator_failure"]
    assert failure["failure_type"] == "invalid_input"
    assert failure["kind"] == "request"


def test_transport_marginal_with_json_string_keys_produces_number():
    """JSON object keys are always strings, so a target marginal supplied
    via the documented JSON-in path arrives as {"true":.7,"false":.3} while
    estimate_transport keys strata on bool. The dispatch coerces the keys
    so the JSON-string and in-process paths produce the same number, rather
    than silently/loudly failing on the JSON path. Real-usage probe 2026-06-16."""
    import json

    prog = _transport_program({"true": 0.7, "false": 0.3})  # string keys
    out = themis.estimate(json.dumps(prog), _transport_source(seed=0),
                          ci_bootstrap=0)  # program as a JSON STRING
    res = out["results"][0]
    assert res["status"] == "numerically_solved"
    assert res.get("estimator_failure") is None
    assert res["numeric_estimate"]["point"] == pytest.approx(0.41, abs=0.05)
