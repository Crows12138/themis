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
- Binary treatments. Two to ``treatment_box.MAX_JOINT_TREATMENTS``
  supported; the saturated basis has 2^K − 1 treatment columns and the
  interaction is a 2^K-corner finite difference, so K is capped to bound
  the design matrix / corner enumeration. Beyond the cap the estimator
  refuses (the dispatch then leaves the structural result untouched — an
  honest capability gap, never a wrong number). Unlike the general-ID
  route, whose contrast needs no fit and so survives the cap, the
  saturated basis is 2^K − 1 columns wide whether or not the interaction
  is wanted, so here the cap stops the whole estimator.
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
from itertools import combinations
from typing import Literal

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression, LogisticRegression

from .contract import validate_data
from .form import (
    MODEL_WORDS_OUTCOME, NO_OTHER_SHAPES, outcome_form, shapes_settled,
)
from .declared import ORDERED_ENTRY_SHAPE, design_block, ordered_entry
from .. import refusals, registry
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from ..intervals import CONFIDENCE_LEVEL
from .resample import (
    Draws, cluster_labels, declared_by, resample_indices,
)
from .treatment_box import (
    MAX_JOINT_TREATMENTS,
    CornerRisk,
    cell as box_cell,
    corners as box_corners,
    interaction_sign,
)


ModelName = Literal["auto", "linear", "logistic"]


