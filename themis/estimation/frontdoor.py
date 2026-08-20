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
to the original 2^k enumeration exactly. Genuinely continuous mediators
(fractional-valued floats, or more than ``MAX_LEVELS_PER_MEDIATOR``
distinct values) need density estimation / integration and are deferred.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression, LogisticRegression

from .. import refusals
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from .contract import validate_data
from .resample import cluster_labels, resample_indices


ModelName = Literal["auto", "linear", "logistic"]

# A mediator with more distinct values than this is treated as continuous /
# high-cardinality and deferred (exact stratum enumeration would be a poor
# model and, past the cross-product cap, infeasible).
MAX_LEVELS_PER_MEDIATOR = 20
# Ceiling on ``∏_i k_i`` — the number of mediator-value strata the outer sum
# enumerates. Guards against combinatorial blow-up across many mediators.
MAX_MEDIATOR_CROSSPRODUCT = 2048


@dataclass(frozen=True)
class FrontdoorEstimate:
    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                   # "frontdoor_linear" | "frontdoor_logistic"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    mediators: tuple[str, ...]
    treatment: str
    outcome: str
    cluster: str | None = None


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
    )
    df = contract.data

    outcome_series = df[outcome]
    is_bool_outcome = pd.api.types.is_bool_dtype(outcome_series)
    resolved = (
        ("logistic" if is_bool_outcome else "linear")
        if model == "auto" else model
    )
    method = f"frontdoor_{resolved}"

    point = _point_estimate_frontdoor(
        df, treatment, outcome, mediators, model=resolved,
    )

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap_ci_frontdoor(
            df, treatment, outcome, mediators,
            model=resolved, ci_bootstrap=ci_bootstrap,
            ci_level=ci_level, random_state=random_state,
            groups=groups,
        )

    assumptions = _assumptions_for(resolved, len(mediators))
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
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        mediators=tuple(mediators),
        treatment=treatment,
        outcome=outcome,
        cluster=cluster,
    )


# --- internals ----------------------------------------------------------------


def _discrete_levels(series: pd.Series, name: str) -> list:
    """Sorted discrete level set of a mediator, or raise ``NotImplementedError``
    when it looks continuous.

    Discrete = integer-valued (bool included) with at most
    ``MAX_LEVELS_PER_MEDIATOR`` distinct values. Fractional values or higher
    cardinality are treated as continuous and deferred: a genuinely
    continuous mediator needs density estimation / integration, a separate
    estimator family.

    Integer-valuedness rather than dtype, because the contract has already
    widened every integer column to float64 by the time a mediator arrives —
    the dtype below only separates the contract's bool arm from its float
    arm, which is why the float arm carries the whole test.
    """
    s = series.dropna()
    if pd.api.types.is_float_dtype(series):
        vals = s.to_numpy(dtype=float)
        integer_valued = bool(vals.size) and bool(
            np.all(np.isfinite(vals)) and np.all(vals == np.round(vals))
        )
        if not integer_valued:
            raise EstimatorFailure(
                Refusal.CONTINUOUS_MEDIATOR,
                f"front-door estimator does not support continuous mediator "
                f"{name!r} (float dtype with non-integer values); only "
                f"discrete/categorical mediators are supported. Continuous-"
                f"mediator front-door needs density estimation and is deferred.",
                mediator=name,
            )
    nunique = int(s.nunique())
    if nunique > MAX_LEVELS_PER_MEDIATOR:
        raise EstimatorFailure(
            Refusal.CONTINUOUS_MEDIATOR,
            f"front-door estimator treats mediator {name!r} as continuous: "
            f"{nunique} distinct values exceeds the {MAX_LEVELS_PER_MEDIATOR}-"
            f"level cap for exact stratum enumeration. High-cardinality / "
            f"continuous front-door is deferred.",
            mediator=name, levels=nunique, cap=MAX_LEVELS_PER_MEDIATOR,
        )
    return sorted(s.unique().tolist())


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
    """
    import itertools

    # Discrete level set per mediator (raises on a continuous mediator).
    levels = {m: _discrete_levels(df[m], m) for m in mediators}
    crossproduct = 1
    for m in mediators:
        crossproduct *= len(levels[m])
    if crossproduct > MAX_MEDIATOR_CROSSPRODUCT:
        raise EstimatorFailure(
            Refusal.MEDIATOR_STRATA_INTRACTABLE,
            f"front-door stratum cross-product {crossproduct} exceeds the "
            f"{MAX_MEDIATOR_CROSSPRODUCT}-combination cap; too many mediator "
            f"level combinations to enumerate exactly.",
            combinations=crossproduct, cap=MAX_MEDIATOR_CROSSPRODUCT,
        )
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
        Refusal.INVALID_INPUT,
        f"unknown model {model!r}; the front-door estimator fits 'logistic' "
        f"or 'linear'",
        model=model,
    )


def _bootstrap_ci_frontdoor(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    mediators: tuple[str, ...],
    *,
    model: str,
    ci_bootstrap: int,
    ci_level: float,
    random_state: int,
    groups: np.ndarray | None = None,
) -> tuple[float, float]:
    rng = np.random.default_rng(random_state)
    n = len(df)
    estimates = np.empty(ci_bootstrap)
    for i in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        sample = df.iloc[idx]
        estimates[i] = _point_estimate_frontdoor(
            sample, treatment, outcome, mediators, model=model,
        )
    alpha = (1 - ci_level) / 2
    return float(np.quantile(estimates, alpha)), float(
        np.quantile(estimates, 1 - alpha)
    )


def _assumptions_for(model: str, n_mediators: int) -> tuple[str, ...]:
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
    if n_mediators > 1:
        common = common + (
            "chain_rule_factoring_of_joint_mediator_conditional",
        )
    return common
