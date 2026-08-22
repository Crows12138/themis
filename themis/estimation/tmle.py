"""Targeted Maximum Likelihood Estimation (TMLE) for the ATE.

TMLE (van der Laan & Rubin 2006; van der Laan & Rose 2011) is the third
doubly-robust estimator for the backdoor ATE, alongside AIPW. Like AIPW
it is consistent if EITHER the outcome regression OR the propensity is
correct, and achieves the semiparametric efficiency bound — the two are
asymptotically equivalent. What TMLE adds over AIPW is that it is a
*substitution* estimator: it targets an initial outcome fit through a
bounded logistic fluctuation, so the final prediction (and hence the
estimate) respects the natural [0,1] range of a probability and behaves
better than AIPW when propensity scores approach 0 / 1.

Algorithm (single binary treatment, backdoor adjustment Z):

1. **Scale** the outcome to [0,1]: for a binary Y, identity; for a
   bounded-continuous Y, Y' = (Y - a)/(b - a) with a,b the observed
   min/max (Gruber & van der Laan 2010).
2. **Initial outcome fit** Q̄⁰(T,Z) = Ê[Y'|T,Z] — a learner matching the
   outcome type (linear for continuous, logistic for binary; same
   nuisance family as AIPW). Predictions clipped to (δ, 1-δ).
3. **Propensity** e(Z) = P(T=1|Z), Winsorized to [floor, 1-floor].
4. **Clever covariate** H(T,Z) = T/e - (1-T)/(1-e); arm versions
   H₁ = 1/e, H₀ = -1/(1-e).
5. **Fluctuation** ε: a one-parameter logistic MLE of Y' on H with
   logit(Q̄⁰) as OFFSET (no intercept). This is the "targeting" step.
6. **Update** Q̄¹(t,Z) = expit(logit(Q̄⁰(t,Z)) + ε·H_t(Z)).
7. **Substitution** ψ' = mean(Q̄¹(1,Z) - Q̄¹(0,Z)); rescale ψ = (b-a)·ψ'.
8. **Inference** via the efficient influence curve
   IC = (b-a)·[ H·(Y' - Q̄¹(T,Z)) + Q̄¹(1,Z) - Q̄¹(0,Z) - ψ' ];
   SE = sqrt(Var(IC)/n) (cluster-robust when a cluster column is set).

**Positivity** is Winsorized and disclosed identically to AIPW
(``PropensitySummary``). **Scope declared**: parametric nuisances, no
cross-fitting (second-order for fixed-dimension parametric fits; the
econml cross-fit DR-learner covers the ML case).

References:
- van der Laan MJ, Rubin D. "Targeted maximum likelihood learning."
  Int J Biostat 2006;2(1).
- van der Laan MJ, Rose S. *Targeted Learning*. Springer 2011 (ch.4-5:
  the ATE TMLE + its efficient influence curve).
- Gruber S, van der Laan MJ. "A targeted maximum likelihood estimator
  of a causal effect on a bounded continuous outcome." Int J Biostat
  2010;6(1) (the [0,1]-scaling for continuous outcomes).

API:

    from themis.estimation.tmle import estimate_tmle_ate
    est = estimate_tmle_ate(data, treatment="x", outcome="y",
                            adjustment=("z1", "z2"))
    print(est.point, est.ci_lower, est.ci_upper, est.epsilon)
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from statistics import NormalDist
from typing import Literal

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression, LogisticRegression

from ..ledger import Provenance
from .form import NO_OTHER_SHAPES, UNSET, pulled_by, shapes_settled
from .support import Support, overlap_assumption
from .declared import ORDERED_ENTRY_SHAPE, design_block, ordered_entry
from .aipw import (
    DEFAULT_PROPENSITY_FLOOR,
    PropensitySummary,
    _propensity_floor_id,
    _influence_function_se,
    _maybe_float,
    _percentiles,
    _prepare,
    _propensity_scores,
)
from .resample import resample_indices


DEFAULT_OUTCOME_FLOOR = 1e-4


@dataclass(frozen=True)
class TMLEEstimate:
    """Result of a targeted-maximum-likelihood ATE estimate."""

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                # "tmle"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    adjustment: tuple[str, ...]
    treatment: str
    outcome: str
    propensity: PropensitySummary
    epsilon: float             # fluctuation parameter (targeting step)
    std_error: float | None    # influence-curve SE (analytic CI path)
    ci_method: str             # "influence_function" | "bootstrap"
    doubly_robust: bool = True
    form: str = ""             # initial outcome-model form: "linear" | "logistic"
    #: TMLE takes no ``model=``: the initial fit follows the outcome's
    #: type and the caller has no lever, so nothing was CHOSEN here.
    form_provenance: str = Provenance.INHERENT
    #: Which shapes a lever BESIDE the outcome model settled, by assumption
    #: id. The ids that RESTATE the outcome model's shape take the answer
    #: above; an id here is a different decision, made by a different lever,
    #: and says so itself — :func:`themis.estimation.form.shapes_settled`.
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES
    cluster: str | None = None


def estimate_tmle_ate(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...] = (),
    propensity_floor: float | None = UNSET,
    outcome_floor: float = DEFAULT_OUTCOME_FLOOR,
    ci_method: Literal["influence_function", "bootstrap"] = "influence_function",
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> TMLEEstimate:
    """Targeted maximum likelihood estimate of the ATE.

    Consistent if EITHER the initial outcome regression OR the propensity
    model is correct. ``ci_method`` mirrors AIPW: ``"influence_function"``
    (default) is the analytic Wald CI from the efficient influence curve
    (cluster-robust when ``cluster`` is set); ``"bootstrap"`` refits the
    whole TMLE per resample.
    """
    # Where the clip sits is the caller's if they said so, and TMLE's
    # own if they did not — a distinction the resolved value cannot
    # carry, which is why it is read before the value is resolved.
    floor_by = pulled_by(propensity_floor)
    floor = (DEFAULT_PROPENSITY_FLOOR if propensity_floor is UNSET
             else float(propensity_floor))

    ctx = _prepare(data, treatment, outcome, adjustment, cluster)
    df, contract, groups = ctx.df, ctx.contract, ctx.groups

    psi, ic, epsilon, prop, form = _tmle_fit(
        df, treatment, outcome, adjustment,
        propensity_floor=floor, outcome_floor=outcome_floor,
    )

    std_error: float | None = None
    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_method == "influence_function":
        # ic is already centered (mean ≈ 0); pass (ic + psi, psi) so the
        # shared helper's internal centering recovers ic exactly.
        std_error = _influence_function_se(ic + psi, psi, groups)
        if std_error is not None and ci_bootstrap != 0:
            z = NormalDist().inv_cdf(1 - (1 - ci_level) / 2)
            ci_lower = psi - z * std_error
            ci_upper = psi + z * std_error
    else:  # bootstrap
        if ci_bootstrap > 0:
            ci_lower, ci_upper = _tmle_bootstrap_ci(
                df, treatment, outcome, adjustment,
                propensity_floor=floor, outcome_floor=outcome_floor,
                ci_bootstrap=ci_bootstrap, ci_level=ci_level,
                random_state=random_state, groups=groups,
            )

    assumptions = _assumptions_tmle(form, len(adjustment), prop, cluster,
                                    ci_method, ctx.support)
    # The design took each adjustment column as ONE term, so a column
    # with more than two levels was read as a number: level three sits
    # twice as far from level one as level two does. Nothing in the
    # program claimed that, and `scale` has no member that could deny
    # it, so the fit says what it assumed.
    assumptions += ordered_entry(ctx.df, adjustment)
    return TMLEEstimate(
        point=float(psi),
        ci_lower=_maybe_float(ci_lower),
        ci_upper=_maybe_float(ci_upper),
        ci_level=ci_level,
        method="tmle",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        adjustment=tuple(adjustment),
        treatment=treatment,
        outcome=outcome,
        propensity=prop,
        epsilon=float(epsilon),
        std_error=_maybe_float(std_error),
        ci_method=ci_method,
        doubly_robust=True,
        form=form,
        # TMLE has no ``model=`` and the constant above says so. It does have
        # a floor, and that one the caller can name.
        shape_provenance=shapes_settled(
            assumptions,
            (_propensity_floor_id(prop), floor_by),
            ORDERED_ENTRY_SHAPE,
        ),
        cluster=cluster,
    )


# --- core -------------------------------------------------------------------


def _logit(p: np.ndarray) -> np.ndarray:
    return np.log(p / (1.0 - p))


def _expit(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _tmle_fit(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    *,
    propensity_floor: float,
    outcome_floor: float,
) -> tuple[float, np.ndarray, float, PropensitySummary, str]:
    """Run the TMLE targeting on a frame; return
    (psi, influence_curve, epsilon, propensity_summary, outcome_form)."""
    import statsmodels.api as sm

    t = df[treatment].to_numpy(dtype=float)
    y = df[outcome].to_numpy()
    if y.dtype == bool:
        y = y.astype(float)
    y = y.astype(float)
    n = len(y)

    # bounded scaling to [0,1]
    uniq = set(np.unique(y).tolist())
    is_binary = uniq <= {0.0, 1.0}
    a, b = (0.0, 1.0) if is_binary else (float(y.min()), float(y.max()))
    span = (b - a) if b > a else 1.0
    ys = (y - a) / span

    # design [T | Z]
    if adjustment:
        Z = design_block(df, adjustment)
        X = np.hstack([t[:, None], Z])
    else:
        X = t[:, None]

    delta = outcome_floor

    # initial Q0 (learner matching outcome type), scaled + clipped to (δ,1-δ)
    if is_binary:
        clf = LogisticRegression(max_iter=1000, solver="lbfgs")
        clf.fit(X, y.astype(int))
        raw_predict = lambda M: clf.predict_proba(M)[:, 1]
        form = "logistic"
        scale = lambda p: np.clip(p, delta, 1.0 - delta)
    else:
        reg = LinearRegression()
        reg.fit(X, ys)                       # fit on scaled outcome
        raw_predict = lambda M: reg.predict(M)
        form = "linear"
        scale = lambda p: np.clip(p, delta, 1.0 - delta)

    def q_at(tv: float) -> np.ndarray:
        M = X.copy()
        M[:, 0] = tv
        return scale(raw_predict(M))

    Q0_obs = scale(raw_predict(X))
    Q0_1 = q_at(1.0)
    Q0_0 = q_at(0.0)

    # propensity + clever covariate
    e, prop = _propensity_scores(df, treatment, adjustment, floor=propensity_floor)
    H_obs = t / e - (1.0 - t) / (1.0 - e)
    H1 = 1.0 / e
    H0 = -1.0 / (1.0 - e)

    # fluctuation: 1-param logistic MLE, offset = logit(Q0), covariate H
    epsilon = 0.0
    try:
        fluc = sm.GLM(
            ys, H_obs[:, None],
            family=sm.families.Binomial(),
            offset=_logit(Q0_obs),
        ).fit()
        eps_hat = float(fluc.params[0])
        if np.isfinite(eps_hat):
            epsilon = eps_hat
    except Exception:
        # PerfectSeparation / non-convergence → ε=0 falls back to the
        # untargeted initial plug-in (safe, loses double robustness).
        epsilon = 0.0

    Q1_obs = _expit(_logit(Q0_obs) + epsilon * H_obs)
    Q1_1 = _expit(_logit(Q0_1) + epsilon * H1)
    Q1_0 = _expit(_logit(Q0_0) + epsilon * H0)

    psi_s = float(np.mean(Q1_1 - Q1_0))
    psi = span * psi_s
    ic = span * (H_obs * (ys - Q1_obs) + (Q1_1 - Q1_0) - psi_s)
    return psi, ic, epsilon, prop, form


def _tmle_bootstrap_ci(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    *,
    propensity_floor: float,
    outcome_floor: float,
    ci_bootstrap: int,
    ci_level: float,
    random_state: int,
    groups: np.ndarray | None,
) -> tuple[float, float]:
    """Percentile bootstrap for TMLE, re-running the full targeting per
    resample (cluster-aware)."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    estimates = np.empty(ci_bootstrap)
    for i in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        sample = df.iloc[idx]
        psi, _, _, _, _ = _tmle_fit(
            sample, treatment, outcome, adjustment,
            propensity_floor=propensity_floor, outcome_floor=outcome_floor,
        )
        estimates[i] = psi
    return _percentiles(estimates, ci_level)


# --- assumption ledger -------------------------------------------------------


def _assumptions_tmle(
    outcome_form: str,
    n_adj: int,
    prop: PropensitySummary,
    cluster: str | None,
    ci_method: str,
    support: Support,
) -> tuple[str, ...]:
    common: tuple[str, ...] = (
        "conditional_exchangeability_given_adjustment_set",
        overlap_assumption(support),
        "consistency_of_potential_outcomes",
        "doubly_robust_outcome_OR_propensity_model_correct",
        "tmle_targeted_substitution_estimator",
    )
    common += (
        "logit_outcome_regression" if outcome_form == "logistic"
        else "linear_outcome_regression",
    )
    if n_adj == 0:
        common += ("unconditional_exchangeability_treatment_is_marginally_randomized",)
    if prop.n_trimmed:
        common += (_propensity_floor_id(prop),)
    if ci_method == "influence_function":
        common += ("ci_via_analytic_influence_function",)
        if cluster is not None:
            common += (f"cluster_robust_influence_variance_on_{cluster}",)
    else:
        common += ("ci_via_percentile_bootstrap",)
        if cluster is not None:
            common += (f"ci_via_pairs_cluster_bootstrap_on_{cluster}",)
    return common
