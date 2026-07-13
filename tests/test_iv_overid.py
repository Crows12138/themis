"""Phase 7.3+ — over-identified 2SLS + Sargan over-identification test.

D1 oracle: an INDEPENDENT full-matrix 2SLS (explicit projection onto the
instrument space [1, W, Z]) computed on the raw data, a different code path
from the estimator's residualised-moment formulas. The Sargan power check
(a genuinely invalid instrument → small p-value) is the falsification signal
that gives the moat its teeth: the data can refute the instruments.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.estimation.iv import (
    HansenJTest,
    OverIDIVEstimate,
    SarganTest,
    estimate_iv_overid,
    solve_hansen_from_s,
    solve_overid_from_moments,
)


# ------------------------------------------------------------- oracle


def _oracle_2sls_sargan(df, treatment, outcome, instruments, conditioning=()):
    """Independent full-matrix 2SLS + Sargan on raw data.

    β̂ = (X̂'X̂)⁻¹X̂'Y with X̂ = P_Zfull · Xfull, P_Zfull the projection onto
    the full instrument matrix [1, W, Z]; Sargan J = n·(û'P_Zfull û)/(û'û)
    with structural residual û = Y − Xfull·β̂, dof = q − 1.
    """
    from scipy.stats import chi2

    n = len(df)
    y = df[outcome].to_numpy(float)
    ones = np.ones((n, 1))
    w = df[list(conditioning)].to_numpy(float) if conditioning else np.empty((n, 0))
    z = df[list(instruments)].to_numpy(float)
    x = df[treatment].to_numpy(float).reshape(-1, 1)

    Zfull = np.hstack([ones, w, z])                 # instruments
    Xfull = np.hstack([ones, w, x])                 # regressors (X last)
    P = Zfull @ np.linalg.solve(Zfull.T @ Zfull, Zfull.T)
    Xhat = P @ Xfull
    beta_full = np.linalg.solve(Xhat.T @ Xhat, Xhat.T @ y)
    beta = float(beta_full[-1])                     # coef on X

    u = y - Xfull @ beta_full
    uu = float(u @ u)
    uPu = float(u @ (P @ u))
    q = len(instruments)
    J = n * uPu / uu
    p = float(chi2.sf(J, q - 1))
    return beta, J, q - 1, p


# ------------------------------------------------------------- DGP


def _valid_2iv(n=6000, seed=0, beta=1.5):
    """Two VALID instruments, single endogenous X with latent confounding."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    z1 = rng.standard_normal(n)
    z2 = rng.standard_normal(n)
    x = 0.9 * z1 + 0.7 * z2 + 0.8 * u + rng.standard_normal(n) * 0.3
    y = beta * x + 2.0 * u + rng.standard_normal(n) * 0.5
    return pd.DataFrame({"z1": z1, "z2": z2, "x": x, "y": y})


def _invalid_2iv(n=6000, seed=0, beta=1.5, leak=1.2):
    """z2 is INVALID: it has a direct effect on Y (exclusion violated)."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    z1 = rng.standard_normal(n)
    z2 = rng.standard_normal(n)
    x = 0.9 * z1 + 0.7 * z2 + 0.8 * u + rng.standard_normal(n) * 0.3
    y = beta * x + leak * z2 + 2.0 * u + rng.standard_normal(n) * 0.5
    return pd.DataFrame({"z1": z1, "z2": z2, "x": x, "y": y})


# ------------------------------------------------------------- tests


def test_point_matches_full_matrix_oracle():
    df = _valid_2iv()
    est = estimate_iv_overid(
        df, treatment="x", outcome="y", instruments=("z1", "z2"), ci_bootstrap=0,
    )
    b_oracle, j_oracle, dof_oracle, p_oracle = _oracle_2sls_sargan(
        df, "x", "y", ("z1", "z2"),
    )
    assert abs(est.point - b_oracle) < 1e-8
    assert est.sargan.dof == dof_oracle == 1
    assert abs(est.sargan.j_stat - j_oracle) < 1e-6
    assert abs(est.sargan.p_value - p_oracle) < 1e-9


def test_point_near_truth():
    df = _valid_2iv(beta=1.5)
    est = estimate_iv_overid(df, treatment="x", outcome="y",
                             instruments=("z1", "z2"), ci_bootstrap=0)
    assert abs(est.point - 1.5) < 0.1


def test_sargan_does_not_reject_valid_instruments():
    """Both instruments valid → over-identifying restrictions hold → large p."""
    df = _valid_2iv(seed=3)
    est = estimate_iv_overid(df, treatment="x", outcome="y",
                             instruments=("z1", "z2"), ci_bootstrap=0)
    assert est.sargan.p_value > 0.05


def test_sargan_rejects_invalid_instrument():
    """z2 leaks directly into Y → Sargan REFUTES joint validity (small p)."""
    df = _invalid_2iv(seed=3)
    est = estimate_iv_overid(df, treatment="x", outcome="y",
                             instruments=("z1", "z2"), ci_bootstrap=0)
    assert est.sargan.p_value < 1e-3
    b_o, j_o, _, p_o = _oracle_2sls_sargan(df, "x", "y", ("z1", "z2"))
    assert abs(est.sargan.j_stat - j_o) < 1e-6


def test_three_instruments_dof_is_two():
    rng = np.random.default_rng(1)
    n = 6000
    u = rng.standard_normal(n)
    z1, z2, z3 = (rng.standard_normal(n) for _ in range(3))
    x = 0.7 * z1 + 0.6 * z2 + 0.5 * z3 + 0.8 * u + rng.standard_normal(n) * 0.3
    y = 1.0 * x + 2.0 * u + rng.standard_normal(n) * 0.5
    df = pd.DataFrame({"z1": z1, "z2": z2, "z3": z3, "x": x, "y": y})
    est = estimate_iv_overid(df, treatment="x", outcome="y",
                             instruments=("z1", "z2", "z3"), ci_bootstrap=0)
    assert est.sargan.dof == 2
    assert est.n_instruments == 3


def test_joint_first_stage_f_is_large_when_strong():
    df = _valid_2iv()
    est = estimate_iv_overid(df, treatment="x", outcome="y",
                             instruments=("z1", "z2"), ci_bootstrap=0)
    assert est.first_stage_f_stat is not None
    assert est.first_stage_f_stat > 10.0


def test_bootstrap_ci_brackets_point():
    df = _valid_2iv(n=1500)
    est = estimate_iv_overid(df, treatment="x", outcome="y",
                             instruments=("z1", "z2"), ci_bootstrap=100,
                             random_state=1)
    assert est.ci_lower is not None
    assert est.ci_lower <= est.point <= est.ci_upper


def test_determinism():
    df = _valid_2iv(n=2000)
    a = estimate_iv_overid(df, treatment="x", outcome="y",
                           instruments=("z1", "z2"), ci_bootstrap=50, random_state=7)
    b = estimate_iv_overid(df, treatment="x", outcome="y",
                           instruments=("z1", "z2"), ci_bootstrap=50, random_state=7)
    assert a.point == b.point
    assert a.ci_lower == b.ci_lower


def test_requires_two_instruments():
    df = _valid_2iv(n=500)
    with pytest.raises(ValueError):
        estimate_iv_overid(df, treatment="x", outcome="y",
                           instruments=("z1",), ci_bootstrap=0)


def test_collinear_instruments_raise():
    df = _valid_2iv(n=1000)
    df = df.assign(z2=df["z1"])  # perfectly collinear instruments
    with pytest.raises(ValueError):
        estimate_iv_overid(df, treatment="x", outcome="y",
                           instruments=("z1", "z2"), ci_bootstrap=0)


def test_moments_round_trip_reproduces_point():
    """The recorded moments alone reproduce the point + J (verifier's basis)."""
    df = _valid_2iv()
    est = estimate_iv_overid(df, treatment="x", outcome="y",
                             instruments=("z1", "z2"), ci_bootstrap=0)
    solved = solve_overid_from_moments(est.moments)
    assert abs(solved["beta"] - est.point) < 1e-12
    assert abs(solved["j_stat"] - est.sargan.j_stat) < 1e-9


def test_conditional_overid_matches_oracle():
    """With an included exogenous control W the residualised moments still
    reproduce the full-matrix oracle."""
    rng = np.random.default_rng(2)
    n = 6000
    w = rng.standard_normal(n)
    u = rng.standard_normal(n)
    z1 = 0.5 * w + rng.standard_normal(n)
    z2 = rng.standard_normal(n)
    x = 0.8 * z1 + 0.7 * z2 + 0.5 * w + 0.8 * u + rng.standard_normal(n) * 0.3
    y = 1.2 * x + 0.6 * w + 2.0 * u + rng.standard_normal(n) * 0.5
    df = pd.DataFrame({"z1": z1, "z2": z2, "w": w, "x": x, "y": y})
    est = estimate_iv_overid(df, treatment="x", outcome="y",
                             instruments=("z1", "z2"), conditioning=("w",),
                             ci_bootstrap=0)
    b_o, j_o, _, p_o = _oracle_2sls_sargan(df, "x", "y", ("z1", "z2"), ("w",))
    assert abs(est.point - b_o) < 1e-8
    assert abs(est.sargan.j_stat - j_o) < 1e-6


# ======================================================= dispatch + verifier e2e

import copy

import themis
from themis.verifier.errors import VerificationError
from themis.verifier import verify_iv_overid_numeric


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _overid_ast(instruments=("z1", "z2")):
    stmts = [{"kind": "variable", "predicate": p, "domain": [True, False]}
             for p in (*instruments, "x", "y")]
    for z in instruments:
        stmts.append({"kind": "cause", "from": _atom(z), "to": _atom("x")})
    stmts.append({"kind": "cause", "from": _atom("x"), "to": _atom("y")})
    stmts.append({"kind": "bidirected", "left": _atom("x"), "right": _atom("y")})
    stmts.append({"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": {"atom": _atom("y"), "value": True},
        "given": []}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": stmts}


def _single_iv_ast():
    return _overid_ast(instruments=("z1",))


def test_dispatch_fires_overid_with_two_instruments():
    df = _valid_2iv()
    out = themis.estimate(_overid_ast(), df, ci_bootstrap=0)
    ne = out["results"][0]["numeric_estimate"]
    assert ne["method"] == "iv_2sls_overid"
    assert ne["instruments"] == ["z1", "z2"]
    assert ne["n_instruments"] == 2
    assert ne["over_identification"]["test"] == "sargan"
    assert ne["over_identification"]["sargan_dof"] == 1
    assert abs(ne["point"] - 1.5) < 0.1


def test_dispatch_overid_verify_round_trips():
    df = _valid_2iv(n=2000)
    ast = _overid_ast()
    out = themis.estimate(ast, df, ci_bootstrap=0)
    assert themis.verify(ast, out["results"][0]) is None


def test_dispatch_single_instrument_unchanged():
    """One instrument → the just-identified path (no over_identification)."""
    rng = np.random.default_rng(0)
    n = 3000
    u = rng.standard_normal(n)
    z1 = rng.standard_normal(n)
    x = 0.9 * z1 + 0.8 * u + rng.standard_normal(n) * 0.3
    y = 1.5 * x + 2.0 * u + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"z1": z1, "x": x, "y": y})
    ne = themis.estimate(_single_iv_ast(), df, ci_bootstrap=0)["results"][0]["numeric_estimate"]
    assert ne["method"] == "iv_2sls"
    assert "over_identification" not in ne
    assert ne["instrument"] == "z1"


def test_dispatch_three_instruments():
    rng = np.random.default_rng(1)
    n = 6000
    u = rng.standard_normal(n)
    z1, z2, z3 = (rng.standard_normal(n) for _ in range(3))
    x = 0.7 * z1 + 0.6 * z2 + 0.5 * z3 + 0.8 * u + rng.standard_normal(n) * 0.3
    y = 1.0 * x + 2.0 * u + rng.standard_normal(n) * 0.5
    df = pd.DataFrame({"z1": z1, "z2": z2, "z3": z3, "x": x, "y": y})
    ast = _overid_ast(instruments=("z1", "z2", "z3"))
    out = themis.estimate(ast, df, ci_bootstrap=0)
    ne = out["results"][0]["numeric_estimate"]
    assert ne["n_instruments"] == 3
    assert ne["over_identification"]["sargan_dof"] == 2
    assert themis.verify(ast, out["results"][0]) is None


def test_sargan_rejection_surfaces_gap():
    """Graph asserts z1, z2 are valid IVs but z2 leaks into Y in the data →
    the Sargan test rejects and a must-disclose gap is attached."""
    df = _invalid_2iv(seed=3)
    out = themis.estimate(_overid_ast(), df, ci_bootstrap=0)
    res = out["results"][0]
    ne = res["numeric_estimate"]
    assert ne["over_identification"]["sargan_p_value"] < 0.05
    assert ne["over_identification"]["rejected_at_0_05"] is True
    kinds = [g["kind"] for g in (res.get("data_gap_report") or {}).get("gaps", [])]
    assert "overidentification_rejected" in kinds
    # still verifies (the number is honestly reported with the caveat)
    assert themis.verify(_overid_ast(), res) is None


# --- verify_iv_overid_numeric: strong re-derivation from moments ------------


@pytest.fixture(scope="module")
def overid_result():
    return themis.estimate(_overid_ast(), _valid_2iv(n=2500), ci_bootstrap=0)["results"][0]


def test_verifier_accepts_genuine(overid_result):
    verify_iv_overid_numeric(overid_result["numeric_estimate"])  # no raise


def test_verifier_rejects_forged_point(overid_result):
    ne = copy.deepcopy(overid_result["numeric_estimate"])
    ne["point"] = 9.9
    with pytest.raises(VerificationError):
        verify_iv_overid_numeric(ne)


def test_verifier_rejects_forged_sargan_j(overid_result):
    ne = copy.deepcopy(overid_result["numeric_estimate"])
    ne["over_identification"]["sargan_j"] = 0.0001
    with pytest.raises(VerificationError):
        verify_iv_overid_numeric(ne)


def test_verifier_rejects_forged_sargan_p(overid_result):
    ne = copy.deepcopy(overid_result["numeric_estimate"])
    ne["over_identification"]["sargan_p_value"] = 0.999
    with pytest.raises(VerificationError):
        verify_iv_overid_numeric(ne)


def test_verifier_rejects_corrupted_moment(overid_result):
    ne = copy.deepcopy(overid_result["numeric_estimate"])
    ne["over_identification"]["sufficient_statistics"]["zy"][0] *= 1.4
    with pytest.raises(VerificationError):
        verify_iv_overid_numeric(ne)


def test_verifier_rejects_wrong_dof(overid_result):
    ne = copy.deepcopy(overid_result["numeric_estimate"])
    ne["over_identification"]["sargan_dof"] = 5
    with pytest.raises(VerificationError):
        verify_iv_overid_numeric(ne)


def test_verifier_noop_on_non_overid():
    verify_iv_overid_numeric({"method": "iv_2sls", "point": 1.5})  # no raise
    verify_iv_overid_numeric({"method": "backdoor_linear", "point": 0.3})


def test_verifier_rejects_missing_sufficient_statistics():
    ne = {"method": "iv_2sls_overid", "point": 1.5,
          "over_identification": {"test": "sargan", "sargan_j": 1.0,
                                  "sargan_dof": 1, "sargan_p_value": 0.3}}
    with pytest.raises(VerificationError):
        verify_iv_overid_numeric(ne)


def test_public_api_exposed():
    assert hasattr(themis, "estimate")
    from themis.verifier import verify_iv_overid_numeric as _v
    assert callable(_v)


# ============================================ Hansen (1982) robust J
#
# D1 oracle: an INDEPENDENT efficient two-step GMM — β̂₁ from the full-matrix
# 2SLS, Ŝ = (1/n)Σ û₁² z̃ z̃' from explicitly residualised instruments, then
# β̂₂ = (Z'x)'Ŝ⁻¹(Z'y)/(Z'x)'Ŝ⁻¹(Z'x) and J = n·ḡ'Ŝ⁻¹ḡ — a different code path
# from the estimator's solve_hansen_from_s. Hansen J is the heteroskedasticity-
# robust generalisation of Sargan: it must COINCIDE with Sargan under a
# homoskedastic error and DIFFER materially under a heteroskedastic one.


def _oracle_hansen_j(df, treatment, outcome, instruments, conditioning=()):
    from scipy.stats import chi2

    n = len(df)
    ones = np.ones((n, 1))
    w = df[list(conditioning)].to_numpy(float) if conditioning else np.empty((n, 0))
    design = np.hstack([ones, w])

    def resid(col):
        v = df[col].to_numpy(float)
        coef, *_ = np.linalg.lstsq(design, v, rcond=None)
        return v - design @ coef

    yr = resid(outcome)
    xr = resid(treatment)
    zr = np.column_stack([resid(z) for z in instruments])
    zz = zr.T @ zr
    zx = zr.T @ xr
    zy = zr.T @ yr
    zzi = np.linalg.inv(zz)
    b1 = (zx @ zzi @ zy) / (zx @ zzi @ zx)          # 2SLS (step 1)
    u = yr - b1 * xr
    S = (zr * (u ** 2)[:, None]).T @ zr / n          # robust weight Ŝ
    Si = np.linalg.inv(S)
    b2 = (zx @ Si @ zy) / (zx @ Si @ zx)             # efficient GMM point
    g = (zy - b2 * zx) / n
    J = n * (g @ Si @ g)
    q = len(instruments)
    return b2, J, q - 1, float(chi2.sf(J, q - 1))


def _hetero_3iv(n=4000, seed=7, beta=1.5):
    """Three VALID instruments, but the structural error is heteroskedastic
    (variance rises with |z1|) — Sargan's homoskedastic weight is wrong here."""
    rng = np.random.default_rng(seed)
    z1 = rng.standard_normal(n)
    z2 = rng.standard_normal(n)
    z3 = rng.standard_normal(n)
    u = rng.standard_normal(n)
    x = 0.8 * z1 + 0.6 * z2 + 0.5 * z3 + 1.2 * u + rng.standard_normal(n)
    eps = rng.standard_normal(n) * (1.0 + 3.0 * np.abs(z1))
    y = beta * x + 1.0 * u + eps
    return pd.DataFrame({"z1": z1, "z2": z2, "z3": z3, "x": x, "y": y})


def test_hansen_present_and_matches_oracle():
    df = _hetero_3iv()
    est = estimate_iv_overid(df, treatment="x", outcome="y",
                             instruments=("z1", "z2", "z3"), ci_bootstrap=0)
    assert est.hansen is not None
    b2_o, j_o, dof_o, p_o = _oracle_hansen_j(df, "x", "y", ("z1", "z2", "z3"))
    assert est.hansen.dof == dof_o == 2
    assert abs(est.hansen.gmm_point - b2_o) < 1e-8
    assert abs(est.hansen.j_stat - j_o) < 1e-7
    assert abs(est.hansen.p_value - p_o) < 1e-9
    # headline point stays 2SLS, distinct from the efficient-GMM point here
    assert abs(est.point - est.hansen.gmm_point) > 1e-4


def test_hansen_coincides_with_sargan_under_homoskedasticity():
    """Homoskedastic error → Hansen J and Sargan J agree asymptotically."""
    df = _valid_2iv(n=20000, seed=11)
    est = estimate_iv_overid(df, treatment="x", outcome="y",
                             instruments=("z1", "z2"), ci_bootstrap=0)
    assert est.hansen is not None
    # both are χ²(1) draws from the same null; at n=20000 they track closely
    assert abs(est.hansen.j_stat - est.sargan.j_stat) < 0.15
    assert abs(est.hansen.gmm_point - est.point) < 1e-2


def test_hansen_differs_from_sargan_under_heteroskedasticity():
    """Heteroskedastic error → the robust weight matters; J's diverge."""
    df = _hetero_3iv(n=8000, seed=3)
    est = estimate_iv_overid(df, treatment="x", outcome="y",
                             instruments=("z1", "z2", "z3"), ci_bootstrap=0)
    assert est.hansen is not None
    rel = abs(est.hansen.j_stat - est.sargan.j_stat) / (1 + abs(est.sargan.j_stat))
    assert rel > 0.02  # materially different, not a cosmetic duplicate


def test_hansen_solve_round_trips_from_recorded_s():
    """solve_hansen_from_s on the recorded moments reproduces the estimate."""
    df = _hetero_3iv()
    est = estimate_iv_overid(df, treatment="x", outcome="y",
                             instruments=("z1", "z2", "z3"), ci_bootstrap=0)
    solved = solve_hansen_from_s(est.moments)
    assert abs(solved["j_stat"] - est.hansen.j_stat) < 1e-9
    assert abs(solved["gmm_point"] - est.hansen.gmm_point) < 1e-9
    assert solved["dof"] == est.hansen.dof


def test_hansen_cluster_robust_weight_differs_and_is_consistent():
    """A declared cluster → the robust weight is the cluster-robust (CR0) sum,
    which differs from the HC0 weight and stays internally consistent."""
    df = _hetero_3iv(n=6000, seed=5)
    rng = np.random.default_rng(0)
    df = df.assign(cl=rng.integers(0, 40, size=len(df)))
    est_hc0 = estimate_iv_overid(df, treatment="x", outcome="y",
                                 instruments=("z1", "z2", "z3"), ci_bootstrap=0)
    est_cr0 = estimate_iv_overid(df, treatment="x", outcome="y",
                                 instruments=("z1", "z2", "z3"), ci_bootstrap=0,
                                 cluster="cl")
    assert est_cr0.hansen is not None
    s_hc0 = np.asarray(est_hc0.moments["s_robust"])
    s_cr0 = np.asarray(est_cr0.moments["s_robust"])
    assert not np.allclose(s_hc0, s_cr0)                      # genuinely CR0
    solved = solve_hansen_from_s(est_cr0.moments)             # self-consistent
    assert abs(solved["j_stat"] - est_cr0.hansen.j_stat) < 1e-9


# --- dispatch + verifier round-trip for the Hansen block --------------------


def test_dispatch_overid_carries_hansen_block():
    df = _valid_2iv(n=3000)
    ne = themis.estimate(_overid_ast(), df, ci_bootstrap=0)["results"][0]["numeric_estimate"]
    oid = ne["over_identification"]
    assert "hansen_j" in oid and "hansen_gmm_point" in oid
    assert oid["hansen_dof"] == 1
    assert "s_robust" in oid["sufficient_statistics"]


@pytest.fixture(scope="module")
def hetero_overid_ne():
    df = _hetero_3iv(n=5000, seed=9)
    ast = _overid_ast(instruments=("z1", "z2", "z3"))
    out = themis.estimate(ast, df, ci_bootstrap=0)
    return out["results"][0]["numeric_estimate"]


def test_hansen_verifier_accepts_genuine(hetero_overid_ne):
    verify_iv_overid_numeric(hetero_overid_ne)  # no raise


def test_hansen_verifier_rejects_forged_hansen_j(hetero_overid_ne):
    ne = copy.deepcopy(hetero_overid_ne)
    ne["over_identification"]["hansen_j"] = 42.0
    with pytest.raises(VerificationError):
        verify_iv_overid_numeric(ne)


def test_hansen_verifier_rejects_forged_gmm_point(hetero_overid_ne):
    ne = copy.deepcopy(hetero_overid_ne)
    ne["over_identification"]["hansen_gmm_point"] = 9.9
    with pytest.raises(VerificationError):
        verify_iv_overid_numeric(ne)


def test_hansen_verifier_rejects_wrong_hansen_dof(hetero_overid_ne):
    ne = copy.deepcopy(hetero_overid_ne)
    ne["over_identification"]["hansen_dof"] = 5
    with pytest.raises(VerificationError):
        verify_iv_overid_numeric(ne)


def test_hansen_verifier_rejects_non_psd_weight(hetero_overid_ne):
    ne = copy.deepcopy(hetero_overid_ne)
    q = ne["over_identification"]["sufficient_statistics"]["q"]
    ne["over_identification"]["sufficient_statistics"]["s_robust"] = [
        [-1.0 if i == j else 0.0 for j in range(q)] for i in range(q)
    ]
    with pytest.raises(VerificationError):
        verify_iv_overid_numeric(ne)


def test_hansen_verifier_rejects_asymmetric_weight(hetero_overid_ne):
    ne = copy.deepcopy(hetero_overid_ne)
    S = np.asarray(ne["over_identification"]["sufficient_statistics"]["s_robust"])
    S[0, 1] += 5.0
    ne["over_identification"]["sufficient_statistics"]["s_robust"] = S.tolist()
    with pytest.raises(VerificationError):
        verify_iv_overid_numeric(ne)


def test_hansen_verifier_rejects_missing_s_robust(hetero_overid_ne):
    ne = copy.deepcopy(hetero_overid_ne)
    ne["over_identification"]["sufficient_statistics"].pop("s_robust")
    with pytest.raises(VerificationError):
        verify_iv_overid_numeric(ne)


def test_hansen_verifier_rejects_inconsistent_rejected_flag(hetero_overid_ne):
    ne = copy.deepcopy(hetero_overid_ne)
    # genuine p is large here (valid instruments); claim rejection
    ne["over_identification"]["hansen_rejected_at_0_05"] = True
    with pytest.raises(VerificationError):
        verify_iv_overid_numeric(ne)


def test_hansen_verifier_backward_compatible_without_hansen(overid_result):
    """A block with no hansen_j (e.g. an older result) still verifies via the
    Sargan path alone."""
    ne = copy.deepcopy(overid_result["numeric_estimate"])
    oid = ne["over_identification"]
    for k in ("hansen_j", "hansen_dof", "hansen_p_value",
              "hansen_gmm_point", "hansen_rejected_at_0_05"):
        oid.pop(k, None)
    oid["sufficient_statistics"].pop("s_robust", None)
    verify_iv_overid_numeric(ne)  # no raise
