"""Measurement-error correction numeric end — confusion-matrix inversion.

The structural layer only *flags* measurement error: an identification-path
variable whose ``measurement`` / ``observability`` text names a noisy modality
raises the ``measurement_error_concern`` gap ("regression dilution attenuates
your estimate; Themis does structural ID + gap diagnosis, not de-attenuation").
This module is the DATA counterpart for the cases where de-attenuation is
point-identified from a **known confusion matrix** (a validation study):

- a **misclassified discrete outcome** — ``estimate_measurement_correction``
  (Rogan-Gladen for the binary case);
- a **misclassified binary exposure** — ``estimate_exposure_measurement_correction``
  (the matrix method; Barron 1977, Greenland 1988, Marshall 1990). Because the
  channel acts on the exposure margin of the joint (X, Y) distribution rather
  than the outcome margin, this is a genuinely different correction (the
  recovered exposure marginal is itself an inversion, not an observed count), so
  it lives in its own estimator below — not a flag on the outcome one.

Model (Barron 1977; Greenland 1988; Kuroki & Pearl 2014; Rogan & Gladen 1978
for the binary special case). Let the true outcome be Y* and the observed
(recorded) outcome be Y, both over the same k discrete states. The confusion
matrix M is column-stochastic with

    M[i, j] = P(Y = state_i | Y* = state_j)          (each column sums to 1)

Under **non-differential** misclassification — Y ⊥ (X, Z) | Y*, i.e. the SAME
matrix applies in every treatment arm and covariate stratum — the observed
per-stratum outcome distribution is a linear image of the true one:

    p_obs(· | x, z) = M · p_true(· | x, z)   ⇒   p_true(· | x, z) = M⁻¹ p_obs(· | x, z)

The corrected effect on the query's target value y* is the back-door
standardised risk difference of the *recovered* true distribution:

    effect = Σ_z [ p_true(y* | 1, z) − p_true(y* | 0, z) ] · P(z)

with p_true(· | x, z) = M⁻¹ p_obs(· | x, z) and P(z) the empirical covariate
marginal. For a binary outcome this is exactly Rogan-Gladen applied per
stratum: p_true(1 | x, z) = (p_obs(1 | x, z) + Sp − 1) / (Se + Sp − 1), and
because det(M) = Se + Sp − 1 is constant the whole thing collapses to
``naive_effect / det(M)`` — the classic "non-differential misclassification
attenuates a risk difference by the factor Se+Sp−1" result, run in reverse.

Guards (honest, not silent):

- **Singular channel.** |det(M)| below ``_DET_FLOOR`` ⇒ the matrix is not
  invertible (the measurement carries no usable information about Y*) ⇒
  refuse (``EstimatorFailure``), mirroring the proximal rank guard — no
  fabricated point from a near-degenerate inversion.
- **Out of the simplex.** M⁻¹ p_obs is the method-of-moments estimator; it is
  unbiased but can land outside [0, 1] when the matrix is weakly informative or
  the non-differential assumption is violated. We report it as-is (clipping
  would bias it) and set the ``out_of_simplex`` diagnostic so the caller can
  surface the instability. The bootstrap CI widens accordingly.
- **Positivity.** A covariate stratum present in the marginal but empty in an
  arm has no P(y|x,z) to correct ⇒ positivity refusal rather than a made-up
  cell.

Scope (declared tradeoffs):

- **Outcome** and **binary-exposure** misclassification are both point-identified
  here, under EITHER non-differential OR **differential** misclassification:

  - non-differential — one matrix everywhere (Y ⊥ (X,Z) | Y*, resp. X ⊥ (Y,Z) | X*);
  - differential — the axis a matrix varies over is named by ``differential_by``.
    The OUTCOME channel may depend on the exposure arm (a per-arm matrix M_x,
    "detection bias", the default) or on a back-door **covariate** (a per-covariate-
    stratum matrix M_z — the rate varies by e.g. site/age). The EXPOSURE channel
    may depend on the outcome (a per-outcome-level matrix M_y, "recall bias", the
    default) or on a back-door **covariate** (a per-covariate-stratum matrix M_z).
    The correction inverts the LEVEL-SPECIFIC matrix within each conditioning
    level. Differential misclassification can bias AWAY from the null (non-
    differential only attenuates toward it), so it gets a per-level inversion
    rather than a single de-attenuation factor det(M) — no ``naive/det`` shortcut.

  A **multi-level exposure** confusion matrix, a matrix jointly differential in the
  arm/outcome AND a covariate, and a differential matrix set that does not cover
  every observed conditioning level are deferred.
- **Combined** misclassification — both channels at once — is point-identified here
  too, by inverting the per-stratum (X, Y) joint on BOTH sides,
  ``P_true = M_x⁻¹ P_obs (M_y⁻¹)ᵀ``. It carries one premise the single-channel
  corrections do not: the two error mechanisms are independent given the truth,
  ``X ⊥ Y | (X*, Y*, Z)``. Two separately non-differential channels can still be
  correlated with each other, so this is strictly stronger and is listed as its own
  assumption. A DIFFERENTIAL matrix on either channel is refused rather than
  approximated — the level that selects one matrix is the quantity the other channel
  mismeasures, so the observed table stops being a two-sided product.
- A confusion matrix is DECLARED either way. Handing one over is the claim that
  it is exact — a coding rule fixed by protocol, an error rate quoted by a
  maker — and the bootstrap then propagates the main sample's variability
  alone. Handing over ``{"validation_counts": [[…]]}`` instead is the claim
  that a study counted it: ``counts[i][j]`` subjects known to be at true state
  j were recorded at state i, the matrix is that table's column-normalisation,
  and the bootstrap redraws it every replicate from the Dirichlet each column
  of counts is. The two are different premises and the ledger says which.
  A differential SET is settled one way for all its levels or refused; and a
  redrawn channel that lands singular is a discarded draw under the species
  that names it, counted like any other.
- **Discrete** outcome (a confusion matrix is a discrete-misclassification
  object); continuous mismeasurement belongs to
  ``regression_calibration`` (a linear outcome), ``simex`` (a declared
  nonlinear one) and ``berkson`` (a declared Berkson structure, where the
  answer needs no correcting and what is produced is its price), not to this
  estimator.

The sufficient statistics recorded on the estimate (the confusion matrix, the
per-(arm, stratum) full outcome value-count vectors, and the covariate marginal
counts) are exactly what ``themis.verify_measurement_correction_numeric``
re-inverts — it never re-touches the raw data and never imports this module.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .contract import validate_data
from ..types import envelope_scalar
from ..ledger import Provenance
from .form import NO_OTHER_SHAPES
from .. import refusals
from ..refusals import Refusal, Remedy
from ..refusals import EstimatorFailure
from .resample import (
    FEWEST_DRAWS, DeclaredMatrix, Draws, cluster_labels, resample_indices,
)

# A covariate with more distinct values than this is treated as continuous and
# refused (no empirical stratum for the saturated stratified correction).
# The cap lives beside the per-stratum count that reads it, so a fourth
# reading of "does this column have strata" cannot come out differently
# from the other three.
from .support import MAX_LEVELS
# |det(M)| below this is a non-invertible measurement channel → refuse.
_DET_FLOOR = 1e-6
_TOL = 1e-9


@dataclass(frozen=True)
class MeasurementCorrectionEstimate:
    """Confusion-matrix-corrected effect on the target value, with a bootstrap CI.

    ``point`` is the corrected Σ_z [p_true(y*|1,z) − p_true(y*|0,z)] P(z).
    ``naive_point`` is the same standardisation on the *observed* (attenuated)
    distribution — the biased number the correction replaces, kept for contrast.
    ``det`` is det(M) (= Se+Sp−1 for a binary outcome); ``out_of_simplex`` flags
    a recovered probability outside [0, 1]. ``sufficient_statistics`` carries the
    confusion matrix, per-(arm, stratum) value-count vectors, and the covariate
    marginal counts — everything the numeric verifier re-inverts the point from.

    Under **differential** (per-exposure-arm) misclassification ``differential`` is
    True, ``confusion_matrix`` / ``det`` are the sentinel empty / NaN (there is no
    single matrix), and ``confusion_matrices`` carries one ``(arm, matrix, det)``
    entry per treatment arm — the per-arm matrices the inversion actually used and
    the verifier re-inverts from.
    """
    point: float
    naive_point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    treatment: str
    outcome: str
    adjustment: tuple[str, ...]
    target_value: object
    states: tuple[object, ...]
    confusion_matrix: tuple[tuple[float, ...], ...]
    det: float
    out_of_simplex: bool
    sufficient_statistics: dict = field(default_factory=dict)
    cluster: str | None = None
    #: The replicates this interval was taken over — see
    #: :class:`themis.estimation.resample.Draws`. ``None`` when no
    #: bootstrap ran, which is the one case with no answer to give.
    draws: "Draws | None" = None
    form: str = "confusion_matrix_inversion_backdoor_standardised"
    #: Nothing chose this shape: it IS the method, and the only way to
    #: overrule it is to answer by a different one.
    form_provenance: str = Provenance.INHERENT
    #: Which shapes a lever BESIDE the outcome model settled, by assumption
    #: id. The ids that RESTATE the outcome model's shape take the answer
    #: above; an id here is a different decision, made by a different lever,
    #: and says so itself — :func:`themis.estimation.form.shapes_settled`.
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES
    differential: bool = False
    # The variable the differential matrices vary over (the exposure arm by
    # default, or a back-door covariate); None for the non-differential case.
    differential_by: str | None = None
    # Per-level matrices when ``differential`` — a tuple of
    # (level, matrix, det); empty for the non-differential single-matrix case.
    confusion_matrices: tuple = ()
    differential_levels: tuple = ()


# --- public entry -------------------------------------------------------------


def estimate_measurement_correction(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    confusion_matrix=None,
    states,
    target_value,
    differential: bool = False,
    differential_by: str | None = None,
    confusion_matrices=None,
    differential_levels=None,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> MeasurementCorrectionEstimate:
    """Recover the back-door effect on a misclassified discrete outcome by
    inverting the confusion matrix, per covariate stratum.

    Parameters
    ----------
    data: the main sample carrying the *observed* (misclassified) outcome.
    treatment / outcome: binary X and discrete Y column names.
    adjustment: the back-door adjustment covariates Z (discrete).
    confusion_matrix: (non-differential) k×k, ``M[i][j] = P(Y=states[i] |
        Y*=states[j])``, each column summing to 1 — or
        ``{"validation_counts": [[…]]}``, the study's own tally in the same
        layout, which says the matrix is its column-normalisation and that
        the interval carries the study's uncertainty as well.
    states: the k outcome states in the row/column order of the confusion
        matrix/matrices (must cover every observed outcome value).
    target_value: the query's target outcome value y* — the effect is the
        corrected risk difference of ``P(Y*=y*)``.
    differential: when True, the outcome misclassification is **differential**
        along ``differential_by`` — supply ``confusion_matrices`` +
        ``differential_levels`` instead of ``confusion_matrix``.
    differential_by: which variable the differential matrices vary over. Defaults
        to the **exposure arm** (``treatment``) — detection bias, ``M_x``. May
        instead be a back-door **covariate** in ``adjustment`` — the
        misclassification rate varies by that covariate stratum (e.g. by site),
        ``M_z``, and the correction inverts the covariate-level-specific matrix
        within each stratum.
    confusion_matrices / differential_levels: (differential) a list of k×k
        matrices and the ``differential_by`` values they apply to, aligned 1:1;
        ``M[i][j] = P(Y=states[i] | Y*=states[j], differential_by=level)``. The
        levels must cover every observed value of ``differential_by``.
    ci_bootstrap / ci_level / random_state / cluster: percentile-bootstrap
        controls. Each matrix is held fixed across resamples where it was
        declared as one and redrawn from its tally where a study counted it.

    Raises
    ------
    EstimatorFailure: differential requested but the matrix set is incomplete /
        misaligned / does not cover every ``differential_by`` level; a
        ``differential_by`` that is neither the exposure nor an adjustment
        covariate; non-binary treatment; continuous adjustment covariate;
        malformed / non-stochastic / singular confusion matrix; states not
        covering the observed outcome; target value absent; a positivity violation
        (a contributing stratum empty in an arm).
    """
    states = tuple(envelope_scalar(s) for s in states)
    k = len(states)
    if k < 2:
        raise EstimatorFailure(
            Refusal.TOO_FEW_INPUTS,
            what="outcome states", needed=2, given=k,
        )
    if len(set(states)) != k:
        raise EstimatorFailure(
            Refusal.DUPLICATE_INPUT,
            what="outcome states", given=list(states),
        )
    target_value = envelope_scalar(target_value)
    if target_value not in states:
        raise EstimatorFailure(
            Refusal.TARGET_VALUE_ABSENT,
            column=outcome, role=refusals.QueryRole.OUTCOME,
            value=target_value, observed=list(states),
        )

    # The differential axis: the variable whose value selects the confusion
    # matrix. Defaults to the exposure arm (detection bias); may instead be a
    # back-door covariate (misclassification rate varies by that stratum). The
    # inverse maps are keyed by ``_level_key`` so a bool/0-1 level matches the
    # data value the contract coerced.
    Minv_by_level: dict = {}
    differential_axis: str | None = None
    if differential:
        axis = differential_by if differential_by is not None else treatment
        if axis != treatment and axis not in adjustment:
            raise EstimatorFailure(
                Refusal.DIFFERENTIAL_BY_UNKNOWN,
                axis=axis, home=treatment, adjustment=list(adjustment),
            )
        differential_axis = axis
        prepared = _prepare_differential(
            confusion_matrices, differential_levels, k,
            channel=refusals.QueryRole.OUTCOME, axis=axis,
        )
        Minv_by_level = {_level_key(lvl): Minv for (lvl, _dm, _d, Minv) in prepared}
        declared_by_level = {_level_key(lvl): dm for (lvl, dm, *_r) in prepared}
        if axis == treatment:
            arm_bools = {bool(lvl) for (lvl, *_rest) in prepared}
            if len(prepared) != 2 or arm_bools != {False, True}:
                raise EstimatorFailure(
                    Refusal.DIFFERENTIAL_LEVELS_NOT_THE_AXIS_LEVELS,
                    axis=axis, expected=[False, True],
                    given=[lvl for (lvl, *_r) in prepared],
                    remedies=[(Remedy.CHANGE_INPUT, "differential_levels")],
                )
            by_arm_records = [
                _matrix_record(_dm, _d, arm=int(bool(lvl)))
                for (lvl, _dm, _d, _inv) in sorted(prepared, key=lambda t: bool(t[0]))
            ]
            suff_extra: dict = {
                "differential": True,
                "confusion_matrices_by_arm": by_arm_records,
            }
            matrices_out: tuple = tuple(by_arm_records)
            differential_by_out: str | None = None
        else:
            by_level_records = [
                _matrix_record(_dm, _d, level=envelope_scalar(lvl))
                for (lvl, _dm, _d, _inv) in prepared
            ]
            suff_extra = {
                "differential": True,
                "differential_by": differential_axis,
                "confusion_matrices_by_level": by_level_records,
            }
            matrices_out = tuple(by_level_records)
            differential_by_out = differential_axis
        det = float("nan")
        confusion_matrix_out: tuple = ()
        declared_out = prepared[0][1]
    else:
        declared_out = _declare_matrix(
            confusion_matrix, k, channel=refusals.QueryRole.OUTCOME)
        M = declared_out.matrix
        det = float(np.linalg.det(M))
        if abs(det) < _DET_FLOOR:
            raise EstimatorFailure(
                Refusal.SINGULAR_CONFUSION_MATRIX,
                role=refusals.QueryRole.OUTCOME,
                determinant=abs(det), floor=_DET_FLOOR,
            )
        Minv = np.linalg.inv(M)
        differential_axis = treatment            # both arms share the one matrix
        Minv_by_level = {_level_key(False): Minv, _level_key(True): Minv}
        # The same OBJECT under both keys, not a copy: the redraw walks this
        # map and gives one declaration one draw, so an arm-keyed map built
        # from one matrix stays the one channel it was declared as.
        declared_by_level = {_level_key(False): declared_out,
                             _level_key(True): declared_out}
        confusion_matrix_out = tuple(tuple(float(v) for v in row) for row in M)
        suff_extra = _matrix_record(declared_out, det, name="confusion_matrix")
        matrices_out = ()
        differential_by_out = None

    adjustment = tuple(sorted(adjustment))
    presence = (cluster,) if cluster is not None else ()
    contract = validate_data(
        data, required_columns={treatment, outcome, *adjustment},
        presence_columns=presence,
    )
    df = contract.data

    _require_binary(df[treatment], treatment)
    for v in adjustment:
        _require_discrete(df[v], v)

    observed_states = set(
        envelope_scalar(v) for v in pd.unique(df[outcome].dropna())
    )
    missing = observed_states - set(states)
    if missing:
        raise EstimatorFailure(
            Refusal.STATES_INCOMPLETE, column=outcome,
            values=sorted(map(str, missing)), states=states,
        )

    groups = (
        cluster_labels(df, cluster, expected_n=len(df))
        if cluster is not None else None
    )

    target_index = states.index(target_value)
    point, naive, oos, suff = _formula(
        df, treatment=treatment, outcome=outcome, adjustment=adjustment,
        states=states, Minv_by_level=Minv_by_level,
        differential_axis=differential_axis, target_index=target_index,
    )

    ci_lower = ci_upper = None
    draws = Draws(ci_bootstrap) if ci_bootstrap > 0 else None
    if draws is not None:
        ci_lower, ci_upper = _bootstrap(
            df, treatment=treatment, outcome=outcome, adjustment=adjustment,
            states=states, Minv_by_level=Minv_by_level,
            declared_by_level=declared_by_level,
            differential_axis=differential_axis, target_index=target_index,
            groups=groups,
            draws=draws, ci_level=ci_level, random_state=random_state,
        )

    assumptions = _assumptions(
        adjustment, cluster, differential=differential,
        differential_axis=differential_axis, treatment=treatment,
        declared=declared_out, mismeasured=outcome,
    )
    return MeasurementCorrectionEstimate(
        point=point,
        naive_point=naive,
        ci_lower=ci_lower, ci_upper=ci_upper, ci_level=ci_level,
        method="measurement_error_correction",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=treatment, outcome=outcome,
        adjustment=adjustment,
        target_value=target_value,
        states=states,
        confusion_matrix=confusion_matrix_out,
        det=det,
        out_of_simplex=oos,
        sufficient_statistics={
            **suff,
            **suff_extra,
            "states": [envelope_scalar(s) for s in states],
            "target_value": target_value,
            "target_index": target_index,
            "adjustment_vars": list(adjustment),
        },
        cluster=cluster,
        draws=draws,
        differential=differential,
        differential_by=differential_by_out,
        confusion_matrices=matrices_out,
        differential_levels=(
            tuple(envelope_scalar(v) for v in differential_levels)
            if differential else ()
        ),
    )


# --- formula core -------------------------------------------------------------


def _formula(
    df: pd.DataFrame, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], states: tuple, Minv_by_level: dict,
    differential_axis: str, target_index: int,
) -> tuple[float, float, bool, dict]:
    """Corrected + naive standardised effect on the target value, plus the
    per-stratum sufficient statistics.

    Enumeration is driven by the covariate marginal P(z); each contributing z
    must have support in BOTH arms (positivity). Each (arm, z) cell is inverted
    with the matrix selected by ``differential_axis``'s value in that cell:
    ``Minv_by_level[_level_key(value)]`` — the same matrix everywhere in the
    non-differential case, per-arm under detection bias, per-covariate-stratum
    when the differential axis is a covariate. ``out_of_simplex`` is True if any
    recovered p_true component lands outside [0, 1]."""
    x = _as_binary(df[treatment])
    yvals = df[outcome].map(envelope_scalar)
    n_total = len(df)

    marginal = _marginal(df, adjustment)              # {z_key: prob}
    marginal_counts = _marginal_counts(df, adjustment)  # {z_key: count}

    # One name for one fact: ``None`` IS "the axis is the exposure arm", so
    # the position of the axis column carries the branch as well.
    axis_idx = (
        None if differential_axis == treatment
        else adjustment.index(differential_axis)
    )

    strata_records: list[dict] = []
    corrected = 0.0
    naive = 0.0
    oos = False

    for z_key, p_z in marginal.items():
        if p_z <= 0:
            continue
        z_mask = _stratum_mask(df, adjustment, z_key)
        arm_true = {}
        for arm in (1, 0):
            mask = z_mask & (x == bool(arm))
            n = int(mask.sum())
            if n == 0:
                raise EstimatorFailure(
                    Refusal.INSUFFICIENT_SUPPORT,
                    cells=[{treatment: bool(arm),
                            **dict(zip(adjustment, _json_key(z_key)))}],
                    quantity=(
                        f"P({outcome} | {treatment}, "
                        + ", ".join(adjustment) + ")"
                    ),
                )
            counts = _value_counts(yvals[mask.to_numpy()], states)
            p_obs = counts.astype(float) / n
            lvl_value = (
                bool(arm) if axis_idx is None
                else envelope_scalar(z_key[axis_idx])
            )
            Minv = Minv_by_level.get(_level_key(lvl_value))
            if Minv is None:
                raise EstimatorFailure(
                    Refusal.DIFFERENTIAL_LEVEL_UNCOVERED,
                    axis=differential_axis, level=lvl_value,
                )
            p_true = Minv @ p_obs
            if (p_true < -_TOL).any() or (p_true > 1 + _TOL).any():
                oos = True
            arm_true[arm] = float(p_true[target_index])
            strata_records.append({
                "arm": arm,
                "z": list(_json_key(z_key)),
                "counts": [int(c) for c in counts],
                "n": n,
            })
        corrected += (arm_true[1] - arm_true[0]) * p_z
        # Naive: the observed target-value risk, standardised — the biased number.
        naive += (
            _obs_target_risk(df, z_mask, x, yvals, states, target_index, 1)
            - _obs_target_risk(df, z_mask, x, yvals, states, target_index, 0)
        ) * p_z

    suff = {
        "strata": sorted(strata_records, key=_stratum_sort),
        "marginal_counts": [
            {"z": list(_json_key(k)), "count": c}
            for k, c in sorted(marginal_counts.items(), key=lambda kv: str(kv[0]))
        ],
        "marginal_total": n_total,
    }
    return corrected, naive, oos, suff


def _obs_target_risk(df, z_mask, x, yvals, states, target_index, arm) -> float:
    mask = z_mask & (x == bool(arm))
    n = int(mask.sum())
    counts = _value_counts(yvals[mask.to_numpy()], states)
    return float(counts[target_index]) / n if n else 0.0


def _value_counts(series: pd.Series, states: tuple) -> np.ndarray:
    """Count of each state (in ``states`` order) among ``series`` values.

    Uses a plain dict (not ``Series.get``) so integer state keys are matched by
    label, not by the deprecated positional fallback."""
    counts = series.value_counts().to_dict()
    return np.array([int(counts.get(s, 0)) for s in states], dtype=float)


def _marginal(df: pd.DataFrame, vars_: tuple[str, ...]) -> dict[tuple, float]:
    n = len(df)
    if not vars_:
        return {(): 1.0}
    counts = _marginal_counts(df, vars_)
    return {k: v / n for k, v in counts.items()}


def _marginal_counts(df: pd.DataFrame, vars_: tuple[str, ...]) -> dict[tuple, int]:
    if not vars_:
        return {(): len(df)}
    out: dict[tuple, int] = {}
    sub = df[list(vars_)]
    for key, idx in sub.groupby(list(vars_), sort=True, observed=True).indices.items():
        out[_as_tuple(key, len(vars_))] = len(idx)
    return out


# --- bootstrap ----------------------------------------------------------------


def _bootstrap(
    df: pd.DataFrame, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], states: tuple, Minv_by_level: dict,
    declared_by_level: dict,
    differential_axis: str, target_index: int, groups: np.ndarray | None,
    draws: Draws, ci_level: float, random_state: int,
) -> tuple[float | None, float | None]:
    """Percentile bootstrap of the corrected effect — resample rows (or
    clusters), recompute the per-stratum correction, collect the point.
    Draws that induce a positivity failure, or a redrawn channel that
    carries no information about the truth, are dropped and filed under the
    refusal that dropped them.

    The matrices are held fixed where the caller declared them and redrawn
    from their validation tallies where a study counted them — the two
    sources of variation this interval is over, drawn independently because
    the main sample and the validation study are two studies. The rows are
    drawn first so a replicate's sample does not depend on whether a study
    was declared."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    measured = _any_measured(declared_by_level)
    pts: list[float] = []
    for _ in draws:
        idx = resample_indices(n, rng, groups=groups)
        sub = df.iloc[idx]
        try:
            inverses = (
                _inverses(declared_by_level, rng,
                          channel=refusals.QueryRole.OUTCOME)
                if measured else Minv_by_level
            )
            pt, _naive, _oos, _suff = _formula(
                sub, treatment=treatment, outcome=outcome, adjustment=adjustment,
                states=states, Minv_by_level=inverses,
                differential_axis=differential_axis, target_index=target_index,
            )
        except EstimatorFailure as exc:
            draws.unusable(exc.failure_type)
            continue
        pts.append(pt)
        draws.usable()
    if not draws.enough:
        return (None, None)
    arr = np.asarray(pts)
    alpha = (1 - ci_level) / 2
    return float(np.quantile(arr, alpha)), float(np.quantile(arr, 1 - alpha))


