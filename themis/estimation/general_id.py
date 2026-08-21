"""General-identification numeric evaluator — non-parametric plug-in of a
point-identified c-factor (Tian–Shpitser ID) estimand on discrete data.

When an effect ``P(Y | do(X))`` is identified ONLY through the general ID
algorithm's c-component factorisation — not by a back-door adjustment, a
front-door set, or an instrument — the identified estimand is a nested
sum / product / ratio of *observational* conditional probabilities (the
Tian–Pearl c-factor form). Pearl's napkin graph (W→Z→X→Y, W↔X, W↔Y) is
the canonical example: no observed set blocks the back-door paths, yet the
effect is non-parametrically identified as a ratio.

The identification layer already derives that estimand as a ``FormulaExpr``
AST (:func:`themis.runtime.c_factor.identify_via_tian`). This module turns
it into a NUMBER on data by the non-parametric plug-in:

    every conditional  P(v | v_predecessors)  in the formula is the
    empirical conditional from its OWN stratum of the data, and the
    sums / products / ratio the identified formula prescribes are carried
    out exactly.

    ATE = P(Y=y_hi | do(X=x_hi)) − P(Y=y_hi | do(X=x_lo))

where ``x_lo < x_hi`` are the two observed treatment levels and ``y_hi`` is
the high outcome level. The evaluator reuses
:func:`themis.runtime.numeric_estimator.estimate_formula` — the SAME
formula walker the kernel uses for theta-supplied evaluation — so the
number is a plug-in of the *identified* formula, never an independent
re-derivation. Confidence intervals are a non-parametric percentile
bootstrap.

Scope (declared):

- DISCRETE variables only. The plug-in is the *saturated* non-parametric
  estimator over empirical conditional probabilities; a continuous
  covariate has no empirical stratum. The back-door / front-door
  regression estimators cover the continuous cases they can — this
  estimator is the catch-all for the genuinely-nested discrete estimands
  none of them reach.
- Binary treatment, binary outcome (the ATE contrast is on the high
  outcome level). Multi-level / E[Y] contrasts are a future extension.
- Unconditional effect (``estimate_general_id_ate``) AND conditional
  ``P(Y | do(X), Z=z)`` (``estimate_general_id_conditional_ate``, identified
  via Shpitser–Pearl IDC — the Rule-2 exchange + ratio normalization). The
  conditional path is a two-do-level contrast taken WITHIN the queried
  ``Z=z`` stratum; the plug-in machinery is shared.
- An empty conditioning stratum is a positivity violation and raises
  ``EstimatorFailure`` rather than fabricating a value. Because the
  c-factor form can condition on a long predecessor sequence, the strata
  can be sparse — the plug-in is unbiased but higher-variance than a
  parametric fit; the bootstrap CI reflects that honestly.

Reference: Tian & Pearl 2002 (general ID / c-factor); Shpitser & Pearl
2006 (ID completeness). Hernán & Robins 2020 ch.13 for the plug-in
(g-formula) principle in the non-parametric limit.

API::

    from themis.estimation.general_id import estimate_general_id_ate
    est = estimate_general_id_ate(
        data, graph=g, bidirected=bi,
        treatment_atom=x, outcome_atom=y,
    )
    print(est.point, est.ci_lower, est.ci_upper)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..types import (
    Atom,
    ConstantExpr,
    FormulaExpr,
    FractionExpr,
    ProbabilityRefExpr,
    ProductExpr,
    SumExpr,
    ValuedAtom,
    envelope_scalar,
)
from ..runtime.numeric_estimator import (
    ProbabilityKey,
    Theta,
    VEIntractable,
    referenced_keys,
    ve_estimate_formula,
)
from .contract import validate_data
from .. import refusals
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from .resample import cluster_labels, resample_indices


@dataclass(frozen=True)
class GeneralIdEstimate:
    """Result of a general-ID (c-factor plug-in) ATE estimate."""

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                       # "general_id_plugin"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    treatment: str
    outcome: str
    # Joint general-ID only: the full treatment vector do(A,B,...) the
    # contrast intervenes on simultaneously. Empty for the single-treatment
    # estimate (whose one treatment is in ``treatment``).
    treatments: tuple[str, ...] = ()
    # The two contrasted treatment levels and the outcome level the
    # contrast is taken on — makes the ATE definition explicit in the
    # audit trail (do(X=x_hi) vs do(X=x_lo), outcome = y_hi).
    treatment_high: object = None
    treatment_low: object = None
    outcome_high: object = None
    # Conditional (IDC) estimate only: the Z=z stratum the contrast is
    # taken WITHIN — a tuple of (predicate, value) pairs. Empty for the
    # unconditional effect. Makes P(Y | do(X), Z=z) explicit in the trail.
    given: tuple = ()
    # Mechanism + structured identification assumptions (assumption-ledger
    # parity with the back-door / dose-response estimators).
    model_assumption: str = ""
    form: str = "nonparametric_plug_in"
    # Variance concern, not a model node: whole-cluster bootstrap when set.
    cluster: str | None = None


def estimate_general_id_ate(
    data: pd.DataFrame,
    *,
    graph,
    bidirected,
    treatment_atom: Atom,
    outcome_atom: Atom,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> GeneralIdEstimate:
    """Plug-in ATE for a general-ID (c-factor) identified effect.

    Parameters
    ----------
    data: DataFrame with a column per observed variable (named by each
        atom's ``predicate``).
    graph: the projected directed graph (networkx ``DiGraph``) of the
        ADMG — same object the kernel identified on.
    bidirected: the ``BidirectedEdgeSet`` (latent-confounding edges).
    treatment_atom / outcome_atom: the intervention / target atoms; must
        be graph nodes with a matching data column.
    ci_bootstrap: number of bootstrap resamples; 0 skips the CI.
    ci_level: two-sided confidence level.
    random_state: deterministic seed.
    cluster: optional cluster-id column for a pairs cluster bootstrap
        (matches the back-door estimator's variance handling). Not part of
        the causal model; excluded from the design and the data hash.

    Raises
    ------
    EstimatorFailure: treatment / outcome not binary, effect not
        identifiable by the general ID algorithm, or insufficient support
        (an empty conditioning stratum — positivity).
    DataContractError (ValueError): the data violates the estimation
        contract (missing column, NaN, or too-small sample).
    """
    from ..runtime import c_factor

    t_col = treatment_atom.predicate
    y_col = outcome_atom.predicate
    if t_col not in data.columns:
        raise EstimatorFailure(
            Refusal.MISSING_COLUMN,
            f"treatment column {t_col!r} not present in the data",
            treatment=t_col,
        )
    if y_col not in data.columns:
        raise EstimatorFailure(
            Refusal.MISSING_COLUMN,
            f"outcome column {y_col!r} not present in the data",
            outcome=y_col,
        )

    # Binary treatment / outcome — the ATE contrast is the two-level
    # difference on the high outcome level.
    t_levels = _sorted_levels(data[t_col])
    if len(t_levels) != 2:
        raise EstimatorFailure(
            Refusal.TREATMENT_NOT_BINARY,
            f"treatment {t_col!r} has {len(t_levels)} observed levels "
            f"({refusals.describe(t_levels)}); the general-ID plug-in "
            f"ATE is a two-level "
            f"contrast. Supply a binary treatment.",
            treatment=t_col,
        )
    y_levels = _sorted_levels(data[y_col])
    if len(y_levels) != 2:
        raise EstimatorFailure(
            Refusal.OUTCOME_NOT_BINARY,
            f"outcome {y_col!r} has {len(y_levels)} observed levels "
            f"({refusals.describe(y_levels)}); v1 of the general-ID "
            f"plug-in ATE requires a "
            f"binary outcome.",
            outcome=y_col,
        )
    x_lo, x_hi = t_levels[0], t_levels[1]
    y_hi = y_levels[-1]

    # Identify the estimand once per do-level (data-independent). The
    # structure is identical; only the do-literal baked into the outer X
    # slot differs.
    res_hi = c_factor.identify_via_tian(
        graph, bidirected, treatment_atom, outcome_atom, x_hi)
    res_lo = c_factor.identify_via_tian(
        graph, bidirected, treatment_atom, outcome_atom, x_lo)
    if not (res_hi.identifiable and res_lo.identifiable
            and res_hi.formula is not None and res_lo.formula is not None):
        raise EstimatorFailure(
            Refusal.NOT_IDENTIFIABLE_BY_GENERAL_ID,
            treatment=t_col,
            outcome=y_col,
        )
    f_hi = _bind_target_value(res_hi.formula, outcome_atom, y_hi)
    f_lo = _bind_target_value(res_lo.formula, outcome_atom, y_hi)

    # Contract validation (no NaN, canonical hash). Required columns are
    # exactly the observed variables the estimand references.
    required = (
        referenced_predicates(f_hi)
        | referenced_predicates(f_lo)
        | {t_col, y_col}
    )
    presence = (cluster,) if cluster is not None else ()
    groups = (
        cluster_labels(data, cluster, expected_n=len(data))
        if cluster is not None
        else None
    )
    # validate_data enforces the no-NaN contract, the canonical hash, and
    # the shared minimum-sample-size floor (raises DataContractError, a
    # ValueError, on a too-small frame).
    contract = validate_data(
        data, required_columns=required, presence_columns=presence,
    )
    df = contract.data

    domains = _domains_from_data(graph, df)
    point = _point_ate(df, f_hi, f_lo, domains)

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap_ci(
            df, f_hi, f_lo, domains,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level,
            random_state=random_state, groups=groups,
        )

    assumptions: tuple[str, ...] = (
        "admg_structure_correct_including_latent_confounders",
        "positivity_every_conditioning_stratum_has_support",
        "consistency_of_potential_outcomes",
        "discrete_variables_saturated_nonparametric_plug_in",
    )
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )
    return GeneralIdEstimate(
        point=float(point),
        ci_lower=float(ci_lower) if ci_lower is not None else None,
        ci_upper=float(ci_upper) if ci_upper is not None else None,
        ci_level=ci_level,
        method="general_id_plugin",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=t_col,
        outcome=y_col,
        treatment_high=envelope_scalar(x_hi),
        treatment_low=envelope_scalar(x_lo),
        outcome_high=envelope_scalar(y_hi),
        model_assumption=(
            "识别公式按非参数 plug-in 求值：每个条件概率用其所属数据层的"
            "经验频率，无函数形式假设（饱和估计）"
        ),
        form="nonparametric_plug_in",
        cluster=cluster,
    )


def estimate_general_id_conditional_ate(
    data: pd.DataFrame,
    *,
    graph,
    bidirected,
    treatment_atom: Atom,
    outcome_atom: Atom,
    given: tuple,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> GeneralIdEstimate:
    """Plug-in CONDITIONAL ATE for a general-ID effect identified via IDC.

    The conditional interventional distribution ``P(Y | do(X), Z=z)`` is
    identified by Shpitser–Pearl IDC (:func:`themis.runtime.c_factor.
    identify_via_idc`): a Rule-2 exchange moves every exchangeable ``Z``
    into the do-set, and the survivors normalize the estimand into the
    ratio ``ID(Y ∪ Z_rem, X') / ID(Z_rem, X')`` (a ``FractionExpr``; the
    bare numerator when every conditioned ``Z`` exchanges away). This turns
    that identified estimand into a number on data by the SAME
    non-parametric plug-in the unconditional path uses — the contrast is
    taken WITHIN the queried ``Z=z`` stratum::

        ATE(z) = P(Y=y_hi | do(X=x_hi), Z=z) − P(Y=y_hi | do(X=x_lo), Z=z)

    mirroring :func:`estimate_general_id_ate` exactly, with the conditioning
    ``Z=z`` bound into both do-levels. Every ``P(v | v_predecessors)`` in
    each identified formula is the empirical conditional from its own data
    stratum, and the sums / products / ratio the formula prescribes are
    carried out by variable elimination (the shared ``_prob_do``); the
    number is a plug-in of the *identified* IDC estimand, never an
    independent re-derivation.

    Parameters mirror :func:`estimate_general_id_ate`, plus:

    given: the conditioning ``Z=z`` — a tuple of ``ValuedAtom`` (the
        query's ``given``). Each atom must be a graph node with a data
        column; each value pins the stratum the contrast is taken within.

    Scope (declared): identical to the unconditional plug-in — DISCRETE
    variables, binary treatment / outcome, an empty conditioning stratum is
    a positivity ``EstimatorFailure``. The verifier depth also mirrors the
    unconditional path: the IDC identifiability is independently re-confirmed
    (``general_id_criterion`` re-runs ``identify_via_idc``), while the plug-in
    arithmetic itself is the shared data-refit ceiling (a metadata audit, not
    re-derived from raw data).

    Raises
    ------
    EstimatorFailure: treatment / outcome not binary, the conditional
        effect not IDC-identifiable on this ADMG, or a positivity failure
        (an empty ``Z=z`` / predecessor stratum).
    DataContractError (ValueError): the data violates the estimation
        contract (missing column, NaN, or too-small sample).
    """
    from ..runtime import c_factor

    t_col = treatment_atom.predicate
    y_col = outcome_atom.predicate
    if t_col not in data.columns:
        raise EstimatorFailure(
            Refusal.MISSING_COLUMN,
            f"treatment column {t_col!r} not present in the data",
            treatment=t_col,
        )
    if y_col not in data.columns:
        raise EstimatorFailure(
            Refusal.MISSING_COLUMN,
            f"outcome column {y_col!r} not present in the data",
            outcome=y_col,
        )

    t_levels = _sorted_levels(data[t_col])
    if len(t_levels) != 2:
        raise EstimatorFailure(
            Refusal.TREATMENT_NOT_BINARY,
            f"treatment {t_col!r} has {len(t_levels)} observed levels "
            f"({refusals.describe(t_levels)}); the general-ID plug-in "
            f"ATE is a two-level "
            f"contrast. Supply a binary treatment.",
            treatment=t_col,
        )
    y_levels = _sorted_levels(data[y_col])
    if len(y_levels) != 2:
        raise EstimatorFailure(
            Refusal.OUTCOME_NOT_BINARY,
            f"outcome {y_col!r} has {len(y_levels)} observed levels "
            f"({refusals.describe(y_levels)}); v1 of the general-ID "
            f"plug-in ATE requires a "
            f"binary outcome.",
            outcome=y_col,
        )
    x_lo, x_hi = t_levels[0], t_levels[1]
    y_hi = y_levels[-1]

    given_atoms = tuple(va.atom for va in given)

    # Identify P(Y | do(X'), Z=z) via IDC once per do-level (the exchange
    # and the fraction structure are value-independent; only the do-literal
    # baked into the outer X slot differs).
    idc_hi = c_factor.identify_via_idc(
        graph, bidirected, treatment_atom, outcome_atom, given_atoms, x_hi)
    idc_lo = c_factor.identify_via_idc(
        graph, bidirected, treatment_atom, outcome_atom, given_atoms, x_lo)
    if not (idc_hi.identifiable and idc_lo.identifiable
            and idc_hi.formula is not None and idc_lo.formula is not None):
        raise EstimatorFailure(
            Refusal.NOT_IDENTIFIABLE_BY_IDC,
            given=[a.predicate for a in given_atoms],
            treatment=t_col,
            outcome=y_col,
        )

    # Bind Y to the contrast level and every conditioned Z to its queried
    # value — reaches BOTH target and given positions (an exchanged Z sits
    # on the do-context side; a surviving Z_rem is a numerator target AND a
    # chain-rule conditioning atom). Same binder the theta path proved to
    # 1e-9 in ``test_idc_conditional_effect``.
    value_map: dict = {outcome_atom: y_hi}
    for va in given:
        value_map[va.atom] = envelope_scalar(va.value)
    f_hi = c_factor.bind_idc_values(idc_hi.formula, value_map)
    f_lo = c_factor.bind_idc_values(idc_lo.formula, value_map)

    required = (
        referenced_predicates(f_hi)
        | referenced_predicates(f_lo)
        | {t_col, y_col}
        | {a.predicate for a in given_atoms}
    )
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
    point = _point_ate(df, f_hi, f_lo, domains)

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap_ci(
            df, f_hi, f_lo, domains,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level,
            random_state=random_state, groups=groups,
        )

    assumptions: tuple[str, ...] = (
        "admg_structure_correct_including_latent_confounders",
        "positivity_every_conditioning_stratum_has_support",
        "consistency_of_potential_outcomes",
        "discrete_variables_saturated_nonparametric_plug_in",
        "conditional_effect_identified_via_idc_rule2_exchange",
    )
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )
    return GeneralIdEstimate(
        point=float(point),
        ci_lower=float(ci_lower) if ci_lower is not None else None,
        ci_upper=float(ci_upper) if ci_upper is not None else None,
        ci_level=ci_level,
        method="general_id_idc_plugin",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=t_col,
        outcome=y_col,
        treatment_high=envelope_scalar(x_hi),
        treatment_low=envelope_scalar(x_lo),
        outcome_high=envelope_scalar(y_hi),
        given=tuple(
            (va.atom.predicate, envelope_scalar(va.value))
            for va in given
        ),
        model_assumption=(
            "条件效应 P(Y | do(X), Z=z) 经 IDC（Rule-2 交换 + 归一化为 "
            "ID(Y∪Z_rem, X')/ID(Z_rem, X') 之比）识别，再按非参数 plug-in "
            "在 Z=z 分层内求两 do-臂之差；每个条件概率用其所属数据层的经验"
            "频率，无函数形式假设（饱和估计）"
        ),
        form="nonparametric_plug_in",
        cluster=cluster,
    )


def estimate_joint_general_id_ate(
    data: pd.DataFrame,
    *,
    graph,
    bidirected,
    treatment_atoms: tuple[Atom, ...],
    outcome_atom: Atom,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> GeneralIdEstimate:
    """Plug-in JOINT contrast for a general-ID (c-factor) identified
    effect of a SET of treatments do(A, B, …).

    The joint interventional distribution ``P(Y | do(A, B, …))`` is
    identified by the set-valued Shpitser–Pearl ID
    (:func:`themis.runtime.c_factor.identify_via_tian_joint`) — the escape
    layer that fires when the joint effect is confounded by latent common
    causes so no ADMG adjustment set exists (front-door / c-component for
    sets), yet the effect is still non-parametrically point-identified.
    The identified estimand is turned into a number by the SAME plug-in
    the single-treatment general-ID path uses; the reported point is the
    joint CONTRAST between the all-hi and all-lo treatment corners::

        joint = P(Y=y_hi | do(A=hi, B=hi, …)) − P(Y=y_hi | do(A=lo, B=lo, …))

    Each corner is uniform (every treatment at the same level), so the
    single-value threading of ``identify_via_tian_joint`` applies directly.

    v1 scope (declared): binary treatments that share one common two-level
    set (the uniform corner value must be well-defined); binary outcome;
    the CONTRAST only — the K-way interaction (which needs mixed corners /
    per-atom value binding) and asymmetric contrasts do(A=1, B=0) are out
    of scope; compact-shortcut-expressible estimands only (napkin-style
    joint nested-ID PUNTs to not-identifiable → the caller refuses).

    Raises
    ------
    EstimatorFailure: a treatment / the outcome is non-binary, the
        treatments do not share one common two-level set, the joint effect
        is not point-identified by the set ID algorithm, or a positivity
        violation (empty conditioning stratum).
    DataContractError (ValueError): missing column, NaN, or too-small
        sample.
    """
    from ..runtime import c_factor

    if len(treatment_atoms) < 2:
        raise EstimatorFailure(
            Refusal.NOT_A_JOINT_INTERVENTION, count=len(treatment_atoms),
            treatments=[t.predicate for t in treatment_atoms],
        )
    t_cols = tuple(t.predicate for t in treatment_atoms)
    y_col = outcome_atom.predicate
    for t_col in t_cols:
        if t_col not in data.columns:
            raise EstimatorFailure(
                Refusal.MISSING_COLUMN,
                f"treatment column {t_col!r} not present in the data",
                treatment=t_col,
            )
    if y_col not in data.columns:
        raise EstimatorFailure(
            Refusal.MISSING_COLUMN,
            f"outcome column {y_col!r} not present in the data",
            outcome=y_col,
        )

    # Every treatment must be binary AND share one common two-level set, so
    # the uniform corner (all treatments at hi / all at lo) is well-defined.
    level_sets = {tuple(_sorted_levels(data[t])) for t in t_cols}
    if len(level_sets) != 1 or len(next(iter(level_sets))) != 2:
        raise EstimatorFailure(
            Refusal.TREATMENT_NOT_BINARY,
            f"the joint general-ID plug-in requires every treatment to be "
            f"binary with one common two-level set; got level sets "
            f"{refusals.describe(sorted(level_sets))} for {refusals.describe(list(t_cols))}. A uniform do-corner "
            f"is undefined otherwise.",
        )
    t_levels = next(iter(level_sets))
    y_levels = _sorted_levels(data[y_col])
    if len(y_levels) != 2:
        raise EstimatorFailure(
            Refusal.OUTCOME_NOT_BINARY,
            f"outcome {y_col!r} has {len(y_levels)} observed levels "
            f"({refusals.describe(y_levels)}); v1 of the general-ID plug-in requires a binary "
            f"outcome.",
            outcome=y_col,
        )
    x_lo, x_hi = t_levels[0], t_levels[1]
    y_hi = y_levels[-1]

    x_set = frozenset(treatment_atoms)
    # Identify the JOINT estimand once per uniform corner (data-independent;
    # only the do-literal baked into every outer X slot differs).
    res_hi = c_factor.identify_via_tian_joint(
        graph, bidirected, x_set, outcome_atom, x_hi)
    res_lo = c_factor.identify_via_tian_joint(
        graph, bidirected, x_set, outcome_atom, x_lo)
    if not (res_hi.identifiable and res_lo.identifiable
            and res_hi.formula is not None and res_lo.formula is not None):
        raise EstimatorFailure(
            Refusal.NOT_IDENTIFIABLE_BY_GENERAL_ID,
            treatment=list(t_cols),
            outcome=y_col,
        )
    f_hi = _bind_target_value(res_hi.formula, outcome_atom, y_hi)
    f_lo = _bind_target_value(res_lo.formula, outcome_atom, y_hi)

    required = (
        referenced_predicates(f_hi)
        | referenced_predicates(f_lo)
        | set(t_cols) | {y_col}
    )
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
    point = _point_ate(df, f_hi, f_lo, domains)

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap_ci(
            df, f_hi, f_lo, domains,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level,
            random_state=random_state, groups=groups,
        )

    assumptions: tuple[str, ...] = (
        "admg_structure_correct_including_latent_confounders",
        "positivity_every_conditioning_stratum_has_support",
        "consistency_of_potential_outcomes_under_joint_intervention",
        "discrete_variables_saturated_nonparametric_plug_in",
        "joint_effect_point_identified_by_set_id_no_adjustment_set_exists",
    )
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )
    return GeneralIdEstimate(
        point=float(point),
        ci_lower=float(ci_lower) if ci_lower is not None else None,
        ci_upper=float(ci_upper) if ci_upper is not None else None,
        ci_level=ci_level,
        method="joint_general_id_plugin",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=t_cols[0],
        treatments=t_cols,
        outcome=y_col,
        treatment_high=envelope_scalar(x_hi),
        treatment_low=envelope_scalar(x_lo),
        outcome_high=envelope_scalar(y_hi),
        model_assumption=(
            "联合效应经集合值 ID 识别（latent 混杂下无调整集，走前门/c-factor "
            "识别）：识别公式按非参数 plug-in 求值，每个条件概率用其所属数据层"
            "的经验频率，无函数形式假设（饱和估计）"
        ),
        form="nonparametric_plug_in",
        cluster=cluster,
    )


def identify_arm_risk_formula(
    graph,
    bidirected,
    *,
    treatment_atom: Atom,
    outcome_atom: Atom,
    arm_value,
    outcome_value,
) -> FormulaExpr:
    """The general-ID estimand for ONE arm: ``P(Y=y | do(X=arm))``.

    The ATE estimators above contrast two arms; a consumer that needs a single
    interventional risk (the binary counterfactual cell needs exactly the one
    arm its cell depends on) takes the same estimand without manufacturing a
    demand for the other arm's data. Returns the formula with the outcome level
    already bound, ready for :func:`evaluate_arm_risk`.

    Raises ``EstimatorFailure`` when the ID algorithm does not point-identify
    this arm on the ADMG — a bow arc (X→Y with X↔Y), for instance, where no
    estimand exists to evaluate.
    """
    from ..runtime import c_factor

    res = c_factor.identify_via_tian(
        graph, bidirected, treatment_atom, outcome_atom, arm_value,
    )
    if not res.identifiable or res.formula is None:
        raise EstimatorFailure(
            Refusal.NOT_IDENTIFIABLE_BY_GENERAL_ID,
            treatment=treatment_atom.predicate,
            outcome=outcome_atom.predicate,
            arm=arm_value,
        )
    return _bind_target_value(res.formula, outcome_atom, outcome_value)


def evaluate_arm_risk(
    formula: FormulaExpr, df: pd.DataFrame, *, domains: dict[Atom, tuple],
) -> float:
    """Non-parametric plug-in value of an arm estimand on this frame.

    Same evaluator as the ATE path (variable elimination over a theta of
    empirical conditionals); a stratum with no support raises rather than
    fabricating a value. ``domains`` comes from :func:`data_domains` and is
    passed explicitly so a bootstrap cannot accidentally re-derive it per draw.
    """
    return _prob_do(formula, df, domains)


def data_domains(graph, df: pd.DataFrame) -> dict[Atom, tuple]:
    """The per-atom value domains an arm estimand sums over, read off ``df``.

    Exposed so a bootstrap can hold the FULL-data domains fixed across
    resamples: a level missing from one draw must surface as a zero-support
    stratum (which the positivity guard catches), not silently narrow the sum
    into a DIFFERENT estimand on that draw.
    """
    return _domains_from_data(graph, df)


# --- internals ----------------------------------------------------------------


def _sorted_levels(series: pd.Series) -> list:
    """Observed distinct levels of a column, sorted, NaN dropped."""
    vals = pd.unique(series.dropna())
    try:
        return sorted(vals.tolist())
    except TypeError:
        return sorted(vals.tolist(), key=str)


def _bind_target_value(
    formula: FormulaExpr, y_atom: Atom, y_value
) -> FormulaExpr:
    """Bind the query-target atom's externally-bound (None) value to a
    concrete literal — the outcome level the P(Y=y | do(X)) contrast is
    taken on. Structure-preserving; population tags are preserved (the
    general-ID formula is single-population, but we never silently drop
    the field)."""

    def rebind(va: ValuedAtom) -> ValuedAtom:
        if va.atom == y_atom and va.value is None:
            return ValuedAtom(atom=va.atom, value=y_value)
        return va

    def walk(node: FormulaExpr) -> FormulaExpr:
        if isinstance(node, ConstantExpr):
            return node
        if isinstance(node, ProbabilityRefExpr):
            return ProbabilityRefExpr(
                target=rebind(node.target),
                given=tuple(rebind(g) for g in node.given),
                population=node.population,
            )
        if isinstance(node, ProductExpr):
            return ProductExpr(terms=tuple(walk(t) for t in node.terms))
        if isinstance(node, SumExpr):
            return SumExpr(bind=node.bind, over=node.over, body=walk(node.body))
        if isinstance(node, FractionExpr):
            return FractionExpr(
                numerator=walk(node.numerator),
                denominator=walk(node.denominator),
            )
        raise TypeError(f"unknown formula node: {type(node).__name__}")

    return walk(formula)


def referenced_predicates(formula: FormulaExpr) -> set[str]:
    """Collect every observed-variable predicate the formula references."""
    preds: set[str] = set()

    def walk(node: FormulaExpr) -> None:
        if isinstance(node, ConstantExpr):
            return
        if isinstance(node, ProbabilityRefExpr):
            preds.add(node.target.atom.predicate)
            for gv in node.given:
                preds.add(gv.atom.predicate)
            return
        if isinstance(node, ProductExpr):
            for t in node.terms:
                walk(t)
            return
        if isinstance(node, SumExpr):
            preds.add(node.over.predicate)
            walk(node.body)
            return
        if isinstance(node, FractionExpr):
            walk(node.numerator)
            walk(node.denominator)
            return
        raise TypeError(f"unknown formula node: {type(node).__name__}")

    walk(formula)
    return preds


def _domains_from_data(graph, df: pd.DataFrame) -> dict[Atom, tuple]:
    """Per-atom observed value domain, keyed by the graph-node Atom (so it
    matches the formula's ``SumExpr.over`` / conditioning atoms by value
    equality)."""
    domains: dict[Atom, tuple] = {}
    for node in graph.nodes():
        col = node.predicate
        if col in df.columns:
            domains[node] = tuple(_sorted_levels(df[col]))
    return domains


def _empirical_conditional(df: pd.DataFrame, key: ProbabilityKey) -> float:
    """Empirical P(target=target_value | given) from the data — the count
    ratio over the conditioning stratum. An empty stratum is a positivity
    violation (raises), never a fabricated value."""
    mask = np.ones(len(df), dtype=bool)
    for atom, value in key.given:
        mask &= (df[atom.predicate].to_numpy() == value)
    denom = int(mask.sum())
    if denom == 0:
        raise EstimatorFailure(
            Refusal.INSUFFICIENT_SUPPORT,
            "positivity violation: the identified estimand conditions on a "
            "covariate stratum with zero support in the data "
            f"({_render_given(key)}); the effect cannot be evaluated there "
            "without extrapolating. Supply data covering that stratum.",
        )
    target_col = df[key.target_atom.predicate].to_numpy()
    num = int((mask & (target_col == key.target_value)).sum())
    return num / denom


def _render_given(key: ProbabilityKey) -> str:
    pairs = sorted(
        ((a.predicate, v) for a, v in key.given), key=lambda p: p[0]
    )
    return ",".join(f"{p}={v}" for p, v in pairs) or "∅"


def _build_data_theta(
    formula: FormulaExpr, df: pd.DataFrame, domains: dict[Atom, tuple]
) -> Theta:
    """A Theta whose entries are the empirical conditionals the formula
    needs. Every key the evaluator looks up is pre-filled from data, so
    ``ve_estimate_formula``'s complete-theta contract holds (no fallbacks).
    Uses ``referenced_keys`` (a linear per-factor walk) rather than
    ``enumerate_keys`` (which materialises the 2^#sums key list — exponential
    and a native-fault site) so a large nested-ID estimand is affordable."""
    theta = Theta(domains=dict(domains))
    for key in referenced_keys(formula, domains):
        theta.entries[key] = _empirical_conditional(df, key)
    return theta


def _prob_do(
    formula: FormulaExpr, df: pd.DataFrame, domains: dict[Atom, tuple]
) -> float:
    theta = _build_data_theta(formula, df, domains)
    # Variable elimination, not the recursive estimate_formula: a nested-ID
    # estimand has |V|-1 nested sums, and bootstrap re-evaluates hundreds of
    # times — the recursive 2^#sums walk is exponential and trips the flaky
    # native fault past |V|≈14. The theta is complete, so VE equals it exactly.
    try:
        return ve_estimate_formula(formula, theta)
    except VEIntractable as exc:
        # A pathological high-treewidth estimand — VE would build an
        # intractable intermediate factor. Degrade gracefully (like a
        # positivity failure) rather than leak the internal VE exception;
        # realistic nested-ID estimands are sparse and never reach this.
        raise EstimatorFailure(
            Refusal.INTRACTABLE_ESTIMAND, limit=str(exc),
        ) from exc


def _point_ate(
    df: pd.DataFrame,
    f_hi: FormulaExpr,
    f_lo: FormulaExpr,
    domains: dict[Atom, tuple],
) -> float:
    """ATE = P(Y=y_hi | do(X=x_hi)) − P(Y=y_hi | do(X=x_lo))."""
    return _prob_do(f_hi, df, domains) - _prob_do(f_lo, df, domains)


def _bootstrap_ci(
    df: pd.DataFrame,
    f_hi: FormulaExpr,
    f_lo: FormulaExpr,
    domains: dict[Atom, tuple],
    *,
    ci_bootstrap: int,
    ci_level: float,
    random_state: int,
    groups: np.ndarray | None = None,
) -> tuple[float | None, float | None]:
    """Non-parametric percentile bootstrap. The identified formula is
    fixed (data-independent); each resample re-estimates the empirical
    Theta on its own domains and re-evaluates. A resample that induces an
    empty stratum (positivity failure on that draw) is skipped — the CI is
    over the draws where the estimand is evaluable."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    estimates: list[float] = []
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        sample = df.iloc[idx]
        # Keep the FULL-data domains across resamples: a level absent from
        # one draw still yields a (zero-support) key that the positivity
        # guard catches and skips, rather than silently changing the sum's
        # range and evaluating a DIFFERENT estimand on that draw.
        try:
            est = (
                _prob_do(f_hi, sample, domains)
                - _prob_do(f_lo, sample, domains)
            )
        except EstimatorFailure:
            continue
        estimates.append(est)
    if len(estimates) < 2:
        return None, None
    arr = np.asarray(estimates)
    alpha = (1 - ci_level) / 2
    return float(np.quantile(arr, alpha)), float(np.quantile(arr, 1 - alpha))
