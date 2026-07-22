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
  adjustment set exists, or supplied experimentally. Only when ALL of those
  fail is the cell answerable purely from a monotonicity that pins it; failing
  that the estimator refuses and the structural answer stands.
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
from ..types import CounterfactualQuery
from .binary_do_risk import (
    as_binary_column,
    backdoor_do_risk,
    minimal_backdoor_adjustment,
    observational_joint_xy,
)
from .contract import validate_data
from .dose_response import EstimatorFailure
from .general_id import (
    data_domains,
    evaluate_arm_risk,
    identify_arm_risk_formula,
    referenced_predicates,
)
from .resample import cluster_labels, resample_indices


# How the interventional risk P(Y=1 | do(x')) behind this cell was obtained.
# The first two mean NO risk was used at all, and each carries its own
# justification for why the answer does not need one — which is what makes the
# claim auditable rather than self-certifying:
#   not_required           - both worlds coincide; consistency answers the cell
#   pinned_by_monotonicity - the declared monotonicity determines it outright
#   user_experimental      - supplied from a randomized experiment
#   exogenous              - back-door standardized over the EMPTY set
#   backdoor_adjustment    - back-door standardized over a non-empty set
#   general_id_plug_in     - no adjustment set exists, but the general ID
#                            algorithm point-identifies the arm anyway
RISK_PROVENANCES = frozenset({
    "not_required",
    "pinned_by_monotonicity",
    "user_experimental",
    "exogenous",
    "backdoor_adjustment",
    "general_id_plug_in",
})

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
    interventional_risk_provenance: str
    adjustment: tuple[str, ...]
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
            "counterfactual_cell_cross_variable",
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
                "counterfactual_cell_not_binary",
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
    if x_cf == x_obs:
        provenance = "not_required"
    else:
        supplied = (
            query.experimental_risk_treated if x_cf
            else query.experimental_risk_control
        )
        if supplied is not None:
            provenance = "user_experimental"
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
                    # Genuinely unidentified (a bow arc): no do-risk from this
                    # frame at all. The cell may STILL be determined if
                    # monotonicity pins it — the solver decides, and refuses
                    # (InterventionalRiskRequired) if not.
                    provenance = "pinned_by_monotonicity"
                else:
                    provenance = "general_id_plug_in"
            else:
                provenance = "exogenous" if not adjustment else "backdoor_adjustment"

    required = {xcol, ycol, *adjustment}
    if risk_formula is not None:
        required |= referenced_predicates(risk_formula)
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

    def _run(x_arr, y_arr, frame):
        """Empirical joint + (if the cell needs it) the one do-risk → solver."""
        joint = observational_joint_xy(x_arr, y_arr)
        if provenance == "user_experimental":
            risk = float(supplied)
        elif provenance in ("exogenous", "backdoor_adjustment"):
            risk = backdoor_do_risk(x_arr, y_arr, frame, adjustment, arm=x_cf)
        elif provenance == "general_id_plug_in":
            risk = evaluate_arm_risk(risk_formula, frame, domains=domains)
        else:
            risk = None
        interval = cf.counterfactual_cell_interval(
            twin, query, joint, p_y_do_x_cf=risk,
        )
        return joint, risk, interval

    # 3. Point estimate.
    try:
        joint, risk, interval = _run(x, y, df)
    except cf.InterventionalRiskRequired as need:
        raise EstimatorFailure(
            "interventional_risk_not_identifiable",
            f"P(Y=1|do({xcol}={need.needed_x_value})) is identified from this "
            f"graph by neither a back-door adjustment set nor the general ID "
            f"algorithm, and was not supplied; this cell is not determined "
            f"without it. Supply experimental_risk_treated / "
            f"experimental_risk_control from a randomized experiment.",
        ) from need
    except cf.CounterfactualInfeasible as exc:
        raise EstimatorFailure(
            "counterfactual_inputs_infeasible", str(exc),
        ) from exc
    except cf.CounterfactualBoundsError as exc:
        raise EstimatorFailure(
            "counterfactual_cell_out_of_scope", str(exc),
        ) from exc

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
        interventional_risk_provenance=provenance,
        adjustment=adjustment,
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
        model_assumption=_model_assumption(provenance),
        form=(
            "nonparametric_c_factor_plug_in"
            if provenance == "general_id_plug_in"
            else "nonparametric_gformula_plug_in"
        ),
        identification_assumptions=_identification_assumptions(
            provenance, adjustment, monotonicity,
        ),
        cluster=cluster,
    )