class _ContrastCornerEmpty(registry.Undeclared, ValueError):
    """A sample has no rows in the all-treated or the all-control cell.

    The point sample is refused before any fit when that happens, so only a
    bootstrap resample can raise this — and the draw loop already treats a
    draw it cannot fit as one that contributes to neither interval. A
    ``ValueError`` subclass so that loop's existing handler catches it
    unchanged, and :class:`themis.registry.Undeclared` because that is the
    whole of what the name is for: the handler drops the draw and never
    opens the exception, so the sentence inside it has no reader.
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
      ``interaction_unavailable`` naming the species (a member of
      ``treatment_box.INTERACTION_UNAVAILABLE_KINDS``) and
      ``interaction_unsupported_cells`` naming which corners.
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
    #: Every corner the data stands on, standardized. Short of 2^K exactly
    #: when the interaction is unavailable, and then the missing entries are
    #: the ones ``interaction_unsupported_cells`` names. See
    #: :class:`themis.estimation.treatment_box.CornerRisk` for why a record
    #: of the walked box is what makes both reported numbers re-derivable.
    #: Required rather than defaulted: an empty box would read as "this
    #: route records none", which is the state this field exists to end.
    corner_risks: tuple[CornerRisk, ...]
    #: The replicates these intervals were taken over — see
    #: :class:`themis.estimation.resample.Draws`. ``None`` when no
    #: bootstrap ran, which is the one case with no answer to give.
    draws: "Draws | None" = None
    # Variance concern, not a model node: when set, both the joint and the
    # interaction CIs were computed by resampling whole clusters (pairs
    # cluster bootstrap) rather than i.i.d. rows. None → i.i.d. bootstrap.
    cluster: str | None = None
    # Set together with ``interaction_point = None``: WHICH way the
    # interaction went missing, and the cells behind it in the same
    # ((name, value), ...) shape as ``treated`` / ``control``. A member of
    # ``treatment_box.INTERACTION_UNAVAILABLE_KINDS`` rather than a
    # sentence — what a reader does about it differs by species, and only
    # the reader's own surface knows which language to say it in.
    interaction_unavailable: str | None = None
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
    ci_level: float = CONFIDENCE_LEVEL,
    random_state: int = 42,
    cluster: str | None = None,
) -> JointEffectEstimate:
    """Joint g-formula contrast + treatment×treatment interaction.

    Parameters
    ----------
    data: DataFrame with treatment / outcome / adjustment columns.
    treatments: ordered tuple of 2..``MAX_JOINT_TREATMENTS`` binary
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
    if len(treatments) > MAX_JOINT_TREATMENTS:
        raise EstimatorFailure(
            Refusal.TOO_MANY_JOINT_TREATMENTS,
            cap=MAX_JOINT_TREATMENTS, count=len(treatments),
            treatments=list(treatments),
        )
    if len(set(treatments)) != len(treatments):
        raise EstimatorFailure(
            Refusal.DUPLICATE_INPUT,
            what="the joint treatment vector", given=list(treatments),
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
    corners = box_corners(K)
    all_hi = (True,) * K
    all_lo = (False,) * K

    def _cell(mask: tuple[bool, ...]) -> tuple[tuple[str, object], ...]:
        """The corner as the caller wrote it — their own hi / lo values, not
        the floats the design matrix works in."""
        return box_cell(mask, tuple(treatments), treated_values, control_values)

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
            cells=[dict(_cell(m)) for m in bare],
            quantity=f"E[{outcome} | " + ", ".join(treatments) + "]",
        )

    def _joint_and_interaction(
        sample: pd.DataFrame, labels: np.ndarray,
    ) -> tuple[float, float | None, dict[tuple[bool, ...], float]]:
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
        # The box is handed back, not just the two differences taken from
        # it. Both reported numbers ARE finite differences of these, so an
        # auditor without them can only check that they are numbers.
        joint = corner_mean[all_hi] - corner_mean[all_lo]
        if any(counts[mask] == 0 for mask in corners):
            return joint, None, corner_mean
        # Highest-order (K-way) interaction: the K-th mixed finite
        # difference — the alternating-sign sum over all 2^K corners, with
        # sign (−1)^{#treatments at lo}. For K=2 this is exactly
        # (m11 − m10) − (m01 − m00); the sum annihilates every lower-order
        # term (main effects, pairwise …) and the Z contribution, isolating
        # the top-order interaction.
        interaction = 0.0
        for mask, val in corner_mean.items():
            interaction += interaction_sign(mask) * val
        return joint, interaction, corner_mean

    try:
        joint_point, interaction_point, corner_mean = _joint_and_interaction(
            df, row_corner)
    except np.linalg.LinAlgError as exc:
        # The bootstrap below tolerates a resample it cannot fit; the point
        # fit has no such loop, and the solver's own error is a ValueError
        # subclass that dispatch's generic guard used to discard.
        raise EstimatorFailure(
            Refusal.SINGULAR_DESIGN,
            design=refusals.Design.SATURATED_JOINT,
            recorded={"diagnostic": str(exc)},
        ) from exc

    joint_lo = joint_hi = None
    inter_lo = inter_hi = None
    draws = Draws(ci_bootstrap) if ci_bootstrap > 0 else None
    if draws is not None:
        rng = np.random.default_rng(random_state)
        n = len(df)
        joint_draws = np.empty(draws.requested)
        inter_draws = np.empty(draws.requested)
        for i in draws:
            idx = resample_indices(n, rng, groups=groups)
            # A draw that lost a corner drops out of that quantity's
            # interval and only that one: the contrast survives a draw the
            # interaction cannot use, and the two are still computed from
            # the same resample wherever both are defined. So the count
            # below is the RESAMPLE's — how many refits the design admitted
            # — and an interaction absent on a draw the refit handled is a
            # fact about the interaction, not about the draw.
            joint_draws[i] = inter_draws[i] = np.nan
            try:
                jd, idd, _ = _joint_and_interaction(
                    df.iloc[idx], row_corner[idx],
                )
            except (ValueError, np.linalg.LinAlgError):
                draws.unusable()
                continue
            joint_draws[i] = jd
            draws.usable()
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
    assumptions += declared_by(draws, cluster=cluster)

    unsupported = tuple(_cell(m) for m in corners if support[m] == 0)
    unavailable = None if interaction_point is not None else "corner_unsupported"
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
        # The corners the data stands on, in the enumeration's own order.
        # Short of 2^K exactly when the interaction is withheld, which is
        # the same condition that withholds it: a corner with no rows would
        # be the model extrapolating, reported as a measurement.
        corner_risks=tuple(
            CornerRisk(cell=_cell(m), risk=float(corner_mean[m]))
            for m in corners if support[m] > 0
        ),
        draws=draws,
        cluster=cluster,
        interaction_unavailable=unavailable,
        interaction_unsupported_cells=unsupported,
        form=resolved,
        form_provenance=form_provenance,
        # The design matrix's own decision, which no ``model=`` names.
        shape_provenance=shapes_settled(assumptions, ORDERED_ENTRY_SHAPE),
    )


# --- internals --------------------------------------------------------------


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
        # By the refusal door and naming the caller's own vocabulary, for
        # the reason ``backdoor._fit_predict`` gives at the same spot.
        raise EstimatorFailure(
            Refusal.UNKNOWN_OPTION,
            option="model", given=model, known=sorted(MODEL_WORDS_OUTCOME),
        )

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
