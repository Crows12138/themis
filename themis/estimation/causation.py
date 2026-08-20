"""Probabilities-of-causation numeric end — PN / PS / PNS from a DataFrame.

The structural layer (:func:`themis.runtime.scheduler._dispatch_causation`)
answers a :class:`~themis.types.CausationQuery` from ``theta`` — the symbolic
parameter store — and hands the four observational cells P(X, Y) plus the two
interventional risks P(Y=1 | do(X=1/0)) to
:func:`themis.runtime.probabilities_of_causation.probabilities_of_causation`,
the Tian & Pearl (2000) oracle. This module is the DATA counterpart: it plugs
EMPIRICAL estimates of exactly those inputs into the SAME oracle and adds a
non-parametric percentile-bootstrap CI. Nothing here re-derives a formula — the
Tian-Pearl transcription lives once, in the oracle, and is reused.

Two quantities have to be estimated from data before the oracle runs — the
four observational cells P(X=x, Y=y) and the two interventional risks
P(Y=1 | do(X=x)). Which route reaches those risks is not this module's
question: :func:`themis.estimation.binary_do_risk.choose_risk_route` is the
one cascade, and this door differs from the counterfactual-cell door only in
asking it for BOTH arms rather than one.

There is a SECOND way to answer, and it consumes no risk at all. When no
route point-identifies the risks but the graph carries an instrument, all
three quantities are bounded directly over the response-type distributions
that reproduce P(X, Y | Z) — and they are three reads of ONE polytope,
because PN, PS and PNS name the same outcome-response map (the unit whose
outcome follows the treatment) and differ only in the factual population the
question asks about. Tian-Pearl's closed form has nothing to consume there,
so this is not a tighter version of that answer; it is an answer where that
one does not exist.

Reference: Tian & Pearl 2000, "Probabilities of Causation: Bounds and
Identification" (Annals of Math & AI 28:287-313); Balke & Pearl 1994 (UAI)
for the response-function program; Hernán & Robins 2020 ch.13 for the
g-formula (standardization) plug-in in the non-parametric limit.

Scope (declared):

- BINARY cause X and BINARY effect Y (PN/PS/PNS are defined only for binary
  X, Y); the estimator coerces {0,1}/{False,True} and refuses otherwise.
- The interventional risks are identified by BACK-DOOR adjustment (the empty
  set = exogeneity is the special case), by the general ID algorithm when no
  adjustment set exists, or supplied experimentally. When none of those reach
  them, the graph is asked for an instrument and the three quantities are
  bounded over the response-type polytope instead. Only when THAT fails too
  does the estimator refuse and the structural answer stand.
- The adjustment set must be DISCRETE (the saturated stratified g-formula has
  no empirical stratum for a continuous covariate); a stratum with no support
  under some treatment arm is a positivity violation and raises. The
  general-ID plug-in likewise needs every stratum its estimand conditions on.
- A declared ``monotonic`` reaches the two routes at different places, because
  the two theorems have different places for it. In the closed form it is a
  SECOND formula (Tian-Pearl Thm 3), so the answer is the assumption-free
  interval WITH a point beside it. On the polytope it is a restriction of the
  model — no unit whose outcome moves against the treatment — so it narrows
  the one interval the program returns and there is no second channel. That
  is not a presentational choice: measured over 400 random binary IV models
  the restriction collapses none of the three to a point (0/365 feasible
  tables) while narrowing every one of them, by a median 0.279 of PN's width;
  reporting the assumption-free set beside an absent point would throw all of
  that away. It also refutes the assumption on 35 of the 400 — a signal that
  exists only when the restriction goes into the program.

API::

    from themis.estimation.causation import estimate_causation_probabilities
    est = estimate_causation_probabilities(
        data, graph=g, bidirected=bi, cause=X, effect=Y, monotonic=True,
    )
    print(est.pn_point, est.pn_point_ci_lower, est.pn_point_ci_upper)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .. import risk_provenance
from ..risk_provenance import RiskProvenance
from ..runtime.probabilities_of_causation import probabilities_of_causation
from ..types import Atom, FormulaExpr, Monotonicity
from .binary_do_risk import (
    DEFAULT_FORM,
    FORM_BY_PROVENANCE,
    as_binary_column,
    backdoor_do_risk,
    choose_risk_route,
    observational_joint_xy,
)
from .bounds_numeric import (
    counterfactual_cell_iv_table,
    sorted_levels,
)
from ..response_polytope import (
    causation_response_bounds,
    polytope_preconditions,
    polytope_sufficient_statistic,
)
from .contract import validate_data
from .general_id import (
    data_domains,
    evaluate_arm_risk,
    referenced_predicates,
)
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from .resample import cluster_labels, resample_indices


#: The derivation rule this module emits — which is what fixes the set of
#: licences it may write for its two do-risks (see
#: :mod:`themis.risk_provenance`).
_RULE = "numeric_causation_estimate"


@dataclass(frozen=True)
class CausationEstimate:
    """Data-based PN/PS/PNS with bootstrap CIs.

    ``*_lower`` / ``*_upper`` is always present and is the identified set the
    route reached. ``*_point`` is present exactly where that set collapses:
    under a declared monotonicity on the closed form, and essentially never on
    the instrument route, where the assumption narrows the same interval
    instead of pinning it. A conditioning cell with zero empirical mass has no
    point either. ``*_point_ci_*`` is the percentile-bootstrap CI on the point
    (present only when the point is); ``*_bounds_ci_*`` is the outer band on
    the interval, which is what the other answer carries instead."""

    # PN — necessity (归因 / liability).
    pn_point: float | None
    pn_lower: float
    pn_upper: float
    pn_point_ci_lower: float | None
    pn_point_ci_upper: float | None
    # PS — sufficiency (prevention).
    ps_point: float | None
    ps_lower: float
    ps_upper: float
    ps_point_ci_lower: float | None
    ps_point_ci_upper: float | None
    # PNS — necessity AND sufficiency.
    pns_point: float | None
    pns_lower: float
    pns_upper: float
    pns_point_ci_lower: float | None
    pns_point_ci_upper: float | None
    # Inputs recovered from data (audit trail; verifier re-runs the oracle
    # on these and checks the reported quantities match).
    p_x1_y1: float
    p_x1_y0: float
    p_x0_y1: float
    p_x0_y0: float
    # None on the instrument route, where no interventional risk was obtained
    # at all — the polytope answers without one, and reporting a number here
    # would name an input the answer never had.
    p_y_do_x1: float | None
    p_y_do_x0: float | None
    monotonic: bool
    interventional_risk_provenance: RiskProvenance
    adjustment: tuple[str, ...]
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
    # Percentile-bootstrap OUTER band on each [lower, upper] identified set —
    # the sampling uncertainty of the whole interval (parity with the Manski /
    # Balke-Pearl data-bounds convention in bounds_numeric._bootstrap_outer_band).
    # Populated when point identification does NOT hold (non-monotone) and a
    # bootstrap ran; under monotonicity the point CI is the reported CI instead.
    pn_bounds_ci_lower: float | None = None
    pn_bounds_ci_upper: float | None = None
    ps_bounds_ci_lower: float | None = None
    ps_bounds_ci_upper: float | None = None
    pns_bounds_ci_lower: float | None = None
    pns_bounds_ci_upper: float | None = None
    # The instrument route's sufficient statistic — the very table the three
    # programs were fitted to, so the verifier re-solves them from it rather
    # than from a second pass over the frame. The level list travels WITH the
    # table because the table's own shape says nothing about which stratum is
    # which, and a permuted reading re-derives different intervals.
    instrument: str | None = None
    instrument_levels: tuple = ()
    p_xyz: tuple = ()
    p_z: tuple = ()
    # The general-ID estimands the two risks were evaluated from, when that is
    # how they were identified (None otherwise). One per arm: the ID algorithm
    # is asked separately for each, and a verifier re-deriving them has to know
    # which arm each belongs to.
    risk_formula_treated: FormulaExpr | None = None
    risk_formula_control: FormulaExpr | None = None
    # Finite-sample behaviour of the feasible set, on the route that has one:
    # a bootstrap draw whose program is empty under the declared monotonicity
    # is that draw refuting the assumption, and the count is reported rather
    # than swallowed (parity with counterfactual_cell.py).
    bootstrap_draws_used: int = 0
    bootstrap_draws_infeasible: int = 0


def estimate_causation_probabilities(
    data: pd.DataFrame,
    *,
    graph,
    bidirected=frozenset(),
    cause: Atom,
    effect: Atom,
    monotonic: bool = False,
    experimental_risk_treated: float | None = None,
    experimental_risk_control: float | None = None,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> CausationEstimate:
    """Estimate PN/PS/PNS on data, by whichever solver the graph licenses.

    Parameters
    ----------
    data: DataFrame with a binary column per observed variable (named by each
        atom's ``predicate``): cause, effect, and whatever the chosen route
        reads — the adjustment set, the estimand's variables, or the
        instrument.
    graph / bidirected: the projected ADMG (same objects the kernel identified
        on). The route is chosen off it by the shared cascade, which is also
        what the counterfactual-cell estimator asks.
    cause / effect: the binary X and Y atoms.
    monotonic: assert Y is monotonic in X (X never prevents Y). On the closed
        form that point-identifies all three (Tian-Pearl Thm 3), reported as a
        point beside the assumption-free interval; on the instrument route it
        is a restriction of the response-type model, so it narrows the
        interval instead and can be refuted by it.
    experimental_risk_treated / experimental_risk_control: P(Y=1 | do(X=1/0))
        from a randomized experiment. Supply BOTH for the confounded-but-
        experimentally-measured case where the observational frame cannot
        identify the do-risks; they pass straight through.
    ci_bootstrap: number of bootstrap resamples; 0 skips CIs.
    ci_level: two-sided confidence level.
    random_state: deterministic seed.
    cluster: optional cluster-id column for a pairs cluster bootstrap.

    Raises
    ------
    EstimatorFailure: cause/effect not binary; no route reaches the do-risks
        and none were supplied; an instrument that never varies or has more
        levels than the LP is solved at; a positivity violation (an empty
        treatment×stratum cell, or an instrument stratum with no rows); a
        declared monotonicity the response-type program refutes.
    DataContractError (ValueError): missing column, NaN, or too-small sample.
    """
    xcol, ycol = cause.predicate, effect.predicate

    # 1. Which route reaches the two risks — the shared cascade, asked for BOTH
    #    arms. That is this door's only difference from the counterfactual-cell
    #    door, and it is a parameter rather than a second cascade.
    route = choose_risk_route(
        graph, bidirected, cause=cause, effect=effect,
        arms=(True, False),
        supplied={True: experimental_risk_treated,
                  False: experimental_risk_control},
    )
    if route is None:
        raise EstimatorFailure(
            Refusal.DO_RISK_NOT_IDENTIFIABLE,
            "P(Y=1|do(X)) is reached by none of the routes this estimator "
            "knows: no admissible back-door adjustment set (likely an "
            "unmeasured confounder), no general-ID estimand for the arms, and "
            "no single instrument on the graph. Supply "
            "experimental_risk_treated / experimental_risk_control from a "
            "randomized experiment, or declare an instrument.",
        )
    provenance = route.provenance
    adjustment = route.adjustment
    # The cascade returns USER_EXPERIMENTAL for both arms or for neither, so
    # the licence and the pair of risks it licences are one fact. Binding them
    # together is what lets the solver below read the pair, instead of
    # re-deriving from a boolean flag that the two numbers must be there.
    supplied_risks: tuple[float, float] | None = (
        None
        if experimental_risk_treated is None or experimental_risk_control is None
        else (float(experimental_risk_treated), float(experimental_risk_control))
    )
    on_polytope = provenance is RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE
    zcol = None if route.instrument is None else route.instrument.predicate
    formulas = route.formulas

    required = {xcol, ycol, *adjustment}
    for formula in formulas.values():
        required |= referenced_predicates(formula)
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

    # 2. Binary cause & effect only (PN/PS/PNS are undefined otherwise).
    x = as_binary_column(df[xcol], xcol)
    y = as_binary_column(df[ycol], ycol)

    # The general-ID estimands are identified ONCE (data-independent) and their
    # sum ranges pinned to the FULL-data domains, and the instrument's levels
    # are likewise fixed on the full data — so every bootstrap replicate
    # evaluates the same estimand and fits a table with the same axes rather
    # than a quietly narrower model.
    domains = data_domains(graph, df) if formulas else {}
    z_levels = [] if zcol is None else sorted_levels(df[zcol])
    if zcol is not None:
        polytope_preconditions(zcol, z_levels)
    # Tian-Pearl's monotonicity — X never prevents Y — is Y non-decreasing in
    # X, which is the same claim the response-type restriction is written in.
    direction = Monotonicity.NON_DECREASING if monotonic else None

    # 3. Point estimate: whichever solver this route licenses.
    def _run(x_arr, y_arr, frame) -> "tuple":
        """Empirical joint, then the route's solver.

        Returns ``(joint, r1, r0, quantities, iv_table)`` where ``quantities``
        maps each of pn/ps/pns to ``(lower, upper, point)``. Both solvers fill
        the same shape, because what a reader and the bootstrap need from them
        is the same three intervals however they were obtained.
        """
        joint = observational_joint_xy(x_arr, y_arr)
        if on_polytope:
            # No scalar risk passes through on this route: the polytope is
            # fitted to the conditional table and the three quantities read
            # off it as three objectives on one program.
            P, p_z = counterfactual_cell_iv_table(
                x_arr, y_arr, frame[zcol].to_numpy(), z_levels,
            )
            bounds = causation_response_bounds(P, p_z, monotonicity=direction)
            return joint, None, None, {
                name: (lo, hi, lo if abs(hi - lo) <= _TOL else None)
                for name, (lo, hi) in bounds.items()
            }, (P, p_z)
        if supplied_risks is not None:
            r1, r0 = supplied_risks
        elif formulas:
            r1 = evaluate_arm_risk(formulas[True], frame, domains=domains)
            r0 = evaluate_arm_risk(formulas[False], frame, domains=domains)
        else:
            r1 = backdoor_do_risk(x_arr, y_arr, frame, adjustment, arm=True)
            r0 = backdoor_do_risk(x_arr, y_arr, frame, adjustment, arm=False)
        poc = probabilities_of_causation(
            p_x1_y1=joint[(True, True)], p_x1_y0=joint[(True, False)],
            p_x0_y1=joint[(False, True)], p_x0_y0=joint[(False, False)],
            p_y_do_x1=r1, p_y_do_x0=r0, monotonic=monotonic,
        )
        return joint, r1, r0, {
            "pn": (poc.pn_lower, poc.pn_upper, poc.pn_point),
            "ps": (poc.ps_lower, poc.ps_upper, poc.ps_point),
            "pns": (poc.pns_lower, poc.pns_upper, poc.pns_point),
        }, None

    joint, p_y_do_x1, p_y_do_x0, quantities, iv_table = _run(x, y, df)

    # 4. Bootstrap CIs (percentile). The POINT CIs are meaningful only where a
    #    point exists; the OUTER band on each [lower, upper] identified set is
    #    the sampling uncertainty of the whole interval and is reported for the
    #    interval answer. One resampling loop feeds both.
    cis = {q: (None, None) for q in quantities}
    bands = dict(cis)
    used = infeasible = 0
    if ci_bootstrap > 0:
        cis, bands, used, infeasible = _bootstrap_cis(
            _run, x, y, df,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level,
            random_state=random_state, groups=groups,
        )

    assumptions = _assumptions(provenance, adjustment, monotonic, cluster, zcol)
    levels, p_xyz, p_z = (
        polytope_sufficient_statistic(iv_table[0], iv_table[1], z_levels)
        if iv_table else ((), (), ())
    )
    return CausationEstimate(
        pn_point=quantities["pn"][2],
        pn_lower=quantities["pn"][0], pn_upper=quantities["pn"][1],
        pn_point_ci_lower=cis["pn"][0], pn_point_ci_upper=cis["pn"][1],
        ps_point=quantities["ps"][2],
        ps_lower=quantities["ps"][0], ps_upper=quantities["ps"][1],
        ps_point_ci_lower=cis["ps"][0], ps_point_ci_upper=cis["ps"][1],
        pns_point=quantities["pns"][2],
        pns_lower=quantities["pns"][0], pns_upper=quantities["pns"][1],
        pns_point_ci_lower=cis["pns"][0], pns_point_ci_upper=cis["pns"][1],
        pn_bounds_ci_lower=bands["pn"][0], pn_bounds_ci_upper=bands["pn"][1],
        ps_bounds_ci_lower=bands["ps"][0], ps_bounds_ci_upper=bands["ps"][1],
        pns_bounds_ci_lower=bands["pns"][0], pns_bounds_ci_upper=bands["pns"][1],
        p_x1_y1=joint[(True, True)], p_x1_y0=joint[(True, False)],
        p_x0_y1=joint[(False, True)], p_x0_y0=joint[(False, False)],
        p_y_do_x1=p_y_do_x1, p_y_do_x0=p_y_do_x0,
        monotonic=monotonic,
        interventional_risk_provenance=risk_provenance.stamp(_RULE, provenance),
        adjustment=adjustment,
        instrument=zcol,
        instrument_levels=levels, p_xyz=p_xyz, p_z=p_z,
        risk_formula_treated=formulas.get(True),
        risk_formula_control=formulas.get(False),
        bootstrap_draws_used=used, bootstrap_draws_infeasible=infeasible,
        ci_level=ci_level,
        method="causation_plugin",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        cause=xcol, effect=ycol,
        model_assumption=_model_assumption(provenance, zcol),
        form=FORM_BY_PROVENANCE.get(provenance, DEFAULT_FORM),
        identification_assumptions=_identification_assumptions(
            provenance, adjustment, monotonic, zcol,
        ),
        cluster=cluster,
    )


# --- internals ----------------------------------------------------------------


_TOL = 1e-12


def _bootstrap_cis(
    run, x: np.ndarray, y: np.ndarray, frame: pd.DataFrame, *,
    ci_bootstrap: int, ci_level: float, random_state: int,
    groups: np.ndarray | None,
) -> tuple[dict, dict, int, int]:
    """Percentile bootstrap of the three quantities' points AND their intervals.

    Resamples rows (or whole clusters) and re-runs ``run`` — the same closure
    that produced the point estimate, so a replicate goes down the route the
    answer went down rather than down a second transcription of it. Per draw it
    collects each point where one is defined (a positivity failure or a zero
    conditioning cell skips the affected quantity) and both interval endpoints.

    Returns ``(point_cis, bands, draws_used, draws_infeasible)``; the outer band
    of a quantity is ``(low-quantile of its LOWER samples, high-quantile of its
    UPPER samples)`` — the Manski / Balke-Pearl data-bounds convention.

    A draw whose feasible set is EMPTY is not a silent skip: it means that
    resample refutes the declared monotonicity, and the count is reported
    beside the intervals. A draw dropped for a positivity hole is neither used
    nor infeasible — the assumption is not what failed.
    """
    rng = np.random.default_rng(random_state)
    n = len(frame)
    names = ("pn", "ps", "pns")
    pt_s: dict[str, list[float]] = {q: [] for q in names}
    lo_s: dict[str, list[float]] = {q: [] for q in names}
    hi_s: dict[str, list[float]] = {q: [] for q in names}
    infeasible = 0
    used = 0
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        try:
            _joint, _r1, _r0, quantities, _table = run(
                x[idx], y[idx], frame.iloc[idx],
            )
        except EstimatorFailure as exc:
            if exc.failure_type is Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE:
                infeasible += 1
            continue
        used += 1
        for q in names:
            lo, hi, pt = quantities[q]
            if pt is not None:
                pt_s[q].append(pt)
            lo_s[q].append(lo)
            hi_s[q].append(hi)

    alpha = (1 - ci_level) / 2

    def _pt_ci(samples: list[float]) -> tuple:
        if len(samples) < 2:
            return (None, None)
        arr = np.asarray(samples)
        return (float(np.quantile(arr, alpha)), float(np.quantile(arr, 1 - alpha)))

    def _band(los: list[float], his: list[float]) -> tuple:
        if len(los) < 2 or len(his) < 2:
            return (None, None)
        return (
            float(np.quantile(np.asarray(los), alpha)),
            float(np.quantile(np.asarray(his), 1 - alpha)),
        )

    return (
        {q: _pt_ci(pt_s[q]) for q in names},
        {q: _band(lo_s[q], hi_s[q]) for q in names},
        used,
        infeasible,
    )


def _model_assumption(
    provenance: RiskProvenance, instrument: str | None,
) -> str:
    """The mechanism sentence: which solver ran, and how its inputs were got."""
    if provenance is RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE:
        # The one route that does not go through Tian-Pearl at all, so the
        # sentence does not start by naming it.
        return (
            "PN/PS/PNS 没有走 Tian-Pearl 公式：两臂干预风险都不可点识别，"
            f"改用工具变量 `{instrument}` 的响应函数模型——在所有能复现经验 "
            "P(X,Y|Z) 的响应型分布上，把三者各作为一个线性泛函取上下确界"
            "（三者共用同一个多面体，只差按哪个事实人群加权；无函数形式假设）；"
            "单调性(若声明)是从总体里去掉反向响应型的额外约束，会收窄区间"
            "但一般不把它收成点"
        )
    if provenance is RiskProvenance.GENERAL_ID_PLUG_IN:
        risk = (
            "两臂干预风险 P(Y=1|do X) 都没有可用的调整集，"
            "改由 general ID（c-factor 分解）识别出的估计量按非参数 plug-in 求值"
            "（每个条件概率取其所属数据层的经验频率，无函数形式假设）"
        )
    elif provenance is RiskProvenance.USER_EXPERIMENTAL:
        risk = "干预风险 P(Y=1|do X) 由调用方以随机实验数据给出，原样代入"
    else:
        risk = (
            "干预风险 P(Y=1|do X) 用后门标准化(饱和 g-formula，无函数形式假设)"
        )
    return (
        "PN/PS/PNS 按 Tian-Pearl(2000)公式求值：观测联合 P(X,Y) 用经验频率，"
        + risk + "；点识别需单调性(X 从不阻止 Y)，否则只给无假设界"
    )


def _assumptions(
    provenance: RiskProvenance, adjustment: tuple[str, ...], monotonic: bool,
    cluster: str | None, instrument: str | None,
) -> tuple[str, ...]:
    out = [
        "binary_cause_and_effect",
        "consistency_of_potential_outcomes",
    ]
    if provenance is RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE:
        out.append("iv1_relevance_instrument_affects_treatment")
        out.append(
            "iv2_exclusion_instrument_affects_outcome_only_via_treatment")
        out.append(
            "iv3_independence_instrument_independent_of_latent_confounders")
    elif provenance is RiskProvenance.USER_EXPERIMENTAL:
        out.append("interventional_risks_from_randomized_experiment")
    elif provenance is RiskProvenance.EXOGENOUS:
        out.append("exogeneity_no_backdoor_path_do_risk_equals_conditional")
    elif provenance is RiskProvenance.GENERAL_ID_PLUG_IN:
        out.append("admg_structure_correct_including_latent_confounders")
        out.append("positivity_every_conditioning_stratum_of_the_estimand_has_support")
        out.append("discrete_variables_saturated_nonparametric_plug_in")
    else:
        out.append(
            "backdoor_adjustment_set_{" + ",".join(adjustment) + "}_sufficient"
        )
        out.append("positivity_every_treatment_arm_has_support_in_each_stratum")
    if monotonic:
        out.append("monotonicity_x_never_prevents_y_point_identification")
    # No else. Assuming nothing declares nothing: an answer that rests on
    # less has to say less, and the reason there is no point belongs to the
    # answer, which already gives it in the shape it comes back as.
    if cluster is not None:
        out.append(f"ci_via_pairs_cluster_bootstrap_on_{cluster}")
    return tuple(out)


def _identification_assumptions(
    provenance: RiskProvenance, adjustment: tuple[str, ...], monotonic: bool,
    instrument: str | None,
) -> tuple[dict, ...]:
    """The structured twin of :func:`_assumptions`, branch for branch.

    ``id`` is what makes it a twin rather than something that reads like
    one: the ledger folds in every flat declaration no entry has claimed,
    so a branch here that forgets its id discloses the same assumption
    twice, and a branch that has none at all is disclosed by the flat
    channel instead of vanishing.
    """
    specs: list[dict] = [
        {"id": "consistency_of_potential_outcomes",
         "claim": "一致性：potential outcomes 良定义，观测到的 Y 等于所受干预下的 Y",
         "layer": "identification", "testable": False},
    ]
    if provenance is RiskProvenance.USER_EXPERIMENTAL:
        specs.append(
            {"id": "interventional_risks_from_randomized_experiment",
             "claim": "干预风险 P(Y=1|do X) 来自随机实验，无混杂",
             "layer": "identification", "testable": False})
    elif provenance is RiskProvenance.EXOGENOUS:
        specs.append(
            {"id": "exogeneity_no_backdoor_path_do_risk_equals_conditional",
             "claim": "外生性：X 到 Y 无后门路径，P(Y|do X)=P(Y|X)",
             "layer": "identification", "testable": False})
    elif provenance is RiskProvenance.GENERAL_ID_PLUG_IN:
        specs.append(
            {"id": "admg_structure_correct_including_latent_confounders",
             "claim": "没有可用的调整集，两臂干预风险经 general ID（c-factor 分解）识别："
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
    else:
        specs.append(
            {"id": "backdoor_adjustment_set_{" + ",".join(adjustment) + "}_sufficient",
             "claim": "后门调整集充分：所选调整集阻断 X→Y 的所有后门路径",
             "layer": "identification", "testable": False})
        specs.append(
            {"id": "positivity_every_treatment_arm_has_support_in_each_stratum",
             "claim": "positivity：每个调整层在两个处理臂下都有样本",
             "layer": "identification", "testable": True})
    if monotonic:
        # Identification, not a layer of its own: without it these three are
        # bounded and not point-identified, which is the definition of the
        # identification layer. It was labelled ``assumption`` on an assumption
        # ledger, where the word says nothing.
        #
        # What it BUYS, and whether the data can argue back, both depend on the
        # route — so neither is stated as though it did not. The closed form
        # takes it as a second theorem and returns a point; the polytope takes
        # it as a restriction of the model, which narrows the intervals and can
        # come out empty, and an empty program under the restriction that is
        # feasible without it IS the data contradicting the declared direction.
        on_polytope = provenance is RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE
        specs.append(
            {"id": "monotonicity_x_never_prevents_y_point_identification",
             "claim": (
                 "单调性：X 从不阻止 Y(Y_x ≥ Y_x')，"
                 + ("据此从响应型总体中去掉反向单位，收窄三个区间"
                    if on_polytope else "使 PN/PS/PNS 点识别")
             ),
             "layer": "identification",
             "testable": on_polytope})
    return tuple(specs)
