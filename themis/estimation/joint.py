"""Joint-intervention g-formula estimator — do(A=a, B=b) on multiple
binary treatments, plus the treatment×treatment causal interaction.

Implements the plug-in (outcome-regression / g-formula) estimator for
the JOINT average treatment effect of intervening on a set of binary
treatments simultaneously:

    joint_contrast
        = E[Y | do(A=a, B=b)] − E[Y | do(A=a', B=b')]
        = (1/n) Σ_i [ Ê(Y | A=a,  B=b,  Z=Z_i)
                     − Ê(Y | A=a', B=b', Z=Z_i) ]

and the highest-order causal interaction on the difference scale
(VanderWeele 2015 ch.14 "interaction"). For K treatments this is the
K-th-order mixed finite difference over the 2^K treatment corners — the
alternating-sign standardized sum

    interaction_K
        = Σ_{s ∈ ∏_k {hi_k, lo_k}} (−1)^{#{k: s_k = lo_k}} E[Y | do(s)]

which for K=2 collapses to the familiar 2×2 form

        = [E[Y|do(A=1,B=1)] − E[Y|do(A=1,B=0)]]
        − [E[Y|do(A=0,B=1)] − E[Y|do(A=0,B=0)]] .

The outcome model E[Y | A, B, …, Z] is fit INCLUDING the *saturated*
treatment-interaction basis (a product term for every non-empty subset
of the treatments — for K=2 exactly the single A:B term), so the
standardization can recover both the joint contrast and the highest-
order interaction under arbitrary interaction structure among the
treatments. ``LinearRegression`` for continuous outcomes,
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
- Binary treatments. Two to ``_MAX_JOINT_TREATMENTS`` (default 5)
  supported; the saturated basis has 2^K − 1 treatment columns and the
  interaction is a 2^K-corner finite difference, so K is capped to bound
  the design matrix / corner enumeration. Beyond the cap the estimator
  raises ``NotImplementedError`` (the dispatch then leaves the
  structural result untouched — an honest capability gap, never a wrong
  number). The cap is a resource bound, not a fundamental limit.
- Bool or continuous outcome.
- Adjustment set ``adjustment`` enters the outcome regression as linear
  features (same backend / restriction as ``backdoor.py``).

API:

    from themis.estimation.joint import estimate_joint_effect
    est = estimate_joint_effect(
        data, treatments=("a", "b", "c"), outcome="y", adjustment=("z",),
    )
    print(est.joint_point, est.interaction_point)  # interaction is K-way
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product
from typing import Literal

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression, LogisticRegression

from .contract import validate_data
from .dose_response import EstimatorFailure
from .resample import cluster_labels, resample_indices


ModelName = Literal["auto", "linear", "logistic"]

# Resource bound on the joint estimator: the saturated treatment basis is
# 2^K − 1 columns and the K-way interaction is a 2^K-corner finite
# difference. Cap K so neither blows up. Not a fundamental limit — the
# identification (``minimal_adjustment_sets_joint``) has no such cap; this
# only bounds the numeric plug-in. Beyond it: honest NotImplementedError.
_MAX_JOINT_TREATMENTS = 5


@dataclass(frozen=True)
class JointEffectEstimate:
    """Result of a joint-intervention g-formula estimate.

    - ``joint_*``: point + CI for the joint contrast
      E[Y|do(A=a,B=b)] − E[Y|do(A=a',B=b')].
    - ``interaction_*``: point + CI for the additive-scale highest-order
      (K-way) treatment interaction — the K-th mixed finite difference
      over the 2^K treatment corners. For K=2 this is the ordinary
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
    treatments: ordered tuple of 2..``_MAX_JOINT_TREATMENTS`` binary
        treatment column names (A, B, …).
    outcome: outcome column name (bool or continuous).
    adjustment: adjustment-set column names (may be empty).
    treated_values / control_values: {name: value} for the treated and
        control cells of the joint contrast. Default treated = all-True,
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
    if len(treatments) < 2:
        raise NotImplementedError(
            f"estimate_joint_effect needs at least two treatments to form a "
            f"joint intervention; got {len(treatments)} ({treatments!r})"
        )
    if len(treatments) > _MAX_JOINT_TREATMENTS:
        raise NotImplementedError(
            f"estimate_joint_effect caps at {_MAX_JOINT_TREATMENTS} "
            f"treatments (the saturated basis is 2^K − 1 columns and the "
            f"interaction is a 2^K-corner finite difference); got "
            f"{len(treatments)} ({treatments!r})"
        )
    if len(set(treatments)) != len(treatments):
        raise ValueError(
            f"joint treatment vector repeats a column: {treatments!r}"
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

    treated_values = treated_values or {t: True for t in treatments}
    control_values = control_values or {t: False for t in treatments}

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

    K = len(treatments)
    hi = tuple(float(treated_values[t]) for t in treatments)
    lo = tuple(float(control_values[t]) for t in treatments)

    def _joint_and_interaction(sample: pd.DataFrame) -> tuple[float, float]:
        predict = _fit(sample, treatments, outcome, adjustment, resolved)
        # Standardized counterfactual mean at each of the 2^K treatment
        # corners (g-formula plug-in), averaged over the sample's empirical
        # Z distribution. A corner is a per-treatment choice of hi / lo.
        # ``mask`` marks which treatments are at their hi level.
        corner_mean: dict[tuple[bool, ...], float] = {}
        for mask in product((True, False), repeat=K):
            cell = tuple(hi[k] if mask[k] else lo[k] for k in range(K))
            corner_mean[mask] = float(np.mean(predict(sample, cell)))
        all_hi = (True,) * K
        all_lo = (False,) * K
        # Joint contrast between the requested treated (all-hi) and control
        # (all-lo) cells.
        joint = corner_mean[all_hi] - corner_mean[all_lo]
        # Highest-order (K-way) interaction: the K-th mixed finite
        # difference — the alternating-sign sum over all 2^K corners, with
        # sign (−1)^{#treatments at lo}. For K=2 this is exactly
        # (m11 − m10) − (m01 − m00); the sum annihilates every lower-order
        # term (main effects, pairwise …) and the Z contribution, isolating
        # the top-order interaction.
        interaction = 0.0
        for mask, val in corner_mean.items():
            n_lo = mask.count(False)
            interaction += (-1.0 if n_lo % 2 else 1.0) * val
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


def _treatment_subsets(k: int) -> tuple[tuple[int, ...], ...]:
    """All non-empty subsets of ``range(k)`` as index tuples, ordered by
    size then lexicographically — the columns of the saturated treatment
    basis. For k=2: ((0,), (1,), (0, 1)) ⇒ [A, B, A·B]."""
    subsets: list[tuple[int, ...]] = []
    for size in range(1, k + 1):
        subsets.extend(combinations(range(k), size))
    return tuple(subsets)


def _fit(
    df: pd.DataFrame,
    treatments: tuple[str, ...],
    outcome: str,
    adjustment: tuple[str, ...],
    model: str,
):
    """Fit E[Y | (saturated treatment basis), Z] and return a callable
    ``predict(sample, cell) -> yhat`` that standardizes the counterfactual
    treatment cell over the sample's adjustment values.

    The treatment block is fully saturated: one product column for every
    non-empty subset of the treatments (main effects + all interactions).
    For two treatments this is exactly [A, B, A·B] — byte-identical to the
    original two-treatment fit."""
    subsets = _treatment_subsets(len(treatments))
    T = np.column_stack([df[t].to_numpy(dtype=float) for t in treatments])

    def _basis(Tmat: np.ndarray) -> np.ndarray:
        # np.prod over the subset's columns; a singleton subset reproduces
        # the raw main-effect column.
        return np.column_stack(
            [np.prod(Tmat[:, list(s)], axis=1) for s in subsets]
        )

    if adjustment:
        z = df[list(adjustment)].to_numpy(dtype=float)
        X = np.column_stack([_basis(T), z])
    else:
        X = _basis(T)
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

    def predict(sample: pd.DataFrame, cell: tuple[float, ...]):
        n = len(sample)
        Tc = np.column_stack([np.full(n, v) for v in cell])
        if adjustment:
            z = sample[list(adjustment)].to_numpy(dtype=float)
            M = np.column_stack([_basis(Tc), z])
        else:
            M = _basis(Tc)
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
        common = common + (
            "linear_outcome_regression_with_saturated_treatment_interactions",
        )
    elif model == "logistic":
        common = common + (
            "logit_outcome_regression_with_saturated_treatment_interactions",
        )
    if n_adj == 0:
        common = common + (
            "unconditional_exchangeability_treatments_marginally_randomized",
        )
    return common
