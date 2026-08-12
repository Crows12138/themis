"""Binary counterfactual cell — the numeric end of ``P(Y_{x'}=y* | X=x [, Y=y])``.

The structural layer (:func:`themis.runtime.scheduler._dispatch_counterfactual`)
answers a :class:`~themis.types.CounterfactualQuery` from ``theta``: it recovers
the observational joint P(X, Y) symbolically, obtains the one interventional
risk P(Y=1 | do(x')) the cell depends on by running the effect identification,
and hands both to
:func:`themis.runtime.counterfactual.counterfactual_cell_interval` — whose one
linear consistency identity covers every cell.

This module is the DATA counterpart: it plugs EMPIRICAL estimates of exactly
those inputs into the SAME solver and adds a non-parametric percentile
bootstrap. Nothing here re-derives the identity; the transcription lives once,
in the solver, and is reused. The two inputs come from
:mod:`themis.estimation.binary_do_risk`, shared with the PN/PS/PNS estimator —
which matters, because the PN cell asked through THIS door and PN asked through
the ``causation`` door are the same number, and they now share the same
empirical inputs on the data side as well as the same theorem on the theta side.

There is a SECOND way to answer the cell, and it is not the identity. When the
interventional risk is not point-identified but the graph carries an
instrument, the cell is bounded directly over the response-type distributions
that reproduce ``P(X, Y | Z)`` — the polytope Balke-Pearl's arm bounds are read
off, with the cell as another linear functional on it
(:func:`themis.estimation.bounds_numeric.counterfactual_cell_response_bounds`).
Feeding the arm's INTERVAL through the identity instead would also be valid and
is strictly weaker: the identity consumes the risk as a scalar, and a scalar
cannot carry the requirement that one distribution produce both the risk and
the cell. Measured over random binary IV models, the two-step route says
something non-trivial about a third as many of them.

What the data end adds over the theta end:

- SAMPLING uncertainty. The theta end answers from a declared distribution and
  so has none; here the interval (or point) carries a percentile bootstrap — a
  point CI when the cell is point-identified, and the OUTER band on the
  identified set otherwise (the Manski / Balke-Pearl data-bounds convention,
  matching ``causation.py``).
- A REFUTATION rate for a declared monotonicity. The solver reports an empty
  feasible set when the joint and the do-risk cannot both hold under the
  declared monotonicity. On the point estimate that is a refusal; across
  bootstrap draws the FRACTION of draws refuted is a finite-sample measure of
  how close the assumption sits to being contradicted by this data, which the
  theta end cannot express at all. It is reported, not swallowed.

Scope (declared):

- BINARY X and Y, and the counterfactual must intervene on the SAME variable
  that is observed (the cell is indexed by that variable's two values).
- The interventional risk is identified by BACK-DOOR adjustment (the empty set
  = exogeneity being the special case), by the general ID algorithm when no
  adjustment set exists, or supplied experimentally. When none of those reach
  it, the graph is asked for an instrument and the cell is bounded over the
  response-type polytope instead. Only when THAT fails too is the cell
  answerable purely from a monotonicity that pins it; failing that the
  estimator refuses and the structural answer stands.
- A declared monotonicity is an extra CONSTRAINT on every route, never a
  second formula: on the identity it pins one cell, and on the instrument it
  removes the response types whose outcome moves against the treatment. The
  instrument route is preferred over the pin where both apply, because the
  pin's own assumption is unfalsifiable without a risk and the polytope can
  refute it — an infeasible program under the restriction, feasible without,
  IS the data contradicting the declared direction.
- The adjustment set must be DISCRETE, and every stratum must have support
  under the arm being standardized (a positivity violation raises). The
  general-ID plug-in likewise needs every stratum its estimand conditions on
  to be present; an IV-identified risk is not wired (a Wald ratio is an ATE,
  not the single arm risk this cell consumes).

API::

    from themis.estimation.counterfactual_cell import estimate_counterfactual_cell
    est = estimate_counterfactual_cell(
        data, graph=g, bidirected=bi, query=q,
    )
    print(est.low, est.high, est.point, est.ci_lower, est.ci_upper)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..runtime import counterfactual as cf
from .. import risk_provenance
from ..risk_provenance import RiskProvenance
from ..output.bounds import MAX_RESPONSE_TYPES, response_type_count
from ..types import Atom, CounterfactualQuery, NumericInterval
from .binary_do_risk import (
    as_binary_column,
    backdoor_do_risk,
    instrument_for,
    minimal_backdoor_adjustment,
    observational_joint_xy,
)
from .bounds_numeric import (
    counterfactual_cell_iv_table,
    counterfactual_cell_response_bounds,
    sorted_levels,
)
from .contract import validate_data
from .. import refusals
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from .general_id import (
    data_domains,
    evaluate_arm_risk,
    identify_arm_risk_formula,
    referenced_predicates,
)
from .resample import cluster_labels, resample_indices


#: The licences this estimator may write, named once in
#: :mod:`themis.risk_provenance` and selected here by the derivation rule this
#: module emits — the rule is what fixes the set, so naming the rule is the
#: whole declaration.
_RULE = "numeric_counterfactual_cell_estimate"

_TOL = 1e-12


@dataclass(frozen=True)
class CounterfactualCellEstimate:
    """One binary counterfactual cell recovered from data, with a bootstrap.

    ``point`` is non-None exactly when the identified set collapsed
    (``low == high``); ``ci_lower`` / ``ci_upper`` is then the point's
    percentile CI, and otherwise the OUTER band on ``[low, high]``.
    """

    # The answer.
    low: float
    high: float
    point: float | None
    ci_lower: float | None
    ci_upper: float | None
    # Inputs recovered from data (audit trail; the verifier re-solves the
    # identity on these and checks the reported cell matches).
    p_x1_y1: float
    p_x1_y0: float
    p_x0_y1: float
    p_x0_y0: float
    p_y_do_x_cf: float | None
    interventional_risk_provenance: RiskProvenance
    adjustment: tuple[str, ...]
    # The instrument route's sufficient statistic. ``instrument`` is None on
    # every other route; when it is set, ``p_xyz`` (|Z|×2×2, positions 0=False
    # 1=True) and ``p_z`` are what the polytope was fitted to and the verifier
    # re-solves the same program from them. The level list travels WITH the
    # table because the table's own shape says nothing about which stratum is
    # which, and a permuted reading re-derives a different interval.
    instrument: str | None
    instrument_levels: tuple
    p_xyz: tuple
    p_z: tuple
    # The general-ID estimand the risk was evaluated from, when that is how it
    # was identified (None otherwise). Carried into the derivation so the
    # verifier can re-derive it and check the arm that was actually evaluated.
    risk_formula: object | None
    # The cell being asked for (the verifier re-reads these off ctx.query).
    x_observed: bool
    x_counterfactual: bool
    y_star: bool
    factual_target_known: bool | None
    monotonicity: str | None
    # Finite-sample behaviour of the feasible set (see the module docstring).
    bootstrap_draws_used: int
    bootstrap_draws_infeasible: int
    # Envelope (parity with the other numeric estimators).
    ci_level: float
    method: str
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    cause: str
    effect: str
    model_assumption: str = ""
    form: str = "nonparametric_gformula_plug_in"
    identification_assumptions: tuple[dict, ...] = ()
    cluster: str | None = None


def estimate_counterfactual_cell(
    data: pd.DataFrame,
    *,
    graph,
    bidirected=frozenset(),
    query: CounterfactualQuery,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> CounterfactualCellEstimate:
    """Estimate one binary counterfactual cell on data + bootstrap its spread.

    Parameters
    ----------
    data: DataFrame with a binary column per observed variable (named by each
        atom's ``predicate``): the treatment, the outcome, and the back-door
        adjustment set.
    graph / bidirected: the projected ADMG (same objects the kernel identified
        on). The minimal back-door adjustment set for the do-risk is read off
        ``graph``.
    query: the counterfactual cell. ``experimental_risk_treated`` /
        ``experimental_risk_control`` on it pass straight through for the
        confounded-but-randomized case, exactly as on the theta path.
    ci_bootstrap: number of bootstrap resamples; 0 skips the CI.
    ci_level: two-sided confidence level.
    random_state: deterministic seed.
    cluster: optional cluster-id column for a pairs cluster bootstrap.

    Raises
    ------
    EstimatorFailure: non-binary or cross-variable cell; the do-risk is
        neither back-door identified nor supplied AND the cell is not pinned;
        the empirical inputs admit no SCM (a do-risk contradicting the joint,
        or a monotonicity the data refute); a positivity violation.
    DataContractError (ValueError): missing column, NaN, or too-small sample.
    """
    x_atom = query.observed.atom
    y_atom = query.counterfactual_target.atom
    if query.counterfactual_intervention.atom != x_atom:
        raise EstimatorFailure(
            Refusal.COUNTERFACTUAL_CELL_CROSS_VARIABLE,
            "the counterfactual cell estimator intervenes on the SAME variable "
            f"it conditions on; got do({query.counterfactual_intervention.atom.predicate}) "
            f"with X={x_atom.predicate} observed",
        )
    x_obs = query.observed.value
    x_cf = query.counterfactual_intervention.value
    y_star = query.counterfactual_target.value
    factual_y = query.factual_target_known
    for label, value in (
        ("observed", x_obs),
        ("counterfactual_intervention", x_cf),
        ("counterfactual_target", y_star),
        ("factual_target_known", factual_y),
    ):
        if value is not None and not isinstance(value, bool):
            raise EstimatorFailure(
                Refusal.COUNTERFACTUAL_CELL_NOT_BINARY,
                f"the counterfactual cell estimator is boolean-only; "
                f"{label}={value!r}",
            )

    xcol, ycol = x_atom.predicate, y_atom.predicate

    # 1. Interventional-risk strategy. Only the ONE arm the cell depends on is
    #    ever fetched — the other is information this answer does not use, and
    #    demanding it would manufacture a data requirement out of nothing.
    supplied: float | None = None
    adjustment: tuple[str, ...] = ()
    risk_formula = None
    instrument: Atom | None = None
    if x_cf == x_obs:
        provenance = RiskProvenance.NOT_REQUIRED
    else:
        supplied = (
            query.experimental_risk_treated if x_cf
            else query.experimental_risk_control
        )
        if supplied is not None:
            provenance = RiskProvenance.USER_EXPERIMENTAL
        else:
            try:
                adjustment = minimal_backdoor_adjustment(
                    graph, x_atom, y_atom, bidirected,
                )
            except EstimatorFailure:
                # No adjustment set. That is NOT the end of identification:
                # the general ID algorithm reaches estimands no covariate set
                # blocks (a front-door structure, a napkin), and the cell only
                # ever needed this ONE arm.
                try:
                    risk_formula = identify_arm_risk_formula(
                        graph, bidirected,
                        treatment_atom=x_atom, outcome_atom=y_atom,
                        # The cell's coordinates are booleans and the column is
                        # binary; True/False and 1/0 compare and hash alike, so
                        # the literal threaded through the estimand matches the
                        # data's own levels either way.
                        arm_value=x_cf, outcome_value=True,
                    )
                except EstimatorFailure:
                    # No do-risk is POINT-identified from this frame (a bow
                    # arc). That is the end of the identity's road, not of
                    # identification: an instrument does not deliver the risk
                    # as a number, but it does deliver the set of models the
                    # data admit, and the cell is a linear functional on it.
                    instrument = instrument_for(graph, x_atom, y_atom, bidirected)
                    provenance = (
                        RiskProvenance.PINNED_BY_MONOTONICITY
                        if instrument is None
                        else RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE
                    )
                else:
                    provenance = RiskProvenance.GENERAL_ID_PLUG_IN
            else:
                provenance = (
                    RiskProvenance.EXOGENOUS if not adjustment
                    else RiskProvenance.BACKDOOR_ADJUSTMENT
                )

    zcol = None if instrument is None else instrument.predicate
    required = {xcol, ycol, *adjustment}
    if risk_formula is not None:
        required |= referenced_predicates(risk_formula)
    if zcol is not None:
        required.add(zcol)
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

    # 2. Binary treatment & outcome only.
    x = as_binary_column(df[xcol], xcol)
    y = as_binary_column(df[ycol], ycol)

    twin = cf.project_twin_network(graph, bidirected, query)
    # The general-ID estimand is identified ONCE (data-independent) and its
    # sum ranges are pinned to the FULL-data domains, so every bootstrap draw
    # evaluates the same estimand rather than a quietly narrower one.
    domains = data_domains(graph, df) if risk_formula is not None else {}
    # The instrument's levels are likewise fixed on the FULL data, so every
    # replicate is fitted to a table with the same axes; a draw that happens to
    # miss a stratum is a positivity failure of that draw, not a smaller model.
    z_levels = [] if zcol is None else sorted_levels(df[zcol])
    if zcol is not None:
        _refuse_unless_the_polytope_is_solvable(zcol, z_levels)
    monotone = (
        query.assumptions.monotonicity
        if query.assumptions is not None else None
    )

    def _run(x_arr, y_arr, frame):
        """Empirical joint, then whichever solver this route licenses.

        The fourth return is the instrument route's sufficient statistic — the
        very table the reported interval came out of, rather than a second
        pass over the same frame that could differ from it.
        """
        joint = observational_joint_xy(x_arr, y_arr)
        if provenance is RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE:
            # No scalar risk passes through on this route: the polytope is
            # fitted to the conditional table and the cell read off it.
            P, p_z = counterfactual_cell_iv_table(
                x_arr, y_arr, frame[zcol].to_numpy(), z_levels,
            )
            low, high = counterfactual_cell_response_bounds(
                P, p_z,
                x_observed=int(x_obs), x_counterfactual=int(x_cf),
                y_star=int(y_star),
                factual_y=None if factual_y is None else int(factual_y),
                monotonicity=monotone,
            )
            return joint, None, NumericInterval(low=low, high=high), (P, p_z)
        if provenance is RiskProvenance.USER_EXPERIMENTAL:
            risk = float(supplied)
        elif provenance in (RiskProvenance.EXOGENOUS,
                            RiskProvenance.BACKDOOR_ADJUSTMENT):
            risk = backdoor_do_risk(x_arr, y_arr, frame, adjustment, arm=x_cf)
        elif provenance is RiskProvenance.GENERAL_ID_PLUG_IN:
            risk = evaluate_arm_risk(risk_formula, frame, domains=domains)
        else:
            risk = None
        interval = cf.counterfactual_cell_interval(
            twin, query, joint, p_y_do_x_cf=risk,
        )
        return joint, risk, interval, None

    # 3. Point estimate.
    try:
        joint, risk, interval, iv_table = _run(x, y, df)
    except cf.InterventionalRiskRequired as need:
        # Its own branch for the message, not for the species: this is the
        # one case where the solver's sentence is not the one to show, since
        # the remedy names data the caller can go and get.
        raise EstimatorFailure(
            need.species,
            f"P(Y=1|do({xcol}={need.needed_x_value})) is identified from this "
            f"graph by neither a back-door adjustment set nor the general ID "
            f"algorithm, and was not supplied; this cell is not determined "
            f"without it. Supply experimental_risk_treated / "
            f"experimental_risk_control from a randomized experiment.",
        ) from need
    except cf.CounterfactualBoundsError as exc:
        # Which species this is belongs to the exception, so the θ end in
        # runtime.scheduler reaches the same one without a second copy of
        # the mapping — the copy it never had.
        raise EstimatorFailure(exc.species, str(exc)) from exc

    # 4. Percentile bootstrap. A draw whose feasible set is empty is NOT a
    #    silent skip: it means that resample refutes the declared monotonicity,
    #    and the count is reported alongside the interval.
    ci_lower = ci_upper = None
    used = infeasible = 0
    if ci_bootstrap > 0:
        ci_lower, ci_upper, used, infeasible = _bootstrap_cell(
            _run, x, y, df,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level,
            random_state=random_state, groups=groups,
            is_point=abs(interval.high - interval.low) <= _TOL,
        )

    is_point = abs(interval.high - interval.low) <= _TOL
    monotonicity = (
        query.assumptions.monotonicity.value
        if query.assumptions is not None and query.assumptions.monotonicity is not None
        else None
    )
    return CounterfactualCellEstimate(
        low=interval.low, high=interval.high,
        point=interval.low if is_point else None,
        ci_lower=ci_lower, ci_upper=ci_upper,
        p_x1_y1=joint[(True, True)], p_x1_y0=joint[(True, False)],
        p_x0_y1=joint[(False, True)], p_x0_y0=joint[(False, False)],
        p_y_do_x_cf=risk,
        interventional_risk_provenance=risk_provenance.stamp(_RULE, provenance),
        adjustment=adjustment,
        instrument=zcol,
        instrument_levels=tuple(_py(v) for v in z_levels),
        p_xyz=_nested(iv_table[0]) if iv_table else (),
        p_z=tuple(float(v) for v in iv_table[1]) if iv_table else (),
        risk_formula=risk_formula,
        x_observed=bool(x_obs), x_counterfactual=bool(x_cf),
        y_star=bool(y_star), factual_target_known=factual_y,
        monotonicity=monotonicity,
        bootstrap_draws_used=used, bootstrap_draws_infeasible=infeasible,
        ci_level=ci_level,
        method="counterfactual_cell_plugin",
        assumptions=_assumptions(provenance, adjustment, monotonicity, cluster),
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        cause=xcol, effect=ycol,
        model_assumption=_model_assumption(provenance, zcol),
        form=_FORM_BY_PROVENANCE.get(
            provenance, "nonparametric_gformula_plug_in",
        ),
        identification_assumptions=_identification_assumptions(
            provenance, adjustment, monotonicity, zcol,
        ),
        cluster=cluster,
    )


# --- internals ----------------------------------------------------------------


#: The mechanism sentence's short name, by the route that produced it. Only
#: the routes that depart from the g-formula appear; the table is a lookup
#: with a default rather than a chain because a fourth route added to the
#: cascade should be a row here, not another branch to get the order right in.
_FORM_BY_PROVENANCE = {
    RiskProvenance.GENERAL_ID_PLUG_IN: "nonparametric_c_factor_plug_in",
    RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE:
        "nonparametric_response_function_lp",
}


def _refuse_unless_the_polytope_is_solvable(zcol: str, z_levels: list) -> None:
    """The instrument route's two preconditions on the instrument column.

    An instrument that never varies enumerates one ``z → x`` map and carries
    no information; one with too many levels enumerates ``2^|Z| · 4`` types and
    the LP behind them is re-solved once per bootstrap replicate. Neither is a
    reason to fall back quietly to a route that would have answered a weaker
    question — the caller is told which of its columns is the obstacle and
    what to do to it.
    """
    if len(z_levels) < 2:
        raise EstimatorFailure(
            Refusal.INSUFFICIENT_SUPPORT,
            f"instrument {zcol!r} takes a single value "
            f"({refusals.describe(z_levels)}) in this sample; an instrument "
            f"that never varies carries no response types to bound over.",
        )
    if response_type_count(
        treatment_levels=2, outcome_levels=2, instrument_levels=len(z_levels),
    ) is None:
        raise EstimatorFailure(
            Refusal.RESPONSE_MODEL_TOO_LARGE,
            f"instrument {zcol!r} has {len(z_levels)} observed levels, so the "
            f"response-function partition has 2^{len(z_levels)}·4 types — "
            f"above the {MAX_RESPONSE_TYPES} this package solves. The sharp "
            f"interval exists; it is the LP, re-solved once per bootstrap "
            f"replicate, that is declined. Coarsening the instrument brings "
            f"the method back in reach.",
        )


def _nested(P: np.ndarray) -> tuple:
    """The ``P(X, Y | Z)`` table as plain nested tuples of floats, so what the
    envelope carries is what the LP consumed and not a numpy view of it."""
    return tuple(
        tuple(tuple(float(P[z, x, y]) for y in range(P.shape[2]))
              for x in range(P.shape[1]))
        for z in range(P.shape[0])
    )


def _py(v):
    """A numpy scalar as the Python value it stands for."""
    return v.item() if isinstance(v, np.generic) else v


def _bootstrap_cell(
    run, x: np.ndarray, y: np.ndarray, frame: pd.DataFrame, *,
    ci_bootstrap: int, ci_level: float, random_state: int,
    groups: np.ndarray | None, is_point: bool,
) -> tuple[float | None, float | None, int, int]:
    """Percentile bootstrap of the cell.

    Point-identified: the CI is the percentile interval of the point across
    draws. Interval-valued: the OUTER band ``(low-quantile of the LOWER
    endpoints, high-quantile of the UPPER endpoints)`` — the Manski /
    Balke-Pearl data-bounds convention shared with ``causation.py``.

    Returns ``(ci_lower, ci_upper, draws_used, draws_infeasible)``. A draw is
    counted infeasible when its empirical inputs admit no SCM under the
    declared assumptions; a draw dropped for a positivity hole is neither used
    nor infeasible (the assumption is not what failed).

    The count keys on WHICH FAILURE it was, not on which exception class
    carried it. The two solvers raise from different hierarchies — the
    identity through :mod:`themis.runtime.counterfactual`, the polytope as an
    estimator refusal — and one refutation of the same declared assumption
    would otherwise be reported to the reader and the other silently dropped.
    """
    rng = np.random.default_rng(random_state)
    n = len(frame)
    lows: list[float] = []
    highs: list[float] = []
    infeasible = 0
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        try:
            _joint, _risk, itv, _table = run(x[idx], y[idx], frame.iloc[idx])
        except (EstimatorFailure, cf.CounterfactualBoundsError) as exc:
            species = getattr(exc, "failure_type", None) or getattr(
                exc, "species", None)
            if species is Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE:
                infeasible += 1
            continue
        lows.append(itv.low)
        highs.append(itv.high)

    used = len(lows)
    if used < 2:
        return None, None, used, infeasible
    alpha = (1 - ci_level) / 2
    if is_point:
        arr = np.asarray(lows)
        return (
            float(np.quantile(arr, alpha)),
            float(np.quantile(arr, 1 - alpha)),
            used, infeasible,
        )
    return (
        float(np.quantile(np.asarray(lows), alpha)),
        float(np.quantile(np.asarray(highs), 1 - alpha)),
        used, infeasible,
    )


def _model_assumption(
    provenance: RiskProvenance, instrument: str | None,
) -> str:
    """The mechanism sentence: which solver ran, and how its inputs were got."""
    if provenance is RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE:
        # The one route that does not go through the identity at all, so the
        # sentence does not start by naming it.
        return (
            "反事实单格 P(Y_{x'}=y*|X=x[,Y=y]) 没有走一致性恒等式："
            f"那一臂干预风险不可点识别，改用工具变量 `{instrument}` 的响应函数模型——"
            "在所有能复现经验 P(X,Y|Z) 的响应型分布上，把本格作为线性泛函取上下确界"
            "（无函数形式假设）；"
            "单调性(若声明)是从总体里去掉反向响应型的额外约束，不是回答的前提"
        )
    if provenance is RiskProvenance.GENERAL_ID_PLUG_IN:
        risk = (
            "所需的那一臂干预风险 P(Y=1|do x') 没有可用的调整集，"
            "改由 general ID（c-factor 分解）识别出的估计量按非参数 plug-in 求值"
            "（每个条件概率取其所属数据层的经验频率，无函数形式假设）"
        )
    else:
        risk = (
            "所需的那一臂干预风险 P(Y=1|do x') "
            "用后门标准化(饱和 g-formula，无函数形式假设)"
        )
    return (
        "反事实单格 P(Y_{x'}=y*|X=x[,Y=y]) 由一条一致性恒等式求解："
        "观测联合 P(X,Y) 用经验频率，" + risk + "；"
        "单调性(若声明)是把区间收紧成点的额外约束，不是回答的前提"
    )


def _assumptions(
    provenance: RiskProvenance, adjustment: tuple[str, ...],
    monotonicity: str | None,
    cluster: str | None,
) -> tuple[str, ...]:
    out = [
        "binary_treatment_and_outcome",
        "consistency_of_potential_outcomes",
    ]
    if provenance is RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE:
        out.append("iv1_relevance_instrument_affects_treatment")
        out.append(
            "iv2_exclusion_instrument_affects_outcome_only_via_treatment")
        out.append(
            "iv3_independence_instrument_independent_of_latent_confounders")
        # Every instrument stratum having observations is NOT listed: the
        # table builder refuses on an empty one, so it is a precondition this
        # answer passed rather than a premise it rests on.
    elif provenance is RiskProvenance.USER_EXPERIMENTAL:
        out.append("interventional_risk_from_randomized_experiment")
    elif provenance is RiskProvenance.EXOGENOUS:
        out.append("exogeneity_no_backdoor_path_do_risk_equals_conditional")
    elif provenance is RiskProvenance.BACKDOOR_ADJUSTMENT:
        out.append(
            "backdoor_adjustment_set_{" + ",".join(adjustment) + "}_sufficient"
        )
        out.append("positivity_the_asked_arm_has_support_in_each_stratum")
    elif provenance is RiskProvenance.GENERAL_ID_PLUG_IN:
        out.append("admg_structure_correct_including_latent_confounders")
        out.append("positivity_every_conditioning_stratum_of_the_estimand_has_support")
        out.append("discrete_variables_saturated_nonparametric_plug_in")
    # No do-risk being available is not a further assumption: it is why the
    # one below cannot be refuted, and it is said on that line rather than
    # beside it.
    if monotonicity is not None:
        out.append(f"monotonicity_{monotonicity}_in_treatment")
    # No else — see :func:`themis.estimation.causation._assumptions`.
    if cluster is not None:
        out.append(f"ci_via_pairs_cluster_bootstrap_on_{cluster}")
    return tuple(out)


def _identification_assumptions(
    provenance: RiskProvenance, adjustment: tuple[str, ...],
    monotonicity: str | None, instrument: str | None,
) -> tuple[dict, ...]:
    specs: list[dict] = [
        {"id": "consistency_of_potential_outcomes",
         "claim": "一致性：potential outcomes 良定义，观测到的 Y 等于所受干预下的 Y",
         "layer": "identification", "testable": False},
    ]
    if provenance is RiskProvenance.USER_EXPERIMENTAL:
        specs.append(
            {"id": "interventional_risk_from_randomized_experiment",
             "claim": "干预风险 P(Y=1|do x') 来自随机实验，无混杂",
             "layer": "identification", "testable": False})
    elif provenance is RiskProvenance.EXOGENOUS:
        specs.append(
            {"id": "exogeneity_no_backdoor_path_do_risk_equals_conditional",
             "claim": "外生性：X 到 Y 无后门路径，P(Y|do x')=P(Y|x')",
             "layer": "identification", "testable": False})
    elif provenance is RiskProvenance.BACKDOOR_ADJUSTMENT:
        specs.append(
            {"id": "backdoor_adjustment_set_{" + ",".join(adjustment) + "}_sufficient",
             "claim": f"后门调整集充分：{{{','.join(adjustment)}}} 阻断 X→Y 的所有后门路径",
             "layer": "identification", "testable": False})
        specs.append(
            {"id": "positivity_the_asked_arm_has_support_in_each_stratum",
             "claim": "positivity：每个调整层在被问的那个处理臂下都有样本",
             "layer": "identification", "testable": True})
    elif provenance is RiskProvenance.GENERAL_ID_PLUG_IN:
        specs.append(
            {"id": "admg_structure_correct_including_latent_confounders",
             "claim": "没有可用的调整集，干预风险经 general ID（c-factor 分解）识别："
                      "ADMG 结构正确——所有有向边与潜混杂 (↔) 边如实建模",
             "layer": "identification", "testable": False})
        specs.append(
            {"id": "positivity_every_conditioning_stratum_of_the_estimand_has_support",
             "claim": "positivity：识别公式条件到的每个前驱层在数据中都有样本",
             "layer": "identification", "testable": True})
    elif provenance is RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE:
        specs.append(
            {"id": "iv1_relevance_instrument_affects_treatment",
             "claim": f"相关性：`{instrument}` 有一条指向处理的边，"
                      f"响应函数模型枚举的就是这条 z→x 映射",
             "layer": "identification", "testable": True})
        specs.append(
            {"id": "iv2_exclusion_instrument_affects_outcome_only_via_treatment",
             "claim": f"排他性：把处理的出边剪掉之后，`{instrument}` 与结局 "
                      f"m-分离——它对结局的全部影响都经过处理",
             "layer": "identification", "testable": False})
        specs.append(
            {"id": "iv3_independence_instrument_independent_of_latent_confounders",
             "claim": f"独立性：`{instrument}` 与那个未测混杂背景无关，"
                      f"这正是「响应型的分布不随 z 变化」这一条",
             "layer": "identification", "testable": True})
    if monotonicity is not None:
        # Monotonicity is testable when the route brings it up against
        # something the data could contradict — an emptiness check needs one.
        # That used to be read off "was a do-risk an input", which was the
        # same question for as long as the identity was the only solver; the
        # polytope refutes it while consuming no risk at all. It used to be a
        # SECOND entry beside this one, saying the cell was pinned by
        # monotonicity alone — but a do-risk being unavailable assumes nothing
        # about the world, and its whole content is what this line can and
        # cannot be checked against. It is said here, on the line it is about,
        # and nowhere else.
        claim = (
            f"单调性（{monotonicity}）：总体中没有结局与处理反向的单位，"
            f"据此收紧本格"
        )
        if not provenance.can_refute_a_premise:
            claim += "——而干预风险不可得，数据无从推翻它"
        specs.append(
            {"id": f"monotonicity_{monotonicity}_in_treatment",
             "claim": claim,
             "layer": "identification",
             "testable": provenance.can_refute_a_premise})
    return tuple(specs)
