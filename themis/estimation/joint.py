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
- The two quantities need different corners of the treatment box, so
  positivity is checked separately for each. The contrast needs only the
  all-treated and all-control cells; the K-way interaction needs all 2^K.
  A cell with no rows is a definitive positivity violation — the outcome
  model still predicts there, so the alternative to refusing is a
  fabricated number, not a missing one. When only the interaction's
  corners are short the contrast is still reported and the interaction
  alone is withheld.

API:

    from themis.estimation.joint import estimate_joint_effect
    est = estimate_joint_effect(
        data, treatments=("a", "b", "c"), outcome="y", adjustment=("z",),
    )
    print(est.joint_point, est.interaction_point)  # interaction is K-way
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import combinations, product
from typing import Literal

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression, LogisticRegression

from .contract import validate_data
from .form import NO_OTHER_SHAPES, outcome_form, shapes_settled
from .declared import ORDERED_ENTRY_SHAPE, design_block, ordered_entry
from .. import refusals
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from .resample import cluster_labels, resample_indices


ModelName = Literal["auto", "linear", "logistic"]

# Resource bound on the joint estimator: the saturated treatment basis is
# 2^K − 1 columns and the K-way interaction is a 2^K-corner finite
# difference. Cap K so neither blows up. Not a fundamental limit — the
# identification (``minimal_adjustment_sets_joint``) has no such cap; this
# only bounds the numeric plug-in. Beyond it: honest NotImplementedError.
_MAX_JOINT_TREATMENTS = 5


class _ContrastCornerEmpty(ValueError):
    """A sample has no rows in the all-treated or the all-control cell.

    The point sample is refused before any fit when that happens, so only a
    bootstrap resample can raise this — and the draw loop already treats a
    draw it cannot fit as one that contributes to neither interval. A
    ``ValueError`` subclass so that loop's existing handler catches it
    unchanged.
    """


