"""Doubly-robust ATE estimation — IPW + AIPW.

The estimation layer's existing backdoor estimator is the outcome-
regression (g-formula) corner: consistent only if the OUTCOME model is
right. This suite pins the two properties that justify adding IPW +
AIPW:

1. **Double robustness** — AIPW recovers the true ATE when EITHER the
   outcome model OR the propensity model is misspecified (but not both),
   while the corresponding single-robust estimator visibly fails. This
   is the whole reason the estimator exists; the DGPs below misspecify
   one nuisance at a time and check AIPW survives.
2. **Correct inference** — the analytic influence-function SE gives a
   Wald CI at ~nominal coverage; the hand-computed estimating equation
   matches the implementation bit-for-bit; the propensity clipping is
   disclosed; and the verifier rejects tampered estimates.

The textbook oracle is the known DGP true ATE = 2 (a homogeneous
additive treatment effect), independently recomputed — not a value the
estimator hands back.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis import kernel
from themis.estimation.aipw import estimate_aipw_ate, estimate_ipw_ate
from themis.estimation.backdoor import estimate_backdoor_ate
from themis.refusals import EstimatorFailure
from themis.input.syntactic_validator import validate_result
from themis.verifier.verify import VerificationError

TRUE_ATE = 2.0


def _expit(x):
    return 1.0 / (1.0 + np.exp(-x))


def _dgp(rng, n=20000, *, prop_nonlinear=False, outcome_nonlinear=False):
    """Single confounder Z. propensity and outcome each either linear-in-Z
    (correctly recoverable by the fitted logistic / linear model) or
    nonlinear (misspecified). True ATE = 2 always."""
    z = rng.normal(0, 1, n)
    lin = np.sin(z) * 2.0 if prop_nonlinear else 1.2 * z
    a = rng.binomial(1, _expit(lin)).astype(float)
    z_eff = 2.0 * np.exp(z) if outcome_nonlinear else 3.0 * z
    y = TRUE_ATE * a + z_eff + rng.normal(0, 1, n)
    return pd.DataFrame({"A": a, "Y": y, "Z": z})


# ============================================================ double robustness


def test_both_models_correct_all_estimators_recover():
    df = _dgp(np.random.default_rng(0))
    gf = estimate_backdoor_ate(df, treatment="A", outcome="Y",
                               adjustment=("Z",), model="linear", ci_bootstrap=0)
    ipw = estimate_ipw_ate(df, treatment="A", outcome="Y",
                           adjustment=("Z",), ci_bootstrap=0)
    aipw = estimate_aipw_ate(df, treatment="A", outcome="Y",
                             adjustment=("Z",), ci_bootstrap=0)
    for est in (gf, ipw, aipw):
        assert abs(est.point - TRUE_ATE) < 0.1


def test_aipw_survives_misspecified_outcome_model():
    """Outcome nonlinear in Z (exp), propensity linear (correct). The
    g-formula's linear outcome model is wrong AND Z confounds, so it is
    biased; AIPW is rescued by the correct propensity."""
    df = _dgp(np.random.default_rng(0), outcome_nonlinear=True)
    gf = estimate_backdoor_ate(df, treatment="A", outcome="Y",
                               adjustment=("Z",), model="linear", ci_bootstrap=0)
    aipw = estimate_aipw_ate(df, treatment="A", outcome="Y",
                             adjustment=("Z",), ci_bootstrap=0)
    assert abs(aipw.point - TRUE_ATE) < 0.1        # rescued
    assert abs(gf.point - TRUE_ATE) > 0.1          # single-robust failed
    # AIPW is decisively closer to truth than the biased g-formula.
    assert abs(aipw.point - TRUE_ATE) < abs(gf.point - TRUE_ATE) / 3


def test_aipw_survives_misspecified_propensity_model():
    """Propensity nonlinear in Z (sin), outcome linear (correct). IPW's
    logistic-on-Z propensity is wrong, so IPW is badly biased; AIPW is
    rescued by the correct outcome model."""
    df = _dgp(np.random.default_rng(0), prop_nonlinear=True)
    ipw = estimate_ipw_ate(df, treatment="A", outcome="Y",
                           adjustment=("Z",), ci_bootstrap=0)
    aipw = estimate_aipw_ate(df, treatment="A", outcome="Y",
                             adjustment=("Z",), ci_bootstrap=0)
    assert abs(aipw.point - TRUE_ATE) < 0.1        # rescued
    assert abs(ipw.point - TRUE_ATE) > 0.3         # single-robust failed badly
    assert abs(aipw.point - TRUE_ATE) < abs(ipw.point - TRUE_ATE) / 3


# ============================================================ estimating equation


def test_aipw_matches_hand_computed_estimating_equation():
    """The point estimate and the influence-function SE reproduce a
    hand-written numpy computation of the AIPW moment bit-for-bit."""
    from sklearn.linear_model import LinearRegression, LogisticRegression

    df = pd.DataFrame({
        "t": [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
        "z": [0.1, -0.4, 0.9, 0.3, -0.2, 1.1, 0.5, -0.7, 0.2, 0.8, -0.3, 0.6],
        "y": [3.1, 0.2, 4.0, 1.1, 1.5, 2.9, 2.8, -0.9, 2.2, 3.5, 0.4, 2.1],
    })
    t = df["t"].to_numpy(); z = df["z"].to_numpy(); y = df["y"].to_numpy()
    clf = LogisticRegression(max_iter=1000, solver="lbfgs").fit(z[:, None], t.astype(int))
    e = np.clip(clf.predict_proba(z[:, None])[:, 1], 0.01, 0.99)
    reg = LinearRegression().fit(np.column_stack([t, z]), y)
    mu1 = reg.predict(np.column_stack([np.ones(len(t)), z]))
    mu0 = reg.predict(np.column_stack([np.zeros(len(t)), z]))
    phi = mu1 - mu0 + t * (y - mu1) / e - (1 - t) * (y - mu0) / (1 - e)
    hand_point = float(np.mean(phi))
    hand_se = float(np.sqrt(np.sum((phi - hand_point) ** 2) / len(phi) ** 2))

    est = estimate_aipw_ate(df, treatment="t", outcome="y",
                            adjustment=("z",), ci_bootstrap=0)
    assert est.point == pytest.approx(hand_point, abs=1e-12)
    assert est.std_error == pytest.approx(hand_se, abs=1e-12)


def test_influence_function_ci_covers_near_nominal():
    """Across independent samples the analytic 95% Wald CI covers the
    true ATE at ~nominal rate (both nuisances correct)."""
    hits = 0
    n_sims = 30
    for s in range(n_sims):
        df = _dgp(np.random.default_rng(100 + s), n=2000)
        est = estimate_aipw_ate(df, treatment="A", outcome="Y",
                                adjustment=("Z",), ci_bootstrap=1)
        if est.ci_lower <= TRUE_ATE <= est.ci_upper:
            hits += 1
    coverage = hits / n_sims
    assert coverage >= 0.80, f"IF-CI coverage {coverage} far below nominal 0.95"


# ============================================================ IPW forms


def test_ipw_stabilized_and_ht_both_recover_under_correct_propensity():
    df = _dgp(np.random.default_rng(1))
    stab = estimate_ipw_ate(df, treatment="A", outcome="Y", adjustment=("Z",),
                            stabilized=True, ci_bootstrap=0)
    ht = estimate_ipw_ate(df, treatment="A", outcome="Y", adjustment=("Z",),
                          stabilized=False, ci_bootstrap=0)
    assert stab.method == "ipw_stabilized" and stab.stabilized is True
    assert ht.method == "ipw_ht" and ht.stabilized is False
    assert abs(stab.point - TRUE_ATE) < 0.15
    assert abs(ht.point - TRUE_ATE) < 0.15


# ============================================================ positivity disclosure


def test_positivity_trimming_is_disclosed():
    """Strong propensity (e = expit(4Z)) pushes some units near 0/1; the
    clip must be reported, not hidden."""
    rng = np.random.default_rng(3)
    n = 4000
    z = rng.normal(0, 1, n)
    a = rng.binomial(1, _expit(4.0 * z)).astype(float)
    y = 2.0 * a + z + rng.normal(0, 1, n)
    df = pd.DataFrame({"A": a, "Y": y, "Z": z})
    est = estimate_aipw_ate(df, treatment="A", outcome="Y",
                            adjustment=("Z",), ci_bootstrap=0)
    assert est.propensity.n_trimmed > 0
    # raw range escapes the clip band, i.e. the disclosure is honest.
    assert est.propensity.raw_min < est.propensity.floor \
        or est.propensity.raw_max > 1 - est.propensity.floor
    assert any("propensity_clipped" in a for a in est.assumptions)


def test_single_treatment_level_refused():
    df = pd.DataFrame({"A": np.ones(50), "Y": np.arange(50.0), "Z": np.arange(50.0)})
    with pytest.raises(EstimatorFailure) as exc:
        estimate_aipw_ate(df, treatment="A", outcome="Y", adjustment=("Z",))
    assert exc.value.failure_type == "overlap_insufficient"


# ============================================================ cluster-robust variance


def test_cluster_robust_if_variance_is_wider():
    """Cluster-LEVEL treatment + a shared family effect on Y: units in a
    cluster share both the treatment and the outcome shock, so their AIPW
    influence contributions are positively correlated and the
    cluster-robust variance exceeds the i.i.d. one (the analytic analogue
    of the cluster bootstrap widening the CI). i.i.d. inference would
    undercount the variance because the effective sample size is the
    number of clusters, not units."""
    rng = np.random.default_rng(5)
    G, per = 60, 25
    clu = np.repeat(np.arange(G), per)
    a_by_cluster = rng.integers(0, 2, G)
    a = a_by_cluster[clu].astype(float)         # whole cluster same arm
    u = rng.standard_normal(G) * 2.0            # shared family effect on Y
    y = 2.0 * a + u[clu] + rng.standard_normal(G * per) * 0.4
    df = pd.DataFrame({"A": a, "Y": y, "fam": clu})
    iid = estimate_aipw_ate(df, treatment="A", outcome="Y", ci_bootstrap=1)
    cl = estimate_aipw_ate(df, treatment="A", outcome="Y",
                           ci_bootstrap=1, cluster="fam")
    assert cl.std_error > iid.std_error
    assert cl.cluster == "fam"
    assert any("cluster_robust_influence_variance" in a for a in cl.assumptions)


# ============================================================ public estimate path


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


@pytest.mark.parametrize("estimator,method", [
    ("aipw", "aipw"),
    ("ipw", "ipw_stabilized"),
])
def test_public_path_routes_validates_and_verifies(estimator, method):
    df = _dgp(np.random.default_rng(0), n=3000)
    prog = _confounded_program()
    r = kernel.estimate(prog, df, random_state=1, ate_estimator=estimator)["results"][0]
    assert r["numeric_estimate"]["method"] == method
    assert r["status"] == "numerically_solved"
    assert "propensity_summary" in r["numeric_estimate"]
    validate_result(r)          # query_result.schema.json
    kernel.verify(prog, r)      # independent re-derivation accepts


def test_options_ate_estimator_matches_kwarg():
    df = _dgp(np.random.default_rng(0), n=3000)
    prog = _confounded_program()
    via_opt = kernel.estimate(dict(prog, options={"ate_estimator": "aipw"}), df,
                              random_state=1)["results"][0]
    via_kwarg = kernel.estimate(prog, df, random_state=1,
                                ate_estimator="aipw")["results"][0]
    assert via_opt["numeric_estimate"]["point"] == via_kwarg["numeric_estimate"]["point"]


def test_gformula_default_is_backward_compatible():
    """The default (gformula) must be byte-identical to not passing the
    option at all — no existing result moves."""
    df = _dgp(np.random.default_rng(0), n=3000)
    prog = _confounded_program()
    default = kernel.estimate(prog, df, random_state=1)["results"][0]
    explicit = kernel.estimate(prog, df, random_state=1,
                               ate_estimator="gformula")["results"][0]
    assert default["numeric_estimate"] == explicit["numeric_estimate"]
    assert default["numeric_estimate"]["method"] == "backdoor_linear"


def test_unknown_ate_estimator_raises():
    df = _dgp(np.random.default_rng(0), n=200)
    prog = _confounded_program()
    with pytest.raises(ValueError):
        kernel.estimate(prog, df, ate_estimator="bogus")


# ============================================================ verifier tamper tests


def _aipw_result():
    df = _dgp(np.random.default_rng(0), n=3000)
    prog = _confounded_program()
    r = kernel.estimate(prog, df, random_state=1, ate_estimator="aipw")["results"][0]
    return prog, r


def test_verifier_rejects_point_outside_ci():
    prog, r = _aipw_result()
    r["derivation"]["steps"][-1]["inputs"]["point"] = 99.0
    r["numeric_estimate"]["point"] = 99.0
    with pytest.raises((VerificationError, Exception)):
        kernel.verify(prog, r)


def test_verifier_rejects_propensity_out_of_range():
    prog, r = _aipw_result()
    r["derivation"]["steps"][-1]["inputs"]["propensity_raw_min"] = 1.5
    with pytest.raises((VerificationError, Exception)):
        kernel.verify(prog, r)


def test_verifier_rejects_wrong_method_name():
    prog, r = _aipw_result()
    r["derivation"]["steps"][-1]["inputs"]["method"] = "backdoor_linear"
    with pytest.raises((VerificationError, Exception)):
        kernel.verify(prog, r)


def test_verifier_rejects_trimmed_exceeding_sample():
    prog, r = _aipw_result()
    ss = r["derivation"]["steps"][-1]["inputs"]["sample_size"]
    r["derivation"]["steps"][-1]["inputs"]["propensity_n_trimmed"] = ss + 1
    with pytest.raises((VerificationError, Exception)):
        kernel.verify(prog, r)