# --- guards / coercion --------------------------------------------------------


def _validate_matrix(confusion_matrix, k: int, *,
                     channel: refusals.QueryRole) -> np.ndarray:
    """``channel`` names the variable this matrix measures, so a rejection
    says WHICH one is malformed instead of leaving the caller to guess.

    Required, with no default. It used to be optional, and an omitted label
    printed as "outcome states" — so the exposure correction, which never
    passed one, rejected the EXPOSURE's matrix by the outcome's name. A
    default that silently means one of the values is not a default; it is
    that value, chosen where the choice is invisible."""
    what = f"{channel} confusion matrix"
    try:
        M = np.array(confusion_matrix, dtype=float)
    except (TypeError, ValueError) as exc:
        raise EstimatorFailure(
            Refusal.MATRIX_NOT_NUMERIC, what=what,
            recorded={"numpy_said": str(exc)},
        )
    if M.shape != (k, k):
        raise EstimatorFailure(
            Refusal.MATRIX_WRONG_SHAPE,
            what=what, expected=f"{k}×{k}",
            given="×".join(str(n) for n in M.shape),
        )
    if not np.isfinite(M).all():
        raise EstimatorFailure(Refusal.MATRIX_NOT_FINITE, what=what)
    if (M < -_TOL).any() or (M > 1 + _TOL).any():
        raise EstimatorFailure(Refusal.MATRIX_NOT_PROBABILITIES, what=what)
    col_sums = M.sum(axis=0)
    if not np.allclose(col_sums, 1.0, atol=1e-6):
        raise EstimatorFailure(
            Refusal.MATRIX_NOT_COLUMN_STOCHASTIC,
            what=what, sums=[round(float(c), 4) for c in col_sums],
        )
    return M