# --- internals ----------------------------------------------------------------


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
    """
    rng = np.random.default_rng(random_state)
    n = len(frame)
    lows: list[float] = []
    highs: list[float] = []
    infeasible = 0
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        try:
            _joint, _risk, itv = run(x[idx], y[idx], frame.iloc[idx])
        except cf.CounterfactualInfeasible:
            infeasible += 1
            continue
        except (EstimatorFailure, cf.CounterfactualBoundsError):
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


def _model_assumption(provenance: str) -> str:
    """The mechanism sentence — one identity, and how its one input was got."""
    if provenance == "general_id_plug_in":
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
    provenance: str, adjustment: tuple[str, ...], monotonicity: str | None,
    cluster: str | None,
) -> tuple[str, ...]:
    out = [
        "binary_treatment_and_outcome",
        "consistency_of_potential_outcomes",
    ]
    if provenance == "user_experimental":
        out.append("interventional_risk_from_randomized_experiment")
    elif provenance == "exogenous":
        out.append("exogeneity_no_backdoor_path_do_risk_equals_conditional")
    elif provenance == "backdoor_adjustment":
        out.append(
            "backdoor_adjustment_set_{" + ",".join(adjustment) + "}_sufficient"
        )
        out.append("positivity_the_asked_arm_has_support_in_each_stratum")
    elif provenance == "general_id_plug_in":
        out.append("admg_structure_correct_including_latent_confounders")
        out.append("positivity_every_conditioning_stratum_of_the_estimand_has_support")
        out.append("discrete_variables_saturated_nonparametric_plug_in")
    elif provenance == "pinned_by_monotonicity":
        # No do-risk was available, so the emptiness check that would have
        # refuted the monotonicity never ran. Say so.
        out.append("cell_determined_by_monotonicity_alone_no_interventional_risk")
    if monotonicity is not None:
        out.append(f"monotonicity_{monotonicity}_in_treatment")
    else:
        out.append("no_monotonicity_assumption_free_interval")
    if cluster is not None:
        out.append(f"ci_via_pairs_cluster_bootstrap_on_{cluster}")
    return tuple(out)


def _identification_assumptions(
    provenance: str, adjustment: tuple[str, ...], monotonicity: str | None,
) -> tuple[dict, ...]:
    specs: list[dict] = [
        {"claim": "一致性：potential outcomes 良定义，观测到的 Y 等于所受干预下的 Y",
         "layer": "identification", "severity": "invalidating", "testable": False},
    ]
    if provenance == "user_experimental":
        specs.append(
            {"claim": "干预风险 P(Y=1|do x') 来自随机实验，无混杂",
             "layer": "identification", "severity": "invalidating", "testable": False})
    elif provenance == "exogenous":
        specs.append(
            {"claim": "外生性：X 到 Y 无后门路径，P(Y|do x')=P(Y|x')",
             "layer": "identification", "severity": "invalidating", "testable": False})
    elif provenance == "backdoor_adjustment":
        specs.append(
            {"claim": f"后门调整集充分：{{{','.join(adjustment)}}} 阻断 X→Y 的所有后门路径",
             "layer": "identification", "severity": "invalidating", "testable": False})
        specs.append(
            {"claim": "positivity：每个调整层在被问的那个处理臂下都有样本",
             "layer": "identification", "severity": "invalidating", "testable": True})
    elif provenance == "general_id_plug_in":
        specs.append(
            {"claim": "没有可用的调整集，干预风险经 general ID（c-factor 分解）识别："
                      "ADMG 结构正确——所有有向边与潜混杂 (↔) 边如实建模",
             "layer": "identification", "severity": "invalidating", "testable": False})
        specs.append(
            {"claim": "positivity：识别公式条件到的每个前驱层在数据中都有样本",
             "layer": "identification", "severity": "invalidating", "testable": True})
    elif provenance == "pinned_by_monotonicity":
        specs.append(
            {"claim": "干预风险不可得，本格完全由单调性钉死——因此数据无从推翻这条单调性",
             "layer": "assumption", "severity": "invalidating", "testable": False})
    if monotonicity is not None:
        specs.append(
            {"claim": f"单调性（{monotonicity}）：把本格的区间收紧成点",
             "layer": "assumption", "severity": "consequential",
             "testable": provenance not in ("not_required", "pinned_by_monotonicity")})
    return tuple(specs)
