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

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..ledger import Provenance
from .form import NO_OTHER_SHAPES
from ..types import (
    Atom,
    AtomValue,
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
from ..refusals import Refusal, Remedy
from ..refusals import EstimatorFailure
from ..refusals import QueryRole
from ..intervals import CONFIDENCE_LEVEL
from .resample import (
    FEWEST_DRAWS, Draws, cluster_labels, declared_by, resample_indices,
)
from .treatment_box import (
    MAX_JOINT_TREATMENTS,
    Cell,
    Corner,
    CornerRisk,
    cell as box_cell,
    corners as box_corners,
    interaction_sign,
)


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
    # How the identified formula was evaluated. What that costs in shape
    # assumptions is declared by id in ``assumptions``, where the
    # mechanism audit reads it.
    form: str = "nonparametric_plug_in"
    #: Nothing chose this shape: it IS the method, and the only way to
    #: overrule it is to answer by a different one.
    form_provenance: str = Provenance.INHERENT
    #: Which shapes a lever BESIDE the outcome model settled, by assumption
    #: id. The ids that RESTATE the outcome model's shape take the answer
    #: above; an id here is a different decision, made by a different lever,
    #: and says so itself — :func:`themis.estimation.form.shapes_settled`.
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES
    # Variance concern, not a model node: whole-cluster bootstrap when set.
    cluster: str | None = None
    #: The replicates this interval was taken over — see
    #: :class:`themis.estimation.resample.Draws`. ``None`` when no
    #: bootstrap ran, which is the one case with no answer to give.
    draws: "Draws | None" = None


@dataclass(frozen=True)
class CornerEstimand:
    """The estimand one corner of the treatment box was evaluated from.

    ``do`` is the corner as an intervention, each treatment atom at the level
    the data holds, and ``estimand`` is the identified formula with the
    outcome level bound. Kept beside the corner's number because the number
    cannot be re-derived without the data, and the estimand can be held to
    the graph.
    """

    do: tuple[ValuedAtom, ...]
    estimand: FormulaExpr


@dataclass(frozen=True)
class JointGeneralIdEstimate:
    """Result of a JOINT general-ID (c-factor plug-in) estimate.

    Same answer shape as the joint back-door estimate
    (:class:`~themis.estimation.joint.JointEffectEstimate`) because it is
    the same quantity by another road: a contrast between two corners of
    the treatment box, and the highest-order interaction across all of
    them. ``interaction_point`` is ``None`` exactly when
    ``interaction_unavailable`` names the species that stopped it — a
    member of ``treatment_box.INTERACTION_UNAVAILABLE_KINDS``.
    """

    joint_point: float
    joint_ci_lower: float | None
    joint_ci_upper: float | None
    interaction_point: float | None
    interaction_ci_lower: float | None
    interaction_ci_upper: float | None
    ci_level: float
    method: str                       # "joint_general_id_plugin"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    treatments: tuple[str, ...]
    treated: Cell
    control: Cell
    outcome: str
    #: The outcome level the risks are taken on — every corner's number is
    #: ``P(Y = outcome_high | do(corner))``, so the level is part of what
    #: they mean rather than a rendering detail.
    outcome_high: object
    #: Every corner the plug-in could evaluate on the full sample. Short of
    #: 2^K exactly when the interaction is unavailable, and then the missing
    #: entries are the ones ``interaction_unsupported_cells`` names.
    corner_risks: tuple[CornerRisk, ...]
    #: The estimand each of those corners was read off, in the same order.
    corner_estimands: tuple[CornerEstimand, ...] = ()
    interaction_unavailable: str | None = None
    interaction_unsupported_cells: tuple[Cell, ...] = ()
    #: The enumeration bound, present only when it is what withheld the
    #: interaction — a reader asked to shorten the treatment vector needs
    #: to know what to shorten it to.
    interaction_cap: int | None = None
    # Variance concern, not a model node: whole-cluster bootstrap when set.
    cluster: str | None = None
    #: The replicates BOTH intervals were taken over — see
    #: :class:`themis.estimation.resample.Draws`. ``None`` when no
    #: bootstrap ran, which is the one case with no answer to give. One
    #: record for two quantities because one loop drew for both; the
    #: interaction's own narrower set is what its band says.
    draws: "Draws | None" = None
    # How the identified formulas were evaluated; see GeneralIdEstimate.
    form: str = "nonparametric_plug_in"
    form_provenance: str = Provenance.INHERENT
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES


def estimate_general_id_ate(
    data: pd.DataFrame,
    *,
    graph,
    bidirected,
    treatment_atom: Atom,
    outcome_atom: Atom,
    ci_bootstrap: int = 500,
    ci_level: float = CONFIDENCE_LEVEL,
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
            Refusal.MISSING_COLUMN, columns=[t_col],
            recorded={"role": QueryRole.EXPOSURE},
        )
    if y_col not in data.columns:
        raise EstimatorFailure(
            Refusal.MISSING_COLUMN, columns=[y_col],
            recorded={"role": QueryRole.OUTCOME},
        )

    # Binary treatment / outcome — the ATE contrast is the two-level
    # difference on the high outcome level.
    t_levels = _sorted_levels(data[t_col])
    if len(t_levels) != 2:
        raise EstimatorFailure(
            Refusal.TREATMENT_NOT_BINARY, treatment=t_col, levels=t_levels,
        )
    y_levels = _sorted_levels(data[y_col])
    if len(y_levels) != 2:
        raise EstimatorFailure(
            Refusal.OUTCOME_NOT_BINARY, outcome=y_col, levels=y_levels,
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
    draws = Draws(ci_bootstrap) if ci_bootstrap > 0 else None
    if draws is not None:
        ci_lower, ci_upper = _bootstrap_ci(
            df, f_hi, f_lo, domains,
            draws=draws, ci_level=ci_level,
            random_state=random_state, groups=groups,
        )

    assumptions: tuple[str, ...] = (
        "admg_structure_correct_including_latent_confounders",
        "positivity_every_conditioning_stratum_has_support",
        "consistency_of_potential_outcomes",
        "discrete_variables_saturated_nonparametric_plug_in",
    )
    assumptions += declared_by(draws, cluster=cluster)
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
        form="nonparametric_plug_in",
        cluster=cluster,
        draws=draws,
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
    ci_level: float = CONFIDENCE_LEVEL,
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
            Refusal.MISSING_COLUMN, columns=[t_col],
            recorded={"role": QueryRole.EXPOSURE},
        )
    if y_col not in data.columns:
        raise EstimatorFailure(
            Refusal.MISSING_COLUMN, columns=[y_col],
            recorded={"role": QueryRole.OUTCOME},
        )

    t_levels = _sorted_levels(data[t_col])
    if len(t_levels) != 2:
        raise EstimatorFailure(
            Refusal.TREATMENT_NOT_BINARY, treatment=t_col, levels=t_levels,
        )
    y_levels = _sorted_levels(data[y_col])
    if len(y_levels) != 2:
        raise EstimatorFailure(
            Refusal.OUTCOME_NOT_BINARY, outcome=y_col, levels=y_levels,
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
    draws = Draws(ci_bootstrap) if ci_bootstrap > 0 else None
    if draws is not None:
        ci_lower, ci_upper = _bootstrap_ci(
            df, f_hi, f_lo, domains,
            draws=draws, ci_level=ci_level,
            random_state=random_state, groups=groups,
        )

    assumptions: tuple[str, ...] = (
        "admg_structure_correct_including_latent_confounders",
        "positivity_every_conditioning_stratum_has_support",
        "consistency_of_potential_outcomes",
        "discrete_variables_saturated_nonparametric_plug_in",
        "conditional_effect_identified_via_idc_rule2_exchange",
    )
    assumptions += declared_by(draws, cluster=cluster)
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
        form="nonparametric_plug_in",
        cluster=cluster,
        draws=draws,
    )


def estimate_joint_general_id_ate(
    data: pd.DataFrame,
    *,
    graph,
    bidirected,
    treatment_atoms: tuple[Atom, ...],
    outcome_atom: Atom,
    ci_bootstrap: int = 500,
    ci_level: float = CONFIDENCE_LEVEL,
    random_state: int = 42,
    cluster: str | None = None,
) -> JointGeneralIdEstimate:
    """Plug-in JOINT contrast + K-way interaction for a general-ID
    (c-factor) identified effect of a SET of treatments do(A, B, …).

    The joint interventional distribution ``P(Y | do(A, B, …))`` is
    identified by the set-valued Shpitser–Pearl ID
    (:func:`themis.runtime.c_factor.identify_via_tian_joint`) — the escape
    layer that fires when the joint effect is confounded by latent common
    causes so no ADMG adjustment set exists (front-door / c-component for
    sets), yet the effect is still non-parametrically point-identified.
    The identified estimand is turned into a number by the SAME plug-in
    the single-treatment general-ID path uses, once per corner of the
    treatment box::

        joint       = P(Y=y_hi | do(all hi)) − P(Y=y_hi | do(all lo))
        interaction = Σ_corners (−1)^{#lo} P(Y=y_hi | do(corner))

    Identification runs per corner because the do-literals differ, not
    because the graph does: identifiability is a property of the ADMG and
    the treatment SET, so every corner identifies or none does, and a
    split would be a bug rather than a case to branch on.

    The interaction is a second quantity resting on a stricter support
    requirement — every one of the 2^K corners must be evaluable, where
    the contrast needs two — so it can be withheld while the contrast
    stands. That is a withholding with a species attached, never a silent
    absence: see ``interaction_unavailable``.

    Scope (declared): binary treatments that share one common two-level
    set; binary outcome; compact-shortcut-expressible estimands only
    (napkin-style joint nested-ID PUNTs to not-identifiable → the caller
    refuses). Above ``MAX_JOINT_TREATMENTS`` the CONTRAST is still
    reported — it needs two corners however wide the box is — and only
    the interaction is withheld.

    Raises
    ------
    EstimatorFailure: a treatment / the outcome is non-binary, the
        treatments do not share one common two-level set, the joint effect
        is not point-identified by the set ID algorithm, or a positivity
        violation in one of the two CONTRAST corners (a violation in any
        other corner withholds the interaction instead).
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
                Refusal.MISSING_COLUMN, columns=[t_col],
                recorded={"role": QueryRole.EXPOSURE},
            )
    if y_col not in data.columns:
        raise EstimatorFailure(
            Refusal.MISSING_COLUMN, columns=[y_col],
            recorded={"role": QueryRole.OUTCOME},
        )

    # Every treatment must be binary AND share one common two-level set, so
    # the uniform corner (all treatments at hi / all at lo) is well-defined.
    level_sets = {tuple(_sorted_levels(data[t])) for t in t_cols}
    if len(level_sets) != 1:
        raise EstimatorFailure(
            Refusal.TREATMENT_LEVELS_DIFFER,
            treatments=list(t_cols), level_sets=sorted(level_sets),
        )
    t_levels = next(iter(level_sets))
    if len(t_levels) != 2:
        # One set, shared, and not a pair: every treatment is the same
        # non-binary column, so this is the plain fact and t_cols is who it
        # is true of.
        raise EstimatorFailure(
            Refusal.TREATMENT_NOT_BINARY,
            treatment=list(t_cols), levels=list(t_levels),
        )
    y_levels = _sorted_levels(data[y_col])
    if len(y_levels) != 2:
        raise EstimatorFailure(
            Refusal.OUTCOME_NOT_BINARY, outcome=y_col, levels=y_levels,
        )
    x_lo, x_hi = t_levels[0], t_levels[1]
    y_hi = y_levels[-1]

    K = len(t_cols)
    # The envelope's copy of the levels; the formulas below take the raw
    # ones, which have to compare equal to what the column holds.
    high = {t: envelope_scalar(x_hi) for t in t_cols}
    low = {t: envelope_scalar(x_lo) for t in t_cols}
    all_hi: Corner = (True,) * K
    all_lo: Corner = (False,) * K
    # Above the cap the box is never walked, so only the contrast's own two
    # corners are identified and evaluated. The contrast is unaffected: it
    # is two corners however wide the box is.
    over_cap = K > MAX_JOINT_TREATMENTS
    wanted: tuple[Corner, ...] = (
        (all_hi, all_lo) if over_cap else box_corners(K)
    )

    # Identify one estimand per corner. The do-literals differ; the graph
    # does not, so a corner that failed to identify while another succeeded
    # would contradict the algorithm rather than describe the data.
    formulas: dict[Corner, FormulaExpr] = {}
    assignments: dict[Corner, dict[Atom, AtomValue]] = {}
    for mask in wanted:
        assignment = assignments[mask] = {
            atom: (x_hi if mask[k] else x_lo)
            for k, atom in enumerate(treatment_atoms)
        }
        res = c_factor.identify_via_tian_joint(
            graph, bidirected, assignment, outcome_atom)
        if not (res.identifiable and res.formula is not None):
            raise EstimatorFailure(
                Refusal.NOT_IDENTIFIABLE_BY_GENERAL_ID,
                treatment=list(t_cols),
                outcome=y_col,
            )
        formulas[mask] = _bind_target_value(res.formula, outcome_atom, y_hi)

    required = set(t_cols) | {y_col}
    for f in formulas.values():
        required |= referenced_predicates(f)
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
    contrast_corners = (all_hi, all_lo)
    # None says the box was never walked, which is a different fact from
    # walking it and finding a corner empty — and the difference is exactly
    # what the two withholding species report.
    interaction_over = None if over_cap else wanted
    risks = _corner_risks(df, formulas, domains, required=contrast_corners)
    joint_point = risks[all_hi] - risks[all_lo]
    interaction_point = _interaction(risks, interaction_over)

    joint_lo = joint_hi = None
    inter_lo = inter_hi = None
    draws = Draws(ci_bootstrap) if ci_bootstrap > 0 else None
    if draws is not None:
        joint_lo, joint_hi, inter_lo, inter_hi = _bootstrap_joint_ci(
            df, formulas, domains,
            contrast=contrast_corners, interaction_over=interaction_over,
            draws=draws, ci_level=ci_level,
            random_state=random_state, groups=groups,
        )
    if interaction_point is None:
        inter_lo = inter_hi = None

    unsupported = tuple(
        box_cell(mask, t_cols, high, low)
        for mask in wanted if mask not in risks
    )
    unavailable: str | None = None
    if interaction_point is None:
        unavailable = "order_above_cap" if over_cap else "corner_unsupported"

    assumptions: tuple[str, ...] = (
        "admg_structure_correct_including_latent_confounders",
        "positivity_every_conditioning_stratum_has_support",
        "consistency_of_potential_outcomes_under_joint_intervention",
        "discrete_variables_saturated_nonparametric_plug_in",
        "joint_effect_point_identified_by_set_id_no_adjustment_set_exists",
    )
    assumptions += declared_by(draws, cluster=cluster)
    return JointGeneralIdEstimate(
        joint_point=float(joint_point),
        joint_ci_lower=joint_lo,
        joint_ci_upper=joint_hi,
        interaction_point=(
            float(interaction_point) if interaction_point is not None else None
        ),
        interaction_ci_lower=inter_lo,
        interaction_ci_upper=inter_hi,
        ci_level=ci_level,
        method="joint_general_id_plugin",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatments=t_cols,
        treated=box_cell(all_hi, t_cols, high, low),
        control=box_cell(all_lo, t_cols, high, low),
        outcome=y_col,
        outcome_high=envelope_scalar(y_hi),
        corner_risks=tuple(
            CornerRisk(cell=box_cell(mask, t_cols, high, low),
                       risk=float(risks[mask]))
            for mask in wanted if mask in risks
        ),
        corner_estimands=tuple(
            CornerEstimand(
                do=tuple(ValuedAtom(atom=atom, value=level)
                         for atom, level in assignments[mask].items()),
                estimand=formulas[mask],
            )
            for mask in wanted if mask in risks
        ),
        interaction_unavailable=unavailable,
        interaction_unsupported_cells=unsupported,
        interaction_cap=MAX_JOINT_TREATMENTS if over_cap else None,
        form="nonparametric_plug_in",
        cluster=cluster,
        draws=draws,
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
            recorded={"arm": arm_value},
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
            cells=[{atom.predicate: value for atom, value in key.given}],
            quantity=(
                f"P({key.target_atom.predicate} | "
                + ", ".join(sorted(a.predicate for a, _ in key.given)) + ")"
            ),
            remedies=[(Remedy.SUPPLY_DATA_STRATUM, _render_given(key))],
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


def _corner_risks(
    df: pd.DataFrame,
    formulas: dict[Corner, FormulaExpr],
    domains: dict[Atom, tuple],
    *,
    required: tuple[Corner, ...],
) -> dict[Corner, float]:
    """``P(Y=y_hi | do(corner))`` at every corner the data can carry.

    A corner whose estimand hits an empty conditioning stratum is ABSENT
    from the result rather than fabricated — the two quantities built on
    top of these have different support requirements, and only the
    contrast's own corners are ``required``. A missing one of those is
    still a refusal, since without it there is no estimate at all.
    """
    risks: dict[Corner, float] = {}
    for mask, formula in formulas.items():
        try:
            risks[mask] = _prob_do(formula, df, domains)
        except EstimatorFailure:
            if mask in required:
                raise
    return risks


def _interaction(
    risks: dict[Corner, float],
    over: tuple[Corner, ...] | None,
) -> float | None:
    """The K-th mixed finite difference over the treatment box, or ``None``
    when it does not exist on this sample.

    ``over is None`` says the box was never walked (K past the enumeration
    bound); a corner missing from ``risks`` says it was walked and found
    empty. Both come back as no number, and the caller keeps them apart —
    what a reader does about them differs.
    """
    if over is None:
        return None
    if any(mask not in risks for mask in over):
        return None
    return sum(interaction_sign(mask) * risks[mask] for mask in over)


def _percentile_band(
    values: list[float], ci_level: float,
) -> tuple[float | None, float | None]:
    """Percentile band over the draws a quantity survived, or no band at
    all when fewer than two of them exist — the same floor
    :data:`themis.estimation.resample.FEWEST_DRAWS` names, applied per
    quantity because a draw can serve one of them and not the other."""
    if len(values) < FEWEST_DRAWS:
        return None, None
    arr = np.asarray(values)
    alpha = (1 - ci_level) / 2
    return float(np.quantile(arr, alpha)), float(np.quantile(arr, 1 - alpha))


def _bootstrap_joint_ci(
    df: pd.DataFrame,
    formulas: dict[Corner, FormulaExpr],
    domains: dict[Atom, tuple],
    *,
    contrast: tuple[Corner, Corner],
    interaction_over: tuple[Corner, ...] | None,
    draws: Draws,
    ci_level: float,
    random_state: int,
    groups: np.ndarray | None = None,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Percentile bootstrap for the contrast and the interaction TOGETHER.

    Both are read off the same resample wherever both exist, so the two
    intervals are mutually consistent rather than two independent
    re-runs. A draw that loses a corner drops out of that quantity's
    interval and only that one: the contrast survives a draw the
    interaction cannot use, which is the same asymmetry the point estimate
    has. ``draws`` therefore counts the resample — a draw the contrast
    could use is a used draw — and the interaction's narrower set is what
    its own band is taken over.
    """
    rng = np.random.default_rng(random_state)
    n = len(df)
    joint_values: list[float] = []
    inter_values: list[float] = []
    for _ in draws:
        idx = resample_indices(n, rng, groups=groups)
        sample = df.iloc[idx]
        # Keep the FULL-data domains across resamples — see _bootstrap_ci.
        try:
            risks = _corner_risks(sample, formulas, domains, required=contrast)
        except EstimatorFailure as exc:
            draws.unusable(exc.failure_type)
            continue
        joint_values.append(risks[contrast[0]] - risks[contrast[1]])
        inter = _interaction(risks, interaction_over)
        if inter is not None:
            inter_values.append(inter)
        draws.usable()
    return (
        *_percentile_band(joint_values, ci_level),
        *_percentile_band(inter_values, ci_level),
    )


def _bootstrap_ci(
    df: pd.DataFrame,
    f_hi: FormulaExpr,
    f_lo: FormulaExpr,
    domains: dict[Atom, tuple],
    *,
    draws: Draws,
    ci_level: float,
    random_state: int,
    groups: np.ndarray | None = None,
) -> tuple[float | None, float | None]:
    """Non-parametric percentile bootstrap. The identified formula is
    fixed (data-independent); each resample re-estimates the empirical
    Theta on its own domains and re-evaluates. A resample that induces an
    empty stratum (positivity failure on that draw) is dropped and filed
    under the refusal that dropped it — the CI is over the draws where the
    estimand is evaluable, and the count of the others travels with it."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    estimates: list[float] = []
    for _ in draws:
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
        except EstimatorFailure as exc:
            draws.unusable(exc.failure_type)
            continue
        estimates.append(est)
        draws.usable()
    if not draws.enough:
        return None, None
    arr = np.asarray(estimates)
    alpha = (1 - ci_level) / 2
    return float(np.quantile(arr, alpha)), float(np.quantile(arr, 1 - alpha))