#: The premise family every confusion matrix declares under, whichever
#: channel it measures — see :meth:`DeclaredMatrix.premise`.
MATRIX_PREMISE = "confusion_matrix"


def _declare_matrix(given, k: int, *,
                    channel: refusals.QueryRole) -> DeclaredMatrix:
    """One channel's declaration: the matrix the correction inverts, and the
    validation tally it was counted in where the caller supplied one.

    The two guards stay apart on purpose. What a TALLY can be wrong about is
    its own — a negative count, a true state nobody stood at — and is judged
    where the tally is read; what a MATRIX can be wrong about is judged here
    as it always was, on the matrix the caller wrote or on the one the tally
    normalises to. A single guard would have to phrase a fault in one of
    them as a fault in the other.
    """
    raw, counts = DeclaredMatrix.declared(
        given, what=f"{channel} confusion matrix")
    return DeclaredMatrix(matrix=_validate_matrix(raw, k, channel=channel),
                          counts=counts)


def _inverses(declared_by_level: dict, rng: np.random.Generator, *,
              channel: refusals.QueryRole) -> dict:
    """One replicate's inverse maps — each level's matrix redrawn from the
    study that counted it, then inverted.

    Raises the singular-channel refusal the fixed matrix raises, so a draw
    whose redrawn channel carries no usable information about the truth
    leaves by the door every other unusable draw leaves by and is counted
    under the species that names it. A study small enough for its Dirichlet
    to reach there has not established an invertible channel, and how often
    it happened is on the record.

    One draw per DECLARATION, not per key. A non-differential channel is
    one matrix reached under every level's key, and drawing it once per key
    would turn it into a differential channel the caller never declared —
    each level's inversion using a different matrix, and the interval
    widening for a variation that is not there.
    """
    drawn: dict[int, np.ndarray] = {}
    out: dict = {}
    for key, declared in declared_by_level.items():
        inverse = drawn.get(id(declared))
        if inverse is None:
            M = np.asarray(declared.draw(rng), dtype=float)
            det = float(np.linalg.det(M))
            if abs(det) < _DET_FLOOR:
                raise EstimatorFailure(
                    Refusal.SINGULAR_CONFUSION_MATRIX,
                    role=channel, determinant=abs(det), floor=_DET_FLOOR,
                )
            inverse = drawn[id(declared)] = np.linalg.inv(M)
        out[key] = inverse
    return out


def _any_measured(declared_by_level: dict) -> bool:
    """Whether any matrix on this channel was counted rather than fixed.

    The gate on redrawing at all, and so the gate on consuming randomness:
    a channel nobody counted leaves the bootstrap's draw sequence exactly
    where it was, which is what keeps every interval this package has ever
    reported reproducible from its record.
    """
    return any(d.measured for d in declared_by_level.values())


def _matrix_record(declared: DeclaredMatrix, det: float, *,
                   name: str = "matrix", **named) -> dict:
    """One matrix as a record carries it: the numbers the correction
    inverted, its determinant, whatever names the level it applies to — and
    the tally it was counted in, where a study counted it.

    Absent rather than null when no study did, because absence is what the
    optional keys beside it have always meant here, and a null would be a
    second way to say the same thing.

    ``name`` is what the matrix is called in this record — a per-level entry
    says ``matrix`` and the single-matrix block says ``confusion_matrix``.
    Those names are read by the verifier and by two renderers, so they are
    the callers' to keep; what is NOT theirs to keep is remembering the
    tally beside it, which is why one function writes both.
    """
    record = {
        **named,
        name: [[float(v) for v in row] for row in declared.matrix],
        "det": det,
    }
    counts = declared.as_lists()
    if counts is not None:
        record["validation_counts"] = counts
    return record


def _level_key(v):
    """Value-based hashable key for a conditioning-variable level.

    Conditioning levels are matched to observed data values BY VALUE, so a bool
    is collapsed onto its numeric image (``False`` ≡ ``0``, ``True`` ≡ ``1``) —
    the data contract coerces a binary column to bool, and a caller who wrote the
    levels as ``[0, 1]`` must still match. This is deliberately the opposite of
    the verifier's type-strict ``_state_key``: here 0 and False are the same
    conditioning level; a caller who lists both is flagged as a duplicate."""
    if isinstance(v, bool):
        return ("n", float(v))
    if isinstance(v, (int, float)):
        return ("n", float(v))
    return ("s", str(v))


def _prepare_differential(confusion_matrices, differential_levels, k: int, *,
                          channel: refusals.QueryRole,
                          axis: str) -> list[tuple]:
    """Validate a differential (per-level) matrix set: a list of column-stochastic,
    invertible k×k matrices aligned 1:1 with a list of conditioning-variable
    levels. Returns ``[(level_py, M, det, Minv), ...]`` in the given order.

    Raises ``EstimatorFailure`` on a missing / misaligned / malformed / singular
    set — never falls back to a single matrix.

    ``axis`` is the differential axis's COLUMN NAME, and reaches five of those
    refusals. It used to be an English phrase each caller assembled — "exposure
    arm", "outcome value", ``f"covariate {axis!r}"`` — which put a fragment of
    the sentence at the call site, in one language, saying less than the column
    name it was built from.

    Two of the five faults here are not this estimator's at all once the axis
    is a slot rather than prose: a level list shorter than two, and a level
    named twice, are what every argument can be, and are counted as that."""
    if confusion_matrices is None or differential_levels is None:
        raise EstimatorFailure(
            Refusal.DIFFERENTIAL_SPEC_INCOMPLETE,
            missing=[
                name for name, given in (
                    ("confusion_matrices=", confusion_matrices),
                    ("differential_levels=", differential_levels),
                ) if given is None
            ],
        )
    mats = list(confusion_matrices)
    levels = [envelope_scalar(v) for v in differential_levels]
    if len(mats) != len(levels):
        raise EstimatorFailure(
            Refusal.DIFFERENTIAL_LEVELS_MISMATCH,
            axis=axis, matrices=len(mats), levels=len(levels),
        )
    # Not the spec's own incompleteness: both halves are here and they agree
    # with each other. What "differential" means is that the matrix differs
    # BETWEEN levels, and one level has nothing to differ from — which is
    # every other argument's too-few fault and is counted as one.
    if len(mats) < 2:
        raise EstimatorFailure(
            Refusal.TOO_FEW_INPUTS,
            what="differential_levels=", needed=2, given=len(levels),
            recorded={"axis": axis, "levels": levels},
        )
    if len({_level_key(v) for v in levels}) != len(levels):
        raise EstimatorFailure(
            Refusal.DUPLICATE_INPUT,
            what="differential_levels=", given=levels,
            recorded={"axis": axis},
        )
    out: list[tuple] = []
    for lvl, cm in zip(levels, mats):
        declared = _declare_matrix(cm, k, channel=channel)
        det = float(np.linalg.det(declared.matrix))
        if abs(det) < _DET_FLOOR:
            raise EstimatorFailure(
                Refusal.SINGULAR_CONFUSION_MATRIX_IN_STRATUM,
                role=channel, axis=axis, level=lvl,
                determinant=abs(det), floor=_DET_FLOOR,
            )
        out.append((lvl, declared, det, np.linalg.inv(declared.matrix)))
    # One channel, settled one way. A set that counts some levels in a study
    # and fixes the rest produces an interval carrying part of a study, which
    # is neither of the two things the premise can say and neither of the two
    # a reader can check.
    counted = [lvl for (lvl, d, *_r) in out if d.measured]
    if counted and len(counted) != len(out):
        raise EstimatorFailure(
            Refusal.MATRIX_SET_DECLARED_TWO_WAYS,
            axis=axis, counted=counted,
            fixed=[lvl for (lvl, d, *_r) in out if not d.measured],
            remedies=[(Remedy.CHANGE_INPUT, "confusion_matrices")],
        )
    return out