@dataclass(frozen=True)
class JointEffectEstimate:
    """Result of a joint-intervention g-formula estimate.

    - ``joint_*``: point + CI for the joint contrast
      E[Y|do(A=a,B=b)] − E[Y|do(A=a',B=b')].
    - ``interaction_*``: point + CI for the additive-scale highest-order
      (K-way) treatment interaction — the K-th mixed finite difference
      over the 2^K treatment corners. For K=2 this is the ordinary
      treatment×treatment interaction. ``None`` when some corner of the
      treatment box has no rows to stand on, with
      ``interaction_unavailable_reason`` saying so and
      ``interaction_unsupported_cells`` naming which.
    - ``treated`` / ``control``: the {treatment: value} cells the joint
      contrast is taken between.
    """

    joint_point: float
    joint_ci_lower: float | None
    joint_ci_upper: float | None
    interaction_point: float | None
    interaction_ci_lower: float | None
    interaction_ci_upper: float | None
    ci_level: float
    method: str                       # "joint_backdoor_linear" | "joint_backdoor_logistic"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    adjustment: tuple[str, ...]
    treatments: tuple[str, ...]
    treated: tuple[tuple[str, object], ...]   # ((name, value), ...) — the (a, b) cell
    control: tuple[tuple[str, object], ...]   # ((name, value), ...) — the (a', b') cell
    outcome: str
    # Variance concern, not a model node: when set, both the joint and the
    # interaction CIs were computed by resampling whole clusters (pairs
    # cluster bootstrap) rather than i.i.d. rows. None → i.i.d. bootstrap.
    cluster: str | None = None
    # Set together with ``interaction_point = None``: the prose a reader
    # gets instead of the number, and the cells behind it in the same
    # ((name, value), ...) shape as ``treated`` / ``control``.
    interaction_unavailable_reason: str | None = None
    interaction_unsupported_cells: tuple[tuple[tuple[str, object], ...], ...] = ()
    #: The outcome model's shape, and who settled it — see
    #: :mod:`themis.estimation.form`. Both empty until the caller's
    #: ``model=`` has been read.
    form: str = ""
    form_provenance: str = ""
    #: Which shapes a lever BESIDE the outcome model settled, by assumption
    #: id. The ids that RESTATE the outcome model's shape take the answer
    #: above; an id here is a different decision, made by a different lever,
    #: and says so itself — :func:`themis.estimation.form.shapes_settled`.
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES


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
        raise EstimatorFailure(
            Refusal.NOT_A_JOINT_INTERVENTION,
            count=len(treatments), treatments=list(treatments),
        )
    if len(treatments) > _MAX_JOINT_TREATMENTS:
        raise EstimatorFailure(
            Refusal.TOO_MANY_JOINT_TREATMENTS,
            cap=_MAX_JOINT_TREATMENTS, count=len(treatments),
            treatments=list(treatments),
        )
    if len(set(treatments)) != len(treatments):
        raise EstimatorFailure(
            Refusal.INVALID_INPUT,
            f"joint treatment vector repeats a column: {refusals.describe(treatments)}",
            treatments=list(treatments),
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
        quantity_columns=(*treatments, outcome),
    )
    df = contract.data

    treated_values = treated_values or {t: True for t in treatments}
    control_values = control_values or {t: False for t in treatments}

    resolved, form_provenance = outcome_form(model, df[outcome])
    method = f"joint_backdoor_{resolved}"

    K = len(treatments)
    hi = tuple(float(treated_values[t]) for t in treatments)
    lo = tuple(float(control_values[t]) for t in treatments)
    corners = tuple(product((True, False), repeat=K))
    all_hi = (True,) * K
    all_lo = (False,) * K

    def _cell(mask: tuple[bool, ...]) -> tuple[tuple[str, object], ...]:
        """The corner as the caller wrote it — their own hi / lo values, not
        the floats the design matrix works in."""
        return tuple(
            (t, (treated_values if mask[k] else control_values)[t])
            for k, t in enumerate(treatments)
        )

    # Which corner of the treatment box each row stands on. The outcome
    # model predicts at every corner whether or not any row is there, so
    # this is the only thing standing between an unsupported corner and a
    # fabricated number.
    row_corner = _corner_of_each_row(df, treatments, hi, lo)
    support = _corner_counts(row_corner, corners)

    # The contrast needs only its own two cells. Without them there is no
    # estimate at all — this subsumes the older per-treatment check, since
    # a treatment stuck at one level empties whichever cell asked for the
    # other, and it says which cell rather than which column.
    bare = [m for m in (all_hi, all_lo) if support[m] == 0]
    if bare:
        raise EstimatorFailure(
            Refusal.INSUFFICIENT_SUPPORT,
            f"the joint contrast is taken between the all-treated and "
            f"all-control cells, and no rows sit in "
            f"{', '.join(_cell_text(_cell(m)) for m in bare)}. Positivity is "
            f"violated outright: the outcome model would still predict "
            f"there, so the contrast would be an extrapolation reported as "
            f"a measurement.",
            unsupported_cells=[dict(_cell(m)) for m in bare],
        )

    def _joint_and_interaction(
        sample: pd.DataFrame, labels: np.ndarray,
    ) -> tuple[float, float | None]:
        counts = _corner_counts(labels, corners)
        if counts[all_hi] == 0 or counts[all_lo] == 0:
            # Only reachable from a bootstrap draw that lost a contrast
            # cell; the point sample was checked above. Raised rather than
            # returned so the guarantee is in the signature: the draw loop
            # already treats it as a draw it cannot use, and the point call
            # can no longer hand a ``None`` to a field declared ``float``.
            raise _ContrastCornerEmpty(
                "the resample has no rows in the all-treated or the "
                "all-control cell"
            )
        predict = _fit(sample, treatments, outcome, adjustment, resolved)
        # Standardized counterfactual mean at each of the 2^K treatment
        # corners (g-formula plug-in), averaged over the sample's empirical
        # Z distribution. A corner is a per-treatment choice of hi / lo.
        # ``mask`` marks which treatments are at their hi level.
        corner_mean: dict[tuple[bool, ...], float] = {}
        for mask in corners:
            cell = tuple(hi[k] if mask[k] else lo[k] for k in range(K))
            corner_mean[mask] = float(np.mean(predict(sample, cell)))
        # Joint contrast between the requested treated (all-hi) and control
        # (all-lo) cells.
        joint = corner_mean[all_hi] - corner_mean[all_lo]
        if any(counts[mask] == 0 for mask in corners):
            return joint, None
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

    try:
        joint_point, interaction_point = _joint_and_interaction(df, row_corner)
    except np.linalg.LinAlgError as exc:
        # The bootstrap below tolerates a resample it cannot fit; the point
        # fit has no such loop, and the solver's own error is a ValueError
        # subclass that dispatch's generic guard used to discard.
        raise EstimatorFailure(
            Refusal.SINGULAR_DESIGN,
            f"the saturated joint design is singular on this sample "
            f"({exc}); a 2^K-corner contrast needs every corner to be "
            f"separately estimable",
        ) from exc

    joint_lo = joint_hi = None
    inter_lo = inter_hi = None
    if ci_bootstrap > 0:
        rng = np.random.default_rng(random_state)
        n = len(df)
        joint_draws = np.empty(ci_bootstrap)
        inter_draws = np.empty(ci_bootstrap)
        for i in range(ci_bootstrap):
            idx = resample_indices(n, rng, groups=groups)
            # A draw that lost a corner drops out of that quantity's
            # interval and only that one: the contrast survives a draw the
            # interaction cannot use, and the two are still computed from
            # the same resample wherever both are defined.
            joint_draws[i] = inter_draws[i] = np.nan
            try:
                jd, idd = _joint_and_interaction(
                    df.iloc[idx], row_corner[idx],
                )
            except (ValueError, np.linalg.LinAlgError):
                continue
            joint_draws[i] = jd
            if idd is not None:
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
    # The design took each adjustment column as ONE term, so a column
    # with more than two levels was read as a number: level three sits
    # twice as far from level one as level two does. Nothing in the
    # program claimed that, and `scale` has no member that could deny
    # it, so the fit says what it assumed.
    assumptions += ordered_entry(df, adjustment)
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )

    unsupported = tuple(_cell(m) for m in corners if support[m] == 0)
    unavailable_reason = None if interaction_point is not None else (
        f"定义 {K} 阶交互的那个 {len(corners)} 角点有限差分，在 "
        f"{'、'.join(_cell_text(c) for c in unsupported)} "
        f"上没有任何一行数据。上面那个对比不受影响"
        f"——它取在全处理格与全对照格之间，两者都有观测——"
        f"但交互项没法与结局模型在空角点上凭空补出来的东西分开。"
    )
    if interaction_point is None:
        inter_lo = inter_hi = None

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
        data_columns=contract.columns,
        adjustment=tuple(adjustment),
        treatments=tuple(treatments),
        treated=tuple((k, treated_values[k]) for k in treatments),
        control=tuple((k, control_values[k]) for k in treatments),
        outcome=outcome,
        cluster=cluster,
        interaction_unavailable_reason=unavailable_reason,
        interaction_unsupported_cells=unsupported,
        form=resolved,
        form_provenance=form_provenance,
        # The design matrix's own decision, which no ``model=`` names.
        shape_provenance=shapes_settled(assumptions, ORDERED_ENTRY_SHAPE),
    )


