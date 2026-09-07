"""Four-way decomposition (VanderWeele 2014, *Explanation in Causal
Inference* Ch. 14): TE = CDE + INTref + INTmed + PIE.

Three layers, mirroring the PN/PS suite:
- the pure core (`four_way_decomposition`) against hand computation, the
  regression-coefficient form (14.4), the additive-identity, and the
  no-interaction reduction;
- the data estimator (`estimate_mediation.four_way`) recovering a known
  DGP and reconciling EXACTLY with the independently-computed NDE/NIE
  (the bridge PNDE=CDE+INTref, TNIE=INTmed+PIE);
- the end-to-end `themis.estimate` surface + schema validation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from themis import kernel
from themis.estimation.four_way import four_way_decomposition as fw
from themis.estimation.mediation import estimate_mediation
from themis.input.syntactic_validator import validate_result


# ============================================ pure core


def test_core_matches_hand_computation():
    # Linear DGP: E[Y|a,m]=1+0.5a+0.3m+0.4am ; E[M|a]=0.2+0.6a.
    r = fw(p00=1.0, p01=1.3, p10=1.5, p11=2.2, q0=0.2, q1=0.8)
    assert abs(r.cde - 0.5) < 1e-12        # theta1
    assert abs(r.intref - 0.08) < 1e-12    # theta3 * q0
    assert abs(r.intmed - 0.24) < 1e-12    # theta3 * beta1
    assert abs(r.pie - 0.18) < 1e-12       # theta2 * beta1
    assert abs(r.te - 1.0) < 1e-12
    assert abs(r.additive_interaction - 0.4) < 1e-12   # theta3


def test_core_reproduces_regression_form_14_4():
    """For a linear outcome, evaluating p_am at m∈{0,1} and q_a at a∈{0,1}
    must reproduce VanderWeele's regression form (14.4): CDE=θ1,
    INTref=θ3·E[M|A=0], INTmed=θ3·β1, PIE=θ2·β1 — for arbitrary coefs."""
    theta0, theta1, theta2, theta3 = -0.7, 1.3, 0.9, -0.5
    beta0, beta1 = 0.4, 0.35

    def p(a, m):
        return theta0 + theta1 * a + theta2 * m + theta3 * a * m

    q0, q1 = beta0, beta0 + beta1
    r = fw(p00=p(0, 0), p01=p(0, 1), p10=p(1, 0), p11=p(1, 1), q0=q0, q1=q1)
    assert abs(r.cde - theta1) < 1e-12
    assert abs(r.intref - theta3 * q0) < 1e-12
    assert abs(r.intmed - theta3 * beta1) < 1e-12
    assert abs(r.pie - theta2 * beta1) < 1e-12


def test_core_additive_identity_and_bridges():
    r = fw(p00=0.1, p01=0.4, p10=0.3, p11=0.9, q0=0.25, q1=0.6)
    assert abs(r.cde + r.intref + r.intmed + r.pie - r.te) < 1e-12
    assert abs(r.pnde - (r.cde + r.intref)) < 1e-12
    assert abs(r.tnie - (r.intmed + r.pie)) < 1e-12
    assert abs(r.pnde + r.tnie - r.te) < 1e-12


def test_core_no_interaction_reduces_to_pure_mediation():
    """When the additive interaction is 0, INTref=INTmed=0 and the total
    effect is exactly CDE + PIE (the classic two-way split)."""
    # Choose p so that p11 - p10 - p01 + p00 = 0.
    r = fw(p00=0.1, p01=0.5, p10=0.3, p11=0.7, q0=0.3, q1=0.8)
    assert abs(r.additive_interaction) < 1e-12
    assert abs(r.intref) < 1e-12 and abs(r.intmed) < 1e-12
    assert abs(r.te - (r.cde + r.pie)) < 1e-12


# ============================================ data estimator


def _binary_mediator_dgp(n=40000, seed=0):
    """A→M→Y with a strong exposure-mediator interaction. Binary M with
    P(M=1|A=1)=0.7, P(M=1|A=0)=0.3 (β1=0.4); Y=0.5A+1.0M+2.0AM+noise.
    True components: CDE=0.5, INTref=2.0·0.3=0.6, INTmed=2.0·0.4=0.8,
    PIE=1.0·0.4=0.4, TE=2.3."""
    rng = np.random.default_rng(seed)
    A = rng.integers(0, 2, n).astype(float)
    M = (rng.random(n) < np.where(A == 1, 0.7, 0.3)).astype(float)
    Y = 0.5 * A + 1.0 * M + 2.0 * A * M + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"A": A, "M": M, "Y": Y})


def test_estimator_recovers_known_components():
    df = _binary_mediator_dgp()
    est = estimate_mediation(
        df, treatment="A", outcome="Y", mediator="M",
        ci_bootstrap=60, random_state=1,
    )
    fw4 = est.four_way
    assert fw4 is not None
    assert abs(fw4.cde.point - 0.5) < 0.08
    assert abs(fw4.intref.point - 0.6) < 0.08
    assert abs(fw4.intmed.point - 0.8) < 0.08
    assert abs(fw4.pie.point - 0.4) < 0.08
    assert abs(fw4.te.point - 2.3) < 0.08
    assert abs(fw4.additive_interaction_point - 2.0) < 0.08


def test_continuous_mediator_logit_outcome_is_gated_not_wrong():
    """Regression (stress-test find): a continuous mediator under a logit
    outcome makes the m∈{0,1} plug-in extrapolate off the mediator's
    support — four_way.te would NOT equal the total effect. The estimator
    must skip it (four_way None + a reason) rather than emit wrong numbers."""
    rng = np.random.default_rng(21)
    n = 30000
    A = rng.integers(0, 2, n).astype(float)
    M = 2.0 + 3.0 * A + rng.standard_normal(n)         # continuous, off [0,1]
    lin = -3.0 + 0.5 * A + 0.6 * M + 0.3 * A * M
    Y = (rng.random(n) < 1 / (1 + np.exp(-lin))).astype(bool)
    est = estimate_mediation(pd.DataFrame({"A": A, "M": M, "Y": Y}),
                             treatment="A", outcome="Y", mediator="M",
                             ci_bootstrap=10, random_state=1)
    assert est.four_way is None
    assert est.four_way_unavailable_reason is not None


def test_continuous_mediator_linear_outcome_is_valid():
    """The same continuous mediator under a LINEAR outcome IS valid — the
    m=0/1 slope is the exact per-unit effect, so te matches te_point."""
    rng = np.random.default_rng(5)
    n = 30000
    A = rng.integers(0, 2, n).astype(float)
    M = 2.0 + 3.0 * A + rng.standard_normal(n)
    Y = 0.5 * A + 0.6 * M + 0.3 * A * M + rng.standard_normal(n) * 0.5
    est = estimate_mediation(pd.DataFrame({"A": A, "M": M, "Y": Y}),
                             treatment="A", outcome="Y", mediator="M",
                             ci_bootstrap=10, random_state=1)
    assert est.four_way is not None
    assert abs(est.four_way.te.point - est.te_point) < 1e-6


def test_estimator_bridge_to_nde_nie_is_exact():
    """The four-way components must aggregate back to the independently
    computed NDE/NIE: PNDE=CDE+INTref == nde_point, TNIE=INTmed+PIE ==
    nie_point (same fitted models)."""
    df = _binary_mediator_dgp(n=20000)
    est = estimate_mediation(
        df, treatment="A", outcome="Y", mediator="M",
        ci_bootstrap=40, random_state=2,
    )
    fw4 = est.four_way
    assert abs((fw4.cde.point + fw4.intref.point) - est.nde_point) < 1e-6
    assert abs((fw4.intmed.point + fw4.pie.point) - est.nie_point) < 1e-6
    assert abs(fw4.te.point - est.te_point) < 1e-6


def test_estimator_cis_present_and_ordered():
    df = _binary_mediator_dgp(n=8000)
    est = estimate_mediation(
        df, treatment="A", outcome="Y", mediator="M",
        ci_bootstrap=40, random_state=3,
    )
    for c in (est.four_way.cde, est.four_way.intref, est.four_way.intmed,
              est.four_way.pie, est.four_way.te,
              est.four_way.prop_mediated, est.four_way.prop_interaction):
        assert c.ci_lower <= c.point <= c.ci_upper


# ============================================ end-to-end via themis.estimate


def test_themis_estimate_surfaces_four_way_and_schema_validates():
    A = {"predicate": "A", "args": [{"type": "const", "name": "u"}]}
    M = {"predicate": "M", "args": [{"type": "const", "name": "u"}]}
    Y = {"predicate": "Y", "args": [{"type": "const", "name": "u"}]}
    prog = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "A"},
            {"kind": "variable", "predicate": "M"},
            {"kind": "variable", "predicate": "Y"},
            {"kind": "cause", "from": A, "to": M},
            {"kind": "cause", "from": M, "to": Y},
            {"kind": "cause", "from": A, "to": Y},
            {"kind": "query", "id": "q1", "query": {
                "kind": "effect",
                "target": {"atom": Y, "value": True},
                "intervention": {"atom": A, "value": True},
                "given": [], "mediator": M}},
        ],
    }
    df = _binary_mediator_dgp(n=12000)
    out = kernel.estimate(prog, df, random_state=1)
    r = out["results"][0]
    validate_result(r)   # the four_way_decomposition block must schema-validate
    fw4 = r["numeric_estimate"]["four_way_decomposition"]
    for key in ("cde", "intref", "intmed", "pie", "te",
                "prop_mediated", "prop_interaction"):
        assert {"point", "ci_lower", "ci_upper"} <= set(fw4[key])
    # bridge against the nde/nie in the same result
    d = r["numeric_estimate"]["decomposition"]
    assert abs((fw4["cde"]["point"] + fw4["intref"]["point"]) - d["nde"]["point"]) < 1e-6
    assert abs((fw4["intmed"]["point"] + fw4["pie"]["point"]) - d["nie"]["point"]) < 1e-6
