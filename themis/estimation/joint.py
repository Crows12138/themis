"""Joint-intervention g-formula estimator — do(A=a, B=b) on multiple
binary treatments, plus the treatment×treatment causal interaction.

Implements the plug-in (outcome-regression / g-formula) estimator for
the JOINT average treatment effect of intervening on a set of binary
treatments simultaneously:

    joint_contrast
        = E[Y | do(A=a, B=b)] − E[Y | do(A=a', B=b')]
        = (1/n) Σ_i [ Ê(Y | A=a,  B=b,  Z=Z_i)
                     − Ê(Y | A=a', B=b', Z=Z_i) ]

and the causal interaction on the difference scale (VanderWeele 2015
ch.14 "interaction"):

    interaction
        = [E[Y|do(A=1,B=1)] − E[Y|do(A=1,B=0)]]
        − [E[Y|do(A=0,B=1)] − E[Y|do(A=0,B=0)]]
        = (1/n) Σ_i { [Ê(Y|1,1,Z_i) − Ê(Y|1,0,Z_i)]
                    − [Ê(Y|0,1,Z_i) − Ê(Y|0,0,Z_i)] }

The outcome model E[Y | A, B, Z] is fit INCLUDING the A:B interaction
term, so the standardization can recover both the joint contrast and
the interaction. ``LinearRegression`` for continuous outcomes,
``LogisticRegression`` for bool outcomes. Confidence intervals via the
non-parametric percentile bootstrap; deterministic given
``random_state`` (a seeded numpy Generator), with the joint contrast
and interaction computed from the SAME resample so the two intervals
are mutually consistent.

Reference: Hernán & Robins 2020 ch.13 (standardization / g-formula) for
the joint contrast; VanderWeele 2015 *Explanation in Causal Inference*
ch.14 for the additive-scale interaction. Identification of the joint
quantity from data rests on the generalized (treatment-set) back-door
criterion — see ``structural_solver.minimal_adjustment_sets_joint``.

Scope (v1):
- Binary treatments (exactly two supported here; the design generalizes
  but >2 multiplies the counterfactual cells and is deferred).
- Bool or continuous outcome.
- Adjustment set ``adjustment`` enters the outcome regression as linear
  features (same backend / restriction as ``backdoor.py``).

API:

    from themis.estimation.joint import estimate_joint_effect
    est = estimate_joint_effect(
        data, treatments=("a", "b"), outcome="y", adjustment=("z",),
    )
    print(est.joint_point, est.interaction_point)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression, LogisticRegression

from .contract import validate_data
from .dose_response import EstimatorFailure
from .resample import cluster_labels, resample_indices


ModelName = Literal["auto", "linear", "logistic"]


@dataclass(frozen=True)
class JointEffectEstimate:
    """Result of a joint-intervention g-formula estimate.

    - ``joint_*``: point + CI for the joint contrast
      E[Y|do(A=a,B=b)] − E[Y|do(A=a',B=b')].
    - ``interaction_*``: point + CI for the additive-scale
      treatment×treatment interaction.
    - ``treated`` / ``control``: the {treatment: value} cells the joint
      contrast is taken between.
    """

    joint_point: float
    joint_ci_lower: float | None
    joint_ci_upper: float | None
    interaction_point: float
    interaction_ci_lower: float | None
    interaction_ci_upper: float | None
    ci_level: float
    method: str                       # "joint_backdoor_linear" | "joint_backdoor_logistic"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    adjustment: tuple[str, ...]
    treatments: tuple[str, ...]
    treated: tuple[tuple[str, object], ...]   # ((name, value), ...) — the (a, b) cell
    control: tuple[tuple[str, object], ...]   # ((name, value), ...) — the (a', b') cell
    outcome: str
    # Variance concern, not a model node: when set, both the joint and the
    # interaction CIs were computed by resampling whole clusters (pairs
    # cluster bootstrap) rather than i.i.d. rows. None → i.i.d. bootstrap.
    cluster: str | None = None


def estimate_joint_effect(
    data: pd.DataFrame,
    *,
    treatments: tuple[str, ...],
    outcome: str,
    adjustment: tuple[str, ...] = (),
    treated_values: dict | None = None,
    control_values: dict | None = None,
    model: ModelName = "auto",
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> JointEffectEstimate:
    """Joint g-formula contrast + treatment×treatment interaction.

    Parameters
    ----------
    data: DataFrame with treatment / outcome / adjustment columns.
    treatments: ordered tuple of exactly two binary treatment column
        names (A, B).
    outcome: outcome column name (bool or continuous).
    adjustment: adjustment-set column names (may be empty).
    treated_values / control_values: {name: value} for the (a, b) and
        (a', b') cells of the joint contrast. Default treated = all-True,
        control = all-False.
    model: 'auto' → logistic for bool outcome, linear otherwise.
    ci_bootstrap: bootstrap resamples; 0 skips CIs.
    ci_level: two-sided level (default 0.95).
    random_state: deterministic seed.
    cluster: optional column naming a cluster / block id. When set, the
        bootstrap resamples whole clusters with replacement (pairs cluster
        bootstrap) instead of i.i.d. rows — the right variance under
        within-cluster dependence. Because the joint contrast and the
        interaction share the SAME resample, both CIs become
        cluster-robust together. ``None`` reproduces the i.i.d. bootstrap
        byte-for-byte. The cluster column is a variance concern, NOT part
        of the causal model: it never enters the outcome regression or the
        data hash.
    """
    if len(treatments) != 2:
        raise NotImplementedError(
            f"estimate_joint_effect v1 supports exactly two treatments; "
            f"got {len(treatments)} ({treatments!r})"
        )

    required = {*treatments, outcome, *adjustment}
    # Pull cluster labels from the raw frame (uncoerced) before the
    # contract subsets to model columns; positionally aligned with df.
    groups = (
        cluster_labels(data, cluster, expected_n=len(data))
        if cluster is not None else None
    )
    contract = validate_data(
        data, required_columns=required,
        presence_columns=(cluster,) if cluster is not None else (),
    )
    df = contract.data

    a_name, b_name = treatments
    treated_values = treated_values or {a_name: True, b_name: True}
    control_values = control_values or {a_name: False, b_name: False}

    # Positivity / overlap precondition: the joint g-formula contrasts
    # across treatment cells, so each treatment must vary in the data.
    # A single observed level fabricates a contrast by extrapolating a
    # zero-variance regressor — refuse, mirroring backdoor.estimate.
    for t in treatments:
        levels = df[t].dropna().unique()
        if len(levels) < 2:
            raise EstimatorFailure(
                "overlap_insufficient",
                f"treatment {t!r} has a single observed level "
                f"({levels.tolist()}) in the data — positivity is maximally "
                f"violated and there is no contrast to estimate for the "
                f"joint effect. Supply data with variation in {t!r}.",
                treatment=t,
            )

    is_bool_outcome = pd.api.types.is_bool_dtype(df[outcome])
    resolved = (
        ("logistic" if is_bool_outcome else "linear")
        if model == "auto" else model
    )
    method = f"joint_backdoor_{resolved}"

    a_hi = float(treated_values[a_name]); a_lo = float(control_values[a_name])
    b_hi = float(treated_values[b_name]); b_lo = float(control_values[b_name])

    def _joint_and_interaction(sample: pd.DataFrame) -> tuple[float, float]:
        predict = _fit(sample, a_name, b_name, outcome, adjustment, resolved)
        # Counterfactual predictions at each (A, B) cell, averaged over
        # the empirical Z distribution of the sample (g-formula plug-in).
        m11 = float(np.mean(predict(sample, a_hi, b_hi)))
        m10 = float(np.mean(predict(sample, a_hi, b_lo)))
        m01 = float(np.mean(predict(sample, a_lo, b_hi)))
        m00 = float(np.mean(predict(sample, a_lo, b_lo)))
        # Joint contrast between the requested treated / control cells.
        treated_pred = float(np.mean(predict(sample, a_hi, b_hi)))
        control_pred = float(np.mean(predict(sample, a_lo, b_lo)))
        joint = treated_pred - control_pred
        # Additive-scale interaction is defined on the canonical 2×2
        # corners (1,1)/(1,0)/(0,1)/(0,0) regardless of which cells the
        # joint contrast used.
        interaction = (m11 - m10) - (m01 - m00)
        return joint, interaction

    joint_point, interaction_point = _joint_and_interaction(df)

    joint_lo = joint_hi = None
    inter_lo = inter_hi = None
    if ci_bootstrap > 0:
        rng = np.random.default_rng(random_state)
        n = len(df)
        joint_draws = np.empty(ci_bootstrap)
        inter_draws = np.empty(ci_bootstrap)
        for i in range(ci_bootstrap):
            idx = resample_indices(n, rng, groups=groups)
            try:
                jd, idd = _joint_and_interaction(df.iloc[idx])
            except (ValueError, np.linalg.LinAlgError):
                jd = idd = np.nan
            joint_draws[i] = jd
            inter_draws[i] = idd
        alpha = (1 - ci_level) / 2
        jd_valid = joint_draws[~np.isnan(joint_draws)]
        id_valid = inter_draws[~np.isnan(inter_draws)]
        if len(jd_valid) > 0:
            joint_lo = float(np.quantile(jd_valid, alpha))
            joint_hi = float(np.quantile(jd_valid, 1 - alpha))
        if len(id_valid) > 0:
            inter_lo = float(np.quantile(id_valid, alpha))
            inter_hi = float(np.quantile(id_valid, 1 - alpha))

    assumptions = _assumptions_for(resolved, len(adjustment))
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )

    return JointEffectEstimate(
        joint_point=joint_point,
        joint_ci_lower=joint_lo,
        joint_ci_upper=joint_hi,
        interaction_point=interaction_point,
        interaction_ci_lower=inter_lo,
        interaction_ci_upper=inter_hi,
        ci_level=ci_level,
        method=method,
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        adjustment=tuple(adjustment),
        treatments=tuple(treatments),
        treated=tuple((k, treated_values[k]) for k in treatments),
        control=tuple((k, control_values[k]) for k in treatments),
        outcome=outcome,
        cluster=cluster,
    )


# --- internals --------------------------------------------------------------


def _fit(
    df: pd.DataFrame,
    a_name: str,
    b_name: str,
    outcome: str,
    adjustment: tuple[str, ...],
    model: str,
):
    """Fit E[Y | A, B, A·B, Z] and return a callable
    ``predict(sample, a_val, b_val) -> yhat`` that standardizes the
    counterfactual cell over the sample's adjustment values."""
    a = df[a_name].to_numpy(dtype=float)
    b = df[b_name].to_numpy(dtype=float)
    inter = a * b
    if adjustment:
        z = df[list(adjustment)].to_numpy(dtype=float)
        X = np.column_stack([a, b, inter, z])
    else:
        X = np.column_stack([a, b, inter])
    y = df[outcome].to_numpy()
    if y.dtype == bool:
        y = y.astype(int)

    if model == "logistic":
        if len(np.unique(y)) < 2:
            raise ValueError("only one outcome value in this draw")
        clf = LogisticRegression(max_iter=1000, solver="lbfgs")
        clf.fit(X, y)
        base = lambda M: clf.predict_proba(M)[:, 1]
    elif model == "linear":
        reg = LinearRegression()
        reg.fit(X, y.astype(float))
        base = lambda M: reg.predict(M)
    else:
        raise ValueError(f"unknown model {model!r}")

    def predict(sample: pd.DataFrame, a_val: float, b_val: float):
        n = len(sample)
        a_col = np.full(n, a_val)
        b_col = np.full(n, b_val)
        inter_col = a_col * b_col
        if adjustment:
            z = sample[list(adjustment)].to_numpy(dtype=float)
            M = np.column_stack([a_col, b_col, inter_col, z])
        else:
            M = np.column_stack([a_col, b_col, inter_col])
        return base(M)

    return predict


def _assumptions_for(model: str, n_adj: int) -> tuple[str, ...]:
    common = (
        "joint_conditional_exchangeability_given_adjustment_set",
        "positivity_overlap_of_every_treatment_cell",
        "consistency_of_potential_outcomes_under_joint_intervention",
        "no_directed_edge_between_treatments",
    )
    if model == "linear":
        common = common + ("linear_outcome_regression_with_AxB_interaction",)
    elif model == "logistic":
        common = common + ("logit_outcome_regression_with_AxB_interaction",)
    if n_adj == 0:
        common = common + (
            "unconditional_exchangeability_treatments_marginally_randomized",
        )
    return common
