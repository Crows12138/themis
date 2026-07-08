"""Counterfactual-conjunction numeric evaluator — non-parametric plug-in of a
general counterfactual (Shpitser-Pearl ID*/IDC*) estimand on discrete data.

The identification layer decides whether a counterfactual conjunction

    P(γ)        (unconditional, ID*)   or
    P(γ | δ)    (conditional,   IDC*)

is identifiable and, when it is, hands back the estimand as a ``FormulaExpr``
AST over *observational* conditional probabilities — a nested sum / product /
ratio of ``P(v | v_predecessors)`` terms (:func:`themis.runtime.ctf_identify.
id_star` / :func:`~themis.runtime.ctf_identify.idc_star`). This module turns
that estimand into a NUMBER on data by the SAME non-parametric plug-in the
general-ID (c-factor) evaluator uses:

    every conditional ``P(v | v_predecessors)`` in the formula is the
    empirical conditional from its OWN stratum of the data, and the sums /
    products / ratio the identified formula prescribes are carried out
    exactly.

It reuses :func:`themis.estimation.general_id._prob_do` (empirical Theta +
:func:`themis.runtime.numeric_estimator.estimate_formula`, the SAME walker the
kernel uses) so the number is a plug-in of the *identified* formula, never an
independent re-derivation. The conditional (IDC*) estimand is a
``FractionExpr`` ``P(γ',δ')/P(δ')`` — the ratio is evaluated natively by the
formula walker. Confidence intervals are a non-parametric percentile
bootstrap.

Scope (declared):

- DISCRETE variables only (the saturated non-parametric plug-in has no
  empirical stratum for a continuous covariate).
- A single conjunction probability, NOT an ATE contrast — the counterfactual
  events already carry their own concrete values, so there is no treatment /
  outcome contrast to bind (unlike the general-ID ATE).
- ``FAIL`` (non-identifiable) and ``UNDEFINED`` (``P(δ)=0``) raise
  ``EstimatorFailure`` rather than fabricating a number; ``ZERO`` (an
  inconsistent conjunction) is the exact data-independent point ``0``.
- An empty conditioning stratum is a positivity violation and raises
  ``EstimatorFailure`` (inherited from ``_empirical_conditional``). Because
  the identified formula can condition on a long predecessor sequence, the
  strata can be sparse — the plug-in is unbiased but higher-variance; the
  bootstrap CI reflects that honestly.

Reference: Shpitser & Pearl 2007 (ID*) / 2008 (IDC*, JMLR 9:1941-1979);
Hernán & Robins 2020 ch.13 for the plug-in (g-formula) principle in the
non-parametric limit.

API::

    from themis.estimation.ctf_conjunction import estimate_ctf_conjunction_prob
    est = estimate_ctf_conjunction_prob(
        data, graph=g, bidirected=bi, gamma=gamma, delta=delta,
    )
    print(est.point, est.ci_lower, est.ci_upper)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..types import ConstantExpr, FormulaExpr
from .contract import validate_data
from .dose_response import EstimatorFailure
from .general_id import (
    _domains_from_data,
    _prob_do,
    _referenced_predicates,
)
from .resample import cluster_labels, resample_indices


@dataclass(frozen=True)
class CtfConjunctionEstimate:
    """Result of a counterfactual-conjunction (ID*/IDC* plug-in) estimate."""

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                       # "ctf_conjunction_plugin"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    # Whether δ was present (IDC*, a conditional P(γ|δ)) or empty (ID*, an
    # unconditional P(γ)); and a human-readable rendering of the estimand.
    conditional: bool
    estimand: str
    # Mechanism + structured identification assumptions (assumption-ledger
    # parity with the general-ID / back-door estimators).
    model_assumption: str = ""
    form: str = "nonparametric_plug_in"
    identification_assumptions: tuple[dict, ...] = ()
    # Variance concern, not a model node: whole-cluster bootstrap when set.
    cluster: str | None = None


def estimate_ctf_conjunction_prob(
    data: pd.DataFrame,
    *,
    graph,
    bidirected,
    gamma,
    delta=(),
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> CtfConjunctionEstimate:
    """Plug-in point of an ID*/IDC*-identified counterfactual conjunction.

    Parameters
    ----------
    data: DataFrame with a column per observed variable (named by each
        atom's ``predicate``).
    graph / bidirected: the projected ADMG (same objects the kernel
        identified on).
    gamma: the counterfactual conjunction γ — a tuple of
        :class:`themis.runtime.ctf_identify.CtfEvent`.
    delta: the optional conditioning conjunction δ (empty = unconditional
        ID*; non-empty = conditional IDC*).
    ci_bootstrap: number of bootstrap resamples; 0 skips the CI.
    ci_level: two-sided confidence level.
    random_state: deterministic seed.
    cluster: optional cluster-id column for a pairs cluster bootstrap.

    Raises
    ------
    EstimatorFailure: the conjunction is not identifiable (``FAIL``), the
        conditioning event has probability 0 (``UNDEFINED``), or the data
        cannot support the estimand (positivity — an empty stratum).
    DataContractError (ValueError): the data violates the estimation
        contract (missing column, NaN, or too-small sample).
    """
    from ..runtime.ctf_identify import FAIL, UNDEFINED, ZERO, id_star, idc_star

    conditional = bool(delta)
    outcome = (
        idc_star(graph, bidirected, gamma, delta)
        if conditional
        else id_star(graph, bidirected, gamma)
    )
    if outcome is FAIL:
        raise EstimatorFailure(
            "not_identifiable_counterfactual",
            "P(γ|δ) is not identifiable by the ID*/IDC* algorithm on this "
            "ADMG — there is no observational estimand to evaluate.",
        )
    if outcome is UNDEFINED:
        raise EstimatorFailure(
            "undefined_conditioning_event",
            "the conditioning conjunction δ has probability 0, so the "
            "conditional P(γ|δ) is undefined; no number can be produced.",
        )
    is_zero = outcome is ZERO
    formula: FormulaExpr = ConstantExpr(value=0.0) if is_zero else outcome

    # Required columns = the observed variables the estimand references,
    # union the query's own event / subscript atoms (so a ZERO estimand,
    # whose formula references nothing, still contracts on its variables).
    event_preds = {e.variable.predicate for e in (*gamma, *delta)} | {
        a.predicate for e in (*gamma, *delta) for (a, _v) in e.subscript
    }
    required = _referenced_predicates(formula) | event_preds
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
    domains = _domains_from_data(graph, df)
    estimand = _render_estimand(gamma, delta)

    ci_lower: float | None = None
    ci_upper: float | None = None
    if is_zero:
        # P(γ|δ)=0 is the exact data-independent point (an inconsistent
        # conjunction); no stratum to estimate, no CI.
        point = 0.0
    else:
        point = _prob_do(formula, df, domains)
        if ci_bootstrap > 0:
            ci_lower, ci_upper = _bootstrap_ci_single(
                df, formula, domains,
                ci_bootstrap=ci_bootstrap, ci_level=ci_level,
                random_state=random_state, groups=groups,
            )

    assumptions = (
        "admg_structure_correct_including_latent_confounders",
        "positivity_every_conditioning_stratum_has_support",
        "consistency_of_potential_outcomes",
        "discrete_variables_saturated_nonparametric_plug_in",
    )
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )
    identification_assumptions = (
        {"claim": "ADMG 结构正确：所有有向边与潜混杂 (↔) 边如实建模",
         "layer": "identification", "severity": "invalidating", "testable": False},
        {"claim": "positivity：反事实识别公式条件到的每个前驱层在数据中都有样本",
         "layer": "identification", "severity": "invalidating", "testable": True},
        {"claim": "一致性：反事实世界定义明确，potential outcomes 良定义",
         "layer": "identification", "severity": "invalidating", "testable": False},
    )
    return CtfConjunctionEstimate(
        point=float(point),
        ci_lower=float(ci_lower) if ci_lower is not None else None,
        ci_upper=float(ci_upper) if ci_upper is not None else None,
        ci_level=ci_level,
        method="ctf_conjunction_plugin",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        conditional=conditional,
        estimand=estimand,
        model_assumption=(
            "反事实识别公式(ID*/IDC*)按非参数 plug-in 求值：每个观察条件概率"
            "用其所属数据层的经验频率，无函数形式假设（饱和估计）"
        ),
        form="nonparametric_plug_in",
        identification_assumptions=identification_assumptions,
        cluster=cluster,
    )


# --- internals ----------------------------------------------------------------


def _render_estimand(gamma, delta) -> str:
    """A compact, human-readable rendering of P(γ) or P(γ|δ) for the audit
    trail (e.g. ``P(y_{x=True}=True | x=False)``)."""

    def one(e) -> str:
        if e.subscript:
            sub = "_{" + ",".join(
                f"{a.predicate}={v}"
                for a, v in sorted(e.subscript, key=lambda p: p[0].predicate)
            ) + "}"
        else:
            sub = ""
        return f"{e.variable.predicate}{sub}={e.value}"

    g = " ∧ ".join(one(e) for e in gamma)
    if delta:
        d = " ∧ ".join(one(e) for e in delta)
        return f"P({g} | {d})"
    return f"P({g})"


def _bootstrap_ci_single(
    df: pd.DataFrame,
    formula: FormulaExpr,
    domains: dict,
    *,
    ci_bootstrap: int,
    ci_level: float,
    random_state: int,
    groups: np.ndarray | None = None,
) -> tuple[float | None, float | None]:
    """Non-parametric percentile bootstrap for a single identified
    probability. The identified formula is fixed (data-independent); each
    resample re-estimates the empirical Theta on the FULL-data domains and
    re-evaluates. A resample that induces an empty stratum (positivity
    failure on that draw) is skipped — the CI is over the draws where the
    estimand is evaluable."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    estimates: list[float] = []
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        sample = df.iloc[idx]
        try:
            estimates.append(_prob_do(formula, sample, domains))
        except EstimatorFailure:
            continue
    if len(estimates) < 2:
        return None, None
    arr = np.asarray(estimates)
    alpha = (1 - ci_level) / 2
    return float(np.quantile(arr, alpha)), float(np.quantile(arr, 1 - alpha))
