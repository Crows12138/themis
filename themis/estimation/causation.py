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
P(Y=1 | do(X=x)), both recovered by :mod:`themis.estimation.binary_do_risk`
(shared with the counterfactual-cell estimator, which needs the same two
inputs for a different theorem). When the confounder is UNMEASURED (no
admissible adjustment set) the risks are not identified from the
observational frame — the caller must supply ``experimental_risk_treated`` /
``experimental_risk_control`` from a randomized experiment (Tian-Pearl's drug
example), which pass straight through.

Reference: Tian & Pearl 2000, "Probabilities of Causation: Bounds and
Identification" (Annals of Math & AI 28:287-313); Hernán & Robins 2020 ch.13
for the g-formula (standardization) plug-in in the non-parametric limit.

Scope (declared):

- BINARY cause X and BINARY effect Y (PN/PS/PNS are defined only for binary
  X, Y); the estimator coerces {0,1}/{False,True} and refuses otherwise.
- The interventional risks are identified by BACK-DOOR adjustment (the empty
  set = exogeneity is the special case) or supplied experimentally. Front-door
  / IV data paths for the do-risks are NOT wired here — when back-door admits
  no set and no experimental risks are given, the estimator refuses and the
  structural (bounds / needs-experiment) answer stands.
- The adjustment set must be DISCRETE (the saturated stratified g-formula has
  no empirical stratum for a continuous covariate); a stratum with no support
  under some treatment arm is a positivity violation and raises.
- POINT values (PN/PS/PNS) exist only under ``monotonic`` (X never prevents Y,
  Tian-Pearl Thm 3); otherwise only the assumption-free bounds are returned.

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

from ..runtime.probabilities_of_causation import probabilities_of_causation
from ..types import Atom
from .binary_do_risk import (
    as_binary_column,
    backdoor_do_risk,
    minimal_backdoor_adjustment,
    observational_joint_xy,
)
from .contract import validate_data
from ..refusals import EstimatorFailure
from .resample import cluster_labels, resample_indices