def _require_binary(col: pd.Series, name: str) -> None:
    vals = set(pd.unique(col.dropna()))
    if not vals <= {0, 1, True, False, 0.0, 1.0}:
        raise EstimatorFailure(
            Refusal.TREATMENT_NOT_BINARY,
            treatment=name, levels=sorted(vals, key=str),
        )


def _require_discrete(col: pd.Series, name: str) -> None:
    k = col.nunique(dropna=True)
    if k > MAX_LEVELS:
        raise EstimatorFailure(
            Refusal.CONTINUOUS_ADJUSTMENT,
            column=name, levels=k, cap=MAX_LEVELS,
        )


def _as_binary(col: pd.Series) -> np.ndarray:
    return col.to_numpy().astype(bool)


def _stratum_mask(df: pd.DataFrame, vars_: tuple[str, ...], key: tuple) -> pd.Series:
    if not vars_:
        return pd.Series(np.ones(len(df), dtype=bool), index=df.index)
    mask = pd.Series(np.ones(len(df), dtype=bool), index=df.index)
    for v, val in zip(vars_, key):
        mask &= (df[v].to_numpy() == val)
    return mask


def _as_tuple(key, arity: int) -> tuple:
    if arity == 1:
        return (key,)
    return tuple(key)


def _json_key(key: tuple) -> tuple:
    return tuple(envelope_scalar(v) for v in key)


def _stratum_sort(rec: dict):
    return (rec["arm"], [str(v) for v in rec["z"]])


def _assumptions(
    adjustment: tuple[str, ...], cluster: str | None, *, differential: bool = False,
    differential_axis: str | None = None, treatment: str | None = None,
    declared: DeclaredMatrix, mismeasured: str,
) -> tuple[str, ...]:
    """The premises this correction rests on, including WHICH axis it varied on.

    Same shape as :func:`_exposure_assumptions`, and it was not: this one took
    only ``differential: bool``, so the string it could write was fixed at the
    default axis. The exposure arm is only the default — the outcome channel's
    matrix may vary over a back-door covariate instead — and a boolean has
    nowhere to put which, so a run that inverted a per-stratum matrix set
    disclosed itself as a per-arm one. That is not a mis-worded string but a
    signature that cannot say what the function exists to say, which is why
    the fix is the parameter rather than a branch on top of it.

    The premise about where the MATRIX came from used to restate that shape
    a second time — one id for a single matrix, one for a per-arm set, one
    for a per-stratum set — and every one of them ended "from a validation
    study" while the interval held the matrix perfectly still. Two faults
    in one string: it restated what ``mech`` beside it already says, and it
    named a study whose uncertainty nothing carried. It is now the
    declaration's own premise, which says which of the two things was true
    and says it about the column that was mismeasured.
    """
    if not differential:
        mech = "non_differential_misclassification_Y_indep_XZ_given_Ytrue"
    elif differential_axis is None or differential_axis == treatment:
        mech = "differential_misclassification_by_exposure_arm_M_depends_on_X"
    else:
        mech = f"differential_misclassification_by_covariate_{differential_axis}"
    out = [
        mech,
        declared.premise(MATRIX_PREMISE, mismeasured),
        "confusion_matrix_invertible",
        "consistency_of_potential_outcomes",
        "positivity_every_contributing_stratum_has_support",
    ]
    if adjustment:
        out.append("backdoor_adjustment_{" + ",".join(adjustment) + "}")
    if cluster is not None:
        out.append(f"ci_via_pairs_cluster_bootstrap_on_{cluster}")
    return tuple(out)


# ==============================================================================
# Exposure (treatment) misclassification — the matrix method.
# ==============================================================================
#
# The channel now sits on the EXPOSURE. Let X* be the true binary exposure, X
# the observed (misclassified) one, both over the two states in ``states`` order.
# The 2×2 confusion matrix is column-stochastic with
#
#     M[i, j] = P(X = state_i | X* = state_j)          (each column sums to 1)
#
# Under **non-differential** exposure misclassification — X ⊥ (Y, Z) | X*, i.e.
# the SAME matrix applies regardless of the outcome and covariate stratum — the
# observed joint (X, Y) is a linear image of the true joint (X*, Y) *along the
# exposure axis*, one outcome column at a time:
#
#     [P(X=0, Y=y | z), P(X=1, Y=y | z)]ᵀ = M · [P(X*=0, Y=y | z), P(X*=1, Y=y | z)]ᵀ
#   ⇒ [P(X*=0, Y=y | z), P(X*=1, Y=y | z)]ᵀ = M⁻¹ · [P(X=0, Y=y | z), P(X=1, Y=y | z)]ᵀ
#
# Recovering the whole 2×k true joint per stratum, the corrected effect on the
# outcome target value y* is the back-door standardised risk difference of the
# *recovered true exposure*:
#
#     P(Y=y* | X*=x, z) = P(X*=x, Y=y* | z) / Σ_y P(X*=x, Y=y | z)
#     effect = Σ_z [ P(Y=y* | X*=1, z) − P(Y=y* | X*=0, z) ] · P(z)
#
# Unlike the outcome case, the denominator P(X*=x | z) is ITSELF an inversion
# (Σ over the recovered outcome columns), not an observed count — the reason this
# is a distinct estimator and not a flag. There is no ``naive/det`` shortcut:
# the exposure attenuation depends on the confounding structure, so the naive
# number is the genuine observed back-door RD on X, kept for contrast.


@dataclass(frozen=True)
class ExposureMeasurementCorrectionEstimate:
    """Confusion-matrix-corrected effect for a MISCLASSIFIED DISCRETE EXPOSURE.

    Mirrors :class:`MeasurementCorrectionEstimate` but inverts the channel on
    the *exposure* margin of the (X, Y) joint per covariate stratum (the matrix
    method; Barron 1977, Greenland 1988, Marshall 1990).

    ``risks`` is the primitive: the back-door standardised risk of the target
    value at each exposure level, ``Σ_z P(Y=y*|X*=states[a], z) P(z)``, recovered
    from the observed joint. Everything else is read off it. ``point`` is a
    contrast against the reference level ``states[0]`` — for a binary exposure
    ``risks[1] − risks[0]``, the risk difference this class has always carried;
    with more levels, the contrast at the queried level, or ``None`` when the
    caller named none. ``dose_response_curve`` carries one entry per non-
    reference level and is empty for a binary exposure, whose curve would be a
    single point restating ``point``.

    ``naive_point`` and each entry's ``naive_*`` are the same standardisation on
    the OBSERVED (misclassified) exposure — the biased numbers the correction
    replaces (no ``naive/det`` shortcut exists here). ``states`` are the kx
    exposure states in the row/column order of ``confusion_matrix``, reference
    first; ``outcome_states`` are the k outcome states in the joint-table column
    order. ``det`` is det(M); ``out_of_simplex`` flags a recovered joint cell
    outside [0, 1]. ``sufficient_statistics`` carries the matrix, per-stratum
    full kx×k (X, Y) joint count tables, and the covariate marginal counts —
    everything the numeric verifier re-inverts every level's risk from.

    Under **differential** exposure misclassification ``differential`` is True,
    ``confusion_matrix`` / ``det`` are the sentinel empty / NaN, and
    ``confusion_matrices`` carries the per-level matrices the inversion used. The
    differential axis is named by ``differential_by``: by the **outcome** (recall
    bias, the default — one ``(outcome_value, matrix, det)`` entry per outcome
    level, the joint's column for outcome y inverted with M_y) or by a back-door
    **covariate** (the matrix varies by e.g. site — one ``(level, matrix, det)``
    entry per covariate level, every column within a stratum inverted with that
    stratum's M_z).
    """
    point: float | None
    naive_point: float | None
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    treatment: str
    outcome: str
    adjustment: tuple[str, ...]
    target_value: object
    states: tuple[object, ...]
    outcome_states: tuple[object, ...]
    confusion_matrix: tuple[tuple[float, ...], ...]
    det: float
    out_of_simplex: bool
    #: The standardised risk at each level, indexed as ``states`` is.
    risks: tuple[float, ...] = ()
    naive_risks: tuple[float, ...] = ()
    #: One entry per non-reference level; empty for a binary exposure.
    dose_response_curve: tuple = ()
    sufficient_statistics: dict = field(default_factory=dict)
    cluster: str | None = None
    #: The replicates the interval — and every band on the curve — was
    #: taken over; see :class:`themis.estimation.resample.Draws`. One
    #: record because one loop drew for all of them. ``None`` when no
    #: bootstrap ran, which is the one case with no answer to give.
    draws: "Draws | None" = None
    form: str = "exposure_confusion_matrix_inversion_backdoor_standardised"
    #: Nothing chose this shape: it IS the method, and the only way to
    #: overrule it is to answer by a different one.
    form_provenance: str = Provenance.INHERENT
    #: Which shapes a lever BESIDE the outcome model settled, by assumption
    #: id. The ids that RESTATE the outcome model's shape take the answer
    #: above; an id here is a different decision, made by a different lever,
    #: and says so itself — :func:`themis.estimation.form.shapes_settled`.
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES
    differential: bool = False
    # The variable the differential matrices vary over (the outcome by default —
    # recall bias — or a back-door covariate); None for the non-differential case.
    differential_by: str | None = None
    # Per-level matrices when ``differential`` — a tuple of (level, matrix, det);
    # empty for the non-differential case.
    confusion_matrices: tuple = ()
    differential_levels: tuple = ()


