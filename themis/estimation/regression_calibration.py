"""Regression calibration — continuous mismeasurement de-attenuation numeric end.

The confusion-matrix module (``measurement.py``) corrects a *discrete*
misclassified variable by inverting a known column-stochastic matrix. This
module is its **continuous** counterpart: one or more continuous design
variables measured with **classical additive error** — we observe ``W = V + U``
instead of the true ``V``, with ``U`` mean-zero, independent of the other design
variables and of the outcome given the truth, and a *known* error variance
``σ²_u`` (from a validation substudy, replicate measurements, or the literature —
the exact analogue of a known confusion matrix). The mismeasured variable may be
the **exposure** (regression dilution → attenuation toward zero) OR a **back-door
covariate / confounder** (imperfect adjustment → *residual confounding*, a bias
in EITHER direction), or several at once.

Model (Carroll, Ruppert, Stefanski & Crainiceanu 2006 *Measurement Error in
Nonlinear Models* §3; Rosner, Willett & Spiegelman 1989; Fuller 1987). Linear
structural outcome model, back-door adjustment set Z, design D = (X*, Z):

    Y = β0 + βx · X* + βz'·Z + ε ,   E[ε | X*, Z] = 0
    W_v = V + U_v  for each mismeasured design column V ∈ D ,
                                     U_v ⟂ (other design cols, ε),  Var(U_v) = σ²_uv  (known)

The naive OLS of Y on the *observed* design is biased: classical error inflates
only the mismeasured columns' variances, so the whole design covariance is

    Σ_obs = Σ_true + E ,   E = diag(σ²_u placed on each mismeasured column, 0 elsewhere)

while Cov(D_obs, Y) = Cov(D_true, Y) is unchanged (each U_v ⟂ Y). Hence the true
structural coefficients are an EXACT moment correction of the naive ones — the
continuous analogue of the confusion-matrix inversion M⁻¹, with E a *diagonal of
the error variances at the mismeasured columns* instead of a single exposure
entry:

    b_naive = Σ_obs⁻¹ Cov(D_obs, Y)                       (biased)
    β_true  = Σ_true⁻¹ Cov(D_obs, Y)
            = (Σ_obs − E)⁻¹ Σ_obs b_naive                 (corrected)

The corrected causal effect is ``βx = β_true[exposure]`` — the effect on Y per
unit of the *true* exposure X*, adjusting for the *true* Z. When only the
exposure is mismeasured this reduces to the classic reliability-ratio correction
``βx_true = b_naive / λ`` with the covariate-adjusted reliability ratio

    λ = Var(X*|Z) / Var(W|Z) = 1 − σ²_u / Var(W|Z)        (continuous "det(M)")

where ``Var(W|Z)`` is the residual variance of W after regressing on Z. λ plays
exactly the role det(M) = Se+Sp−1 plays for a binary outcome: the factor the
naive estimate is divided by. When a *confounder* is the mismeasured column there
is no such scalar shortcut for the exposure slope — the matrix inversion is
essential (adjusting for a noisy proxy of Z leaves residual confounding that the
full (Σ_obs − E)⁻¹ removes). Each mismeasured column carries its own reliability
λ_v = 1 − σ²_uv / Var(V | rest). For the linear model this is regression
calibration (replace each mismeasured V by Ê[V|observed] and refit) and the
moment correction coincide, so the recovery is exact (no normality needed).

Guards (honest, not silent):

- **Degenerate reliability.** σ²_uv ≥ Var(V|rest) for some mismeasured V ⇒ λ_v ≤ 0,
  or more generally Σ_obs − E not positive definite: the claimed error variance
  meets or exceeds the observed conditional variance, so the measurement carries
  no usable signal ⇒ refuse (``EstimatorFailure``), mirroring the singular-matrix
  guard in ``measurement``.
- **Non-positive error variance.** σ²_uv ≤ 0 is not a variance ⇒ refuse.
- **Non-continuous mismeasured variable.** A near-discrete column (≤
  ``_MIN_CONTINUOUS_DISTINCT`` distinct values) is a misclassification object, not
  classical additive error ⇒ refuse, pointing at the confusion-matrix method.
- **Mismeasured variable not in the design.** An error variance keyed by a
  variable that is neither the exposure nor an adjustment covariate ⇒ refuse.
- **Singular design.** A collinear covariate set (Σ_obs not invertible) ⇒ refuse.

Scope (declared tradeoffs):

- **Continuous** mismeasured variables, **classical additive** error (``W = V + U``,
  ``U ⟂``) — the exposure and/or one or more back-door covariates. A mismeasured
  *outcome* is deferred. A DIFFERENTIAL error — one carrying a component that
  tracks the outcome — is not: it inflates the observed covariance as well as
  the exposure's variance, so this correction moves one of the two things that
  moved and lands somewhere else rather than merely short. A caller who knows
  the coefficient declares it (``differential_coefficient=δ`` on the same spec)
  and :mod:`themis.estimation.differential_error` answers instead; at δ = 0 it
  reduces to this module exactly. BERKSON error is not deferred
  and is not corrected either: under ``X* = W + U`` the naive slope is already
  the causal one, so running this module on it would divide a right number
  through by a reliability ratio. Which structure holds has no witness in the
  data, so it arrives as ``measurement_error={<exposure>: {"structure":
  "berkson", …}}`` and that word keeps this row off —
  :mod:`themis.estimation.berkson` prices what such an error costs instead.
- **Linear** structural outcome model — the moment correction is exact for a
  linear Y (or the linear-probability projection of a binary Y). For a
  coefficient in a NONLINEAR outcome model there is
  :mod:`themis.estimation.simex`, which the caller reaches by declaring the
  model their coefficient lives in (``measurement_error={<exposure>:
  {"error_variance": …, "outcome_model": "logistic"}}``). That is a different
  estimand rather than a better computation of this one: on a binary Y this
  module de-attenuates the linear-probability slope and that one the log-odds
  ratio, both from the same two columns, so only the caller can say which was
  wanted. An absent or ``"linear"`` declaration keeps the closed form here,
  which beats a seeded simulation of itself. Cox is still deferred; the
  approximate RC "replace-and-refit" is not planned, because where it applies
  simulation-extrapolation answers the same question without the
  approximation being invisible.
- **Known, FIXED** error variances σ²_uv (validation-study / replicate quantities),
  exactly as the confusion matrix is fixed. Propagating validation-study
  uncertainty in σ²_uv itself (a second layer) is deferred; the bootstrap
  propagates the main-sample sampling variability only.
- **Numeric** design columns; a categorical covariate (dummy coding) is deferred.

The sufficient statistics recorded on the estimate (the design covariance matrix
Σ_obs, the Cov(D, Y) vector, the per-variable error variances, and n) are exactly
what ``themis.verify_regression_calibration_numeric`` re-derives the corrected
point, the naive point, and the reliabilities from — it never re-touches the raw
data and never imports this module.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .contract import validate_data
from .. import refusals
from ..refusals import Refusal, Remedy
from ..ledger import Provenance
from .form import NO_OTHER_SHAPES
from ..refusals import EstimatorFailure
from .resample import DeclaredVariance, cluster_labels, resample_indices

# A mismeasured variable with fewer than this many distinct values is treated as
# discrete (a misclassification object) rather than a continuously-mismeasured one.
_MIN_CONTINUOUS_DISTINCT = 10
# λ (reliability ratio) at or below this ⇒ the corrected design is not positive
# definite ⇒ refuse.
_LAMBDA_FLOOR = 1e-9
_TOL = 1e-9


@dataclass(frozen=True)
class RegressionCalibrationEstimate:
    """Regression-calibration-corrected effect of a continuously-mismeasured
    exposure and/or back-door covariate, with a bootstrap CI.

    ``point`` is the corrected per-unit slope βx of the true exposure X* on Y
    adjusting for the *true* Z. ``naive_point`` is the biased naive OLS slope of
    Y on the observed design — the number the correction replaces. ``reliability``
    is the exposure's λ = 1 − σ²_u/Var(W|Z) (the continuous analogue of det(M));
    it is 1.0 when the exposure is measured accurately (only a covariate is
    mismeasured). ``error_variances`` maps each mismeasured design variable to its
    known σ²_uv; ``reliabilities`` maps each to its λ_v. ``sufficient_statistics``
    carries the design covariance matrix Σ_obs, the Cov(D, Y) vector, the error
    variances, and n — everything the numeric verifier re-derives the point from.
    """
    point: float
    naive_point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    treatment: str
    outcome: str
    adjustment: tuple[str, ...]
    error_variance: float
    reliability: float
    naive_slope: tuple[float, ...]
    corrected_slope: tuple[float, ...]
    design_vars: tuple[str, ...]
    error_variances: dict = field(default_factory=dict)

    validation_df: dict = field(default_factory=dict)
    """Each mismeasured column whose σ²_uv came from a study, and that
    study's degrees of freedom. A column absent here is one the caller
    declared exactly — which is a claim about the measurement rather than
    a field left blank, and the assumption ledger carries it as one."""

    reliabilities: dict = field(default_factory=dict)
    sufficient_statistics: dict = field(default_factory=dict)
    cluster: str | None = None
    form: str = "regression_calibration_backdoor_linear"
    #: Nothing chose this shape: it IS the method, and the only way to
    #: overrule it is to answer by a different one.
    form_provenance: str = Provenance.INHERENT
    #: Which shapes a lever BESIDE the outcome model settled, by assumption
    #: id. The ids that RESTATE the outcome model's shape take the answer
    #: above; an id here is a different decision, made by a different lever,
    #: and says so itself — :func:`themis.estimation.form.shapes_settled`.
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES


# --- public entry -------------------------------------------------------------


def estimate_regression_calibration(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    error_variance: float | dict,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> RegressionCalibrationEstimate:
    """De-attenuate the linear back-door effect of a continuously-mismeasured
    exposure and/or covariate by the regression-calibration moment correction.

    Parameters
    ----------
    data: the main sample carrying the *observed* (error-prone) columns.
    treatment / outcome: exposure and (linear) outcome columns.
    adjustment: the back-door adjustment covariates Z (numeric).
    error_variance: the declared classical additive error variance(s) σ²_u. A
        scalar is sugar for ``{treatment: σ²_u}`` (a mismeasured exposure); a
        dict maps each mismeasured design variable name (the exposure and/or
        any adjustment covariate) to its declaration. A declaration is a bare
        number — σ²_uv taken as exact — or the caller's whole measurement spec,
        whose ``validation_df`` says a study estimated it and how big that
        study was. :class:`DeclaredVariance` normalises the three shapes.
    ci_bootstrap / ci_level / random_state / cluster: percentile-bootstrap
        controls. A variance declared exactly is held fixed across resamples;
        one declared with a df is redrawn from its own sampling distribution
        each round, so the interval carries that study's uncertainty as well
        as the main sample's.

    Raises
    ------
    EstimatorFailure: non-positive / non-finite error variance; a mismeasured
        variable that is near-discrete or not among the design columns; a
        collinear (singular) design; or a degenerate reliability (σ²_uv ≥
        Var(V|rest), so the corrected design is not positive definite).
    """
    # Normalize the error spec: a scalar σ²_u is sugar for {exposure: σ²_u}; a
    # dict maps design-variable names → their known classical error variance.
    if isinstance(error_variance, dict):
        given_error = {str(k): v for k, v in error_variance.items()}
    else:
        given_error = {treatment: error_variance}
    # Absence is not a value that fails a test — nothing was declared, and
    # the reader's next move is to declare one rather than to correct one.
    if not given_error:
        raise EstimatorFailure(
            Refusal.ARGUMENT_NOT_GIVEN,
            argument="error_variance=",
            remedies=[(Remedy.SUPPLY_INPUT, "error_variance")],
        )
    for name, ev in given_error.items():
        value = DeclaredVariance.declared_value(ev)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not np.isfinite(value)
            or value <= 0
        ):
            raise EstimatorFailure(
                Refusal.NON_POSITIVE_ERROR_VARIANCE,
                variable=name, given=value,
            )
    # Each column's variance together with how well it is known — one
    # record, so a site cannot read the number and miss the precision.
    declared = {name: DeclaredVariance.read(ev)
                for name, ev in given_error.items()}
    raw_error = {name: one.value for name, one in declared.items()}

    adjustment = tuple(sorted(adjustment))
    presence = (cluster,) if cluster is not None else ()
    contract = validate_data(
        data, required_columns={treatment, outcome, *adjustment},
        presence_columns=presence,
        # Every design column, not just the exposure: classical additive
        # error is a statement about a magnitude, and the reliability
        # matrix here is indexed one entry per NAME. A covariate that
        # expanded into indicators would silently break that pairing.
        quantity_columns=(treatment, outcome, *adjustment),
    )
    df = contract.data

    design_vars = (treatment, *adjustment)
    unknown = [k for k in raw_error if k not in design_vars]
    if unknown:
        raise EstimatorFailure(
            Refusal.MISMEASURED_VARIABLE_NOT_IN_DESIGN,
            variable=unknown, design=list(design_vars),
        )

    for name in raw_error:
        n_distinct = int(df[name].dropna().nunique())
        if n_distinct < _MIN_CONTINUOUS_DISTINCT:
            ftype = (
                Refusal.EXPOSURE_NOT_CONTINUOUS if name == treatment
                else Refusal.MISMEASURED_COVARIATE_NOT_CONTINUOUS
            )
            raise EstimatorFailure(
                ftype,
                column=name, levels=n_distinct,
                floor=_MIN_CONTINUOUS_DISTINCT,
                remedies=[(Remedy.SUPPLY_INPUT, "misclassification=")],
            )

    D = np.column_stack([df[v].to_numpy(dtype=float) for v in design_vars])
    y = df[outcome].to_numpy(dtype=float)
    n = len(df)
    # Error variance aligned to the design columns (0 for accurately-measured).
    e_vec = np.array([float(raw_error.get(v, 0.0)) for v in design_vars])

    groups = (
        cluster_labels(df, cluster, expected_n=n)
        if cluster is not None else None
    )

    point, naive, beta, b, reliabilities, Sigma, cov_Dy = _formula(
        D, y, e_vec, design_vars,
    )
    reliability_x = reliabilities.get(treatment, 1.0)

    # Aligned to the design columns exactly as ``e_vec`` is, so a draw can
    # rebuild the vector without re-deciding which column is which.
    e_declared = tuple(declared.get(v, DeclaredVariance(0.0))
                       for v in design_vars)

    ci_lower = ci_upper = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap(
            D, y, e_declared, design_vars, groups=groups,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level, random_state=random_state,
        )

    mismeasured = [v for v in design_vars if raw_error.get(v, 0.0) > 0]
    assumptions = _assumptions(adjustment, mismeasured, cluster, declared)
    error_variances = {v: float(raw_error[v]) for v in design_vars if v in raw_error}
    validation_df = {v: one.validation_df
                     for v, one in declared.items()
                     if one.validation_df is not None}
    return RegressionCalibrationEstimate(
        point=point,
        naive_point=naive,
        ci_lower=ci_lower, ci_upper=ci_upper, ci_level=ci_level,
        method="regression_calibration",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=treatment, outcome=outcome,
        adjustment=adjustment,
        error_variance=float(raw_error.get(treatment, 0.0)),
        reliability=reliability_x,
        naive_slope=tuple(float(v) for v in b),
        corrected_slope=tuple(float(v) for v in beta),
        design_vars=design_vars,
        error_variances=error_variances,
        validation_df=validation_df,
        reliabilities={k: float(v) for k, v in reliabilities.items()},
        sufficient_statistics={
            "design_vars": list(design_vars),
            "cov_matrix": [[float(v) for v in row] for row in Sigma],
            "cov_design_y": [float(v) for v in cov_Dy],
            "var_y": float(np.var(y, ddof=1)),
            "error_variance": float(raw_error.get(treatment, 0.0)),
            "error_variances": error_variances,
            "n": int(n),
            "exposure_index": 0,
            "reliability": reliability_x,
            "reliabilities": {k: float(v) for k, v in reliabilities.items()},
            "naive_slope": [float(v) for v in b],
            "corrected_slope": [float(v) for v in beta],
            "adjustment_vars": list(adjustment),
        },
        cluster=cluster,
    )


# --- formula core -------------------------------------------------------------


def _conditional_var(Sigma: np.ndarray, idx: int) -> float:
    """Residual variance of design column ``idx`` after regressing on the others:
    Var(V_idx | rest) = Σ_ii − Σ_i,rest Σ_rest,rest⁻¹ Σ_rest,i (the Schur
    complement). A single column ⇒ Var(V) = Σ_ii."""
    p = Sigma.shape[0]
    if p == 1:
        return float(Sigma[0, 0])
    others = [j for j in range(p) if j != idx]
    s_ii = float(Sigma[idx, idx])
    s_io = Sigma[idx, others]
    s_oo = Sigma[np.ix_(others, others)]
    return s_ii - float(s_io @ np.linalg.solve(s_oo, s_io))


def _formula(D: np.ndarray, y: np.ndarray, e_vec: np.ndarray, design_vars):
    """Corrected + naive slope vector from the design D and outcome y with the
    per-column error variances ``e_vec``.

    Returns (point, naive, corrected_slope, naive_slope, reliabilities, Σ_obs,
    Cov(D, y)) where ``point`` / ``naive`` are the exposure components. Raises on
    a singular design or a degenerate reliability (any Σ_obs − E non-PD)."""
    p = D.shape[1]
    Dc = D - D.mean(axis=0)
    yc = y - y.mean()
    Sigma = (Dc.T @ Dc) / (len(y) - 1)              # Σ_obs
    cov_Dy = (Dc.T @ yc) / (len(y) - 1)             # Cov(D, y)

    try:
        b = np.linalg.solve(Sigma, cov_Dy)          # naive OLS slopes
    except np.linalg.LinAlgError:
        raise EstimatorFailure(
            Refusal.SINGULAR_DESIGN,
            design=refusals.Design.DESIGN_COVARIANCE,
        )

    # Per-mismeasured-column reliability λ_v = 1 − σ²_uv / Var(V|rest); ≤ 0 means
    # the claimed error meets/exceeds the conditional variance ⇒ refuse.
    reliabilities: dict = {}
    for i in range(p):
        if e_vec[i] > 0:
            var_i = _conditional_var(Sigma, i)
            lam_i = 1.0 - e_vec[i] / var_i
            reliabilities[design_vars[i]] = float(lam_i)
            if lam_i <= _LAMBDA_FLOOR:
                raise EstimatorFailure(
                    Refusal.DEGENERATE_RELIABILITY,
                    variable=design_vars[i],
                    error_variance=float(e_vec[i]),
                    residual_variance=float(var_i),
                    reliability=float(lam_i),
                )

    E = np.diag(e_vec)
    Sigma_star = Sigma - E                          # Σ_true
    # Positive-definiteness is the general degeneracy condition (per-column λ > 0
    # is necessary but not sufficient once several columns are mismeasured), and
    # every per-column λ is positive by the time control reaches here — so this
    # is a fact about the variances TOGETHER, and says so under its own name.
    try:
        np.linalg.cholesky(Sigma_star)
    except np.linalg.LinAlgError:
        raise EstimatorFailure(
            Refusal.CORRECTED_DESIGN_NOT_POSITIVE_DEFINITE,
            recorded={
                "design_variables": list(design_vars),
                "error_variances": [float(v) for v in e_vec],
                "reliabilities": {k: float(v) for k, v in reliabilities.items()},
            },
        )
    beta = np.linalg.solve(Sigma_star, cov_Dy)      # corrected slopes

    return (
        float(beta[0]), float(b[0]), beta, b, reliabilities, Sigma, cov_Dy,
    )


def _bootstrap(
    D: np.ndarray, y: np.ndarray, e_declared, design_vars, *,
    groups: np.ndarray | None,
    ci_bootstrap: int, ci_level: float, random_state: int,
) -> tuple[float | None, float | None]:
    """Percentile bootstrap of the corrected exposure slope — resample rows (or
    clusters), redraw each error variance that came from a validation study,
    recompute the correction, collect βx. Draws that induce a degenerate
    reliability / singular design are skipped.

    **Two studies, two draws.** The row resample carries the main sample's
    uncertainty; the variance draw carries the validation study's, and they
    are independent because the studies are. A variance declared without
    degrees of freedom is the claim that no study estimated it, and
    :meth:`DeclaredVariance.draw` then consumes no randomness — so a run
    that declares none reproduces its old interval exactly, rng stream
    included.
    """
    rng = np.random.default_rng(random_state)
    n = len(y)
    pts: list[float] = []
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        e_vec = np.array([one.draw(rng) for one in e_declared])
        try:
            point, *_ = _formula(D[idx], y[idx], e_vec, design_vars)
        except EstimatorFailure:
            continue
        pts.append(point)
    if not pts:
        return None, None
    alpha = (1.0 - ci_level) / 2.0
    lo = float(np.quantile(pts, alpha))
    hi = float(np.quantile(pts, 1.0 - alpha))
    return lo, hi


def _assumptions(
    adjustment: tuple[str, ...], mismeasured: list[str], cluster: str | None,
    declared: dict,
) -> tuple[str, ...]:
    """The premises, as ids — which is what every other estimator declares.

    They were Chinese sentences, and a sentence cannot be an identity. The
    ledger needs two things per premise that no prose carries: which layer
    it sits in, and whether the reader can go check it. Keyed on prose, the
    only handle left was what the sentence STARTS with, so the glossary held
    four rows keyed on 「经典加性测量误差」 and the like — rows that could match
    exactly one language, and would fall silently to the unclassified
    default the moment this module spoke a second one.

    One row per mismeasured column rather than one row naming them all:
    each column's σ²_u comes from its own validation study and each can
    separately be wrong, and a premise the reader cannot refute one piece at
    a time is a premise they cannot act on.

    What the fourth sentence used to say — that a single mismeasured
    exposure has a scalar reliability ratio and a mismeasured confounder
    does not — is a consequence of the design rather than something that
    could be false. Which design ran is on the derivation chain, where
    the route belongs.

    An empty adjustment set is a different claim rather than an empty one,
    which is why it has its own id: with nothing to condition on, what the
    answer rests on is that the exposure was as good as randomised to begin
    with. The prose said 「调整集 Z = {∅}」 and left the reader to work that
    out.
    """
    # Which of the two the variance premise is depends on whether the
    # caller said a study estimated it. They are different claims, so they
    # are different ids: one says the number is taken as exact, the other
    # says its own uncertainty is priced into the interval and names what
    # THAT rests on. One id with a conditional clause would be a claim a
    # reader cannot refute without knowing which half applied.
    out = [
        *(f"design_error_classical_additive_on_{v}" for v in mismeasured),
        *(declared[v].premise("design_error_variance", v)
          for v in mismeasured),
        "linear_structural_outcome_model_in_the_true_values",
    ]
    if adjustment:
        out.append("backdoor_adjustment_{" + ",".join(adjustment) + "}")
    else:
        out.append(
            "unconditional_exchangeability_treatment_is_marginally_randomized")
    if cluster is not None:
        out.append(f"ci_via_pairs_cluster_bootstrap_on_{cluster}")
    return tuple(out)