@dataclass(frozen=True)
class CausationEstimate:
    """Data-based PN/PS/PNS (Tian-Pearl) with bootstrap CIs.

    ``*_point`` is ``None`` when the quantity is not point-identified (no
    monotonicity) or its conditioning cell has zero empirical mass; the
    ``*_lower`` / ``*_upper`` assumption-free bounds are always present.
    ``*_point_ci_*`` is the percentile-bootstrap CI on the point (present only
    when the point is)."""

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
    p_y_do_x1: float
    p_y_do_x0: float
    monotonic: bool
    interventional_risk_provenance: str  # exogenous | backdoor_adjustment | user_experimental
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
    """Estimate PN/PS/PNS on data via the Tian-Pearl oracle + bootstrap.

    Parameters
    ----------
    data: DataFrame with a binary column per observed variable (named by
        each atom's ``predicate``): cause, effect, and the back-door
        adjustment set.
    graph / bidirected: the projected ADMG (same objects the kernel
        identified on). The minimal back-door adjustment set for the do-risks
        is read off ``graph``.
    cause / effect: the binary X and Y atoms.
    monotonic: assert Y is monotonic in X (X never prevents Y), which
        point-identifies PN/PS/PNS (Tian-Pearl Thm 3). Otherwise only the
        assumption-free bounds are returned.
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
    EstimatorFailure: cause/effect not binary; the do-risks are not back-door
        identified and no experimental risks were supplied; a positivity
        violation (empty treatment×stratum cell).
    DataContractError (ValueError): missing column, NaN, or too-small sample.
    """
    xcol, ycol = cause.predicate, effect.predicate
    supplied = (
        experimental_risk_treated is not None
        and experimental_risk_control is not None
    )

    # 1. Interventional-risk strategy + required columns.
    if supplied:
        provenance = "user_experimental"
        adjustment: tuple[str, ...] = ()
    else:
        adjustment = minimal_backdoor_adjustment(graph, cause, effect, bidirected)
        provenance = "exogenous" if not adjustment else "backdoor_adjustment"

    required = {xcol, ycol, *adjustment}
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

    # 3. Point estimate: empirical joint + g-formula do-risks → oracle.
    def _run(x_arr, y_arr, frame) -> "tuple":
        joint = observational_joint_xy(x_arr, y_arr)
        if supplied:
            r1 = float(experimental_risk_treated)
            r0 = float(experimental_risk_control)
        else:
            r1 = backdoor_do_risk(x_arr, y_arr, frame, adjustment, arm=True)
            r0 = backdoor_do_risk(x_arr, y_arr, frame, adjustment, arm=False)
        poc = probabilities_of_causation(
            p_x1_y1=joint[(True, True)], p_x1_y0=joint[(True, False)],
            p_x0_y1=joint[(False, True)], p_x0_y0=joint[(False, False)],
            p_y_do_x1=r1, p_y_do_x0=r0, monotonic=monotonic,
        )
        return joint, r1, r0, poc

    joint, p_y_do_x1, p_y_do_x0, poc = _run(x, y, df)

    # 4. Bootstrap CIs (percentile). The POINT CIs are meaningful only under
    #    monotonicity; the OUTER band on each [lower, upper] identified set is
    #    the sampling uncertainty of the whole interval and is reported for the
    #    non-monotone (bounds-only) answer. One resampling loop feeds both.
    pn_ci = ps_ci = pns_ci = (None, None)
    pn_band = ps_band = pns_band = (None, None)
    if ci_bootstrap > 0:
        (pn_ci, ps_ci, pns_ci), (pn_band, ps_band, pns_band) = _bootstrap_cis(
            x, y, df, adjustment, supplied,
            experimental_risk_treated, experimental_risk_control, monotonic,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level,
            random_state=random_state, groups=groups,
        )

    assumptions = _assumptions(provenance, adjustment, monotonic, cluster)
    return CausationEstimate(
        pn_point=poc.pn_point, pn_lower=poc.pn_lower, pn_upper=poc.pn_upper,
        pn_point_ci_lower=pn_ci[0], pn_point_ci_upper=pn_ci[1],
        ps_point=poc.ps_point, ps_lower=poc.ps_lower, ps_upper=poc.ps_upper,
        ps_point_ci_lower=ps_ci[0], ps_point_ci_upper=ps_ci[1],
        pns_point=poc.pns_point, pns_lower=poc.pns_lower, pns_upper=poc.pns_upper,
        pns_point_ci_lower=pns_ci[0], pns_point_ci_upper=pns_ci[1],
        pn_bounds_ci_lower=pn_band[0], pn_bounds_ci_upper=pn_band[1],
        ps_bounds_ci_lower=ps_band[0], ps_bounds_ci_upper=ps_band[1],
        pns_bounds_ci_lower=pns_band[0], pns_bounds_ci_upper=pns_band[1],
        p_x1_y1=joint[(True, True)], p_x1_y0=joint[(True, False)],
        p_x0_y1=joint[(False, True)], p_x0_y0=joint[(False, False)],
        p_y_do_x1=p_y_do_x1, p_y_do_x0=p_y_do_x0,
        monotonic=monotonic,
        interventional_risk_provenance=provenance,
        adjustment=adjustment,
        ci_level=ci_level,
        method="causation_plugin",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        cause=xcol, effect=ycol,
        model_assumption=(
            "PN/PS/PNS 按 Tian-Pearl(2000)公式求值：观测联合 P(X,Y) 用经验频率，"
            "干预风险 P(Y=1|do X) 用后门标准化(饱和 g-formula，无函数形式假设)；"
            "点识别需单调性(X 从不阻止 Y)，否则只给无假设界"
        ),
        form="nonparametric_gformula_plug_in",
        identification_assumptions=_identification_assumptions(
            provenance, adjustment, monotonic,
        ),
        cluster=cluster,
    )


# --- internals ----------------------------------------------------------------