# --- internals --------------------------------------------------------------


def _cell_text(cell: tuple[tuple[str, object], ...]) -> str:
    """A corner as prose. The values are the caller's own, so a bool reads
    as ``True`` rather than as whatever the design matrix turned it into."""
    return "(" + ", ".join(f"{name}={value}" for name, value in cell) + ")"


def _corner_of_each_row(
    frame: pd.DataFrame,
    treatments: tuple[str, ...],
    hi: tuple[float, ...],
    lo: tuple[float, ...],
) -> np.ndarray:
    """Label every row with the corner of the hi/lo box it stands on.

    The label packs the per-treatment choice into an integer — bit ``k``
    set means treatment ``k`` is at its hi level. Rows at neither level of
    some treatment get ``-1``: they carry the adjustment distribution the
    g-formula averages over, but they are nobody's support.

    Labelling once and slicing it per resample is what keeps the check
    affordable inside the bootstrap.
    """
    label = np.zeros(len(frame), dtype=np.int64)
    off = np.zeros(len(frame), dtype=bool)
    for k, t in enumerate(treatments):
        col = frame[t].to_numpy(dtype=float)
        at_hi = col == hi[k]
        off |= ~(at_hi | (col == lo[k]))
        label |= at_hi.astype(np.int64) << k
    label[off] = -1
    return label


def _corner_counts(
    label: np.ndarray, corners: tuple[tuple[bool, ...], ...],
) -> dict[tuple[bool, ...], int]:
    """How many rows stand on each corner, keyed the way the estimator
    names corners (a per-treatment hi/lo mask)."""
    counts = np.bincount(label[label >= 0], minlength=len(corners))
    return {
        mask: int(counts[sum(1 << k for k, at_hi in enumerate(mask) if at_hi)])
        for mask in corners
    }


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
        z = design_block(df, adjustment)
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
            z = design_block(sample, adjustment)
            M = np.column_stack([_basis(Tc), z])
        else:
            M = _basis(Tc)
        return base(M)

    return predict


def _assumptions_for(model: str, n_adj: int) -> tuple[str, ...]:
    common: tuple[str, ...] = (
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
