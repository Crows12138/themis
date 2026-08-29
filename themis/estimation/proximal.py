"""Proximal causal inference — numeric estimation (Miao-Geng-Tchetgen 2018,
discrete model (f) identifying formula (5)).

Once :func:`themis.runtime.proximal_identify.identify_proximal` certifies that
the unobserved confounder ``U`` admits a valid treatment proxy ``Z`` and outcome
proxy ``W`` (model (f)), the average causal effect is — in the fully discrete
regime — a closed-form matrix functional of the observed law:

    P(y | do(x)) = P(y | Z, x) · P(W | Z, x)^{-1} · P(W)                    (5)

with, for a fixed ordering of the ``k`` levels of ``Z`` and ``W``,

    M[i, j] = P(W = w_i | Z = z_j, X = x)     (k×k contingency, rows W, cols Z)
    py[j]   = P(Y = y* | Z = z_j, X = x)      (row over Z)
    pw[i]   = P(W = w_i)                       (marginal over W)
    point   = py @ M^{-1} @ pw

Unlike every other Themis estimator this is NOT an ``estimate_formula`` walk over
a symbolic AST — proximal identification produces a matrix operation, not a
do-calculus formula. The empirical conditionals filling M / py / pw are ordinary
count ratios over discrete strata (the same saturated non-parametric plug-in
spirit as the general-ID / counterfactual estimators), but the identifying step
is a linear solve (``numpy.linalg``).

Scope (declared):

- DISCRETE variables only, and this ATE entry takes BINARY treatment / outcome:
  the contrast is E[Y=1 | do(X=1)] − E[Y=1 | do(X=0)]. The proxies Z, W may be
  k-ary and must resolve to exactly ``k`` COLUMNS (k = the assumed cardinality of
  U): each observed level is its own column unless the query declares a
  ``ProxyCoarsening``, which says which observed levels of each proxy make up one
  of the k groups. Folding is sound — a conditional independence survives any
  function of the variable it holds for, so a grouped proxy still satisfies the
  model-(f) criteria, and the folded channel's rank is checked like any other —
  but WHICH grouping is not something the data settles, and two groupings of the
  same sample give two numbers. So the estimator never invents one: a proxy whose
  level count ≠ k with no declared grouping raises, and the refusal names the
  field to declare.
- The RANK condition — M = P(W|Z,x) invertible for every x — is the numeric heart
  of proximal identification and is CHECKED here (ill-conditioned ⇒ refuse). A
  singular M means the proxies are not jointly relevant enough to U to restore the
  effect; that is an ``EstimatorFailure``, never a fabricated number.
- An empty (Z=z, X=x) stratum is a positivity violation ⇒ ``EstimatorFailure``.
- Continuous U (the Fredholm integral / bridge-function regime, Miao §3) is out
  of scope; it needs a two-stage / minimax bridge solver Themis does not have.

Reference: Miao, Geng & Tchetgen Tchetgen 2018 (Biometrika 105(4), formula 5);
Kuroki & Pearl 2014 (Biometrika 101(2)) as the independent effect-restoration
source.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import numpy as np
import pandas as pd

from ..runtime.proximal_identify import ProximalNotIdentified, identify_proximal
from ..types import (
    BridgeChannel, DiscreteChannel, ProximalChannel, ProximalEstimator,
    envelope_scalar,
)
from .proximal_bridge import (
    design_columns, estimate_bridge, estimate_curve, mentions_treatment,
    penalty_verdict, resolve_levels,
)
from ..ledger import Provenance
from .form import NO_OTHER_SHAPES
from .contract import validate_data
from .. import refusals
from ..refusals import BridgeSide, Refusal
from ..refusals import EstimatorFailure
from .resample import cluster_labels, resample_indices

# A conditioning matrix this ill-conditioned means the proxies carry too little
# independent information about U to invert the measurement channel — the rank
# condition has effectively failed even if M is not exactly singular.
_MAX_CONDITION_NUMBER = 1e10

#: What an estimate carries when nothing built it — an empty channel, which
#: the verifier reads as "there is nothing here to re-derive from" rather
#: than as a table that happened to be right.
_NO_CHANNEL: Mapping[str, object] = MappingProxyType({})


@dataclass(frozen=True)
class ProximalEstimate:
    """Result of a proximal ATE estimate via Miao's discrete formula (5)."""

    #: ``None`` where the answer is a CURVE. A curve has no contrast to lead
    #: with — which two of its levels a reader wants differenced is theirs to
    #: pick — and manufacturing one from a chosen pair would put a number
    #: here that nothing asked for and that every downstream surface would
    #: read as the answer.
    point: float | None                # E[Y=1|do(X=1)] − E[Y=1|do(X=0)]
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                        # "proximal_matrix"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    treatment: str
    outcome: str
    #: Z and W as SETS. One source of confounding rarely has one shadow, and
    #: an estimate that could name only one of a study's negative controls
    #: was an estimate that had thrown the others away before arriving here.
    treatment_proxy: tuple[str, ...]   # Z
    outcome_proxy: tuple[str, ...]     # W
    #: The channel this run was made under, as the query declared it. It
    #: replaced a bare ``latent_cardinality``, which was the assumed number
    #: of states of U AND the statement that a matrix was being inverted —
    #: two facts that coincide in the discrete regime and come apart in the
    #: continuous one, where U's cardinality is not assumed at all. Which
    #: shape it holds is also what ``channel`` below is: the sufficient
    #: statistics of a matrix inverse and of a sieve solve are different
    #: objects because they are different computations.
    declared_channel: "ProximalChannel"
    #: Both ``None`` on the curve, for the reason ``point`` is: the two arms
    #: of a contrast are not a subset of a curve's levels, they are a choice
    #: among them.
    do_prob_treated: float | None      # E[Y|do(X=1)]
    do_prob_control: float | None      # E[Y|do(X=0)]
    #: The Z×W contingency counts formula (5) was inverted from — the
    #: sufficient statistics for this estimate, recorded so a second pass can
    #: re-derive the number rather than audit its metadata. See
    #: :func:`_arm_counts` for why counts and not conditionals.
    channel: Mapping[str, object] = _NO_CHANNEL
    #: The levels the curve was evaluated at, and the effect at each against
    #: the first of them. Empty on the binary contrast, which is the shape
    #: this estimate had before a treatment could have more than two levels.
    #: The three fields travel together because the envelope's curve contract
    #: is the three of them and a consumer given two would derive the third —
    #: the reference is ``sampling_points[0]`` and would be re-derived by
    #: whoever needed it, which is one rule in two places.
    sampling_points: tuple[float, ...] = ()
    reference_point: float | None = None
    dose_response_curve: tuple[Mapping[str, object], ...] = ()
    #: C — what the whole estimate was read within, and averaged over at the
    #: end. Empty is the unstratified question, which is what every proximal
    #: estimate was before there was anywhere to put these.
    covariates: tuple[str, ...] = ()
    form: str = "nonparametric_matrix_plug_in"
    #: Nothing chose this shape: it IS the method, and the only way to
    #: overrule it is to answer by a different one.
    form_provenance: str = Provenance.INHERENT
    #: Which shapes a lever BESIDE the outcome model settled, by assumption
    #: id. The ids that RESTATE the outcome model's shape take the answer
    #: above; an id here is a different decision, made by a different lever,
    #: and says so itself — :func:`themis.estimation.form.shapes_settled`.
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES
    cluster: str | None = None


