"""Targeted Maximum Likelihood Estimation (TMLE) for the ATE.

TMLE is the third doubly-robust estimator on the backdoor estimand,
alongside AIPW — asymptotically equivalent, but a bounded *substitution*
estimator that targets an initial outcome fit through a logistic
fluctuation. This suite pins:

1. **Double robustness** — TMLE recovers the true ATE when EITHER the
   outcome model OR the propensity model is misspecified (one at a time).
2. **Correct targeting + inference** — the substitution estimate + the
   efficient-influence-curve SE reproduce an independent hand
   computation; the binary path stays in the outcome's natural range;
   coverage is ~nominal; TMLE and AIPW agree on the same data.
3. **Verifier** rejects tampered estimates (point outside CI, propensity
   out of range, non-finite fluctuation parameter).

Textbook oracle: known DGP true ATE = 2, independently recomputed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis import kernel
from themis.estimation.aipw import estimate_aipw_ate
from themis.refusals import EstimatorFailure
from themis.estimation.tmle import estimate_tmle_ate
from themis.input.syntactic_validator import validate_result
from themis.verifier.verify import VerificationError

TRUE_ATE = 2.0


def _expit(x):
    return 1.0 / (1.0 + np.exp(-x))


def _dgp(rng, n=20000, *, prop_nonlinear=False, outcome_nonlinear=False):
    z = rng.normal(0, 1, n)
    lin = np.sin(z) * 2.0 if prop_nonlinear else 1.2 * z
    a = rng.binomial(1, _expit(lin)).astype(float)
    z_eff = 2.0 * np.exp(z) if outcome_nonlinear else 3.0 * z
    y = TRUE_ATE * a + z_eff + rng.normal(0, 1, n)
    return pd.DataFrame({"A": a, "Y": y, "Z": z})


# ============================================================ double robustness


def test_both_models_correct_recovers():
    df = _dgp(np.random.default_rng(0))
    est = estimate_tmle_ate(df, treatment="A", outcome="Y",
                            adjustment=("Z",), ci_bootstrap=0)
    assert abs(est.point - TRUE_ATE) < 0.1


def test_tmle_survives_misspecified_outcome_model():
    """Outcome nonlinear (exp Z), propensity correct → TMLE rescued."""
    df = _dgp(np.random.default_rng(0), outcome_nonlinear=True)
    est = estimate_tmle_ate(df, treatment="A", outcome="Y",
                            adjustment=("Z",), ci_bootstrap=0)
    assert abs(est.point - TRUE_ATE) < 0.1


def test_tmle_survives_misspecified_propensity_model():
    """Propensity nonlinear (sin Z), outcome correct → TMLE rescued."""
    df = _dgp(np.random.default_rng(0), prop_nonlinear=True)
    est = estimate_tmle_ate(df, treatment="A", outcome="Y",
                            adjustment=("Z",), ci_bootstrap=0)
    assert abs(est.point - TRUE_ATE) < 0.1


def test_tmle_and_aipw_agree_on_well_specified_data():
    """The two doubly-robust estimators are asymptotically equivalent —
    on the same large well-specified sample they land close together."""
    df = _dgp(np.random.default_rng(0))
    t = estimate_tmle_ate(df, treatment="A", outcome="Y",
                          adjustment=("Z",), ci_bootstrap=0)
    a = estimate_aipw_ate(df, treatment="A", outcome="Y",
                          adjustment=("Z",), ci_bootstrap=0)
    assert abs(t.point - a.point) < 0.05


# ============================================================ targeting + inference


def _hand_tmle(df, *, floor=0.01, delta=1e-4):
    """Independent re-implementation of the TMLE targeting for a
    continuous outcome (linear initial fit)."""
    import statsmodels.api as sm
    from sklearn.linear_model import LinearRegression, LogisticRegression

    t = df["A"].to_numpy(float); z = df["Z"].to_numpy(float); y = df["Y"].to_numpy(float)
    n = len(y)
    a, b = float(y.min()), float(y.max())
    span = b - a
    ys = (y - a) / span
    X = np.column_stack([t, z])
    reg = LinearRegression().fit(X, ys)
    clip = lambda p: np.clip(p, delta, 1 - delta)
    Q0 = clip(reg.predict(X))
    Q0_1 = clip(reg.predict(np.column_stack([np.ones(n), z])))
    Q0_0 = clip(reg.predict(np.column_stack([np.zeros(n), z])))
    clf = LogisticRegression(max_iter=1000, solver="lbfgs").fit(z[:, None], t.astype(int))
    e = np.clip(clf.predict_proba(z[:, None])[:, 1], floor, 1 - floor)
    H = t / e - (1 - t) / (1 - e)
    H1, H0 = 1 / e, -1 / (1 - e)
    logit = lambda p: np.log(p / (1 - p))
    fluc = sm.GLM(ys, H[:, None], family=sm.families.Binomial(),
                  offset=logit(Q0)).fit()
    eps = float(fluc.params[0])
    ex = lambda x: 1 / (1 + np.exp(-x))
    Q1 = ex(logit(Q0) + eps * H)
    Q1_1 = ex(logit(Q0_1) + eps * H1)
    Q1_0 = ex(logit(Q0_0) + eps * H0)
    psi_s = float(np.mean(Q1_1 - Q1_0))
    psi = span * psi_s
    ic = span * (H * (ys - Q1) + (Q1_1 - Q1_0) - psi_s)
    se = float(np.sqrt(np.sum(ic ** 2) / n ** 2))
    return psi, se, eps


def test_tmle_matches_hand_computed_targeting():
    rng = np.random.default_rng(7)
    z = rng.normal(0, 1, 800)
    a = rng.binomial(1, _expit(z)).astype(float)
    y = 2.0 * a + z + rng.normal(0, 1, 800)
    df = pd.DataFrame({"A": a, "Y": y, "Z": z})
    hp, hse, heps = _hand_tmle(df)
    est = estimate_tmle_ate(df, treatment="A", outcome="Y",
                            adjustment=("Z",), ci_bootstrap=0)
    assert est.point == pytest.approx(hp, abs=1e-9)
    assert est.std_error == pytest.approx(hse, abs=1e-9)
    assert est.epsilon == pytest.approx(heps, abs=1e-9)


def test_binary_outcome_stays_in_range():
    rng = np.random.default_rng(2)
    z = rng.normal(0, 1, 8000)
    a = rng.binomial(1, _expit(z)).astype(float)
    yb = rng.binomial(1, _expit(-0.5 + 1.0 * a + 0.8 * z)).astype(float)
    df = pd.DataFrame({"A": a, "Y": yb, "Z": z})
    est = estimate_tmle_ate(df, treatment="A", outcome="Y",
                            adjustment=("Z",), ci_bootstrap=0)
    assert -1.0 <= est.point <= 1.0
    assert est.form == "logistic"
    true_rd = float(np.mean(_expit(-0.5 + 1.0 + 0.8 * z) - _expit(-0.5 + 0.8 * z)))
    assert abs(est.point - true_rd) < 0.05


def test_influence_curve_ci_covers_near_nominal():
    hits = 0
    n_sims = 30
    for s in range(n_sims):
        df = _dgp(np.random.default_rng(200 + s), n=2000)
        est = estimate_tmle_ate(df, treatment="A", outcome="Y",
                                adjustment=("Z",), ci_bootstrap=1)
        if est.ci_lower <= TRUE_ATE <= est.ci_upper:
            hits += 1
    assert hits / n_sims >= 0.80


def test_positivity_trimming_is_disclosed():
    rng = np.random.default_rng(3)
    n = 4000
    z = rng.normal(0, 1, n)
    a = rng.binomial(1, _expit(4.0 * z)).astype(float)
    y = 2.0 * a + z + rng.normal(0, 1, n)
    df = pd.DataFrame({"A": a, "Y": y, "Z": z})
    est = estimate_tmle_ate(df, treatment="A", outcome="Y",
                            adjustment=("Z",), ci_bootstrap=0)
    assert est.propensity.n_trimmed > 0
    assert any("propensity_clipped" in a for a in est.assumptions)


def test_single_treatment_level_refused():
    df = pd.DataFrame({"A": np.ones(50), "Y": np.arange(50.0), "Z": np.arange(50.0)})
    with pytest.raises(EstimatorFailure) as exc:
        estimate_tmle_ate(df, treatment="A", outcome="Y", adjustment=("Z",))
    assert exc.value.failure_type == "overlap_insufficient"


def test_cluster_robust_if_variance_is_wider():
    """Cluster-level treatment + shared family outcome shock → positively
    correlated influence within clusters → cluster-robust IC variance
    exceeds the i.i.d. one."""
    rng = np.random.default_rng(5)
    G, per = 60, 25
    clu = np.repeat(np.arange(G), per)
    a_by = rng.integers(0, 2, G)
    a = a_by[clu].astype(float)
    u = rng.standard_normal(G) * 2.0
    y = 2.0 * a + u[clu] + rng.standard_normal(G * per) * 0.4
    df = pd.DataFrame({"A": a, "Y": y, "fam": clu})
    iid = estimate_tmle_ate(df, treatment="A", outcome="Y", ci_bootstrap=1)
    cl = estimate_tmle_ate(df, treatment="A", outcome="Y",
                           ci_bootstrap=1, cluster="fam")
    assert cl.std_error > iid.std_error
    assert cl.cluster == "fam"


# ============================================================ public path


def _confounded_program():
    A = {"predicate": "A", "args": [{"type": "const", "name": "u"}]}
    Y = {"predicate": "Y", "args": [{"type": "const", "name": "u"}]}
    Z = {"predicate": "Z", "args": [{"type": "const", "name": "u"}]}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "A"},
            {"kind": "variable", "predicate": "Y"},
            {"kind": "variable", "predicate": "Z"},
            {"kind": "cause", "from": Z, "to": A},
            {"kind": "cause", "from": Z, "to": Y},
            {"kind": "cause", "from": A, "to": Y},
            {"kind": "query", "id": "q1", "query": {
                "kind": "effect", "target": {"atom": Y, "value": True},
                "intervention": {"atom": A, "value": True}, "given": []}},
        ],
    }


def test_public_path_routes_validates_and_verifies():
    df = _dgp(np.random.default_rng(0), n=3000)
    prog = _confounded_program()
    r = kernel.estimate(prog, df, random_state=1, ate_estimator="tmle")["results"][0]
    ne = r["numeric_estimate"]
    assert ne["method"] == "tmle"
    assert "tmle_epsilon" in ne and "propensity_summary" in ne
    assert r["status"] == "numerically_solved"
    validate_result(r)
    kernel.verify(prog, r)


def test_options_ate_estimator_matches_kwarg():
    df = _dgp(np.random.default_rng(0), n=3000)
    prog = _confounded_program()
    via_opt = kernel.estimate(dict(prog, options={"ate_estimator": "tmle"}), df,
                              random_state=1)["results"][0]
    via_kwarg = kernel.estimate(prog, df, random_state=1,
                                ate_estimator="tmle")["results"][0]
    assert via_opt["numeric_estimate"]["point"] == via_kwarg["numeric_estimate"]["point"]


# ============================================================ verifier tamper tests


def _tmle_result():
    df = _dgp(np.random.default_rng(0), n=3000)
    prog = _confounded_program()
    r = kernel.estimate(prog, df, random_state=1, ate_estimator="tmle")["results"][0]
    return prog, r


def test_verifier_rejects_point_outside_ci():
    prog, r = _tmle_result()
    r["derivation"]["steps"][-1]["inputs"]["point"] = 99.0
    r["numeric_estimate"]["point"] = 99.0
    with pytest.raises((VerificationError, Exception)):
        kernel.verify(prog, r)


def test_verifier_rejects_non_finite_epsilon():
    prog, r = _tmle_result()
    r["derivation"]["steps"][-1]["inputs"]["tmle_epsilon"] = float("inf")
    with pytest.raises((VerificationError, Exception)):
        kernel.verify(prog, r)


def test_verifier_rejects_propensity_out_of_range():
    prog, r = _tmle_result()
    r["derivation"]["steps"][-1]["inputs"]["propensity_raw_max"] = 1.7
    with pytest.raises((VerificationError, Exception)):
        kernel.verify(prog, r)
