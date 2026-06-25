"""Phase 7.4 + 7.5 — mediation numeric estimators.

S.MN.1 (Phase 7.4): NDE / NIE / TE via statsmodels' Mediation class
(Imai, Keele, Tingley 2010 algorithms 1 & 2). See ``estimate_mediation``.

S.CDE (Phase 7.5, iter 125): Controlled Direct Effect at a fixed
mediator value m* via plug-in g-formula on a fitted outcome model
``Y ~ X + M + Z``. See ``estimate_cde``. Implementation is sklearn-
based (not statsmodels) because choosing a reference m* and computing
``E[Y|do(X=x), do(M=m*)]`` requires a custom plug-in that the
statsmodels Mediation API doesn't expose. Bootstrap CI matches the
backdoor estimator's percentile pattern.

Scope (current):
- Single mediator (bool or continuous)
- Binary treatment
- Bool or continuous outcome (logit / OLS)
- Adjustment set ``adjustment`` threaded into both outcome and
  mediator models as linear features
- CDE: requires the user to pass ``mediator_value=m*`` (no implicit
  reference choice — Themis does not invent which level is the
  "control" for the mediator)

Uses statsmodels as a production backend (not dev-only parity) per
the 5-rule API gate:
- deterministic given a seed
- statsmodels 15+ year track record
- version pinned in environment
- parity-testable against DoWhy's mediation estimator
- all outputs (3 point estimates + 3 CIs) fit in derivation JSON

CDE path uses sklearn linear / logistic regression for the outcome
model, same backend as ``themis/estimation/backdoor.py``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

import statsmodels.api as sm

from .contract import validate_data
from .four_way import four_way_decomposition


@dataclass(frozen=True)
class ComponentEstimate:
    """A single decomposition component: point estimate + percentile CI."""

    point: float
    ci_lower: float
    ci_upper: float


@dataclass(frozen=True)
class FourWayDecomposition:
    """VanderWeele 2014 four-way decomposition of the total effect into
    CDE + INTref + INTmed + PIE (unification of mediation and interaction).

    Each component carries a bootstrap percentile CI. ``prop_mediated``
    = (INTmed+PIE)/TE and ``prop_interaction`` = (INTref+INTmed)/TE are
    the two headline attribution proportions (Ch. 14.2). ``scale`` is
    the risk-difference scale; ``cde_mediator_reference`` records that
    the controlled direct effect fixes M at 0 and the mediator contrast
    is the M=0→1 unit change (exact for binary M; the M=0/1 evaluation
    linearizes the mediator effect for a continuous M under a nonlinear
    outcome model).
    """

    cde: ComponentEstimate
    intref: ComponentEstimate
    intmed: ComponentEstimate
    pie: ComponentEstimate
    te: ComponentEstimate
    prop_mediated: ComponentEstimate
    prop_interaction: ComponentEstimate
    additive_interaction_point: float
    ci_level: float
    scale: str
    cde_mediator_reference: object


@dataclass(frozen=True)
class MediationEstimate:
    """Numeric mediation decomposition.

    - ``nde`` / ``nie`` / ``te`` are point + CI for the natural direct,
      natural indirect, and total effects.
    - ``method`` distinguishes the outcome-model family.
    """

    nde_point: float
    nde_ci_lower: float
    nde_ci_upper: float
    nie_point: float
    nie_ci_lower: float
    nie_ci_upper: float
    te_point: float
    te_ci_lower: float
    te_ci_upper: float
    # Proportion of total effect mediated through M = NIE / TE.
    # The user's "X 占多少比例" question — surfaced explicitly so the
    # renderer doesn't have to compute it from {nie, te} (and lose the
    # CI by doing the division naively).
    proportion_mediated_point: float
    proportion_mediated_ci_lower: float
    proportion_mediated_ci_upper: float
    ci_level: float
    method: str                   # "mediation_linear_imai" | "mediation_logit_imai"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    adjustment: tuple[str, ...]
    mediator: str
    treatment: str
    outcome: str
    n_rep: int
    # VanderWeele 2014 four-way split of the same total effect. Computed
    # from the same fitted (interaction-aware) models; None only if the
    # decomposition could not be formed (it always can for the supported
    # binary-treatment scope, so this stays populated in practice).
    four_way: "FourWayDecomposition | None" = None


def estimate_mediation(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    mediator: str,
    adjustment: tuple[str, ...] = (),
    model: str = "auto",
    n_rep: int = 200,
    ci_level: float = 0.95,
    random_state: int = 42,
) -> MediationEstimate:
    """Compute NDE / NIE / TE via the Imai et al. 2010 algorithm as
    implemented in statsmodels. See module docstring for scope.
    """
    required = {treatment, outcome, mediator, *adjustment}
    contract = validate_data(data, required_columns=required)
    df = contract.data

    outcome_series = df[outcome]
    is_bool_outcome = pd.api.types.is_bool_dtype(outcome_series)
    resolved = (
        ("logit" if is_bool_outcome else "linear")
        if model == "auto" else model
    )

    # Coerce to float for statsmodels formula API
    fit_df = df.copy()
    bool_cols = [c for c in fit_df.columns if fit_df[c].dtype == bool]
    for c in bool_cols:
        fit_df[c] = fit_df[c].astype(float)

    adj_term = " + ".join(adjustment) if adjustment else ""
    sep = " + " if adj_term else ""

    # Outcome model: Y ~ X + M + X:M [+ adjustment]. The exposure-mediator
    # interaction is INCLUDED so the natural-effect decomposition is correct
    # under interaction. Omitting it silently collapses NDE/NIE to the
    # Baron-Kenny estimates (θ1, θ2·β1), which VanderWeele (2015, §2.2) shows
    # are biased whenever an interaction is present. statsmodels' Mediation does
    # NOT propagate an interaction term to the counterfactual exposure (it sets
    # the X column but leaves the stale X:M product), so we compute the natural
    # effects ourselves with a g-formula that re-predicts the outcome on rebuilt
    # design rows — patsy then recomputes X:M at the counterfactual exposure.
    interaction = f"{treatment}:{mediator}"
    outcome_formula = (
        f"{outcome} ~ {treatment} + {mediator} + {interaction}{sep}{adj_term}"
    )
    if resolved == "logit":
        is_logit = True
        method = "mediation_logit_imai"
    elif resolved == "linear":
        is_logit = False
        method = "mediation_linear_imai"
    else:
        raise ValueError(f"unknown model {model!r}")

    # Mediator model: M ~ X [+ adjustment]. Always OLS; for a bool mediator this
    # is a linear-probability first stage (a standard Imai-framework
    # approximation when the treatment effect on M is away from the [0,1] edge).
    mediator_formula = f"{mediator} ~ {treatment}{sep}{adj_term}"

    rng = np.random.default_rng(random_state)
    n_sim = 100  # Monte-Carlo mediator draws for the nonlinear (logit) g-formula

    def _fit(frame: pd.DataFrame):
        if is_logit:
            om = sm.Logit.from_formula(outcome_formula, data=frame).fit(disp=0)
        else:
            om = sm.OLS.from_formula(outcome_formula, data=frame).fit()
        mm = sm.OLS.from_formula(mediator_formula, data=frame).fit()
        return om, mm

    def _nde_nie(om, mm, frame: pd.DataFrame) -> tuple[float, float]:
        # NDE = E[Y_{1,M0} - Y_{0,M0}], NIE = E[Y_{1,M1} - Y_{1,M0}], where
        # M_x ~ (mediator model | X = x). The outcome is predicted on rebuilt
        # rows so the X:M interaction is re-evaluated at the counterfactual X.
        def _mean_M(xval: float):
            d = frame.copy()
            d[treatment] = xval
            return np.asarray(mm.predict(d))

        def _EY(xval: float, m_values, base: pd.DataFrame):
            d = base.copy()
            d[treatment] = xval
            d[mediator] = m_values
            return np.asarray(om.predict(d))

        if is_logit:
            # Nonlinear outcome: integrate over M's distribution by Monte Carlo.
            sd = float(np.std(np.asarray(mm.resid), ddof=1))
            mu0, mu1 = _mean_M(0.0), _mean_M(1.0)
            k = len(frame)
            big = pd.concat([frame] * n_sim, ignore_index=True)
            m0 = np.tile(mu0, n_sim) + rng.standard_normal(n_sim * k) * sd
            m1 = np.tile(mu1, n_sim) + rng.standard_normal(n_sim * k) * sd
            nde = float(np.mean(_EY(1.0, m0, big) - _EY(0.0, m0, big)))
            nie = float(np.mean(_EY(1.0, m1, big) - _EY(1.0, m0, big)))
            return nde, nie
        # Linear outcome: E[Y|X,M] is linear in M, so plugging in E[M|X] is exact.
        m0, m1 = _mean_M(0.0), _mean_M(1.0)
        nde = float(np.mean(_EY(1.0, m0, frame) - _EY(0.0, m0, frame)))
        nie = float(np.mean(_EY(1.0, m1, frame) - _EY(1.0, m0, frame)))
        return nde, nie

    def _four_way_inputs(om, mm, frame: pd.DataFrame) -> dict:
        # Standardized conditional outcome means p_am = E[Y|A=a,M=m] and
        # mediator means q_a = E[M|A=a], averaged over the sample's
        # covariates (g-formula standardization). For a linear outcome
        # these reproduce VanderWeele's regression form (14.4) exactly;
        # for binary M they are the empirical 14.1b quantities.
        def _ey(a: float, m: float) -> float:
            d = frame.copy()
            d[treatment] = a
            d[mediator] = m
            return float(np.mean(np.asarray(om.predict(d))))

        def _em(a: float) -> float:
            d = frame.copy()
            d[treatment] = a
            return float(np.mean(np.asarray(mm.predict(d))))

        return dict(
            p00=_ey(0.0, 0.0), p01=_ey(0.0, 1.0),
            p10=_ey(1.0, 0.0), p11=_ey(1.0, 1.0),
            q0=_em(0.0), q1=_em(1.0),
        )

    om_point, mm_point = _fit(fit_df)
    nde_p, nie_p = _nde_nie(om_point, mm_point, fit_df)
    te_p = nde_p + nie_p
    pm_p = nie_p / te_p if te_p != 0 else float("nan")

    fw_point = four_way_decomposition(
        **_four_way_inputs(om_point, mm_point, fit_df)
    )
    fw_pm_p = (
        (fw_point.intmed + fw_point.pie) / fw_point.te
        if fw_point.te != 0 else float("nan")
    )
    fw_pi_p = (
        (fw_point.intref + fw_point.intmed) / fw_point.te
        if fw_point.te != 0 else float("nan")
    )

    # Bootstrap CIs: resample rows with replacement, refit both models,
    # recompute the natural effects.
    n_rows = len(fit_df)
    nde_s: list[float] = []
    nie_s: list[float] = []
    te_s: list[float] = []
    pm_s: list[float] = []
    cde_s: list[float] = []
    intref_s: list[float] = []
    intmed_s: list[float] = []
    pie_s: list[float] = []
    fwte_s: list[float] = []
    fw_pm_s: list[float] = []
    fw_pi_s: list[float] = []
    for _ in range(n_rep):
        idx = rng.integers(0, n_rows, n_rows)
        bframe = fit_df.iloc[idx].reset_index(drop=True)
        try:
            om_b, mm_b = _fit(bframe)
            nb, ib = _nde_nie(om_b, mm_b, bframe)
            fwb = four_way_decomposition(
                **_four_way_inputs(om_b, mm_b, bframe)
            )
        except Exception:
            continue
        tb = nb + ib
        nde_s.append(nb)
        nie_s.append(ib)
        te_s.append(tb)
        pm_s.append(ib / tb if tb != 0 else float("nan"))
        cde_s.append(fwb.cde)
        intref_s.append(fwb.intref)
        intmed_s.append(fwb.intmed)
        pie_s.append(fwb.pie)
        fwte_s.append(fwb.te)
        fw_pm_s.append(
            (fwb.intmed + fwb.pie) / fwb.te if fwb.te != 0 else float("nan")
        )
        fw_pi_s.append(
            (fwb.intref + fwb.intmed) / fwb.te if fwb.te != 0 else float("nan")
        )

    half = (1.0 - ci_level) / 2.0

    def _ci(samples: list[float], point: float) -> tuple[float, float]:
        arr = np.array([s for s in samples if np.isfinite(s)], dtype=float)
        if arr.size < 2:
            return point, point
        lo = float(np.quantile(arr, half))
        hi = float(np.quantile(arr, 1.0 - half))
        # Guarantee the interval brackets the point estimate.
        return min(lo, point), max(hi, point)

    nde_lo, nde_hi = _ci(nde_s, nde_p)
    nie_lo, nie_hi = _ci(nie_s, nie_p)
    te_lo, te_hi = _ci(te_s, te_p)
    pm_lo, pm_hi = _ci(pm_s, pm_p)

    def _comp(samples: list[float], point: float) -> ComponentEstimate:
        lo, hi = _ci(samples, point)
        return ComponentEstimate(point=point, ci_lower=lo, ci_upper=hi)

    four_way = FourWayDecomposition(
        cde=_comp(cde_s, fw_point.cde),
        intref=_comp(intref_s, fw_point.intref),
        intmed=_comp(intmed_s, fw_point.intmed),
        pie=_comp(pie_s, fw_point.pie),
        te=_comp(fwte_s, fw_point.te),
        prop_mediated=_comp(fw_pm_s, fw_pm_p),
        prop_interaction=_comp(fw_pi_s, fw_pi_p),
        additive_interaction_point=fw_point.additive_interaction,
        ci_level=ci_level,
        scale="risk_difference",
        cde_mediator_reference=0,
    )

    return MediationEstimate(
        nde_point=nde_p, nde_ci_lower=nde_lo, nde_ci_upper=nde_hi,
        nie_point=nie_p, nie_ci_lower=nie_lo, nie_ci_upper=nie_hi,
        te_point=te_p, te_ci_lower=te_lo, te_ci_upper=te_hi,
        proportion_mediated_point=pm_p,
        proportion_mediated_ci_lower=pm_lo,
        proportion_mediated_ci_upper=pm_hi,
        ci_level=ci_level,
        method=method,
        assumptions=_assumptions_for(resolved, len(adjustment)),
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        adjustment=tuple(adjustment),
        mediator=mediator,
        treatment=treatment,
        outcome=outcome,
        n_rep=n_rep,
        four_way=four_way,
    )


@dataclass(frozen=True)
class CDEEstimate:
    """Phase 7.5 (iter 125) — Controlled Direct Effect at fixed M=m*.

    CDE(x, x', m*) = E[Y | do(X=x), do(M=m*)] - E[Y | do(X=x'), do(M=m*)]

    Differences from NDE/NIE:
    - CDE fixes M at a chosen level m* (the "control" for the
      mediator); NDE/NIE take expectations over M's natural distribution.
    - CDE only requires the X→Y identification given M (one-step
      no-unmeasured-confounders), not Pearl's full sequential
      ignorability — a strictly weaker assumption set.
    - Per VanderWeele 2015 ch.2.3.3, CDE is the policy-relevant
      direct effect when M is itself an intervention target (e.g.
      "what would the effect of X on Y look like if we forced
      everyone's M to m*?").
    """

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                   # "cde_linear" | "cde_logit"
    mediator_value: object        # the m* the CDE was computed at
    treatment_low: object         # the x' (control treatment level)
    treatment_high: object        # the x (treated level)
    sample_size: int
    data_hash: str
    adjustment: tuple[str, ...]
    mediator: str
    treatment: str
    outcome: str
    assumptions: tuple[str, ...]


def estimate_cde(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    mediator: str,
    mediator_value: object,
    adjustment: tuple[str, ...] = (),
    treatment_low: object = False,
    treatment_high: object = True,
    model: str = "auto",
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
) -> CDEEstimate:
    """Plug-in g-formula CDE at fixed ``M = mediator_value``.

    Steps:
    1. Fit ``E[Y | X, M, Z]`` with sklearn (linear if Y continuous,
       logistic if Y bool).
    2. For each row i, predict at ``(X=high, M=m*, Z=Z_i)`` and
       ``(X=low, M=m*, Z=Z_i)``; the CDE is the sample-mean difference.
    3. Percentile bootstrap CI (same pattern as backdoor.py).

    Returns ``CDEEstimate``. Does NOT require statsmodels — purely
    sklearn — because the statsmodels Mediation API doesn't expose
    do(M=m*) plug-in directly.
    """
    from sklearn.linear_model import LinearRegression, LogisticRegression

    required = {treatment, outcome, mediator, *adjustment}
    contract = validate_data(data, required_columns=required)
    df = contract.data

    is_bool_outcome = pd.api.types.is_bool_dtype(df[outcome])
    if model == "auto":
        resolved = "logit" if is_bool_outcome else "linear"
    else:
        resolved = model

    feature_cols = [treatment, mediator, *adjustment]

    def _fit_predict_diff(sample: pd.DataFrame) -> float:
        X_full = sample[feature_cols].to_numpy(dtype=float)
        y = sample[outcome].to_numpy()
        if resolved == "logit":
            y_int = y.astype(int)
            if len(np.unique(y_int)) < 2:
                raise ValueError("only one outcome value in this draw")
            clf = LogisticRegression(max_iter=1000, solver="lbfgs")
            clf.fit(X_full, y_int)
            X_high = X_full.copy()
            X_low = X_full.copy()
            # Replace the treatment column (index 0) and mediator (index 1)
            X_high[:, 0] = float(treatment_high)
            X_low[:, 0] = float(treatment_low)
            X_high[:, 1] = float(mediator_value)
            X_low[:, 1] = float(mediator_value)
            p_high = clf.predict_proba(X_high)[:, 1]
            p_low = clf.predict_proba(X_low)[:, 1]
            return float(np.mean(p_high - p_low))
        elif resolved == "linear":
            reg = LinearRegression()
            reg.fit(X_full, y.astype(float))
            X_high = X_full.copy()
            X_low = X_full.copy()
            X_high[:, 0] = float(treatment_high)
            X_low[:, 0] = float(treatment_low)
            X_high[:, 1] = float(mediator_value)
            X_low[:, 1] = float(mediator_value)
            return float(np.mean(reg.predict(X_high) - reg.predict(X_low)))
        else:
            raise ValueError(f"unknown model {model!r}")

    point = _fit_predict_diff(df)

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        rng = np.random.default_rng(random_state)
        n = len(df)
        draws = np.empty(ci_bootstrap)
        for i in range(ci_bootstrap):
            idx = rng.integers(0, n, size=n)
            try:
                draws[i] = _fit_predict_diff(df.iloc[idx])
            except (ValueError, np.linalg.LinAlgError):
                draws[i] = np.nan
        draws = draws[~np.isnan(draws)]
        if len(draws) > 0:
            alpha = (1 - ci_level) / 2
            ci_lower = float(np.quantile(draws, alpha))
            ci_upper = float(np.quantile(draws, 1 - alpha))

    method = f"cde_{resolved}"
    assumptions = (
        "no_unmeasured_confounder_x_y_given_m_and_adjustment",
        "no_unmeasured_confounder_m_y_given_x_and_adjustment",
        "consistency_of_potential_outcomes",
    )
    if adjustment:
        assumptions = assumptions + (
            "adjustment_set_blocks_xy_and_my_backdoors",
        )

    return CDEEstimate(
        point=point,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        method=method,
        mediator_value=mediator_value,
        treatment_low=treatment_low,
        treatment_high=treatment_high,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        adjustment=tuple(adjustment),
        mediator=mediator,
        treatment=treatment,
        outcome=outcome,
        assumptions=assumptions,
    )


@dataclass(frozen=True)
class CDEChainEstimate:
    """Phase 7.5+ (iter 134) — Controlled Direct Effect for a chain of
    N mediators X → M_1 → M_2 → ... → M_n → Y, fixing each M_i at
    a chosen reference value m_i*.

    CDE_chain(x, x', m1*, m2*, ..., mn*) =
        E[Y | do(X=x), do(M_1=m1*), do(M_2=m2*), ..., do(M_n=mn*)]
      - E[Y | do(X=x'), do(M_1=m1*), ..., do(M_n=mn*)]

    Differences from single-M ``CDEEstimate`` (iter 125):
    - ``mediators`` is a tuple of predicate names (chain order)
    - ``mediator_values`` is a parallel tuple of reference values
      (m_i* for each M_i)
    - method is "cde_chain_linear" / "cde_chain_logit"

    Same identification footing as single-M CDE per VanderWeele 2015
    ch.5 chain extension: fits a single outcome model
    ``Y ~ X + M_1 + ... + M_n + Z`` and plug-in evaluates at the
    chain-fixed mediator values.
    """

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                         # "cde_chain_linear" | "cde_chain_logit"
    mediators: tuple[str, ...]          # chain order
    mediator_values: tuple              # parallel to mediators
    treatment_low: object
    treatment_high: object
    sample_size: int
    data_hash: str
    adjustment: tuple[str, ...]
    treatment: str
    outcome: str
    assumptions: tuple[str, ...]


def estimate_cde_chain(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    mediators: tuple[str, ...],
    mediator_values: tuple,
    adjustment: tuple[str, ...] = (),
    treatment_low: object = False,
    treatment_high: object = True,
    model: str = "auto",
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
) -> CDEChainEstimate:
    """Plug-in g-formula CDE for a chain of N mediators, each fixed
    at a chosen value.

    Steps:
    1. Fit ``E[Y | X, M_1, ..., M_n, Z]`` with sklearn.
    2. For each row i, predict at
       (X=high, M_i=m_i* for each i, Z=Z_i) vs
       (X=low, M_i=m_i* for each i, Z=Z_i).
       Sample-mean difference is the CDE_chain.
    3. Percentile bootstrap CI.

    For N=1 this is exactly equivalent to ``estimate_cde``; the
    separate function exists so callers signal chain semantics
    explicitly and the audit trail records the chain-CDE assumption
    set (which adds "no unmeasured confounder between successive
    mediators given X and Z").

    Raises ``ValueError`` when:
    - ``mediators`` and ``mediator_values`` have different length
    - ``mediators`` is empty (use ``estimate_backdoor_ate`` for the
      no-mediator case)
    """
    from sklearn.linear_model import LinearRegression, LogisticRegression

    if len(mediators) != len(mediator_values):
        raise ValueError(
            f"mediators ({len(mediators)}) and mediator_values "
            f"({len(mediator_values)}) length mismatch"
        )
    if len(mediators) == 0:
        raise ValueError(
            "estimate_cde_chain requires at least one mediator; use "
            "estimate_backdoor_ate for the no-mediator case"
        )

    required = {treatment, outcome, *mediators, *adjustment}
    contract = validate_data(data, required_columns=required)
    df = contract.data

    is_bool_outcome = pd.api.types.is_bool_dtype(df[outcome])
    if model == "auto":
        resolved = "logit" if is_bool_outcome else "linear"
    else:
        resolved = model

    feature_cols = [treatment, *mediators, *adjustment]

    def _fit_predict_diff(sample: pd.DataFrame) -> float:
        X_full = sample[feature_cols].to_numpy(dtype=float)
        y = sample[outcome].to_numpy()
        if resolved == "logit":
            y_int = y.astype(int)
            if len(np.unique(y_int)) < 2:
                raise ValueError("only one outcome value in this draw")
            clf = LogisticRegression(max_iter=1000, solver="lbfgs")
            clf.fit(X_full, y_int)
            X_high = X_full.copy()
            X_low = X_full.copy()
            # Substitute treatment column (index 0) and each mediator
            # column (indices 1..len(mediators)).
            X_high[:, 0] = float(treatment_high)
            X_low[:, 0] = float(treatment_low)
            for i, mv in enumerate(mediator_values):
                X_high[:, 1 + i] = float(mv)
                X_low[:, 1 + i] = float(mv)
            p_high = clf.predict_proba(X_high)[:, 1]
            p_low = clf.predict_proba(X_low)[:, 1]
            return float(np.mean(p_high - p_low))
        elif resolved == "linear":
            reg = LinearRegression()
            reg.fit(X_full, y.astype(float))
            X_high = X_full.copy()
            X_low = X_full.copy()
            X_high[:, 0] = float(treatment_high)
            X_low[:, 0] = float(treatment_low)
            for i, mv in enumerate(mediator_values):
                X_high[:, 1 + i] = float(mv)
                X_low[:, 1 + i] = float(mv)
            return float(np.mean(reg.predict(X_high) - reg.predict(X_low)))
        else:
            raise ValueError(f"unknown model {model!r}")

    point = _fit_predict_diff(df)

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        rng = np.random.default_rng(random_state)
        n = len(df)
        draws = np.empty(ci_bootstrap)
        for i in range(ci_bootstrap):
            idx = rng.integers(0, n, size=n)
            try:
                draws[i] = _fit_predict_diff(df.iloc[idx])
            except (ValueError, np.linalg.LinAlgError):
                draws[i] = np.nan
        draws = draws[~np.isnan(draws)]
        if len(draws) > 0:
            alpha = (1 - ci_level) / 2
            ci_lower = float(np.quantile(draws, alpha))
            ci_upper = float(np.quantile(draws, 1 - alpha))

    method = f"cde_chain_{resolved}"
    assumptions = (
        "no_unmeasured_confounder_x_y_given_chain_and_adjustment",
        "no_unmeasured_confounder_between_successive_mediators",
        "consistency_of_potential_outcomes",
        "outcome_model_correctly_specified_at_chain_fixed_values",
    )
    if adjustment:
        assumptions = assumptions + (
            "adjustment_set_blocks_xy_and_my_chain_backdoors",
        )

    return CDEChainEstimate(
        point=point,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        method=method,
        mediators=tuple(mediators),
        mediator_values=tuple(mediator_values),
        treatment_low=treatment_low,
        treatment_high=treatment_high,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        adjustment=tuple(adjustment),
        treatment=treatment,
        outcome=outcome,
        assumptions=assumptions,
    )


def _assumptions_for(model: str, n_adj: int) -> tuple[str, ...]:
    common = (
        "sequential_ignorability_treatment_and_mediator",
        "no_intermediate_confounder_affected_by_treatment",
        "pearl_2001_four_conditions_hold_on_the_graph",
    )
    if model == "linear":
        common = common + ("linear_outcome_regression",)
    elif model == "logit":
        common = common + ("logit_outcome_regression",)
    if n_adj > 0:
        common = common + (
            "adjustment_set_blocks_mediator_outcome_backdoor_given_treatment",
        )
    return common