def estimate_proximal_ate(
    data: pd.DataFrame,
    *,
    graph,
    bidirected=frozenset(),
    treatment,
    outcome,
    latent,
    treatment_proxy,
    outcome_proxy,
    covariates=(),
    channel: ProximalChannel,
    outcome_success=True,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> ProximalEstimate:
    """The proximal ATE, by whichever algebra ``channel`` names.

    Parameters mirror :func:`identify_proximal`; ``data`` must carry a column per
    observed variable named by each atom's ``predicate`` (the latent ``U`` has no
    column). ``outcome_success`` is the outcome level the P(Y=y*) contrast is
    taken on and belongs to the discrete regime alone — the bridge regime
    estimates ``E[Y | do(x)]`` for the column as it stands.

    The graph decision is made once here, before the branch, because it is the
    same decision either way: model (f) is the identifying condition in both
    regimes, and what the two do not share is which condition the graph cannot
    discharge and which arithmetic then runs.

    Raises
    ------
    EstimatorFailure: not proximal-identifiable, or whatever the chosen
        regime cannot do — the proxies not resolving to k columns, a declared
        coarsening that is not a partition, a singular channel or an empty
        stratum in the discrete regime; a degenerate basis or an ill-posed
        system at the penalty in force in the bridge regime.
    ValueError: the data violates the estimation contract.
    """
    ident = identify_proximal(
        graph, bidirected, treatment=treatment, outcome=outcome, latent=latent,
        treatment_proxy=treatment_proxy, outcome_proxy=outcome_proxy,
        covariates=covariates, channel=channel,
    )
    if isinstance(ident, ProximalNotIdentified):
        raise EstimatorFailure(
            Refusal.NOT_IDENTIFIABLE_PROXIMAL, detail=ident.statement,
        )
    if isinstance(channel, BridgeChannel):
        return _bridge_estimate(
            data, xcol=treatment.predicate, ycol=outcome.predicate,
            zcols=tuple(a.predicate for a in treatment_proxy),
            wcols=tuple(a.predicate for a in outcome_proxy),
            ccols=tuple(a.predicate for a in covariates),
            spec=channel, ci_bootstrap=ci_bootstrap, ci_level=ci_level,
            random_state=random_state, cluster=cluster,
        )
    latent_cardinality = channel.latent_cardinality
    coarsening = channel.proxy_coarsening

    xcol, ycol = treatment.predicate, outcome.predicate
    # The discrete channel inverts ONE k×k matrix, so it reads one proxy per
    # side; that the query cannot carry more than one here is settled where
    # the program is read, not rediscovered by indexing into a tuple.
    (zcol,) = (a.predicate for a in treatment_proxy)
    (wcol,) = (a.predicate for a in outcome_proxy)
    required = frozenset({xcol, ycol, zcol, wcol})
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

    z_levels = sorted(df[zcol].unique())
    w_levels = sorted(df[wcol].unique())
    x_levels = sorted(df[xcol].unique())
    z_groups = _resolve_groups(
        z_levels, None if coarsening is None else coarsening.treatment_proxy,
        proxy=zcol, k=latent_cardinality)
    w_groups = _resolve_groups(
        w_levels, None if coarsening is None else coarsening.outcome_proxy,
        proxy=wcol, k=latent_cardinality)
    # Reachable only where nothing was declared: a declaration's arity is
    # answered inside ``_resolve_groups``, by the species that can say the
    # declaration is what disagrees.
    if len(z_groups) != latent_cardinality or len(w_groups) != latent_cardinality:
        raise EstimatorFailure(
            Refusal.PROXY_CARDINALITY_MISMATCH,
            k=latent_cardinality, z=len(z_groups), w=len(w_groups),
        )
    if set(x_levels) - {False, True, 0, 1} or len(x_levels) < 2:
        raise EstimatorFailure(
            Refusal.TREATMENT_NOT_BINARY, treatment=xcol, levels=x_levels,
        )

    w_marginal = _w_marginal(df, wcol, w_levels)
    treated = _arm_counts(
        df, xcol, ycol, zcol, wcol, x=True, z_levels=z_levels,
        w_levels=w_levels, z_groups=z_groups, outcome_success=outcome_success)
    control = _arm_counts(
        df, xcol, ycol, zcol, wcol, x=False, z_levels=z_levels,
        w_levels=w_levels, z_groups=z_groups, outcome_success=outcome_success)
    p_treated = _risk_from_counts(
        treated, w_marginal, len(df), z_groups=z_groups, w_groups=w_groups)
    p_control = _risk_from_counts(
        control, w_marginal, len(df), z_groups=z_groups, w_groups=w_groups)
    point = p_treated - p_control
    channel_record = {
        # The levels the columns HOLD, and the grouping that turns them into
        # the k columns of M — rather than the folded table. Folding is a
        # step, and a step nobody re-walks is a place the answer can be moved
        # without leaving a mark: recording the fold's inputs is what lets a
        # second pass run the fold rather than take its word for the result.
        "z_levels": tuple(envelope_scalar(z) for z in z_levels),
        "w_levels": tuple(envelope_scalar(w) for w in w_levels),
        "z_groups": z_groups,
        "w_groups": w_groups,
        "outcome_success": envelope_scalar(outcome_success),
        "n_total": int(len(df)),
        "w_marginal_counts": w_marginal,
        "treated": treated,
        "control": control,
    }

    ci_lower = ci_upper = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap_ci(
            df, xcol, ycol, zcol, wcol, z_levels=z_levels, w_levels=w_levels,
            z_groups=z_groups, w_groups=w_groups,
            outcome_success=outcome_success, ci_bootstrap=ci_bootstrap,
            ci_level=ci_level, random_state=random_state, groups=groups)

    assumptions: tuple[str, ...] = (
        "diagram_correct_including_unobserved_confounder_U_and_proxy_roles",
        "U_sufficient_confounder_and_proxies_satisfy_miao_model_f",
        # Which of the two is said depends on whether a grouping was
        # declared, because the first states as a fact the thing a coarsened
        # run is not doing. The second is attributed to the CALLER — see
        # :class:`themis.ledger.Provenance.CALLER_CHOSE`.
        ("latent_cardinality_k_correct_and_proxies_have_exactly_k_levels"
         if coarsening is None else
         "latent_cardinality_k_correct_and_the_declared_coarsening_"
         "folds_each_proxy_to_k_levels"),
        "rank_condition_P(W|Z,x)_invertible_verified_on_data",
        "positivity_every_conditioning_stratum_has_support",
        "consistency_and_no_interference",
    )
    if cluster is not None:
        assumptions = assumptions + (f"ci_via_pairs_cluster_bootstrap_on_{cluster}",)
    return ProximalEstimate(
        point=float(point),
        ci_lower=float(ci_lower) if ci_lower is not None else None,
        ci_upper=float(ci_upper) if ci_upper is not None else None,
        ci_level=ci_level,
        method="proximal_matrix",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=xcol,
        outcome=ycol,
        treatment_proxy=(zcol,),
        outcome_proxy=(wcol,),
        declared_channel=DiscreteChannel(
            latent_cardinality=latent_cardinality,
            proxy_coarsening=coarsening,
        ),
        do_prob_treated=float(p_treated),
        do_prob_control=float(p_control),
        channel=channel_record,
        form="nonparametric_matrix_plug_in",
        cluster=cluster,
    )


# --- the continuous regime ----------------------------------------------------


def _bridge_estimate(
    data: pd.DataFrame, *, xcol: str, ycol: str,
    zcols: tuple[str, ...], wcols: tuple[str, ...], ccols: tuple[str, ...],
    spec: BridgeChannel, ci_bootstrap: int, ci_level: float,
    random_state: int, cluster: str | None,
) -> ProximalEstimate:
    """Assemble the same estimate object around the sieve solve.

    The one thing this does that the discrete path does not is put the
    penalty on the ledger under an author. A run where the caller named λ and
    a run where nobody did produce the same arithmetic and are not the same
    claim, and the difference is a fact about who to argue with — so it is an
    assumption id and not a comment.
    """
    # The columns the DESIGN reads, not the roles the query declared: a
    # proxy the caller named and gave no term to would otherwise be demanded
    # of the frame and then never looked at.
    required = frozenset({xcol, ycol, *design_columns(spec)})
    presence = (cluster,) if cluster is not None else ()
    groups = (
        cluster_labels(data, cluster, expected_n=len(data))
        if cluster is not None else None
    )
    contract = validate_data(
        data, required_columns=required, presence_columns=presence)
    df = contract.data

    x_levels = sorted(df[xcol].unique())
    if len(x_levels) < 2:
        raise EstimatorFailure(
            Refusal.TREATMENT_NOT_BINARY, treatment=xcol, levels=x_levels)
    # Two questions, and they are answered by different things. WHICH SOLVE
    # runs is the declaration's to say: a sieve that names the treatment is
    # asking for one bridge indexed by the level, and one that does not is
    # asking for a bridge per arm. WHAT SHAPE comes back is the treatment's
    # cardinality, because a contrast between two levels is undefined once
    # there are more than two of them.
    #
    # The remaining cell is the only refusal: more than two levels and a
    # sieve that cannot vary with them. The old refusal covered it by
    # covering everything past two levels, which is why narrowing that one
    # needs this one to exist rather than merely to be nicer.
    binary = not (set(x_levels) - {False, True, 0, 1})
    if mentions_treatment(spec, xcol):
        return _bridge_curve_estimate(
            df, contract=contract, xcol=xcol, ycol=ycol, zcols=zcols,
            wcols=wcols, ccols=ccols, spec=spec, ci_bootstrap=ci_bootstrap,
            ci_level=ci_level, random_state=random_state, groups=groups,
            cluster=cluster)
    if not binary:
        raise EstimatorFailure(
            Refusal.BRIDGE_CANNOT_VARY_WITH_THE_TREATMENT,
            treatment=xcol, levels=len(x_levels), design=BridgeSide.SPAN)

    solved = estimate_bridge(df, xcol=xcol, ycol=ycol, spec=spec)

    ci_lower = ci_upper = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bridge_bootstrap_ci(
            df, xcol=xcol, ycol=ycol, spec=spec,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level,
            random_state=random_state, groups=groups)

    assumptions: tuple[str, ...] = (
        "diagram_correct_including_unobserved_confounder_U_and_proxy_roles",
        "U_sufficient_confounder_and_proxies_satisfy_miao_model_f",
        # Completeness is the continuous rank condition and, unlike the rank
        # condition, is not testable from data (Canay-Santos-Shaikh 2013) —
        # so it is a line the reader accepts, not one the estimator checks.
        "completeness_of_the_conditional_operator_E[.|Z,X=x]",
        *_span_assumptions(spec),
        ("regularisation_lambda_chosen_by_the_caller"
         if spec.outcome_bridge.ridge is not None
         else "regularisation_lambda_defaulted_by_the_estimator"),
        *_treatment_bridge_assumptions(spec),
        "consistency_and_no_interference",
    )
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",)
    return ProximalEstimate(
        point=float(solved.point),
        ci_lower=float(ci_lower) if ci_lower is not None else None,
        ci_upper=float(ci_upper) if ci_upper is not None else None,
        ci_level=ci_level,
        method="proximal_bridge",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=xcol,
        outcome=ycol,
        treatment_proxy=zcols,
        outcome_proxy=wcols,
        covariates=ccols,
        declared_channel=spec,
        do_prob_treated=float(solved.do_treated),
        do_prob_control=float(solved.do_control),
        # Absent where the estimator has no analytic standard error, rather
        # than present and null: a consumer asking whether there is one gets
        # its answer from the key existing, and a null would make "no error
        # was computed" and "the error is nothing" the same wire.
        channel=(dict(solved.channel, standard_error=solved.standard_error)
                 if solved.standard_error is not None else dict(solved.channel)),
        form="sieve_two_stage_bridge",
        cluster=cluster,
    )


def _bridge_curve_estimate(
    df, *, contract, xcol, ycol, zcols, wcols, ccols, spec, ci_bootstrap,
    ci_level, random_state, groups, cluster,
) -> ProximalEstimate:
    """``E[Y(a)]`` at every level, as the envelope's curve.

    The effects are reported against the LOWEST level rather than against
    the sample mean or an untreated state the data need not contain, which
    is the contract the envelope's curve already has and the one the
    report renders: the reference row's own effect is zero by construction,
    so a reader can see which level everything is being read against
    instead of inferring it.
    """
    levels = resolve_levels(df[xcol].to_numpy(dtype=float))
    solved = estimate_curve(df, xcol=xcol, ycol=ycol, spec=spec, levels=levels)
    bands = _bridge_curve_bootstrap(
        df, xcol=xcol, ycol=ycol, spec=spec, levels=levels,
        ci_bootstrap=ci_bootstrap, ci_level=ci_level,
        random_state=random_state, groups=groups)

    reference = solved.means[0]
    curve = tuple({
        "x": float(level),
        "effect": float(mean - reference),
        "ci_lower": band[0],
        "ci_upper": band[1],
    } for level, mean, band in zip(solved.levels, solved.means, bands))

    assumptions: tuple[str, ...] = (
        "diagram_correct_including_unobserved_confounder_U_and_proxy_roles",
        "U_sufficient_confounder_and_proxies_satisfy_miao_model_f",
        "completeness_of_the_conditional_operator_E[.|Z,X=x]",
        *_span_assumptions(spec),
        # The curve's own line, and the one a reader most needs: the shape
        # BETWEEN the levels is the declared basis on the treatment and not
        # something the data chose. A sieve linear in the dose draws a
        # straight line through a curved truth and reports no misfit.
        "the_bridge_varies_with_the_treatment_as_the_declared_basis_does",
        ("regularisation_lambda_chosen_by_the_caller"
         if spec.outcome_bridge.ridge is not None
         else "regularisation_lambda_defaulted_by_the_estimator"),
        "consistency_and_no_interference",
    )
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",)
    return ProximalEstimate(
        point=None, ci_lower=None, ci_upper=None, ci_level=ci_level,
        method="proximal_bridge",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=xcol,
        outcome=ycol,
        treatment_proxy=zcols,
        outcome_proxy=wcols,
        covariates=ccols,
        declared_channel=spec,
        do_prob_treated=None,
        do_prob_control=None,
        sampling_points=solved.levels,
        reference_point=float(solved.levels[0]),
        dose_response_curve=curve,
        channel=dict(solved.channel),
        form="sieve_two_stage_bridge",
        cluster=cluster,
    )


def _bridge_curve_bootstrap(
    df, *, xcol, ycol, spec, levels, ci_bootstrap, ci_level, random_state,
    groups,
) -> tuple[tuple[float | None, float | None], ...]:
    """Percentile bootstrap of each EFFECT, resampled jointly.

    One resample gives one whole curve, and the interval at each level is
    taken across those curves — so every band is computed from the same
    draws and the reference level's own uncertainty is inside all of them.
    Bootstrapping each level against a separately drawn reference would put
    a non-zero band on the reference itself, which by construction has no
    effect to be uncertain about.
    """
    if ci_bootstrap <= 0:
        return tuple((None, None) for _ in levels)
    rng = np.random.default_rng(random_state)
    n = len(df)
    draws: list[np.ndarray] = []
    for _ in range(ci_bootstrap):
        sample = df.iloc[resample_indices(n, rng, groups=groups)]
        try:
            got = estimate_curve(sample, xcol=xcol, ycol=ycol, spec=spec,
                                 levels=levels)
        except EstimatorFailure:
            continue
        means = np.asarray(got.means, dtype=float)
        draws.append(means - means[0])
    if len(draws) < 2:
        return tuple((None, None) for _ in levels)
    stacked = np.vstack(draws)
    alpha = (1 - ci_level) / 2
    return tuple(
        (float(np.quantile(stacked[:, i], alpha)),
         float(np.quantile(stacked[:, i], 1 - alpha)))
        for i in range(len(levels)))


def _span_assumptions(spec: BridgeChannel) -> tuple[str, ...]:
    """Which span has to be right for THIS estimator's answer to be right.

    The whole content of the estimator choice, written where a reader meets
    it. Which family and which dimension are NOT spelled into these ids —
    they are on the estimand block, and an id that carried them would be a
    new assumption every time somebody changed a number, with no glossary
    entry and therefore no reader.

    Under the doubly robust estimator the two individual lines are ABSENT
    rather than both present, and that absence is the theorem: it needs
    neither span to be right on its own, only one of them, and a ledger
    listing both as required would be describing a stricter estimator.
    """
    if spec.estimator == ProximalEstimator.OUTCOME_REGRESSION:
        return ("the_outcome_bridge_lies_in_the_span_of_the_declared_sieve",)
    if spec.estimator == ProximalEstimator.INVERSE_PROBABILITY:
        return ("the_treatment_bridge_lies_in_the_span_of_the_declared_sieve",)
    if spec.estimator == ProximalEstimator.DOUBLY_ROBUST:
        return ("at_least_one_of_the_two_bridges_lies_in_its_declared_span",)
    raise TypeError(f"unknown proximal estimator: {spec.estimator!r}")


def _treatment_bridge_assumptions(spec: BridgeChannel) -> tuple[str, ...]:
    """What a second bridge adds to the ledger, when there is one."""
    if spec.treatment_bridge is None:
        return ()
    return (
        # Assumption 11 of Cui et al. 2024 — the mirror of the completeness
        # already listed, in the direction q is pinned down along.
        "completeness_of_the_conditional_operator_E[.|W,A=a,X]",
        ("treatment_bridge_regularisation_lambda_chosen_by_the_caller"
         if spec.treatment_bridge.ridge is not None
         else "treatment_bridge_regularisation_lambda_defaulted_by_the_estimator"),
    )


def _bridge_bootstrap_ci(
    df, *, xcol, ycol, spec, ci_bootstrap, ci_level, random_state, groups,
) -> tuple[float | None, float | None]:
    """Percentile bootstrap of the bridge ATE, penalty held where it was.

    The bases are re-fitted inside each draw on purpose: their constants are
    sample quantiles and moments, so holding them fixed would treat a chosen
    knot as a known one and report an interval narrower than the procedure
    is. A draw whose basis or penalised system will not solve is skipped, and
    the interval is over the draws where the bridge exists.
    """
    rng = np.random.default_rng(random_state)
    n = len(df)
    estimates: list[float] = []
    for _ in range(ci_bootstrap):
        sample = df.iloc[resample_indices(n, rng, groups=groups)]
        try:
            estimates.append(estimate_bridge(
                sample, xcol=xcol, ycol=ycol, spec=spec).point)
        except EstimatorFailure:
            continue
    if len(estimates) < 2:
        return None, None
    arr = np.asarray(estimates)
    alpha = (1 - ci_level) / 2
    return float(np.quantile(arr, alpha)), float(np.quantile(arr, 1 - alpha))


# --- internals ----------------------------------------------------------------


def _resolve_groups(levels, declared, *, proxy, k) -> tuple[tuple[int, ...], ...]:
    """Which observed levels make up each column of M, as indices into
    ``levels``.

    Absent a declaration every level is its own column, which is both the
    ordinary case and the reason there is one code path rather than two: a
    proxy that already presents k levels is a proxy with the identity
    grouping, and the fold over singletons is the arithmetic that was
    already being done.

    Indices and not the values themselves, because what travels onto the
    envelope has to be checkable against the level list it refers to — a
    group naming values is a second copy of them, and two copies of a thing
    are a thing that can disagree with itself.

    Raises ``EstimatorFailure`` unless the declaration is a PARTITION of the
    observed levels with as many groups as the query posits states of the
    latent. Every direction is a refusal and none is a correction: a level
    in no group would silently drop rows out of the channel, a group naming
    a level the column does not hold means the caller and the data disagree
    about what was measured, and the wrong number of groups is the caller's
    two statements disagreeing with each other — none of which this module
    will decide on their behalf.

    A declaration's arity is checked HERE and the undeclared case's in the
    caller, because the two are different findings: without a declaration
    the proxy simply has more levels than k and the errand is to write the
    field, and with one the field is written and says the wrong thing.
    Refusals rather than parse errors, so a reader meets them in their own
    language; the cost is that they wait for data, which is also the first
    moment a coarsening can change an answer.
    """
    if declared is None:
        return tuple((i,) for i in range(len(levels)))
    if len(declared) != k:
        raise EstimatorFailure(
            Refusal.COARSENING_GROUP_COUNT_IS_NOT_K,
            proxy=proxy, groups=len(declared), k=k,
        )
    here = [envelope_scalar(v) for v in levels]
    index = {v: i for i, v in enumerate(here)}
    named = [envelope_scalar(v) for group in declared for v in group]
    # The observed levels are distinct by construction, so "as many names as
    # levels, and the same set" IS the partition: a level named twice makes
    # the count too big, one named nowhere makes it too small, and a group
    # that names nothing is a column of M with no rows behind it.
    if (any(not group for group in declared)
            or len(named) != len(here) or set(named) != set(here)):
        raise EstimatorFailure(
            Refusal.COARSENING_DOES_NOT_PARTITION_THE_PROXY,
            proxy=proxy,
            declared=", ".join(sorted(map(str, named))),
            observed=", ".join(sorted(map(str, here))),
        )
    return tuple(
        tuple(index[envelope_scalar(v)] for v in group) for group in declared)


def _arm_counts(
    df: pd.DataFrame, xcol, ycol, zcol, wcol, *, x, z_levels, w_levels,
    z_groups, outcome_success,
) -> tuple[dict, ...]:
    """The (Z, W, Y) contingency counts one arm of formula (5) is built from,
    at the resolution the COLUMN has rather than the one M has.

    Counts, and not the conditionals they normalise to. All a second pass
    can check about a probability is that it lies in [0, 1]; about a count
    it can check that the W row sums to its stratum, that the strata sum to
    the sample, and that the number the whole thing produces comes back.
    **A normalisation is a step, and a step nobody re-walks is a place the
    answer can be moved without leaving a mark**, and the same argument is
    why the fold happens downstream of this: a folded table is a table
    somebody has already made a decision about.

    An empty raw stratum is therefore NOT a positivity violation — with a
    coarsening declared, a sparse level is often precisely what was grouped
    away. Positivity is a property of the strata the formula conditions on,
    so it is checked over ``z_groups``, and it is checked here rather than
    where the fold runs because this is the last place holding the names a
    reader would need to go and look.
    """
    sub = df[df[xcol] == x]
    rows: list[dict] = []
    for zj in z_levels:
        stratum = sub[sub[zcol] == zj]
        rows.append({
            "z": envelope_scalar(zj),
            "n": int(len(stratum)),
            "w_counts": tuple(
                int((stratum[wcol] == wi).sum()) for wi in w_levels),
            "y_count": int((stratum[ycol] == outcome_success).sum()),
        })
    for group in z_groups:
        if sum(rows[j]["n"] for j in group) == 0:
            raise EstimatorFailure(
                Refusal.INSUFFICIENT_SUPPORT,
                cells=[{zcol: [rows[j]["z"] for j in group], xcol: x}],
                quantity=f"P({wcol} | {zcol}, {xcol})",
            )
    return tuple(rows)


def _risk_from_counts(
    rows, w_marginal_counts, n_total, *, z_groups, w_groups,
) -> float:
    """Miao formula (5) on one arm: P(Y=y* | do(X=x)) = py @ M^{-1} @ pw.

    ``M[i,j] = P(W in w_group_i | Z in z_group_j, X=x)``, ``py[j] = P(Y=y* |
    Z in z_group_j, X=x)``, ``pw[i] = P(W in w_group_i)`` — each folded out
    of the raw counts and THEN normalised, which is the only order that
    gives the conditionals of the grouped variables. Raises
    ``EstimatorFailure`` on an ill-conditioned M, which is the rank
    condition failing on the channel as grouped: a coarsening can destroy
    the rank the finer proxy had, and that is a real answer about the
    grouping rather than a reason to try another one.

    This is the whole of the arithmetic, in one place. The verifier writes
    its own second transcription of it rather than calling this one.
    """
    k = len(z_groups)
    M = np.empty((k, k))
    py = np.empty(k)
    for j, group in enumerate(z_groups):
        n_zx = sum(rows[c]["n"] for c in group)
        for i, wgroup in enumerate(w_groups):
            M[i, j] = sum(
                rows[c]["w_counts"][d] for c in group for d in wgroup) / n_zx
        py[j] = sum(rows[c]["y_count"] for c in group) / n_zx
    pw = np.asarray(
        [sum(w_marginal_counts[d] for d in wgroup) for wgroup in w_groups],
        dtype=float) / n_total

    condition = np.linalg.cond(M)
    if not np.isfinite(condition) or condition > _MAX_CONDITION_NUMBER:
        raise EstimatorFailure(Refusal.RANK_CONDITION_VIOLATED)
    return float(py @ np.linalg.solve(M, pw))


def _w_marginal(df, wcol, w_levels) -> tuple[int, ...]:
    """How many rows sit at each W level, over the whole sample."""
    return tuple(int((df[wcol] == wi).sum()) for wi in w_levels)


def _proximal_do_prob(
    df: pd.DataFrame, xcol, ycol, zcol, wcol, *, x, z_levels, w_levels,
    z_groups, w_groups, outcome_success,
) -> float:
    """One arm end to end, for the bootstrap.

    The two halves above composed, so a resampled draw walks the same
    transcription the point does rather than a second one beside it.
    """
    rows = _arm_counts(
        df, xcol, ycol, zcol, wcol, x=x, z_levels=z_levels,
        w_levels=w_levels, z_groups=z_groups, outcome_success=outcome_success)
    return _risk_from_counts(
        rows, _w_marginal(df, wcol, w_levels), len(df),
        z_groups=z_groups, w_groups=w_groups)


def _bootstrap_ci(
    df, xcol, ycol, zcol, wcol, *, z_levels, w_levels, z_groups, w_groups,
    outcome_success, ci_bootstrap, ci_level, random_state, groups,
) -> tuple[float | None, float | None]:
    """Non-parametric percentile bootstrap of the proximal ATE. Level sets are
    fixed from the full data; a resample that induces an empty stratum or a
    singular M is skipped (the CI is over the draws where (5) is evaluable)."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    estimates: list[float] = []
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        sample = df.iloc[idx]
        try:
            pt = _proximal_do_prob(
                sample, xcol, ycol, zcol, wcol, x=True, z_levels=z_levels,
                w_levels=w_levels, z_groups=z_groups, w_groups=w_groups,
                outcome_success=outcome_success)
            pc = _proximal_do_prob(
                sample, xcol, ycol, zcol, wcol, x=False, z_levels=z_levels,
                w_levels=w_levels, z_groups=z_groups, w_groups=w_groups,
                outcome_success=outcome_success)
        except EstimatorFailure:
            continue
        estimates.append(pt - pc)
    if len(estimates) < 2:
        return None, None
    arr = np.asarray(estimates)
    alpha = (1 - ci_level) / 2
    return float(np.quantile(arr, alpha)), float(np.quantile(arr, 1 - alpha))