def estimate_exposure_measurement_correction(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    confusion_matrix=None,
    states,
    target_value,
    differential: bool = False,
    differential_by: str | None = None,
    confusion_matrices=None,
    differential_levels=None,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> ExposureMeasurementCorrectionEstimate:
    """Recover the back-door effect of a misclassified discrete exposure by
    inverting the confusion matrix on the exposure margin, per covariate stratum.

    The exposure may have any number of levels k ≥ 2. Nothing in the matrix
    method is binary — a stratum's joint is inverted column by column,
    ``Minv @ p_obs[:, y]``, at whatever width the channel has. What a polytomous
    exposure changes is the SHAPE OF THE ANSWER: with k levels there is no
    single "the" difference, so the estimate carries the standardised risk at
    every level and contrasts them against ``states[0]``. A binary exposure
    reduces to the one risk difference exactly, and reports it as ``point`` the
    way it always has.

    Parameters
    ----------
    data: the main sample carrying the *observed* (misclassified) exposure.
    treatment / outcome: binary X and discrete Y column names.
    adjustment: the back-door adjustment covariates Z (discrete).
    confusion_matrix: (non-differential) k×k over the exposure's levels,
        ``M[i][j] = P(X=states[i] | X*=states[j])``, each column summing to 1.
    states: the exposure states in the row/column order of the confusion
        matrix/matrices. ``states[0]`` is the REFERENCE level every contrast is
        taken against — a binary exposure must be ``[control, treated]`` (so
        ``states[1]`` is do(X)=treated), and with more than two levels the
        caller's ordering IS the declaration of which level is the reference.
    target_value: the query's target outcome value y* — the effect is the
        corrected risk difference of ``P(Y=y*)`` between the recovered exposures.
    differential: when True, the exposure misclassification is **differential**
        along ``differential_by`` — supply ``confusion_matrices`` +
        ``differential_levels`` instead of ``confusion_matrix``.
    differential_by: which variable the differential matrices vary over. Defaults
        to the **outcome** (recall bias, ``M_y``). May instead be a back-door
        adjustment covariate, in which case the exposure-misclassification rate
        varies by that covariate stratum (e.g. by measurement site), and the
        matrix that inverts a stratum's joint is that stratum's own ``M_z``.
    confusion_matrices / differential_levels: (differential) a list of 2×2
        matrices and the ``differential_by`` values they apply to, aligned 1:1;
        ``M[i][j] = P(X=states[i] | X*=states[j], differential_by=level)``. By the
        outcome the levels must be exactly the observed outcome values (each
        outcome column inverted with its M_y); by a covariate they must cover
        every observed covariate value (each stratum inverted with its M_z).
    ci_bootstrap / ci_level / random_state / cluster: percentile-bootstrap
        controls. Each matrix is held fixed across resamples where it was
        declared as one and redrawn from its tally where a study counted it.

    Raises
    ------
    EstimatorFailure: differential requested but the matrix set is incomplete /
        misaligned / does not cover every observed differential level; a
        ``differential_by`` that is neither the outcome nor an adjustment
        covariate; exposure states not a binary ``[control, treated]`` pair;
        observed exposure not covered by the states; continuous / high-cardinality
        outcome; continuous adjustment covariate; malformed / non-stochastic /
        singular confusion matrix; target value absent; a positivity violation (a
        contributing stratum empty in an observed arm); a degenerate recovered
        exposure marginal (≤ 0, the conditional risk is undefined).
    """
    states = tuple(envelope_scalar(s) for s in states)
    if len(states) < 2:
        raise EstimatorFailure(
            Refusal.TOO_FEW_INPUTS,
            what="states=", needed=2, given=len(states),
            remedies=[(Remedy.CHANGE_INPUT, "states")],
        )
    if len(set(states)) != len(states):
        raise EstimatorFailure(
            Refusal.DUPLICATE_INPUT,
            what="states=", given=list(states),
            remedies=[(Remedy.CHANGE_INPUT, "states")],
        )
    kx = len(states)
    # No cap on kx, and the outcome side has one. The asymmetry is the point:
    # ``outcome_states`` is READ FROM THE DATA, so an unbounded read needs a
    # bound, while the exposure's states are DECLARED by the caller alongside a
    # matching kx×kx matrix — a channel nobody could write down is one
    # ``_validate_matrix`` already refuses by shape.
    #
    # The binary arm order stays enforced: with two states there is a
    # ``[control, treated]`` convention to be wrong about, and every number this
    # estimator has ever shipped was signed by it. With more levels there is no
    # such convention to read — the caller's ordering IS the declaration, and
    # ``states[0]`` is the reference the contrasts are taken against.
    if kx == 2 and (bool(states[0]) is not False or bool(states[1]) is not True):
        raise EstimatorFailure(
            Refusal.ARM_ORDER_UNREADABLE,
            what="states=", given=list(states),
            remedies=[(Remedy.CHANGE_INPUT, "states")],
        )
    target_value = envelope_scalar(target_value)

    # Non-differential: validate the single matrix now. Differential: the matrices
    # are keyed by outcome value, so they are prepared AFTER the observed outcome
    # levels are read from the data (below), to check coverage.
    if not differential:
        declared_out = _declare_matrix(
            confusion_matrix, kx, channel=refusals.QueryRole.EXPOSURE)
        M = declared_out.matrix
        det = float(np.linalg.det(M))
        if abs(det) < _DET_FLOOR:
            raise EstimatorFailure(
                Refusal.SINGULAR_CONFUSION_MATRIX,
                role=refusals.QueryRole.EXPOSURE,
                determinant=abs(det), floor=_DET_FLOOR,
            )
        Minv = np.linalg.inv(M)
    else:
        # No single ``M`` here at all: the per-level set is prepared below,
        # once the observed outcome levels are known.
        det = float("nan")

    adjustment = tuple(sorted(adjustment))
    presence = (cluster,) if cluster is not None else ()
    contract = validate_data(
        data, required_columns={treatment, outcome, *adjustment},
        presence_columns=presence,
    )
    df = contract.data

    observed_x = set(
        envelope_scalar(v) for v in pd.unique(df[treatment].dropna())
    )
    if not observed_x <= set(states):
        raise EstimatorFailure(
            Refusal.STATES_INCOMPLETE, column=treatment,
            values=sorted(map(str, observed_x - set(states))), states=states,
        )
    for v in adjustment:
        _require_discrete(df[v], v)

    outcome_states = tuple(sorted(
        (envelope_scalar(v) for v in pd.unique(df[outcome].dropna())), key=str
    ))
    if len(outcome_states) < 1:
        raise EstimatorFailure(Refusal.EMPTY_OUTCOME, outcome=outcome)
    if len(outcome_states) > MAX_LEVELS:
        raise EstimatorFailure(
            Refusal.CONTINUOUS_OUTCOME,
            outcome=outcome, states=len(outcome_states), cap=MAX_LEVELS,
        )
    if target_value not in outcome_states:
        raise EstimatorFailure(
            Refusal.TARGET_VALUE_ABSENT,
            column=outcome, role=refusals.QueryRole.OUTCOME,
            value=target_value, observed=list(outcome_states),
        )

    # Build the inverse-matrix map. Non-differential: the same M for every column
    # and stratum. Differential: distinct matrices along ``differential_by`` — by
    # the OUTCOME (recall bias, the default; a distinct M_y per outcome level, each
    # outcome column inverted with its own matrix) or by a back-door COVARIATE (the
    # rate varies by e.g. site; a distinct M_z per covariate level, every column in
    # a stratum inverted with that stratum's matrix). Maps are keyed by
    # ``_level_key`` so a bool/0-1 level matches the value the contract coerced.
    differential_axis: str | None = None
    if differential:
        axis = differential_by if differential_by is not None else outcome
        if axis == treatment:
            raise EstimatorFailure(
                Refusal.DIFFERENTIAL_BY_THE_MISMEASURED_VARIABLE,
                axis=axis, role=refusals.QueryRole.EXPOSURE,
                alternatives=[outcome, *adjustment],
                remedies=[(Remedy.CHANGE_INPUT, "differential_by")],
            )
        if axis != outcome and axis not in adjustment:
            raise EstimatorFailure(
                Refusal.DIFFERENTIAL_BY_UNKNOWN,
                axis=axis, home=outcome, adjustment=list(adjustment),
            )
        differential_axis = axis
        axis_is_outcome = axis == outcome
        prepared = _prepare_differential(
            confusion_matrices, differential_levels, kx,
            channel=refusals.QueryRole.EXPOSURE, axis=axis,
        )
        Minv_by_level = {_level_key(lvl): Minv for (lvl, _dm, _d, Minv) in prepared}
        declared_by_level = {_level_key(lvl): dm for (lvl, dm, *_r) in prepared}
        declared_out = prepared[0][1]
        if axis_is_outcome:
            # Recall bias: map each supplied level onto the canonical observed
            # outcome value (by value — the contract may have coerced Y to bool),
            # and require the set to cover every observed outcome level exactly.
            canon = {_level_key(y): y for y in outcome_states}
            level_keys = {_level_key(lvl) for (lvl, *_r) in prepared}
            if level_keys != set(canon):
                raise EstimatorFailure(
                    Refusal.DIFFERENTIAL_LEVELS_NOT_THE_AXIS_LEVELS,
                    axis=axis, expected=list(outcome_states),
                    given=[lvl for (lvl, *_r) in prepared],
                    remedies=[(Remedy.CHANGE_INPUT, "differential_levels")],
                )
            by_outcome_records = sorted(
                (_matrix_record(_dm, _d, outcome=canon[_level_key(lvl)])
                 for (lvl, _dm, _d, _inv) in prepared),
                key=lambda r: str(r["outcome"]),
            )
            suff_extra: dict = {
                "differential": True,
                "confusion_matrices_by_outcome": by_outcome_records,
            }
            matrices_out: tuple = tuple(by_outcome_records)
            differential_by_out: str | None = None
        else:
            # Covariate-differential: coverage of every observed covariate value is
            # enforced per stratum in ``_exposure_formula`` (differential_level_
            # uncovered), so an unused extra matrix is harmless.
            by_level_records = [
                _matrix_record(_dm, _d, level=envelope_scalar(lvl))
                for (lvl, _dm, _d, _inv) in prepared
            ]
            suff_extra = {
                "differential": True,
                "differential_by": differential_axis,
                "confusion_matrices_by_level": by_level_records,
            }
            matrices_out = tuple(by_level_records)
            differential_by_out = differential_axis
        confusion_matrix_out: tuple = ()
    else:
        Minv_by_level = {_level_key(y): Minv for y in outcome_states}
        # The same object under every key — see :func:`_inverses`.
        declared_by_level = {_level_key(y): declared_out for y in outcome_states}
        differential_axis = outcome
        confusion_matrix_out = tuple(tuple(float(v) for v in row) for row in M)
        suff_extra = _matrix_record(declared_out, det, name="confusion_matrix")
        matrices_out = ()
        differential_by_out = None

    groups = (
        cluster_labels(df, cluster, expected_n=len(df))
        if cluster is not None else None
    )

    target_index = outcome_states.index(target_value)
    risks, naive_risks, oos, suff = _exposure_formula(
        df, treatment=treatment, outcome=outcome, adjustment=adjustment,
        states=states, outcome_states=outcome_states,
        Minv_by_level=Minv_by_level, differential_axis=differential_axis,
        target_index=target_index,
    )

    # ``states[0]`` is the reference; a contrast is a level's risk minus it.
    # For kx == 2 this is ``risks[1] - risks[0]`` — the risk difference this
    # estimator has always returned, by the same arithmetic in the same order.
    # A binary exposure has one contrast and reports it. A polytomous one has
    # k−1, so it reports none of them as "the" point and answers with the curve
    # — which is what :mod:`themis.answers` means by declaring two shapes: they
    # are alternatives, and exactly one is a given run's answer. Naming a point
    # here as well would leave the curve carrying no answer at all, since the
    # surfaces render the first shape that detects.
    contrast_index = 1 if kx == 2 else None
    point = (
        None if contrast_index is None
        else risks[contrast_index] - risks[0]
    )
    naive = (
        None if contrast_index is None
        else naive_risks[contrast_index] - naive_risks[0]
    )

    boot = None
    ci_lower = ci_upper = None
    draws = Draws(ci_bootstrap) if ci_bootstrap > 0 else None
    if draws is not None:
        boot = _exposure_bootstrap(
            df, treatment=treatment, outcome=outcome, adjustment=adjustment,
            states=states, outcome_states=outcome_states,
            Minv_by_level=Minv_by_level, declared_by_level=declared_by_level,
            differential_axis=differential_axis,
            target_index=target_index, groups=groups,
            draws=draws, ci_level=ci_level, random_state=random_state,
        )
        if contrast_index is not None:
            ci_lower, ci_upper = boot[contrast_index]

    # Only when there is more than one contrast to show. A binary exposure's
    # curve would be one point restating ``point``, and a second place to read
    # the same number is a second place for it to disagree with itself.
    curve: tuple = ()
    if kx > 2:
        curve = tuple(
            {
                "level": states[a],
                "point": risks[a] - risks[0],
                "risk": risks[a],
                "naive_point": naive_risks[a] - naive_risks[0],
                "naive_risk": naive_risks[a],
                "ci_lower": None if boot is None else boot[a][0],
                "ci_upper": None if boot is None else boot[a][1],
                "ci_level": ci_level,
            }
            for a in range(1, kx)
        )

    assumptions = _exposure_assumptions(
        adjustment, cluster, differential=differential,
        differential_axis=differential_axis, outcome=outcome,
        declared=declared_out, mismeasured=treatment,
    )
    return ExposureMeasurementCorrectionEstimate(
        point=point,
        naive_point=naive,
        ci_lower=ci_lower, ci_upper=ci_upper, ci_level=ci_level,
        method="exposure_measurement_error_correction",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=treatment, outcome=outcome,
        adjustment=adjustment,
        target_value=target_value,
        states=states,
        outcome_states=outcome_states,
        confusion_matrix=confusion_matrix_out,
        det=det,
        out_of_simplex=oos,
        risks=risks,
        naive_risks=naive_risks,
        dose_response_curve=curve,
        sufficient_statistics={
            **suff,
            **suff_extra,
            "side": "exposure",
            "states": [envelope_scalar(s) for s in states],
            "outcome_states": [envelope_scalar(s) for s in outcome_states],
            "target_value": target_value,
            "target_index": target_index,
            "adjustment_vars": list(adjustment),
            # The level every contrast is taken against. Recorded so a reader
            # of the block does not have to know that it is ``states[0]``; the
            # verifier re-derives it and checks the two agree.
            "reference_value": states[0],
        },
        cluster=cluster,
        draws=draws,
        differential=differential,
        differential_by=differential_by_out,
        confusion_matrices=matrices_out,
        differential_levels=(
            tuple(envelope_scalar(v) for v in differential_levels)
            if differential else ()
        ),
    )


def _exposure_formula(
    df: pd.DataFrame, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], states: tuple, outcome_states: tuple,
    Minv_by_level: dict, differential_axis: str, target_index: int,
) -> tuple[tuple[float, ...], tuple[float, ...], bool, dict]:
    """The standardised risk of the target value AT EACH exposure level —
    corrected and naive — plus the per-stratum sufficient statistics (the full
    kx×k (X, Y) joint count tables).

    The risk at a level is what this returns, not the difference between two of
    them, because with more than two levels there is no single difference to
    return and choosing one would be choosing a reference the caller never
    named. The caller contrasts against whichever level it declared first; for
    a binary exposure that reproduces the risk difference exactly.

    Enumeration is driven by the covariate marginal P(z); each contributing z
    must have observed support in EVERY exposure arm (positivity), and its
    recovered exposure marginal P(X*=x|z) must be strictly positive at every
    level (else that level's conditional risk is undefined). Each column of a
    stratum's joint is inverted with the matrix selected by
    ``differential_axis``'s value: ``Minv_by_level[_level_key(value)]`` — the
    same matrix for every column in the non-differential case, a distinct M_y
    per outcome column under recall bias (axis = the outcome), a single
    per-stratum M_z applied to every column when the axis is a covariate (its
    value read from ``z_key``). ``out_of_simplex`` is True if any recovered
    joint cell lands outside [0, 1]."""
    k = len(outcome_states)
    kx = len(states)
    xvals = df[treatment].map(envelope_scalar)
    yvals = df[outcome].map(envelope_scalar)
    n_total = len(df)

    marginal = _marginal(df, adjustment)              # {z_key: prob}
    marginal_counts = _marginal_counts(df, adjustment)  # {z_key: count}

    # One name for one fact: ``None`` IS "the axis is the outcome", so the
    # position of the axis column carries the branch as well.
    axis_idx = (
        None if differential_axis == outcome
        else adjustment.index(differential_axis)
    )

    strata_records: list[dict] = []
    corrected = np.zeros(kx, dtype=float)
    naive = np.zeros(kx, dtype=float)
    oos = False

    for z_key, p_z in marginal.items():
        if p_z <= 0:
            continue
        z_mask = _stratum_mask(df, adjustment, z_key).to_numpy()
        sub_x = xvals[z_mask].to_numpy()
        sub_y = yvals[z_mask].to_numpy()

        joint = np.zeros((kx, k), dtype=float)  # rows: exposure state idx, cols: outcome
        for xi, xval in enumerate(states):
            arm_mask = sub_x == xval
            n_arm = int(arm_mask.sum())
            if n_arm == 0:
                raise EstimatorFailure(
                    Refusal.INSUFFICIENT_SUPPORT,
                    cells=[{treatment: xval,
                            **dict(zip(adjustment, _json_key(z_key)))}],
                    quantity=(
                        f"P({outcome} | {treatment}, "
                        + ", ".join(adjustment) + ")"
                    ),
                )
            sub_y_arm = sub_y[arm_mask]
            for yj, yval in enumerate(outcome_states):
                joint[xi, yj] = float(int((sub_y_arm == yval).sum()))

        Nz = joint.sum()
        p_obs = joint / Nz
        p_true = np.empty_like(p_obs)
        for yj in range(k):
            lvl_value = (
                outcome_states[yj] if axis_idx is None
                else envelope_scalar(z_key[axis_idx])
            )
            Minv = Minv_by_level.get(_level_key(lvl_value))
            if Minv is None:
                raise EstimatorFailure(
                    Refusal.DIFFERENTIAL_LEVEL_UNCOVERED,
                    axis=differential_axis, level=lvl_value,
                )
            p_true[:, yj] = Minv @ p_obs[:, yj]
        if (p_true < -_TOL).any() or (p_true > 1 + _TOL).any():
            oos = True

        px = p_true.sum(axis=1)
        degenerate = [i for i in range(kx) if float(px[i]) <= _TOL]
        if degenerate:
            raise EstimatorFailure(
                Refusal.DEGENERATE_RECOVERED_EXPOSURE,
                stratum=_json_key(z_key),
                levels=[envelope_scalar(states[i]) for i in degenerate],
                recovered=[round(float(px[i]), 6) for i in degenerate],
            )
        for a in range(kx):
            corrected[a] += (
                float(p_true[a, target_index]) / float(px[a])
            ) * p_z

        # Naive: the same standardisation on the OBSERVED exposure (the biased
        # number). Row sums are the observed arm sizes, all > 0 by the
        # positivity check above.
        for a in range(kx):
            naive[a] += (
                float(joint[a, target_index]) / float(joint[a, :].sum())
            ) * p_z

        strata_records.append({
            "z": list(_json_key(z_key)),
            "joint_counts": [[int(c) for c in row] for row in joint],
        })

    suff = {
        "strata": sorted(strata_records, key=lambda r: [str(v) for v in r["z"]]),
        "marginal_counts": [
            {"z": list(_json_key(k2)), "count": c}
            for k2, c in sorted(marginal_counts.items(), key=lambda kv: str(kv[0]))
        ],
        "marginal_total": n_total,
    }
    return (tuple(float(v) for v in corrected),
            tuple(float(v) for v in naive), oos, suff)


