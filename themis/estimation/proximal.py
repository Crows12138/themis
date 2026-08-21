"""Proximal causal inference — numeric estimation (Miao-Geng-Tchetgen 2018,
discrete model (f) identifying formula (5)).

Once :func:`themis.runtime.proximal_identify.identify_proximal` certifies that
the unobserved confounder ``U`` admits a valid treatment proxy ``Z`` and outcome
proxy ``W`` (model (f)), the average causal effect is — in the fully discrete
regime — a closed-form matrix functional of the observed law:

    P(y | do(x)) = P(y | Z, x) · P(W | Z, x)^{-1} · P(W)                    (5)

with, for a fixed ordering of the ``k`` levels of ``Z`` and ``W``,

    M[i, j] = P(W = w_i | Z = z_j, X = x)     (k×k contingency, rows W, cols Z)
    py[j]   = P(Y = y* | Z = z_j, X = x)      (row over Z)
    pw[i]   = P(W = w_i)                       (marginal over W)
    point   = py @ M^{-1} @ pw

Unlike every other Themis estimator this is NOT an ``estimate_formula`` walk over
a symbolic AST — proximal identification produces a matrix operation, not a
do-calculus formula. The empirical conditionals filling M / py / pw are ordinary
count ratios over discrete strata (the same saturated non-parametric plug-in
spirit as the general-ID / counterfactual estimators), but the identifying step
is a linear solve (``numpy.linalg``).

Scope (declared):

- DISCRETE variables only, and this ATE entry takes BINARY treatment / outcome:
  the contrast is E[Y=1 | do(X=1)] − E[Y=1 | do(X=0)]. The proxies Z, W may be
  k-ary but MUST each present exactly ``k`` observed levels (k = the assumed
  cardinality of U). Coarsening a finer proxy down to k levels (Miao §2, end) is
  deferred — a proxy whose observed level count ≠ k raises rather than guessing a
  coarsening.
- The RANK condition — M = P(W|Z,x) invertible for every x — is the numeric heart
  of proximal identification and is CHECKED here (ill-conditioned ⇒ refuse). A
  singular M means the proxies are not jointly relevant enough to U to restore the
  effect; that is an ``EstimatorFailure``, never a fabricated number.
- An empty (Z=z, X=x) stratum is a positivity violation ⇒ ``EstimatorFailure``.
- Continuous U (the Fredholm integral / bridge-function regime, Miao §3) is out
  of scope; it needs a two-stage / minimax bridge solver Themis does not have.

Reference: Miao, Geng & Tchetgen Tchetgen 2018 (Biometrika 105(4), formula 5);
Kuroki & Pearl 2014 (Biometrika 101(2)) as the independent effect-restoration
source.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..runtime.proximal_identify import ProximalNotIdentified, identify_proximal
from .contract import validate_data
from .. import refusals
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from .resample import cluster_labels, resample_indices

# A conditioning matrix this ill-conditioned means the proxies carry too little
# independent information about U to invert the measurement channel — the rank
# condition has effectively failed even if M is not exactly singular.
_MAX_CONDITION_NUMBER = 1e10


@dataclass(frozen=True)
class ProximalEstimate:
    """Result of a proximal ATE estimate via Miao's discrete formula (5)."""

    point: float                       # E[Y=1|do(X=1)] − E[Y=1|do(X=0)]
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                        # "proximal_matrix"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    treatment: str
    outcome: str
    treatment_proxy: str               # Z
    outcome_proxy: str                 # W
    latent_cardinality: int            # assumed k
    do_prob_treated: float             # P(Y=1|do(X=1))
    do_prob_control: float             # P(Y=1|do(X=0))
    model_assumption: str = ""
    form: str = "nonparametric_matrix_plug_in"
    cluster: str | None = None


