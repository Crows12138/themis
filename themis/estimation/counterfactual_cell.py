"""Binary counterfactual cell — the numeric end of ``P(Y_{x'}=y* | X=x [, Y=y])``.

The structural layer (:func:`themis.runtime.scheduler._dispatch_counterfactual`)
answers a :class:`~themis.types.CounterfactualQuery` from ``theta``: it recovers
the observational joint P(X, Y) symbolically, obtains the one interventional
risk P(Y=1 | do(x')) the cell depends on by running the effect identification,
and hands both to
:func:`themis.runtime.counterfactual.counterfactual_cell_interval` — whose one
linear consistency identity covers every cell. Where the graph leaves no risk to
be had it reaches the same instrument route this module does, over the same
program, from the ``P(X, Y | Z)`` its own recovery produces.

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
(:func:`themis.response_polytope.counterfactual_cell_response_bounds`).
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

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..runtime import counterfactual as cf
from ..ledger import Provenance
from .form import NO_OTHER_SHAPES
from .. import risk_provenance
from ..risk_provenance import RiskProvenance
from ..types import CounterfactualQuery, FormulaExpr, NumericInterval
from .binary_do_risk import (
    DEFAULT_FORM,
    FORM_BY_PROVENANCE,
    RiskRoute,
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
    counterfactual_cell_response_bounds,
    polytope_preconditions,
    polytope_sufficient_statistic,
)
from .contract import validate_data
from ..refusals import Refusal, Remedy
from ..refusals import EstimatorFailure
from .general_id import (
    data_domains,
    evaluate_arm_risk,
    referenced_predicates,
)
from .resample import Draws, cluster_labels, resample_indices


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
    percentile CI, and otherwise the OUTER band on ``[low, high]``. Which
    of the two travels on the block as ``ci_width_is`` rather than being
    left here to be re-derived: this is the estimator's own record of what
    it produced, and four reader surfaces used to work the same thing out
    from ``point`` afterwards (:mod:`themis.intervals`).
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
    risk_formula: FormulaExpr | None
    # The cell being asked for (the verifier re-reads these off ctx.query).
    x_observed: bool
    x_counterfactual: bool
    y_star: bool
    factual_target_known: bool | None
    monotonicity: str | None
    #: The replicates this interval was taken over, and what became of the
    #: rest — see :class:`themis.estimation.resample.Draws`. ``None`` when
    #: no bootstrap ran, which is the one case with no answer to give. The
    #: finite-sample behaviour of the feasible set (see the module
    #: docstring) is the share filed here under
    #: ``counterfactual_inputs_infeasible``; it used to be two integers on
    #: this class, which said less — no denominator for the draws lost to
    #: something else, and no name on what that something else was.
    draws: "Draws | None"
    # Envelope (parity with the other numeric estimators).
    ci_level: float
    method: str
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    cause: str
    effect: str
    form: str = "nonparametric_gformula_plug_in"
    #: Nothing chose this shape: it IS the method, and the only way to
    #: overrule it is to answer by a different one.
    form_provenance: str = Provenance.INHERENT
    #: Which shapes a lever BESIDE the outcome model settled, by assumption
    #: id. The ids that RESTATE the outcome model's shape take the answer
    #: above; an id here is a different decision, made by a different lever,
    #: and says so itself — :func:`themis.estimation.form.shapes_settled`.
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES
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
            intervened=query.counterfactual_intervention.atom.predicate,
            observed=x_atom.predicate,
        )
    # Each check hands back what it checked, so the three cell indices ARE
    # bools from here on. They are asked a different question from the fourth:
    # a cell is INDEXED by two concrete values of one binary variable, while
    # ``factual_target_known`` is the one input whose absence means something
    # (no factual outcome in evidence). One loop asking all four whether they
    # were "None or a bool" answered the fourth's question four times, and let
    # a value-less index through to be read as False further down.
    x_obs = _require_binary("observed", query.observed.value)
    x_cf = _require_binary(
        "counterfactual_intervention", query.counterfactual_intervention.value,
    )
    y_star = _require_binary(
        "counterfactual_target", query.counterfactual_target.value,
    )
    factual_y = _require_optional_binary(
        "factual_target_known", query.factual_target_known,
    )

    xcol, ycol = x_atom.predicate, y_atom.predicate

    # 1. Interventional-risk strategy — the shared cascade, asked for the ONE
    #    arm this cell depends on. The other is information this answer does
    #    not use, and demanding it would manufacture a data requirement out of
    #    nothing; the cascade takes the arms as a parameter for exactly that
    #    reason, so asking for one is not a narrower copy of asking for two.
    same_world = x_cf == x_obs
    supplied: float | None = (
        None if same_world
        else (query.experimental_risk_treated if x_cf
              else query.experimental_risk_control)
    )
    route = choose_risk_route(
        graph, bidirected, cause=x_atom, effect=y_atom,
        arms=() if same_world else (x_cf,),
        supplied={} if same_world else {x_cf: supplied},
    )
    if route is None:
        # The cascade reached nothing. What is left is this door's own, and
        # not a route: a declared monotonicity can determine the cell outright,
        # obtaining no risk at all. The identity below either pins it from the
        # assumption or raises for the risk it still needs — which is why the
        # licence is claimed here and the claim is settled there.
        route = RiskRoute(RiskProvenance.PINNED_BY_MONOTONICITY)
    provenance = route.provenance
    adjustment = route.adjustment
    risk_formula = route.formulas.get(x_cf)
    instrument = route.instrument

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
        polytope_preconditions(zcol, z_levels)
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
        if provenance == RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE:
            # No scalar risk passes through on this route: the polytope is
            # fitted to the conditional table and the cell read off it.
            P, p_z = counterfactual_cell_iv_table(
                x_arr, y_arr, frame[zcol].to_numpy(), z_levels,
                instrument=zcol,
            )
            low, high = counterfactual_cell_response_bounds(
                P, p_z,
                x_observed=int(x_obs), x_counterfactual=int(x_cf),
                y_star=int(y_star),
                factual_y=None if factual_y is None else int(factual_y),
                monotonicity=monotone,
            )
            return joint, None, NumericInterval(low=low, high=high), (P, p_z)
        if provenance == RiskProvenance.USER_EXPERIMENTAL:
            risk = float(supplied)
        elif provenance in (RiskProvenance.EXOGENOUS,
                            RiskProvenance.BACKDOOR_ADJUSTMENT):
            risk = backdoor_do_risk(x_arr, y_arr, frame, adjustment,
                                    arm=x_cf, treatment=xcol)
        elif provenance == RiskProvenance.GENERAL_ID_PLUG_IN:
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
        # Its own branch for the ROUTE OUT, not for the sentence. Why there
        # is no number is the species' to say and it says it; what this
        # layer knows and the solver does not is that a caller on the data
        # end has somewhere to put the arm — the θ end reaches the same
        # refusal with no such input, so the route belongs to the occasion
        # rather than to the name.
        raise EstimatorFailure(
            need.failure_type, **need.details,
            remedies=[(Remedy.SUPPLY_INPUT,
                       "experimental_risk_treated / "
                       "experimental_risk_control")],
        ) from need
    # Everything else the solver raises is already an EstimatorFailure and
    # already carries its species and its occasion, so it flies. The handler
    # that used to stand here existed to translate a ValueError, and the
    # translation was `str(exc)` — which is how fourteen sentences written
    # in the solver became the reader's, one door away from the count that
    # would have seen them.

    # 4. Percentile bootstrap. A draw whose feasible set is empty is NOT a
    #    silent skip: it means that resample refutes the declared monotonicity,
    #    and the count is reported alongside the interval.
    ci_lower = ci_upper = None
    draws = Draws(ci_bootstrap) if ci_bootstrap > 0 else None
    if draws is not None:
        ci_lower, ci_upper = _bootstrap_cell(
            _run, x, y, df,
            draws=draws, ci_level=ci_level,
            random_state=random_state, groups=groups,
            is_point=abs(interval.high - interval.low) <= _TOL,
        )

    is_point = abs(interval.high - interval.low) <= _TOL
    levels, p_xyz, p_z = (
        polytope_sufficient_statistic(iv_table[0], iv_table[1], z_levels)
        if iv_table else ((), (), ())
    )
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
        instrument_levels=levels, p_xyz=p_xyz, p_z=p_z,
        risk_formula=risk_formula,
        x_observed=bool(x_obs), x_counterfactual=bool(x_cf),
        y_star=bool(y_star), factual_target_known=factual_y,
        monotonicity=monotonicity,
        draws=draws,
        ci_level=ci_level,
        method="counterfactual_cell_plugin",
        assumptions=_assumptions(provenance, adjustment, monotonicity, cluster),
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        cause=xcol, effect=ycol,
        form=FORM_BY_PROVENANCE.get(provenance, DEFAULT_FORM),
        cluster=cluster,
    )


# --- internals ----------------------------------------------------------------


def _require_binary(label: str, value: object) -> bool:
    """Return ``value`` as the bool this estimator is scoped to, or refuse.

    The scope declaration is BINARY X and Y, and this is where it is enforced;
    handing the value back is what lets the rest of the function have it as a
    bool rather than as something a separate assertion once vouched for.
    """
    if not isinstance(value, bool):
        raise EstimatorFailure(
            Refusal.COUNTERFACTUAL_CELL_NOT_BINARY,
            label=label, given=value,
        )
    return value


def _require_optional_binary(label: str, value: object) -> bool | None:
    """Same, where absence is itself an answer — no factual outcome in
    evidence is a different cell, not a malformed one."""
    return None if value is None else _require_binary(label, value)


def _bootstrap_cell(
    run, x: np.ndarray, y: np.ndarray, frame: pd.DataFrame, *,
    draws: Draws, ci_level: float, random_state: int,
    groups: np.ndarray | None, is_point: bool,
) -> tuple[float | None, float | None]:
    """Percentile bootstrap of the cell.

    Point-identified: the CI is the percentile interval of the point across
    draws. Interval-valued: the OUTER band ``(low-quantile of the LOWER
    endpoints, high-quantile of the UPPER endpoints)`` — the Manski /
    Balke-Pearl data-bounds convention shared with ``causation.py``.

    Every dropped draw is filed on ``draws`` under the refusal that dropped
    it, so the infeasible ones — the resamples whose empirical inputs admit
    no SCM under the declared assumptions — are separable from a draw lost
    to a positivity hole, where the assumption is not what failed.

    The count keys on WHICH FAILURE it was, not on which exception class
    carried it. The two solvers raise from different hierarchies — the
    identity through :mod:`themis.runtime.counterfactual`, the polytope as an
    estimator refusal — and one refutation of the same declared assumption
    would otherwise be reported to the reader under a different name.
    """
    rng = np.random.default_rng(random_state)
    n = len(frame)
    lows: list[float] = []
    highs: list[float] = []
    for _ in draws:
        idx = resample_indices(n, rng, groups=groups)
        try:
            _joint, _risk, itv, _table = run(x[idx], y[idx], frame.iloc[idx])
        except EstimatorFailure as exc:
            draws.unusable(exc.failure_type)
            continue
        lows.append(itv.low)
        highs.append(itv.high)
        draws.usable()

    if not draws.enough:
        return None, None
    alpha = (1 - ci_level) / 2
    if is_point:
        arr = np.asarray(lows)
        return (
            float(np.quantile(arr, alpha)),
            float(np.quantile(arr, 1 - alpha)),
        )
    return (
        float(np.quantile(np.asarray(lows), alpha)),
        float(np.quantile(np.asarray(highs), 1 - alpha)),
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
    if provenance == RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE:
        out.append("iv1_relevance_instrument_affects_treatment")
        out.append(
            "iv2_exclusion_instrument_affects_outcome_only_via_treatment")
        out.append(
            "iv3_independence_instrument_independent_of_latent_confounders")
        # Every instrument stratum having observations is NOT listed: the
        # table builder refuses on an empty one, so it is a precondition this
        # answer passed rather than a premise it rests on.
    elif provenance == RiskProvenance.USER_EXPERIMENTAL:
        out.append("interventional_risk_from_randomized_experiment")
    elif provenance == RiskProvenance.EXOGENOUS:
        out.append("exogeneity_no_backdoor_path_do_risk_equals_conditional")
    elif provenance == RiskProvenance.BACKDOOR_ADJUSTMENT:
        out.append(
            "backdoor_adjustment_set_sufficient_{" + ",".join(adjustment) + "}"
        )
        out.append("positivity_the_asked_arm_has_support_in_each_stratum")
    elif provenance == RiskProvenance.GENERAL_ID_PLUG_IN:
        out.append("admg_structure_correct_including_latent_confounders")
        out.append("positivity_every_conditioning_stratum_of_the_estimand_has_support")
        out.append("discrete_variables_saturated_nonparametric_plug_in")
    # No do-risk being available is not a further assumption: it is why the
    # one below cannot be refuted, and it is said on that line rather than
    # beside it.
    if monotonicity is not None:
        out.append(
            f"monotonicity_refutable_{monotonicity}_in_treatment"
            if provenance.can_refute_a_premise
            else f"monotonicity_assumed_{monotonicity}_in_treatment")
    # No else — see :func:`themis.estimation.causation._assumptions`.
    if cluster is not None:
        out.append(f"ci_via_pairs_cluster_bootstrap_on_{cluster}")
    return tuple(out)