def _bootstrap_cis(
    x: np.ndarray, y: np.ndarray, frame: pd.DataFrame,
    adjustment: tuple[str, ...], supplied: bool,
    r1_fixed, r0_fixed, monotonic: bool, *,
    ci_bootstrap: int, ci_level: float, random_state: int,
    groups: np.ndarray | None,
) -> tuple[tuple, tuple]:
    """Percentile bootstrap of BOTH the three point values and an OUTER band on
    each [lower, upper] identified set. Resamples rows (or whole clusters),
    re-runs the full joint + g-formula + oracle, and per draw collects (a) each
    point where it is defined (monotone; a positivity failure or zero
    conditioning cell skips the affected quantity) and (b) the interval
    endpoints (always defined). Returns ``((pn_pt_ci, ps_pt_ci, pns_pt_ci),
    (pn_band, ps_band, pns_band))``; the outer band of a quantity is
    ``(low-quantile of its LOWER samples, high-quantile of its UPPER samples)``
    — the Manski / Balke-Pearl data-bounds convention."""
    rng = np.random.default_rng(random_state)
    n = len(frame)
    pt_s = {"pn": [], "ps": [], "pns": []}       # point samples (monotone)
    lo_s = {"pn": [], "ps": [], "pns": []}       # lower-endpoint samples
    hi_s = {"pn": [], "ps": [], "pns": []}       # upper-endpoint samples
    x_arr = x
    y_arr = y
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        bx = x_arr[idx]
        by = y_arr[idx]
        bframe = frame.iloc[idx]
        joint = observational_joint_xy(bx, by)
        try:
            if supplied:
                br1, br0 = float(r1_fixed), float(r0_fixed)
            else:
                br1 = backdoor_do_risk(bx, by, bframe, adjustment, arm=True)
                br0 = backdoor_do_risk(bx, by, bframe, adjustment, arm=False)
        except EstimatorFailure:
            continue
        poc = probabilities_of_causation(
            p_x1_y1=joint[(True, True)], p_x1_y0=joint[(True, False)],
            p_x0_y1=joint[(False, True)], p_x0_y0=joint[(False, False)],
            p_y_do_x1=br1, p_y_do_x0=br0, monotonic=monotonic,
        )
        for q, pt, lo, hi in (
            ("pn", poc.pn_point, poc.pn_lower, poc.pn_upper),
            ("ps", poc.ps_point, poc.ps_lower, poc.ps_upper),
            ("pns", poc.pns_point, poc.pns_lower, poc.pns_upper),
        ):
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

    point_cis = (_pt_ci(pt_s["pn"]), _pt_ci(pt_s["ps"]), _pt_ci(pt_s["pns"]))
    bands = (
        _band(lo_s["pn"], hi_s["pn"]),
        _band(lo_s["ps"], hi_s["ps"]),
        _band(lo_s["pns"], hi_s["pns"]),
    )
    return point_cis, bands


def _assumptions(
    provenance: str, adjustment: tuple[str, ...], monotonic: bool,
    cluster: str | None,
) -> tuple[str, ...]:
    out = [
        "binary_cause_and_effect",
        "consistency_of_potential_outcomes",
    ]
    if provenance == "user_experimental":
        out.append("interventional_risks_from_randomized_experiment")
    elif provenance == "exogenous":
        out.append("exogeneity_no_backdoor_path_do_risk_equals_conditional")
    else:
        out.append(
            "backdoor_adjustment_set_{" + ",".join(adjustment) + "}_sufficient"
        )
        out.append("positivity_every_treatment_arm_has_support_in_each_stratum")
    if monotonic:
        out.append("monotonicity_x_never_prevents_y_point_identification")
    else:
        out.append("no_monotonicity_assumption_free_bounds_only")
    if cluster is not None:
        out.append(f"ci_via_pairs_cluster_bootstrap_on_{cluster}")
    return tuple(out)


def _identification_assumptions(
    provenance: str, adjustment: tuple[str, ...], monotonic: bool,
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
         "layer": "identification", "severity": "invalidating", "testable": False},
    ]
    if provenance == "user_experimental":
        specs.append(
            {"id": "interventional_risks_from_randomized_experiment",
             "claim": "干预风险 P(Y=1|do X) 来自随机实验，无混杂",
             "layer": "identification", "severity": "invalidating", "testable": False})
    elif provenance == "exogenous":
        specs.append(
            {"id": "exogeneity_no_backdoor_path_do_risk_equals_conditional",
             "claim": "外生性：X 到 Y 无后门路径，P(Y|do X)=P(Y|X)",
             "layer": "identification", "severity": "invalidating", "testable": False})
    else:
        specs.append(
            {"id": "backdoor_adjustment_set_{" + ",".join(adjustment) + "}_sufficient",
             "claim": "后门调整集充分：所选调整集阻断 X→Y 的所有后门路径",
             "layer": "identification", "severity": "invalidating", "testable": False})
        specs.append(
            {"id": "positivity_every_treatment_arm_has_support_in_each_stratum",
             "claim": "positivity：每个调整层在两个处理臂下都有样本",
             "layer": "identification", "severity": "invalidating", "testable": True})
    if monotonic:
        specs.append(
            {"id": "monotonicity_x_never_prevents_y_point_identification",
             "claim": "单调性：X 从不阻止 Y(Y_x ≥ Y_x')，使 PN/PS/PNS 点识别",
             "layer": "assumption", "severity": "invalidating", "testable": False})
    return tuple(specs)