def estimate_proximal_ate(
    data: pd.DataFrame,
    *,
    graph,
    bidirected=frozenset(),
    treatment,
    outcome,
    latent,
    treatment_proxy,
    outcome_proxy,
    latent_cardinality: int,
    outcome_success=True,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> ProximalEstimate:
    """Plug-in of Miao's proximal formula (5) for a binary-treatment ATE.

    Parameters mirror :func:`identify_proximal`; ``data`` must carry a column per
    observed variable named by each atom's ``predicate`` (the latent ``U`` has no
    column). ``outcome_success`` is the outcome level the P(Y=y*) contrast is
    taken on (default ``True``).

    Raises
    ------
    EstimatorFailure: not proximal-identifiable, a proxy's observed level count
        ≠ k, the rank condition fails (M singular / ill-conditioned), or a
        conditioning stratum is empty (positivity).
    ValueError: the data violates the estimation contract.
    """
    ident = identify_proximal(
        graph, bidirected, treatment=treatment, outcome=outcome, latent=latent,
        treatment_proxy=treatment_proxy, outcome_proxy=outcome_proxy,
        latent_cardinality=latent_cardinality,
    )
    if isinstance(ident, ProximalNotIdentified):
        raise EstimatorFailure(
            Refusal.NOT_IDENTIFIABLE_PROXIMAL,
            criterion=ident.failed_criterion, detail=ident.reason,
        )

    xcol, ycol = treatment.predicate, outcome.predicate
    zcol, wcol = treatment_proxy.predicate, outcome_proxy.predicate
    required = frozenset({xcol, ycol, zcol, wcol})
    presence = (cluster,) if cluster is not None else ()
    groups = (
        cluster_labels(data, cluster, expected_n=len(data))
        if cluster is not None
        else None
    )
    contract = validate_data(
        data, required_columns=required, presence_columns=presence,
    )
    df = contract.data

    z_levels = sorted(df[zcol].unique())
    w_levels = sorted(df[wcol].unique())
    x_levels = sorted(df[xcol].unique())
    if len(z_levels) != latent_cardinality or len(w_levels) != latent_cardinality:
        raise EstimatorFailure(
            Refusal.PROXY_CARDINALITY_MISMATCH,
            k=latent_cardinality, z=len(z_levels), w=len(w_levels),
        )
    if set(x_levels) - {False, True, 0, 1} or len(x_levels) < 2:
        raise EstimatorFailure(
            Refusal.TREATMENT_NOT_BINARY,
            "the proximal ATE entry takes a binary treatment (two observed "
            f"levels); observed X levels = {refusals.describe(x_levels)}.",
        )

    p_treated = _proximal_do_prob(
        df, xcol, ycol, zcol, wcol, x=True,
        z_levels=z_levels, w_levels=w_levels, outcome_success=outcome_success)
    p_control = _proximal_do_prob(
        df, xcol, ycol, zcol, wcol, x=False,
        z_levels=z_levels, w_levels=w_levels, outcome_success=outcome_success)
    point = p_treated - p_control

    ci_lower = ci_upper = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap_ci(
            df, xcol, ycol, zcol, wcol, z_levels=z_levels, w_levels=w_levels,
            outcome_success=outcome_success, ci_bootstrap=ci_bootstrap,
            ci_level=ci_level, random_state=random_state, groups=groups)

    assumptions: tuple[str, ...] = (
        "diagram_correct_including_unobserved_confounder_U_and_proxy_roles",
        "U_sufficient_confounder_and_proxies_satisfy_miao_model_f",
        "latent_cardinality_k_correct_and_proxies_have_exactly_k_levels",
        "rank_condition_P(W|Z,x)_invertible_verified_on_data",
        "positivity_every_conditioning_stratum_has_support",
        "consistency_and_no_interference",
    )
    if cluster is not None:
        assumptions = assumptions + (f"ci_via_pairs_cluster_bootstrap_on_{cluster}",)
    return ProximalEstimate(
        point=float(point),
        ci_lower=float(ci_lower) if ci_lower is not None else None,
        ci_upper=float(ci_upper) if ci_upper is not None else None,
        ci_level=ci_level,
        method="proximal_matrix",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=xcol,
        outcome=ycol,
        treatment_proxy=zcol,
        outcome_proxy=wcol,
        latent_cardinality=latent_cardinality,
        do_prob_treated=float(p_treated),
        do_prob_control=float(p_control),
        model_assumption=(
            "未观测混杂 U 下的近端识别(Miao 2018 formula 5)：P(y|do x)="
            "P(y|Z,x)·P(W|Z,x)⁻¹·P(W)，离散饱和经验矩阵求解，无函数形式假设"
        ),
        form="nonparametric_matrix_plug_in",
        cluster=cluster,
    )


# --- internals ----------------------------------------------------------------


def _proximal_do_prob(
    df: pd.DataFrame, xcol, ycol, zcol, wcol, *, x, z_levels, w_levels,
    outcome_success,
) -> float:
    """Miao formula (5): P(Y=y* | do(X=x)) = py @ M^{-1} @ pw on discrete data.

    M[i,j] = P(W=w_i | Z=z_j, X=x); py[j] = P(Y=y* | Z=z_j, X=x); pw[i] = P(W=w_i).
    Raises ``EstimatorFailure`` on an empty (Z,X) stratum (positivity) or an
    ill-conditioned M (rank condition)."""
    k = len(z_levels)
    sub = df[df[xcol] == x]
    M = np.empty((k, k))
    py = np.empty(k)
    for j, zj in enumerate(z_levels):
        stratum = sub[sub[zcol] == zj]
        n_zx = len(stratum)
        if n_zx == 0:
            raise EstimatorFailure(
                Refusal.INSUFFICIENT_SUPPORT,
                f"empty stratum (Z={refusals.describe(zj)}, "
                f"X={refusals.describe(x)}); proximal formula (5) has no "
                f"P(W|Z={refusals.describe(zj)},X={refusals.describe(x)}) "
                f"to estimate (positivity violation).",
            )
        for i, wi in enumerate(w_levels):
            M[i, j] = (stratum[wcol] == wi).mean()
        py[j] = (stratum[ycol] == outcome_success).mean()
    pw = np.array([(df[wcol] == wi).mean() for wi in w_levels])

    if not np.isfinite(np.linalg.cond(M)) or np.linalg.cond(M) > _MAX_CONDITION_NUMBER:
        raise EstimatorFailure(Refusal.RANK_CONDITION_VIOLATED)
    return float(py @ np.linalg.solve(M, pw))


def _bootstrap_ci(
    df, xcol, ycol, zcol, wcol, *, z_levels, w_levels, outcome_success,
    ci_bootstrap, ci_level, random_state, groups,
) -> tuple[float | None, float | None]:
    """Non-parametric percentile bootstrap of the proximal ATE. Level sets are
    fixed from the full data; a resample that induces an empty stratum or a
    singular M is skipped (the CI is over the draws where (5) is evaluable)."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    estimates: list[float] = []
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        sample = df.iloc[idx]
        try:
            pt = _proximal_do_prob(
                sample, xcol, ycol, zcol, wcol, x=True, z_levels=z_levels,
                w_levels=w_levels, outcome_success=outcome_success)
            pc = _proximal_do_prob(
                sample, xcol, ycol, zcol, wcol, x=False, z_levels=z_levels,
                w_levels=w_levels, outcome_success=outcome_success)
        except EstimatorFailure:
            continue
        estimates.append(pt - pc)
    if len(estimates) < 2:
        return None, None
    arr = np.asarray(estimates)
    alpha = (1 - ci_level) / 2
    return float(np.quantile(arr, alpha)), float(np.quantile(arr, 1 - alpha))