def _exposure_bootstrap(
    df: pd.DataFrame, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], states: tuple, outcome_states: tuple,
    Minv_by_level: dict, declared_by_level: dict,
    differential_axis: str, target_index: int,
    groups: np.ndarray | None,
    draws: Draws, ci_level: float, random_state: int,
) -> tuple[tuple[float | None, float | None], ...]:
    """Percentile bootstrap of EVERY level's contrast against the reference —
    resample rows (or clusters), recompute the per-stratum correction with the
    matrix/matrices held fixed where the caller declared them and redrawn from
    their validation tallies where a study counted them. Draws that induce a
    positivity / degenerate-recovery failure, or a redrawn channel that carries
    no information about the truth, are dropped and filed under what dropped
    them.

    One interval per level, indexed the way ``states`` is, so the caller reads
    ``[a]`` for level ``states[a]``; index 0 is the reference contrasted with
    itself and is ``(None, None)``. The levels are resampled TOGETHER — one
    draw yields one whole curve — because they are contrasts against a shared
    reference estimated on the same rows, and intervals built from independent
    per-level draws would not be intervals for anything jointly. One record
    of the draws, for the same reason."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    kx = len(states)
    measured = _any_measured(declared_by_level)
    per_level: list[list[float]] = [[] for _ in range(kx)]
    for _ in draws:
        idx = resample_indices(n, rng, groups=groups)
        sub = df.iloc[idx]
        try:
            inverses = (
                _inverses(declared_by_level, rng,
                          channel=refusals.QueryRole.EXPOSURE)
                if measured else Minv_by_level
            )
            risks, _naive, _oos, _suff = _exposure_formula(
                sub, treatment=treatment, outcome=outcome, adjustment=adjustment,
                states=states, outcome_states=outcome_states,
                Minv_by_level=inverses, differential_axis=differential_axis,
                target_index=target_index,
            )
        except EstimatorFailure as exc:
            draws.unusable(exc.failure_type)
            continue
        for a in range(kx):
            per_level[a].append(risks[a] - risks[0])
        draws.usable()
    alpha = (1 - ci_level) / 2
    out: list[tuple[float | None, float | None]] = []
    for a in range(kx):
        if len(per_level[a]) < FEWEST_DRAWS:
            out.append((None, None))
            continue
        arr = np.asarray(per_level[a])
        out.append((float(np.quantile(arr, alpha)),
                    float(np.quantile(arr, 1 - alpha))))
    return tuple(out)


def _exposure_assumptions(
    adjustment: tuple[str, ...], cluster: str | None, *, differential: bool = False,
    differential_axis: str | None = None, outcome: str | None = None,
    declared: DeclaredMatrix, mismeasured: str,
) -> tuple[str, ...]:
    """The premises the exposure-channel correction rests on — see
    :func:`_assumptions` for why the matrix's provenance is the
    declaration's own premise rather than a fourth restatement of the shape
    ``mech`` already names."""
    if not differential:
        mech = "non_differential_misclassification_X_indep_YZ_given_Xtrue"
    elif differential_axis == outcome:
        mech = "differential_misclassification_by_outcome_M_depends_on_Y"
    else:
        mech = f"differential_misclassification_by_covariate_{differential_axis}"
    out = [
        mech,
        declared.premise(MATRIX_PREMISE, mismeasured),
        "confusion_matrix_invertible",
        "recovered_true_exposure_marginal_positive",
        "consistency_of_potential_outcomes",
        "positivity_every_contributing_stratum_has_support",
    ]
    if adjustment:
        out.append("backdoor_adjustment_{" + ",".join(adjustment) + "}")
    if cluster is not None:
        out.append(f"ci_via_pairs_cluster_bootstrap_on_{cluster}")
    return tuple(out)


# ==============================================================================
# Combined misclassification — both channels at once.
# ==============================================================================
#
# The exposure and the outcome are BOTH measured with error, each with its own
# validated column-stochastic matrix over its own states:
#
#     M_x[a, a*] = P(X = state_a  | X* = state_a*)        (2×2)
#     M_y[b, b*] = P(Y = ystate_b | Y* = ystate_b*)       (k×k)
#
# Correcting one channel and shipping the number leaves the other channel's bias
# in place, which is why the two single-channel estimators refuse to run
# together. Composing them needs one premise neither of them makes on its own:
# the two error mechanisms are INDEPENDENT GIVEN THE TRUTH,
#
#     X ⊥ Y | (X*, Y*, Z)
#
# — the recorder who mis-transcribes the exposure does not thereby become more
# likely to mis-transcribe the outcome. Two separately non-differential channels
# can still be correlated with each other; this is strictly stronger, and it is
# what makes the observed table a two-sided linear image of the true one. Within
# a covariate stratum,
#
#     P_obs(z)[a, b] = Σ_{a*, b*} M_x[a, a*] M_y[b, b*] P_true(z)[a*, b*]
#                    = ( M_x · P_true(z) · M_yᵀ )[a, b]
#   ⇒ P_true(z)      = M_x⁻¹ · P_obs(z) · (M_y⁻¹)ᵀ
#
# so the correction is the exposure-side inversion on the left composed with the
# outcome-side inversion on the right, on the SAME 2×k joint table. The effect is
# then the exposure side's standardisation over the recovered joint:
#
#     P(Y*=y* | X*=x, z) = P_true(z)[x, y*] / Σ_b P_true(z)[x, b]
#     effect = Σ_z [ P(Y*=y* | X*=1, z) − P(Y*=y* | X*=0, z) ] · P(z)
#
# Neither channel may be DIFFERENTIAL here, and the reason is structural rather
# than budgetary: detection bias makes M_y depend on the exposure arm and recall
# bias makes M_x depend on the outcome, so the level that selects one matrix is
# the very quantity the other channel is mismeasuring. The observed table is then
# no longer M_x P_true M_yᵀ — the map stays linear in the 2k unknowns but is not
# a two-sided product, and inverting it as one would return a wrong number rather
# than a refusal.


@dataclass(frozen=True)
class CombinedMeasurementCorrectionEstimate:
    """Effect corrected for misclassification in BOTH the exposure and the outcome.

    ``risks`` is the primitive, as in
    :class:`ExposureMeasurementCorrectionEstimate`: the back-door standardised
    risk at each exposure level over the doubly recovered joint,
    ``Σ_z P(Y*=y*|X*=states[a], z) P(z)``. ``point`` is a contrast against the
    reference ``states[0]`` — for a binary exposure the risk difference this
    class has always carried — and ``dose_response_curve`` carries the rest when
    the exposure has more than two levels. ``naive_point`` and ``naive_risks``
    are the same standardisation on the observed (doubly biased) table, the
    numbers the correction replaces. There is no single ``det``: each channel
    has its own, and ``det_joint = det(M_x)^k · det(M_y)^kx`` is the determinant
    of the composed kx·k map, i.e. how much information the two channels destroy
    together. ``out_of_simplex`` flags a recovered joint cell outside [0, 1] —
    reported, never clipped, since it is the signal that the data refute the
    declared matrices. ``sufficient_statistics`` carries both matrices, the
    per-stratum kx×k observed joint count tables and the covariate marginal
    counts — everything the numeric verifier re-inverts every level's risk from.
    """
    point: float | None
    naive_point: float | None
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    treatment: str
    outcome: str
    adjustment: tuple[str, ...]
    target_value: object
    states: tuple[object, ...]
    outcome_states: tuple[object, ...]
    exposure_confusion_matrix: tuple[tuple[float, ...], ...]
    outcome_confusion_matrix: tuple[tuple[float, ...], ...]
    det_exposure: float
    det_outcome: float
    det_joint: float
    out_of_simplex: bool
    #: The doubly corrected standardised risk at each exposure level, indexed
    #: as ``states`` is; see :class:`ExposureMeasurementCorrectionEstimate`.
    risks: tuple[float, ...] = ()
    naive_risks: tuple[float, ...] = ()
    #: One entry per non-reference level; empty for a binary exposure.
    dose_response_curve: tuple = ()
    sufficient_statistics: dict = field(default_factory=dict)
    cluster: str | None = None
    #: The replicates the interval — and every band on the curve — was
    #: taken over; see :class:`themis.estimation.resample.Draws`. One
    #: record because one loop drew for all of them. ``None`` when no
    #: bootstrap ran, which is the one case with no answer to give.
    draws: "Draws | None" = None
    form: str = "combined_confusion_matrix_inversion_backdoor_standardised"
    #: Nothing chose this shape: it IS the method, and the only way to
    #: overrule it is to answer by a different one.
    form_provenance: str = Provenance.INHERENT
    #: Which shapes a lever BESIDE the outcome model settled, by assumption
    #: id. The ids that RESTATE the outcome model's shape take the answer
    #: above; an id here is a different decision, made by a different lever,
    #: and says so itself — :func:`themis.estimation.form.shapes_settled`.
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES


def estimate_combined_measurement_correction(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    exposure_confusion_matrix,
    exposure_states,
    outcome_confusion_matrix,
    outcome_states,
    target_value,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> CombinedMeasurementCorrectionEstimate:
    """Recover the back-door effect when the discrete exposure AND the discrete
    outcome are both misclassified, by inverting both channels of the per-stratum
    (X, Y) joint.

    The exposure may have any number of levels, on the same terms as the
    single-channel exposure correction: ``M_x_inv @ p_obs @ M_y_inv.T`` is
    already written at both channels' widths, and what a polytomous exposure
    changes is the shape of the answer — the risk at each level, contrasted
    against ``exposure_states[0]``.

    Parameters
    ----------
    data: the main sample carrying both *observed* (misclassified) columns.
    treatment / outcome: discrete X and discrete Y column names.
    adjustment: the back-door adjustment covariates Z (discrete, measured
        without error — a mismeasured covariate is a different channel).
    exposure_confusion_matrix: kx×kx, ``M_x[i][j] = P(X=exposure_states[i] |
        X*=exposure_states[j])``, each column summing to 1.
    exposure_states: the exposure states in row/column order, reference first;
        a binary pair must be in ``[control, treated]`` order.
    outcome_confusion_matrix: k×k, ``M_y[i][j] = P(Y=outcome_states[i] |
        Y*=outcome_states[j])``, each column summing to 1.
    outcome_states: the k outcome states in the row/column order of
        ``outcome_confusion_matrix`` (must cover every observed outcome value).
    target_value: the query's target TRUE outcome value y*.
    ci_bootstrap / ci_level / random_state / cluster: percentile-bootstrap
        controls (both matrices are held fixed across resamples).

    Raises
    ------
    EstimatorFailure: exposure states not a binary ``[control, treated]`` pair;
        observed exposure not covered by them; outcome states not covering the
        observed outcome; target value absent; a high-cardinality outcome;
        continuous adjustment covariate; a malformed, non-stochastic or singular
        matrix on either channel; a positivity violation (a contributing stratum
        empty in an observed arm); a degenerate recovered true-exposure marginal.
    """
    exposure_states = tuple(envelope_scalar(s) for s in exposure_states)
    if len(exposure_states) < 2:
        raise EstimatorFailure(
            Refusal.TOO_FEW_INPUTS,
            what="exposure_states=", needed=2, given=len(exposure_states),
            remedies=[(Remedy.CHANGE_INPUT, "exposure_states")],
        )
    if len(set(exposure_states)) != len(exposure_states):
        raise EstimatorFailure(
            Refusal.DUPLICATE_INPUT,
            what="exposure_states=", given=list(exposure_states),
            remedies=[(Remedy.CHANGE_INPUT, "exposure_states")],
        )
    kx = len(exposure_states)
    if kx == 2 and (bool(exposure_states[0]) is not False
                    or bool(exposure_states[1]) is not True):
        raise EstimatorFailure(
            Refusal.ARM_ORDER_UNREADABLE,
            what="exposure_states=", given=list(exposure_states),
            remedies=[(Remedy.CHANGE_INPUT, "exposure_states")],
        )

    outcome_states = tuple(envelope_scalar(s) for s in outcome_states)
    k = len(outcome_states)
    if k < 2:
        raise EstimatorFailure(
            Refusal.TOO_FEW_INPUTS,
            what="outcome states", needed=2, given=k,
        )
    if len(set(outcome_states)) != k:
        raise EstimatorFailure(
            Refusal.DUPLICATE_INPUT,
            what="outcome states", given=list(outcome_states),
        )
    if k > MAX_LEVELS:
        raise EstimatorFailure(
            Refusal.CONTINUOUS_OUTCOME,
            outcome=outcome, states=k, cap=MAX_LEVELS,
        )
    target_value = envelope_scalar(target_value)
    if target_value not in outcome_states:
        raise EstimatorFailure(
            Refusal.TARGET_VALUE_ABSENT,
            column=outcome, role=refusals.QueryRole.OUTCOME,
            value=target_value, observed=list(outcome_states),
        )

    declared_x = _declare_matrix(exposure_confusion_matrix, kx,
                                 channel=refusals.QueryRole.EXPOSURE)
    Mx = declared_x.matrix
    det_x = float(np.linalg.det(Mx))
    if abs(det_x) < _DET_FLOOR:
        raise EstimatorFailure(
            Refusal.SINGULAR_CONFUSION_MATRIX,
            role=refusals.QueryRole.EXPOSURE,
            determinant=abs(det_x), floor=_DET_FLOOR,
        )
    declared_y = _declare_matrix(outcome_confusion_matrix, k,
                                 channel=refusals.QueryRole.OUTCOME)
    My = declared_y.matrix
    det_y = float(np.linalg.det(My))
    if abs(det_y) < _DET_FLOOR:
        raise EstimatorFailure(
            Refusal.SINGULAR_CONFUSION_MATRIX,
            role=refusals.QueryRole.OUTCOME,
            determinant=abs(det_y), floor=_DET_FLOOR,
        )
    Mx_inv = np.linalg.inv(Mx)
    My_inv = np.linalg.inv(My)
    # The composed map on the kx·k-vector of joint cells is the Kronecker
    # product, so its determinant factorises — one honest number for how much
    # the two channels destroy together, which neither det reports on its own.
    # det(A ⊗ B) = det(A)^k · det(B)^kx, each raised to the OTHER channel's
    # width; with a binary exposure the second exponent is 2.
    det_joint = float(det_x ** k * det_y ** kx)

    adjustment = tuple(sorted(adjustment))
    presence = (cluster,) if cluster is not None else ()
    contract = validate_data(
        data, required_columns={treatment, outcome, *adjustment},
        presence_columns=presence,
    )
    df = contract.data

    observed_x = set(
        envelope_scalar(v) for v in pd.unique(df[treatment].dropna())
    )
    if not observed_x <= set(exposure_states):
        raise EstimatorFailure(
            Refusal.STATES_INCOMPLETE, column=treatment,
            values=sorted(map(str, observed_x - set(exposure_states))), states=exposure_states,
        )
    for v in adjustment:
        _require_discrete(df[v], v)

    observed_y = set(
        envelope_scalar(v) for v in pd.unique(df[outcome].dropna())
    )
    missing = observed_y - set(outcome_states)
    if missing:
        raise EstimatorFailure(
            Refusal.STATES_INCOMPLETE, column=outcome,
            values=sorted(map(str, missing)), states=outcome_states,
        )

    groups = (
        cluster_labels(df, cluster, expected_n=len(df))
        if cluster is not None else None
    )

    target_index = outcome_states.index(target_value)
    risks, naive_risks, oos, suff = _combined_formula(
        df, treatment=treatment, outcome=outcome, adjustment=adjustment,
        states=exposure_states, outcome_states=outcome_states,
        Mx_inv=Mx_inv, My_inv=My_inv, target_index=target_index,
    )

    # Binary reports its one contrast, polytomous answers with the curve — see
    # the single-channel correction.
    contrast_index = 1 if kx == 2 else None
    point = (
        None if contrast_index is None else risks[contrast_index] - risks[0]
    )
    naive = (
        None if contrast_index is None
        else naive_risks[contrast_index] - naive_risks[0]
    )

    boot = None
    ci_lower = ci_upper = None
    draws = Draws(ci_bootstrap) if ci_bootstrap > 0 else None
    if draws is not None:
        boot = _combined_bootstrap(
            df, treatment=treatment, outcome=outcome, adjustment=adjustment,
            states=exposure_states, outcome_states=outcome_states,
            Mx_inv=Mx_inv, My_inv=My_inv,
            declared_x=declared_x, declared_y=declared_y,
            target_index=target_index,
            groups=groups,
            draws=draws, ci_level=ci_level, random_state=random_state,
        )
        if contrast_index is not None:
            ci_lower, ci_upper = boot[contrast_index]

    curve: tuple = ()
    if kx > 2:
        curve = tuple(
            {
                "level": exposure_states[a],
                "point": risks[a] - risks[0],
                "risk": risks[a],
                "naive_point": naive_risks[a] - naive_risks[0],
                "naive_risk": naive_risks[a],
                "ci_lower": None if boot is None else boot[a][0],
                "ci_upper": None if boot is None else boot[a][1],
                "ci_level": ci_level,
            }
            for a in range(1, kx)
        )

    assumptions = _combined_assumptions(
        adjustment, cluster, declared_x=declared_x, declared_y=declared_y,
        treatment=treatment, outcome=outcome,
    )
    return CombinedMeasurementCorrectionEstimate(
        point=point,
        naive_point=naive,
        ci_lower=ci_lower, ci_upper=ci_upper, ci_level=ci_level,
        method="combined_measurement_error_correction",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=treatment, outcome=outcome,
        adjustment=adjustment,
        target_value=target_value,
        states=exposure_states,
        outcome_states=outcome_states,
        exposure_confusion_matrix=tuple(
            tuple(float(v) for v in row) for row in Mx
        ),
        outcome_confusion_matrix=tuple(
            tuple(float(v) for v in row) for row in My
        ),
        det_exposure=det_x, det_outcome=det_y, det_joint=det_joint,
        out_of_simplex=oos,
        risks=risks,
        naive_risks=naive_risks,
        dose_response_curve=curve,
        sufficient_statistics={
            **suff,
            "side": "combined",
            "reference_value": exposure_states[0],
            "exposure_confusion_matrix": [[float(v) for v in row] for row in Mx],
            "outcome_confusion_matrix": [[float(v) for v in row] for row in My],
            # Each channel's tally beside its own matrix, present only where
            # a study counted that channel — the two are separate studies and
            # either may be the one that was measured.
            **({"exposure_validation_counts": declared_x.as_lists()}
               if declared_x.measured else {}),
            **({"outcome_validation_counts": declared_y.as_lists()}
               if declared_y.measured else {}),
            "det_exposure": det_x,
            "det_outcome": det_y,
            "det_joint": det_joint,
            "states": [envelope_scalar(s) for s in exposure_states],
            "outcome_states": [envelope_scalar(s) for s in outcome_states],
            "target_value": target_value,
            "target_index": target_index,
            "adjustment_vars": list(adjustment),
        },
        cluster=cluster,
        draws=draws,
    )


def _combined_formula(
    df: pd.DataFrame, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], states: tuple, outcome_states: tuple,
    Mx_inv: np.ndarray, My_inv: np.ndarray, target_index: int,
) -> tuple[tuple[float, ...], tuple[float, ...], bool, dict]:
    """The doubly corrected + naive standardised risk of the target value AT
    EACH exposure level, plus the per-stratum sufficient statistics (the full
    kx×k observed (X, Y) joint tables).

    Returns the risk at a level rather than a difference between two, for the
    reason :func:`_exposure_formula` gives: with more than two levels there is
    no single difference to return.

    Enumeration is driven by the covariate marginal P(z); each contributing z
    must have observed support in EVERY exposure arm (positivity), and its
    recovered true-exposure marginal must be strictly positive at every level
    (else that level's conditional risk is undefined). Each stratum's joint is
    inverted on both sides at once — ``M_x⁻¹ P_obs (M_y⁻¹)ᵀ`` — so neither
    channel's bias survives into the standardisation. ``out_of_simplex`` is
    True if any recovered cell lands outside [0, 1]."""
    k = len(outcome_states)
    kx = len(states)
    xvals = df[treatment].map(envelope_scalar)
    yvals = df[outcome].map(envelope_scalar)
    n_total = len(df)

    marginal = _marginal(df, adjustment)                # {z_key: prob}
    marginal_counts = _marginal_counts(df, adjustment)  # {z_key: count}

    strata_records: list[dict] = []
    corrected = np.zeros(kx, dtype=float)
    naive = np.zeros(kx, dtype=float)
    oos = False

    for z_key, p_z in marginal.items():
        if p_z <= 0:
            continue
        z_mask = _stratum_mask(df, adjustment, z_key).to_numpy()
        sub_x = xvals[z_mask].to_numpy()
        sub_y = yvals[z_mask].to_numpy()

        joint = np.zeros((kx, k), dtype=float)  # rows: exposure state, cols: outcome
        for xi, xval in enumerate(states):
            arm_mask = sub_x == xval
            n_arm = int(arm_mask.sum())
            if n_arm == 0:
                raise EstimatorFailure(
                    Refusal.INSUFFICIENT_SUPPORT,
                    cells=[{treatment: xval,
                            **dict(zip(adjustment, _json_key(z_key)))}],
                    quantity=(
                        f"P({outcome} | {treatment}, "
                        + ", ".join(adjustment) + ")"
                    ),
                )
            sub_y_arm = sub_y[arm_mask]
            for yj, yval in enumerate(outcome_states):
                joint[xi, yj] = float(int((sub_y_arm == yval).sum()))

        p_obs = joint / joint.sum()
        p_true = Mx_inv @ p_obs @ My_inv.T
        if (p_true < -_TOL).any() or (p_true > 1 + _TOL).any():
            oos = True

        px = p_true.sum(axis=1)
        degenerate = [i for i in range(kx) if float(px[i]) <= _TOL]
        if degenerate:
            raise EstimatorFailure(
                Refusal.DEGENERATE_RECOVERED_EXPOSURE,
                stratum=_json_key(z_key),
                levels=[envelope_scalar(states[i]) for i in degenerate],
                recovered=[round(float(px[i]), 6) for i in degenerate],
            )
        for a in range(kx):
            corrected[a] += (
                float(p_true[a, target_index]) / float(px[a])
            ) * p_z

        # Naive: the back-door risk on the observed X and observed Y — both
        # biases left in. Row sums are the observed arm sizes (positive by the
        # check above).
        for a in range(kx):
            naive[a] += (
                float(joint[a, target_index]) / float(joint[a, :].sum())
            ) * p_z

        strata_records.append({
            "z": list(_json_key(z_key)),
            "joint_counts": [[int(c) for c in row] for row in joint],
        })

    suff = {
        "strata": sorted(strata_records, key=lambda r: [str(v) for v in r["z"]]),
        "marginal_counts": [
            {"z": list(_json_key(k2)), "count": c}
            for k2, c in sorted(marginal_counts.items(), key=lambda kv: str(kv[0]))
        ],
        "marginal_total": n_total,
    }
    return (tuple(float(v) for v in corrected),
            tuple(float(v) for v in naive), oos, suff)


def _combined_bootstrap(
    df: pd.DataFrame, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], states: tuple, outcome_states: tuple,
    Mx_inv: np.ndarray, My_inv: np.ndarray,
    declared_x: DeclaredMatrix, declared_y: DeclaredMatrix,
    target_index: int,
    groups: np.ndarray | None,
    draws: Draws, ci_level: float, random_state: int,
) -> tuple[tuple[float | None, float | None], ...]:
    """Percentile bootstrap of every level's doubly corrected contrast against
    the reference — resample rows (or clusters), recompute with each matrix
    held fixed where the caller declared it and redrawn from its validation
    tally where a study counted it. Draws that induce a positivity /
    degenerate-recovery failure, or a redrawn channel carrying no information
    about the truth, are dropped and filed under what dropped them. Indexed as
    ``states`` is, index 0 being ``(None, None)``; the levels are resampled
    together, for the reason ``_exposure_bootstrap`` gives.

    The two channels are redrawn independently because they are two studies,
    which is the same premise that licenses the two-sided product in the
    first place."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    kx = len(states)
    measured = declared_x.measured or declared_y.measured
    per_level: list[list[float]] = [[] for _ in range(kx)]
    for _ in draws:
        idx = resample_indices(n, rng, groups=groups)
        try:
            xi, yi = (Mx_inv, My_inv) if not measured else (
                _inverses({0: declared_x}, rng,
                          channel=refusals.QueryRole.EXPOSURE)[0],
                _inverses({0: declared_y}, rng,
                          channel=refusals.QueryRole.OUTCOME)[0],
            )
            risks, _naive, _oos, _suff = _combined_formula(
                df.iloc[idx], treatment=treatment, outcome=outcome,
                adjustment=adjustment, states=states,
                outcome_states=outcome_states,
                Mx_inv=xi, My_inv=yi, target_index=target_index,
            )
        except EstimatorFailure as exc:
            draws.unusable(exc.failure_type)
            continue
        for a in range(kx):
            per_level[a].append(risks[a] - risks[0])
        draws.usable()
    alpha = (1 - ci_level) / 2
    out: list[tuple[float | None, float | None]] = []
    for a in range(kx):
        if len(per_level[a]) < FEWEST_DRAWS:
            out.append((None, None))
            continue
        arr = np.asarray(per_level[a])
        out.append((float(np.quantile(arr, alpha)),
                    float(np.quantile(arr, 1 - alpha))))
    return tuple(out)


def _combined_assumptions(
    adjustment: tuple[str, ...], cluster: str | None, *,
    declared_x: DeclaredMatrix, declared_y: DeclaredMatrix,
    treatment: str, outcome: str,
) -> tuple[str, ...]:
    """Both channels' premises. The matrix provenance is TWO ids here, one
    per channel, because they are two studies: a correction that counted the
    exposure's channel and was handed the outcome's rests on one of each,
    and a single id covering both could only be right when they agree."""
    out = [
        "non_differential_misclassification_X_indep_YZ_given_Xtrue",
        "non_differential_misclassification_Y_indep_XZ_given_Ytrue",
        # The premise neither single-channel correction makes, and the one that
        # licenses the two-sided product — named so it is auditable on its own.
        "independent_error_channels_X_indep_Y_given_Xtrue_Ytrue_Z",
        declared_x.premise(MATRIX_PREMISE, treatment),
        declared_y.premise(MATRIX_PREMISE, outcome),
        "confusion_matrix_invertible",
        "recovered_true_exposure_marginal_positive",
        "consistency_of_potential_outcomes",
        "positivity_every_contributing_stratum_has_support",
    ]
    if adjustment:
        out.append("backdoor_adjustment_{" + ",".join(adjustment) + "}")
    if cluster is not None:
        out.append(f"ci_via_pairs_cluster_bootstrap_on_{cluster}")
    return tuple(out)
