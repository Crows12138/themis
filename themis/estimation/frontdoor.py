"""Phase 7.2 S.FDN.1 — front-door adjusted ATE estimator.

Implements Pearl's front-door formula (Pearl 2009 Eq. 3.29) as a
plug-in estimator:

    P(Y | do(X=x)) = ∑_z P(Z=z | X=x) · ∑_{x'} P(Y | X=x', Z=z) · P(X=x')

ATE = E[Y | do(X=1)] - E[Y | do(X=0)].

Fits two conditional models via sklearn:
- ``P(Z | X)`` — linear / logistic on each mediator
- ``P(Y | X, Z)`` — linear / logistic on the outcome

Then combines them with the empirical marginal P(X).

Generalises to multi-mediator via the topological chain-rule
factoring (matches Phase 6.front-door-multi's identification-layer
formula):

    P(Z1, ..., Zk | X) = ∏_i P(Zi | Z_{<i}, X)

API:

    from themis.estimation.frontdoor import estimate_frontdoor_ate
    est = estimate_frontdoor_ate(
        data, treatment="x", outcome="y",
        mediators=("m1", "m2"),  # topological order
    )

Binary treatment + bool-or-continuous outcome. Mediators may be bool
or any discrete/categorical variable (integer, string, or categorical
dtype, or an integer-valued float): each mediator is drop-first one-hot
encoded, the chain factors ``P(Zi | X, Z_<i)`` become multinomial
logistic, and the outer sum ranges over the full Cartesian product of
the mediators' level sets (``∏_i k_i`` strata). Binary mediators reduce
to the original 2^k enumeration exactly.

A mediator whose values are not levels — a genuine continuum, or more
of them than the sum can be taken over — is answered by a second plug-in
for the same estimand, not deferred. It takes P(M | X) from the arm's
own rows rather than from a fitted chain, which turns the outer sum into
an average over the rows of one arm:

    E[Y | do(x)] = ⟨ ∑_x' P(x') · Ê[Y | X=x', M=M_i] ⟩_{i : X_i = x}

Which of the two answers is decided once per call, by
:func:`exactly_summable`, and the assumption list says which one did.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression, LogisticRegression

from .. import refusals
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from .contract import integer_valued, validate_data
from ..ledger import Provenance
from .declared import design_block
from .form import NO_OTHER_SHAPES, outcome_form, shapes_settled
from .resample import Draws, cluster_labels, resample_indices


ModelName = Literal["auto", "linear", "logistic"]

# Where the road forks, not where the answer stops. Past either of these the
# exact sum over mediator strata is a poor model or an infeasible one, and the
# empirical plug-in answers instead — see :func:`exactly_summable`.
MAX_LEVELS_PER_MEDIATOR = 20
# Ceiling on ``∏_i k_i`` — the number of mediator-value strata the outer sum
# would enumerate.
MAX_MEDIATOR_CROSSPRODUCT = 2048


@dataclass(frozen=True)
class FrontdoorEstimate:
    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    #: ``frontdoor_{linear,logistic}`` when the exact sum over mediator
    #: strata was taken, ``frontdoor_empirical_{linear,logistic}`` when
    #: P(M | X) came from the arms' own rows instead.
    method: str
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    mediators: tuple[str, ...]
    treatment: str
    outcome: str
    #: The replicates this interval was taken over — see
    #: :class:`themis.estimation.resample.Draws`. ``None`` when no
    #: bootstrap ran, which is the one case with no answer to give.
    draws: "Draws | None" = None
    cluster: str | None = None
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
    #: The two standardized arms this contrast is a difference of, and what
    #: they were built from. Empty on the enumerating route, whose arms are
    #: sums over strata a verifier cannot re-take without the frame; the
    #: empirical route's are two means and it can, so this is where the
    #: re-derivation gets its numbers.
    sufficient_statistics: Mapping[str, object] = MappingProxyType({})


def estimate_frontdoor_ate(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    mediators: tuple[str, ...],
    model: ModelName = "auto",
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> FrontdoorEstimate:
    """Front-door-adjusted ATE via plug-in Pearl Eq 3.29 + bootstrap CI.

    See module docstring for the formula + assumptions. Mediators
    must be passed in topological order (matching the scheduler's
    ``front_door_sets`` output).

    ``cluster`` (optional column name) switches the bootstrap CI to a
    pairs cluster bootstrap; ``None`` reproduces the i.i.d. bootstrap.
    """
    if not mediators:
        raise ValueError("estimate_frontdoor_ate requires >=1 mediator")

    required = {treatment, outcome, *mediators}
    presence = (cluster,) if cluster is not None else ()
    groups = (
        cluster_labels(data, cluster, expected_n=len(data))
        if cluster is not None
        else None
    )
    contract = validate_data(
        data, required_columns=required, presence_columns=presence,
        # The mediators are absent on purpose: this estimator sums over
        # their level sets rather than reading them as magnitudes, so a
        # mediator with no order is one it can genuinely use.
        quantity_columns=(treatment, outcome),
    )
    df = contract.data

    resolved, form_provenance = outcome_form(model, df[outcome])

    # Which plug-in, decided ONCE. The two differ in where P(M | X) comes
    # from, and a decision re-made inside the bootstrap would be a decision
    # nothing on the envelope could state — the assumption the answer rests
    # on would be per-replicate.
    summable = exactly_summable(df, mediators)
    method = (f"frontdoor_{resolved}" if summable
              else f"frontdoor_empirical_{resolved}")
    statistics: dict = {}

    def _point_of(frame: pd.DataFrame) -> float:
        if summable:
            return _point_estimate_frontdoor(
                frame, treatment, outcome, mediators, model=resolved,
            )
        return _point_estimate_frontdoor_empirical(
            frame, treatment, outcome, mediators, model=resolved,
        )[0]

    if summable:
        point = _point_estimate_frontdoor(
            df, treatment, outcome, mediators, model=resolved,
        )
    else:
        point, statistics = _point_estimate_frontdoor_empirical(
            df, treatment, outcome, mediators, model=resolved,
        )

    ci_lower: float | None = None
    ci_upper: float | None = None
    draws = Draws(ci_bootstrap) if ci_bootstrap > 0 else None
    if draws is not None:
        ci_lower, ci_upper = _bootstrap_ci_frontdoor(
            df, draws=draws, point_of=_point_of,
            ci_level=ci_level, random_state=random_state,
            groups=groups,
        )

    assumptions = _assumptions_for(
        resolved, len(mediators), summable=summable)
    # No ordering row here, and there used to be one. This estimator does
    # NOT take a mediator column as one term: ``encode_column`` gives each
    # of them one indicator per level, drop-first, because the front-door
    # formula enumerates mediator assignments and a level it could not name
    # is a level it could not sum over. So the row said the answer rested on
    # an ordering the fit never used — a false line on the surface that
    # exists to be true. The check that would not have been fooled is the
    # one #417 built: what a column IS is read from the frame at the design
    # build, so a column that became k-1 indicators cannot also be reported
    # as one ordered term.
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )

    return FrontdoorEstimate(
        point=float(point),
        ci_lower=float(ci_lower) if ci_lower is not None else None,
        ci_upper=float(ci_upper) if ci_upper is not None else None,
        ci_level=ci_level,
        method=method,
        draws=draws,
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        mediators=tuple(mediators),
        treatment=treatment,
        outcome=outcome,
        cluster=cluster,
        form=resolved,
        form_provenance=form_provenance,
        sufficient_statistics=MappingProxyType(statistics),
        # Factoring the joint mediator conditional by the chain rule is not a
        # shape anything chose: there is no other factoring on offer and no
        # argument that changes it.
        shape_provenance=shapes_settled(
            assumptions,
            ("chain_rule_factoring_of_joint_mediator_conditional",
             Provenance.INHERENT),
        ),
    )


# --- internals ----------------------------------------------------------------


def enumerable(series: pd.Series) -> bool:
    """Whether this column has levels an exact sum can be taken over.

    Integer-valuedness rather than dtype, because the contract has already
    widened every integer column to float64 by the time a mediator arrives —
    the dtype test below only separates the contract's bool arm from its
    float arm, which is why the float arm carries the whole question. The
    reading itself is :func:`contract.integer_valued`, beside the cast.

    An EMPTY column is not integer-valued and this once called it
    continuous, which is a sentence about a column with nothing in it. The
    contract requires ten rows and refuses a NaN in a model column, so a
    mediator reaching here has never been empty; the difference was
    unreachable, which is why nothing had compared the two readings.
    """
    s = series.dropna()
    if pd.api.types.is_float_dtype(series) and not integer_valued(s):
        return False
    return int(s.nunique()) <= MAX_LEVELS_PER_MEDIATOR


def exactly_summable(df: pd.DataFrame, mediators: tuple[str, ...]) -> bool:
    """Whether the exact outer sum over the mediators' JOINT assignment can
    be taken — the one question that decides which plug-in answers.

    Two things can stop it and they are one question: a column with no
    levels to sum over, and a set whose levels have too many combinations.
    Both used to be refusals, on the ground that a front door needing more
    than the exact sum needed density estimation. It does not, so what they
    are now is the fork in the road: this returns false and the empirical
    plug-in answers instead, at the cost of one more assumption row.

    Resampling can only shrink a column's distinct values, never add one,
    so a sample this calls summable has summable resamples. That is what
    lets the bootstrap re-enter the enumerating plug-in without re-asking.
    """
    combinations = 1
    for m in mediators:
        if not enumerable(df[m]):
            return False
        combinations *= int(df[m].dropna().nunique())
    return combinations <= MAX_MEDIATOR_CROSSPRODUCT


def mediator_levels(series: pd.Series) -> list:
    """The sorted level set the front-door encoding sums over.

    It refuses nothing, and it used to refuse two things. Both were the
    same sentence — this column has no levels, or too many — and both were
    said at the moment the levels were asked for, which is one step too
    late to be a decision: by then the only thing left to do with the
    answer is stop. Asked one step earlier, by :func:`exactly_summable`, it
    is a fork, and both of this function's callers now take it before
    calling. So the reading survives and the refusal does not.
    """
    return sorted(series.dropna().unique().tolist())


def _point_estimate_frontdoor(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    mediators: tuple[str, ...],
    *,
    model: str,
) -> float:
    """Evaluate Pearl Eq 3.29 on the fitted conditionals.

    Each mediator is drop-first one-hot encoded over its discrete level
    set; the outer sum ranges over the full Cartesian product of those
    level sets (``∏_i k_i`` strata). For binary mediators this is exactly
    the original 2^k enumeration. We compute
    ``∑_z P(Z=z|X=x) · ∑_x' P(Y|X=x',Z=z) · P(X=x')`` for each do(X) arm,
    then return the difference.

    Precondition: :func:`exactly_summable` on this frame's mediators. It
    is asked once, at the route, and this function does not ask it again —
    a threshold checked in both places is one number two callers can
    disagree about, and the caller that would lose is the one whose answer
    is already on an envelope.
    """
    import itertools

    # Discrete level set per mediator. Recomputed per resample rather than
    # inherited, because a resample's level set is its own and the chain
    # factors are fitted against it — the same reason the degenerate
    # single-level factor below has a branch.
    levels = {m: mediator_levels(df[m]) for m in mediators}
    val_to_idx = {
        m: {v: i for i, v in enumerate(levels[m])} for m in mediators
    }

    def encode_value(m: str, v) -> np.ndarray:
        """Drop-first one-hot of a single mediator value (length k-1)."""
        vec = np.zeros(len(levels[m]) - 1, dtype=float)
        idx = val_to_idx[m][v]
        if idx > 0:
            vec[idx - 1] = 1.0
        return vec

    def encode_column(m: str) -> np.ndarray:
        """Vectorised drop-first one-hot of a mediator column (n x k-1)."""
        idx = df[m].map(val_to_idx[m]).to_numpy(dtype=int)
        onehot = np.zeros((len(df), len(levels[m])), dtype=float)
        onehot[np.arange(len(df)), idx] = 1.0
        return onehot[:, 1:]

    def encode_assignment(combo: tuple) -> np.ndarray:
        """Concatenated drop-first one-hot for a full mediator assignment."""
        if not mediators:
            return np.zeros(0)
        return np.concatenate(
            [encode_value(m, combo[i]) for i, m in enumerate(mediators)]
        )

    x_arr = df[treatment].to_numpy(dtype=float).reshape(-1, 1)  # n x 1
    y_arr = df[outcome].to_numpy()
    if y_arr.dtype == bool:
        y_arr = y_arr.astype(int)

    # Fit P(Y | X, Z) — single model on [X, one-hot(Z1..Zk)].
    if mediators:
        z_train = np.hstack([encode_column(m) for m in mediators])
        xz = np.hstack([x_arr, z_train])
    else:
        xz = x_arr
    predict_y = _fit_predict(xz, y_arr, model)

    # Fit P(Zi | X, Z_<i) via chain rule — each factor a (multinomial)
    # logistic on [X, one-hot(Z_<i)]. A degenerate single-level factor is
    # stored as a constant so LogisticRegression is never asked to fit a
    # single class (which happens in bootstrap resamples).
    # No tag beside the entry: a degenerate factor is the constant level
    # itself and a fitted one is the classifier, so the entry's type
    # already says which it is. A parallel "const"/"clf" string would be
    # a second place for the same fact to be recorded, and the reader
    # would have to trust the two agree.
    chain: list[int | LogisticRegression] = []
    for i, m in enumerate(mediators):
        target = df[m].map(val_to_idx[m]).to_numpy(dtype=int)
        if i == 0:
            feats = x_arr
        else:
            feats = np.hstack(
                [x_arr] + [encode_column(mediators[j]) for j in range(i)]
            )
        distinct = np.unique(target)
        if distinct.size <= 1:
            chain.append(int(distinct[0]) if distinct.size else 0)
        else:
            clf = LogisticRegression(max_iter=1000, solver="lbfgs")
            clf.fit(feats, target)
            chain.append(clf)

    # Empirical P(X) — treatment prevalence (binary treatment).
    p_x1 = float(df[treatment].mean())
    p_x0 = 1.0 - p_x1

    def p_factor(i: int, combo: tuple, x_value: float) -> float:
        """P(Zi = combo[i] | X=x, Z_<i = combo[:i])."""
        factor = chain[i]
        target_idx = val_to_idx[mediators[i]][combo[i]]
        if isinstance(factor, int):
            return 1.0 if target_idx == factor else 0.0
        clf = factor
        if i == 0:
            feats = np.array([[x_value]])
        else:
            prior = np.concatenate(
                [encode_value(mediators[j], combo[j]) for j in range(i)]
            )
            feats = np.concatenate([[x_value], prior]).reshape(1, -1)
        proba = clf.predict_proba(feats)[0]
        cols = np.nonzero(clf.classes_ == target_idx)[0]
        return float(proba[cols[0]]) if cols.size else 0.0

    def p_z_given_x(combo: tuple, x_value: float) -> float:
        """Joint conditional P(Z1=z1,...,Zk=zk | X=x) via chain rule."""
        acc = 1.0
        for i in range(len(mediators)):
            acc *= p_factor(i, combo, x_value)
        return acc

    def inner_marginalise(combo: tuple) -> float:
        """∑_x' P(Y | X=x', Z=z) · P(X=x')."""
        z_oh = encode_assignment(combo)
        feats1 = np.concatenate([[1.0], z_oh]).reshape(1, -1)
        feats0 = np.concatenate([[0.0], z_oh]).reshape(1, -1)
        y_at_1 = float(predict_y(feats1)[0])
        y_at_0 = float(predict_y(feats0)[0])
        return y_at_1 * p_x1 + y_at_0 * p_x0

    level_lists = [levels[m] for m in mediators]

    def do_arm(x_arm: float) -> float:
        total = 0.0
        for combo in itertools.product(*level_lists):
            total += p_z_given_x(combo, x_arm) * inner_marginalise(combo)
        return total

    return do_arm(1.0) - do_arm(0.0)


def _point_estimate_frontdoor_empirical(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    mediators: tuple[str, ...],
    *,
    model: str,
) -> tuple[float, dict]:
    """Pearl Eq 3.29 with the SAMPLE'S OWN conditional standing in for
    P(M | X), and the two standardized arms it is a difference of.

    The refusal this replaces said the high-cardinality case "needs density
    estimation, which is deferred", and that bound two things together
    which are not one. The formula needs P(m | x) as a WEIGHT in an
    average, not as a curve to be drawn: under a binary treatment the
    sample already splits into the two groups whose empirical M-spreads
    estimate it, so the outer integral is an average over the rows of one
    arm and nothing has to be smoothed. What was deferred was the
    non-parametric density, and a closed form that never needed one went
    with it.

        E[Y | do(x)] = ⟨ Σ_x' P(x') · Ê[Y | X=x', M=M_i] ⟩_{i : X_i = x}

    The inner sum is over two treatment values, so this is two model
    evaluations per row rather than one per mediator stratum: no
    enumeration, no cross-product cap, and a mediator that is continuous,
    discrete, or a mix of both is the same arithmetic. The outcome model
    may be either shape — nothing here integrates it, which is why the
    logistic arm is available too.

    Its relation to the enumerating plug-in beside it is that both are
    plug-ins for the same estimand differing in where P(M | X) comes from:
    a fitted chain of multinomial logistics there, the sample here. The
    enumerating one is kept for columns whose levels can be enumerated,
    where a fitted conditional smooths thin strata this one would take at
    face value — and keeping it is also what keeps every front-door number
    this package has already reported unchanged.
    """
    x_arr = df[treatment].to_numpy(dtype=float)
    y_arr = df[outcome].to_numpy()
    if y_arr.dtype == bool:
        y_arr = y_arr.astype(int)

    # The mediator half of the design, as the columns are: a magnitude
    # enters as itself and a set of levels as its indicators, which is the
    # same reading ``design_block`` makes everywhere else in the package.
    m_block = design_block(df, mediators)
    xz = np.hstack([x_arr.reshape(-1, 1), m_block])
    predict_y = _fit_predict(xz, y_arr, model)

    p_x1 = float(np.mean(x_arr))
    p_x0 = 1.0 - p_x1

    # ⟨Ê[Y | X=x', M=M_i]⟩ over the treatment's own marginal, at every row's
    # observed mediator — the inner sum, evaluated once for all rows.
    inner = (
        p_x1 * np.asarray(predict_y(
            np.hstack([np.ones((len(df), 1)), m_block])))
        + p_x0 * np.asarray(predict_y(
            np.hstack([np.zeros((len(df), 1)), m_block])))
    )

    treated = x_arr > 0.5
    if not treated.any() or treated.all():
        # Both arms have to be OCCUPIED, because each of them is where an
        # arm's mediator spread is read from. The enumerating plug-in beside
        # this one never needed the check: it takes P(M|X=x) from a fitted
        # model, which returns a number at a treatment level no row holds.
        raise EstimatorFailure(
            Refusal.OVERLAP_INSUFFICIENT,
            column=treatment, role=refusals.QueryRole.EXPOSURE,
            levels=sorted(set(float(v) for v in x_arr)),
        )
    arm1 = float(np.mean(inner[treated]))
    arm0 = float(np.mean(inner[~treated]))
    return arm1 - arm0, {
        # The two arms the contrast is a difference of, and the marginal
        # that weighted the inner sum. A verifier holding these can
        # re-derive the contrast without the frame; on the linear arm it
        # can go further, which is why the coefficients are here too.
        "arm_treated": arm1,
        "arm_control": arm0,
        "treatment_prevalence": p_x1,
        "outcome_coefficients": _coefficients_of(xz, y_arr, model),
        "mediator_shift": [
            float(np.mean(m_block[treated, j]) - np.mean(m_block[~treated, j]))
            for j in range(m_block.shape[1])
        ],
    }


def _coefficients_of(X: np.ndarray, y: np.ndarray, model: str) -> list[float]:
    """The fitted outcome model's coefficients, treatment column first."""
    if model == "logistic":
        clf = LogisticRegression(max_iter=1000, solver="lbfgs")
        clf.fit(X, y)
        return [float(c) for c in np.ravel(clf.coef_)]
    reg = LinearRegression()
    reg.fit(X, y)
    return [float(c) for c in np.ravel(reg.coef_)]


def _fit_predict(X: np.ndarray, y: np.ndarray, model: str):
    if model == "logistic":
        clf = LogisticRegression(max_iter=1000, solver="lbfgs")
        clf.fit(X, y)
        return lambda X_new: clf.predict_proba(X_new)[:, 1]
    if model == "linear":
        reg = LinearRegression()
        reg.fit(X, y)
        return lambda X_new: reg.predict(X_new)
    raise EstimatorFailure(
        Refusal.UNKNOWN_OPTION,
        option="model", given=model, known=["logistic", "linear"],
    )


def _bootstrap_ci_frontdoor(
    df: pd.DataFrame,
    *,
    point_of: "Callable[[pd.DataFrame], float]",
    draws: Draws,
    ci_level: float,
    random_state: int,
    groups: np.ndarray | None = None,
) -> tuple[float, float]:
    """Percentile interval over resamples of whichever plug-in was chosen.

    It takes the point estimator rather than the columns and re-deciding:
    the choice between the two plug-ins is made once, above, and a
    replicate that re-made it could answer with a different estimator than
    the point estimate did — on a resample where a 21-level mediator
    happens to show 20.
    """
    rng = np.random.default_rng(random_state)
    n = len(df)
    estimates = np.empty(draws.requested)
    for i in draws:
        idx = resample_indices(n, rng, groups=groups)
        estimates[i] = point_of(df.iloc[idx])
        draws.usable()
    alpha = (1 - ci_level) / 2
    return float(np.quantile(estimates, alpha)), float(
        np.quantile(estimates, 1 - alpha)
    )


def _assumptions_for(
    model: str, n_mediators: int, *, summable: bool = True,
) -> tuple[str, ...]:
    common: tuple[str, ...] = (
        "front_door_criterion_holds_on_graph",
        "mediator_intercepts_all_directed_paths_from_treatment_to_outcome",
        "no_unblocked_backdoor_from_treatment_to_mediator",
        "backdoor_from_mediator_to_outcome_blocked_by_treatment",
        "consistency_of_potential_outcomes",
    )
    if model == "linear":
        common = common + ("linear_outcome_regression",)
    elif model == "logistic":
        common = common + ("logit_outcome_regression",)
    if not summable:
        # Where P(M | X) came from. The enumerating plug-in fits it and can
        # be asked for it anywhere; this one reads it off the arm's own rows,
        # so the answer rests on the arms being large enough for their
        # mediator spreads to BE that conditional — a different assumption,
        # and one only this route makes.
        return common + (
            "mediator_conditional_taken_from_the_arms_own_rows",
        )
    if n_mediators > 1:
        common = common + (
            "chain_rule_factoring_of_joint_mediator_conditional",
        )
    return common
