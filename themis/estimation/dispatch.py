"""Phase 7.1 S.N.3 — estimate dispatch: wire data + identification into
a numeric answer.

Pipeline:

1. Runs the identification pipeline via ``themis.run`` to get
   adjustment strategies + derivation per query.
2. Validates the user's DataFrame against the data contract.
3. For each effect query whose identification strategy is backdoor
   (either success or fallback-to-structural), recomputes the
   adjustment set from the graph and dispatches to
   ``estimate_backdoor_ate``. The numeric result is attached as
   ``result["numeric_estimate"]`` and the status flips to
   ``numerically_solved`` (still carrying the structural derivation).

Later slices (7.2 / 7.3 / 7.4) will plug in front-door / IV /
mediation estimators behind the same dispatch switch.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Callable

from .. import blocks, refusals
# Imported here and not in each handler that catches it. It was a
# per-function import at twenty-four sites; the twenty-fifth handler
# forgot, and an ``except`` clause evaluates its name only when it
# fires, so the doubly-robust path answered a refusal with NameError.
from .. import intervals
from ..refusals import EstimatorFailure, Refusal
from ..output.sample_size import estimate_n_for_target_ci_half_width
from ..runtime.investigation_pusher import summarise
from ..types import (
    DataGap,
    DataGapReport,
    GapBlocks,
    GapKind,
    GapProvenanceRef,
    GapRefKind,
    GapRequiredData,
    GapSeverity,
    Priority,
    RequiredDataType,
    envelope_scalar,
)
from .claim import Claim, annotated, answered, blocked, passed
from . import declared as _declared
from .contract import DataContract, validate_data
from .. import gaps as _gaps
from ..gaps import Route, Sentence, sentence as _sentence
from .. import language as _lang
from ..routing import End, route
from .strategy import (
    STRUCTURE_BERKSON,
    STRUCTURE_CLASSICAL,
    EffectFacts,
    EffectKnobs,
    Estimand,
    Evaluation,
    Role,
    Strategy,
    check_table,
    run_cascade,
)
from .resample import DeclaredVariance, Draws, share_lost_to

if TYPE_CHECKING:  # the estimators themselves stay behind local imports, so
    # that a name used only in a signature cannot become a load-time edge.
    from .outcome_error import OutcomeErrorDesign


def estimate_program(
    program: dict | str | bytes,
    data: Any,
    *,
    random_state: int = 42,
    ci_bootstrap: int = 500,
    model: str = "auto",
    cluster: str | None = None,
    ate_estimator: str = "gformula",
    reference_data: Any = None,
    misclassification: dict | None = None,
    measurement_error: dict | None = None,
) -> dict:
    """Estimate every query in ``program`` on ``data``; see ``themis.estimate``.

    A thin single exit around :func:`_estimate_program`, so that what must
    hold for EVERY numeric answer holds in one place rather than once per
    estimator family. Doing it per family is what left most of them out: it
    took remembering two separate things, and forgetting either was silent.

    Four things hold here. Its declared assumptions reach the assumption
    ledger, the surface both the report assembler and the rendering bridge
    lead with. What the identification pass asked for as a precondition
    of running is withdrawn once running has happened — after the ledger,
    which is where the disclosure the withdrawal relies on lands. Every
    block it left on the envelope is one
    :mod:`themis.blocks` declares, so a new block cannot reach a reader
    the registry has never heard of. And a refusal leaves carrying both
    the species :mod:`themis.refusals` declares and the ``kind`` that
    says what the reader should do about it, so a consumer branches on a
    closed set rather than on whatever the estimator spelled.

    A fifth, for the same reason: ``model`` is a closed vocabulary with
    five readers, and it becomes the option here rather than at each of
    them. Two of the five normalised and three compared exactly, so the
    same spelling was accepted on one route and refused on another, and
    the one that reached the envelope was whatever the caller typed.
    """
    from ..output.result_orchestrator import augment_assumption_ledger

    output = _estimate_program(
        program, data,
        random_state=random_state, ci_bootstrap=ci_bootstrap,
        model=_declared_model(model),
        cluster=cluster, ate_estimator=ate_estimator,
        reference_data=reference_data, misclassification=misclassification,
        measurement_error=measurement_error,
    )
    for result in output.get("results", []):
        augment_assumption_ledger(result)
        _withdraw_asks_estimating_supersedes(result)
        blocks.check_registered(result)
        refusals.stamp(result)
    return output


def _estimate_program(
    program: dict | str | bytes,
    data: Any,
    *,
    random_state: int = 42,
    ci_bootstrap: int = 500,
    model: str = "auto",
    cluster: str | None = None,
    ate_estimator: str = "gformula",
    reference_data: Any = None,
    misclassification: dict | None = None,
    measurement_error: dict | None = None,
) -> dict:
    """See ``themis.estimate`` for the full contract.

    ``cluster`` names a column carrying a cluster / block id (families,
    repeated measures, schools). When supplied — either as this kwarg or
    via the program AST's ``options.cluster`` — every estimator's
    bootstrap CI resamples whole clusters (pairs cluster bootstrap)
    instead of i.i.d. rows. The cluster column is a variance concern, so
    it is added to the data contract as a presence-only column (required
    to exist + be non-null) but never enters the causal model or the
    data hash.

    ``ate_estimator`` selects the estimator for the backdoor-identified
    ATE: ``"gformula"`` (default — the outcome-regression plug-in,
    byte-identical to before this option existed), ``"ipw"`` (inverse-
    probability weighting on the propensity), or ``"aipw"`` (the
    doubly-robust augmented estimator: consistent if EITHER the outcome
    OR the propensity model is correct). May also be set via the program
    AST's ``options.ate_estimator``. Only the backdoor branch honours it;
    front-door / IV / mediation keep their own estimators.

    ``reference_data`` is an optional second DataFrame — the external
    *unbiased* sample T required to recover a causal effect under selection
    bias (Bareinboim-Pearl selection backdoor). It is used ONLY when a query's
    result carries a ``selection_recovery`` block: the biased primary ``data``
    supplies the S-conditioned risks and ``reference_data`` supplies the
    adjustment weights P(z⁺)/P(z⁻|x,z⁺). Ordinary (no-selection) programs never
    touch it.

    ``misclassification`` is an optional dict keyed by outcome variable name,
    each value a validated confusion-matrix spec ``{"confusion_matrix": [[…]],
    "states": [...], "target_value": …?, "differential": False?, "source": …?}``
    from a validation study. When an effect query's OUTCOME has a spec, the
    numeric end de-attenuates the misclassification by inverting the confusion
    matrix per back-door stratum (Rogan-Gladen for a binary outcome) instead of
    shipping the attenuated naive g-formula number. Like ``reference_data`` it is
    a load-bearing external input used only at estimate time; ordinary programs
    never touch it. A spec on the query's EXPOSURE routes to the exposure-side
    matrix method instead; a spec on BOTH routes to the combined correction,
    which inverts the joint on both sides at once rather than leaving one
    channel's bias in the number. Deferred: a DIFFERENTIAL matrix on either
    channel of a combined correction.

    ``measurement_error`` is the CONTINUOUS counterpart, an optional dict keyed by
    EXPOSURE variable name, each value ``{"error_variance": σ²_u, "source": …?}``
    — the known classical additive measurement-error variance of a continuously-
    mismeasured exposure (W = X* + U). When an effect query's exposure has a spec,
    the numeric end de-attenuates the regression dilution by the regression-
    calibration moment correction β_true = (Σ_WZ − E)⁻¹ Σ_WZ b_naive instead of
    shipping the attenuated naive back-door slope. Like ``misclassification`` it is
    a load-bearing external input used only at estimate time.

    That moment correction is an IDENTITY about a linear outcome, so the exposure's
    spec may additionally declare which model the wanted coefficient lives in:
    ``{"error_variance": σ²_u, "outcome_model": "logistic", "extrapolant": …?,
    "lambdas": …?, "n_replicates": …?}`` routes to simulation-extrapolation
    (SIMEX) instead. The declaration is not a preference between two roads to one
    number — on a binary outcome the moment correction de-attenuates the
    linear-probability slope and SIMEX de-attenuates the log-odds ratio, and
    nothing in the data says which the caller meant. An absent or ``"linear"``
    model keeps the closed form, which beats a seeded simulation of itself.

    A spec on the OUTCOME is a different object, because what a mismeasured
    variable costs depends on the role it plays. A classical additive error on a
    continuous outcome leaves every conditional mean — and so every estimand here
    — unchanged, so nothing is de-attenuated and the ordinary number stands. What
    the declared σ²_v buys instead is the price: an ``outcome_error`` block
    splitting the residual variance into signal and measurement noise, and the
    factor by which that noise widens the interval (the part of the uncertainty
    more subjects cannot buy back). It composes with an exposure-side spec rather
    than displacing it. A differential error on the OUTCOME channel is still
    deferred — the spec has no way to declare one there, so accepting it would
    be inventing a premise nobody made.

    A spec naming a ``structure`` other than the classical one is the third
    reading, and it routes past the ladder rather than into it. Under Berkson
    error the answer needs no correction, so there is no row to displace and
    nothing to compute until the answer exists — what the error cost is
    β̂²σ²_u, scaled by the very number the query returns.
    """
    from ..kernel import run as _run

    identification_output = _run(program)

    cluster = _resolve_cluster_option(program, cluster)
    ate_estimator = _resolve_ate_estimator_option(program, ate_estimator)

    # Record the resolved cluster column at RUN level, before any branch
    # can consume it. Without this the envelope cannot distinguish "no
    # cluster column was named" from "one was named and this estimator
    # dropped it" — the two look identical, so no verifier can catch the
    # second. Written only when a column was resolved, keeping the
    # cluster-free envelope byte-identical.
    if cluster is not None:
        for result in identification_output.get("results", []):
            result.setdefault("estimation_context", {})["cluster"] = cluster

    # Phase 9 §S9.2 numeric end: a program declaring missingness indicators
    # carries NaN in its partially-observed columns, which the standard data
    # contract (validate_data) forbids. Route it to the missing-data recovery
    # estimator, which applies the ordered-factorization recovery formula and
    # honours the identification verdict (only produces a number when the
    # estimand is recoverable). Guarded on the indicator declaration, so
    # ordinary (no-indicator) programs never reach here and are byte-identical.
    if _declares_missingness(program):
        _maybe_estimate_missing_recovery(
            program, identification_output, data,
            random_state=random_state, ci_bootstrap=ci_bootstrap,
            cluster=cluster,
        )
        return identification_output

    required_columns = _collect_required_columns(program)
    if not required_columns:
        return identification_output

    presence_columns = (
        {cluster} if cluster and cluster not in required_columns else set()
    )
    # What the program declared, applied before the contract asks what the
    # frame holds. A three-level channel arriving as text is the commonest
    # shape business data has, and it was refused while the same variable
    # coded 0/1/2 was accepted — the encoding deciding the run. Left of this
    # line the frame is the user's; right of it, it is the program's.
    ast = _ensure_dict(program)
    contract = validate_data(
        _declared.conform(ast, data),
        required_columns=required_columns,
        presence_columns=presence_columns,
    )
    # The OTHER frame this program describes. It reaches a ``validate_data``
    # of its own inside the recovery estimators, so a labelled column there
    # would end the run exactly where one in the primary frame used to. One
    # entry conformed and one not is the same defect with a smaller blast
    # radius rather than a smaller defect.
    if reference_data is not None:
        reference_data = _declared.conform(ast, reference_data)

    for result in identification_output.get("results", []):
        result.setdefault("estimation_context", {}).update({
            "data_hash": contract.data_hash,
            "data_columns": list(contract.columns),
            "sample_size": contract.sample_size,
            "data_contract_warnings": list(contract.warnings),
            "random_state": random_state,
            "ci_bootstrap": ci_bootstrap,
            "model_preference": model,
        })
        # The same loop that records what arrived records what arriving
        # answered. Before any estimator runs, because a θ ask is settled
        # by the sample existing — not by what an estimator makes of it.
        _settle_asks_the_sample_answers(result, contract.columns)

    # Phase 7.L — g-methods for time-varying treatments. Detected via an
    # explicit ``options.longitudinal`` spec (not the structural query
    # shape): the longitudinal g-formula needs the time ordering of
    # treatments + covariates, which the cross-sectional AST doesn't carry.
    # Runs first so the per-query backdoor loop's guard skips re-estimating
    # the same effect query with the (biased!) static adjustment.
    _maybe_estimate_longitudinal(
        program, identification_output, contract,
        random_state=random_state, ci_bootstrap=ci_bootstrap,
        cluster=cluster,
    )

    _estimate_effect_queries(
        program, identification_output, contract,
        random_state=random_state, ci_bootstrap=ci_bootstrap, model=model,
        cluster=cluster, ate_estimator=ate_estimator,
        reference_data=reference_data,
        misclassification=misclassification,
        measurement_error=measurement_error,
    )

    # Numeric end for the counterfactual rung: evaluate an ID*/IDC*-identified
    # counterfactual conjunction P(γ) / P(γ|δ) on data by the same
    # non-parametric plug-in. Purely additive — attaches a numeric_estimate
    # only when the conjunction is identifiable and the data support it.
    _estimate_ctf_conjunction_queries(
        program, identification_output, contract,
        random_state=random_state, ci_bootstrap=ci_bootstrap, cluster=cluster,
    )

    # Numeric end for the proximal rung: recover the ATE under an unobserved
    # confounder via Miao formula (5). Purely additive — attaches a
    # numeric_estimate only when proximal-identifiable and the data support it.
    _estimate_proximal_queries(
        program, identification_output, contract,
        random_state=random_state, ci_bootstrap=ci_bootstrap, cluster=cluster,
    )

    # Numeric end for the attribution rung: recover PN/PS/PNS (Tian-Pearl) from
    # the empirical joint + g-formula do-risks. Purely additive — attaches a
    # numeric_estimate only when the quantities are point-identified (monotone)
    # and the do-risks are back-door / experimentally available.
    _estimate_causation_queries(
        program, identification_output, contract,
        random_state=random_state, ci_bootstrap=ci_bootstrap, cluster=cluster,
    )

    # Numeric end for the single binary counterfactual cell — the same
    # consistency identity the theta path solves, on empirical inputs, plus a
    # bootstrap the theta path cannot express. Purely additive: on any refusal
    # the structural (theta) answer stays primary.
    _estimate_counterfactual_cell_queries(
        program, identification_output, contract,
        random_state=random_state, ci_bootstrap=ci_bootstrap, cluster=cluster,
    )

    # Numeric end for the deterministic-counterfactual rung: fit a recursive
    # linear SCM from the DataFrame (per-node OLS) and compute the queried
    # unit's counterfactual value under the intervention. Purely additive —
    # attaches a number only when the mechanisms are fittable and the unit is
    # fully observed; the coefficient-declared structural path stays primary.
    _estimate_scm_counterfactual_queries(
        program, identification_output, contract,
        random_state=random_state, ci_bootstrap=ci_bootstrap, cluster=cluster,
    )

    # Numeric end for the partial-identification layer: when point ID failed
    # and the kernel attached SYMBOLIC bounds_results, evaluate them on data.
    # Runs after the point-estimate loop so it only ever ADDS numeric fields
    # to already-symbolic bounds_results — never competes with a point.
    _attach_numeric_bounds(
        program, identification_output, contract,
        random_state=random_state, ci_bootstrap=ci_bootstrap, cluster=cluster,
    )

    # Pre-flight data diagnostic (borrow-list #3): reconcile each variable's
    # declared measurement type (scale / domain) against the supplied
    # column. Runs last so the reconciliation gap joins any data_gap_report
    # the estimators already attached. Uses the ORIGINAL data (not the
    # coerced contract) so integer discreteness survives.
    _attach_type_reconciliation(program, identification_output, data)

    return identification_output


def _maybe_estimate_longitudinal(
    program: dict | str | bytes,
    output: dict,
    contract: DataContract,
    *,
    random_state: int,
    ci_bootstrap: int,
    cluster: str | None = None,
) -> None:
    """Attach a longitudinal g-formula ``numeric_estimate`` block when the
    program carries an ``options.longitudinal`` spec.

    Spec shape (kernel_ast.schema.json options.longitudinal)::

        {"treatments": ["A0", "A1"],
         "confounders_by_time": [["L0"], ["L1"]],
         "outcome": "Y",
         "strategy_treated": 1, "strategy_control": 0,
         "n_sim": 10000, "ci_bootstrap": 200}

    The block is attached to the FIRST effect-query result (so the
    structural derivation context is preserved), or — when the program
    declares no effect query — to the first result. Status is left
    untouched (mirrors the mediation path: the numeric block is
    supplementary; the structural answer remains primary). Failures
    (overlap_insufficient / malformed spec) surface as
    ``estimator_failure`` rather than silently dropping.
    """
    ast = _ensure_dict(program)
    options = ast.get("options") or {}
    spec = options.get("longitudinal")
    if not isinstance(spec, dict):
        return

    treatments = spec.get("treatments")
    confounders_by_time = spec.get("confounders_by_time")
    outcome = spec.get("outcome")
    if not (treatments and confounders_by_time and outcome):
        return

    target = _longitudinal_target_result(output)
    if target is None:
        return

    # Honest gate: if the structural pass found the strategy effect is NOT
    # g-formula-identified (an unblocked back-door from some A_k to Y —
    # unmeasured / mis-declared time-varying confounding), the estimator's
    # number would be biased. Refuse it (mirrors missing-data recovery's
    # not_recoverable), attaching an estimator_failure instead of shipping a
    # number the structure doesn't support.
    ident = (target.get("extensions") or {}).get(blocks.Block.LONGITUDINAL_IDENTIFICATION)
    if isinstance(ident, dict) and ident.get("identified") is False:
        target["estimator_failure"] = refusals.block(
            estimator=(
                "longitudinal_ipw_msm"
                if spec.get("estimator") == "ipw_msm"
                else "longitudinal_gformula"
            ),
            failure_type=Refusal.NOT_IDENTIFIED,
        )
        return

    from .longitudinal import (
        LongitudinalGFormulaEstimate,
        LongitudinalIPWMSMEstimate,
        estimate_longitudinal_gformula,
        estimate_longitudinal_ipw_msm,
    )

    estimator = spec.get("estimator", "gformula")
    if estimator not in ("gformula", "ipw_msm"):
        target["estimator_failure"] = refusals.block(
            estimator="longitudinal",
            failure_type=Refusal.UNKNOWN_OPTION,
            details={"option": "options.longitudinal.estimator",
                     "given": estimator,
                     "known": ["gformula", "ipw_msm"]},
        )
        return
    method_name = (
        "longitudinal_gformula" if estimator == "gformula"
        else "longitudinal_ipw_msm"
    )

    kwargs = {
        "treatments": tuple(treatments),
        "confounders_by_time": tuple(tuple(b) for b in confounders_by_time),
        "outcome": outcome,
        "random_state": random_state,
        "ci_bootstrap": int(spec.get("ci_bootstrap", ci_bootstrap)),
        "cluster": cluster,
    }
    if "strategy_treated" in spec:
        kwargs["strategy_treated"] = spec["strategy_treated"]
    if "strategy_control" in spec:
        kwargs["strategy_control"] = spec["strategy_control"]
    if estimator == "gformula" and "n_sim" in spec:
        kwargs["n_sim"] = int(spec["n_sim"])
    if estimator == "ipw_msm" and "stabilized" in spec:
        kwargs["stabilized"] = bool(spec["stabilized"])

    est: LongitudinalGFormulaEstimate | LongitudinalIPWMSMEstimate
    try:
        if estimator == "gformula":
            est = estimate_longitudinal_gformula(contract.data, **kwargs)
        else:
            est = estimate_longitudinal_ipw_msm(contract.data, **kwargs)
    except EstimatorFailure as exc:
        # The species the estimator raised, not a re-spelling of it. This
        # used to collapse anything outside two names to 'unknown', which
        # is how a caller was told "we don't know why" about a refusal
        # that knew exactly why.
        refusals.record(target, estimator=method_name, exc=exc)
        return
    except (ValueError, KeyError) as exc:
        target["estimator_failure"] = refusals.block(
            estimator=method_name,
            failure_type=Refusal.UNKNOWN,
            recorded={"diagnostic": str(exc)},
        )
        return

    numeric_estimate: dict[str, object] = {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": est.method,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "treatment": ",".join(est.treatments),
        "outcome": est.outcome,
    }
    # Which estimate this is, asked of the estimate. ``estimator`` decided
    # which one to call, but the block below is a claim about what the
    # object in hand actually carries.
    if isinstance(est, LongitudinalGFormulaEstimate):
        numeric_estimate["longitudinal_gformula"] = {
            "point": est.point,
            "ci_lower": est.ci_lower,
            "ci_upper": est.ci_upper,
            "treatments": list(est.treatments),
            "confounders_by_time": [list(b) for b in est.confounders_by_time],
            "outcome": est.outcome,
            "strategy_treated": est.strategy_treated,
            "strategy_control": est.strategy_control,
            "e_y_treated": est.e_y_treated,
            "e_y_control": est.e_y_control,
            "n_sim": est.n_sim,
        }
    else:
        numeric_estimate["longitudinal_ipw_msm"] = {
            "point": est.point,
            "ci_lower": est.ci_lower,
            "ci_upper": est.ci_upper,
            "treatments": list(est.treatments),
            "confounders_by_time": [list(b) for b in est.confounders_by_time],
            "outcome": est.outcome,
            "strategy_treated": est.strategy_treated,
            "strategy_control": est.strategy_control,
            "e_y_treated": est.e_y_treated,
            "e_y_control": est.e_y_control,
            "stabilized": est.stabilized,
            "msm_coefficients": list(est.msm_coefficients),
            "weight_mean": est.weight_mean,
            "weight_max": est.weight_max,
        }
    target["numeric_estimate"] = numeric_estimate
    # Stamp what the estimator REPORTS having resampled over, not what the
    # caller asked for — the claim and the fact then cannot drift apart.
    _attach_bootstrap_meta(target["numeric_estimate"], est.cluster, est.draws)
    _attach_precision_budget(target["numeric_estimate"])
    _attach_mechanism_audit(target, est, target=est.outcome)
    # Flip to numerically_solved, preserving the g-formula structural
    # derivation (identify_via_gformula) the scheduler attached — the same
    # pattern transport uses (structural identify terminal + numeric value).
    # The verifier accepts that terminal for a longitudinal-numeric result
    # and additionally re-derives the number via verify_longitudinal_numeric.
    _finalise_numeric_result(target)


def _longitudinal_target_result(output: dict):
    """The result carrying the g-formula structural identification (the
    scheduler attaches ``extensions.longitudinal_identification`` to the
    longitudinal strategy query), else the first effect-query result, else
    the first result, else None."""
    results = output.get("results", [])
    for result in results:
        if (result.get("extensions") or {}).get(blocks.Block.LONGITUDINAL_IDENTIFICATION):
            return result
    for result in results:
        if result.get("query_kind") == "effect":
            return result
    return results[0] if results else None


def _declares_missingness(program: dict | str | bytes) -> bool:
    """True iff the program declares ≥1 ``missingness_indicator`` statement."""
    ast = _ensure_dict(program)
    return any(
        isinstance(s, dict) and s.get("kind") == "missingness_indicator"
        for s in ast.get("statements", [])
    )


def _effect_treatment_outcome(
    program: dict | str | bytes, query_id: str | None,
) -> tuple[str | None, str | None]:
    """Treatment / outcome predicates of the effect query with ``query_id``."""
    ast = _ensure_dict(program)
    for s in ast.get("statements", []):
        if not isinstance(s, dict) or s.get("kind") != "query":
            continue
        if query_id is not None and s.get("id") != query_id:
            continue
        q = s.get("query") or {}
        if q.get("kind") == "effect":
            try:
                return (
                    q["intervention"]["atom"]["predicate"],
                    q["target"]["atom"]["predicate"],
                )
            except (KeyError, TypeError):
                return None, None
    return None, None


def _maybe_estimate_missing_recovery(
    program: dict | str | bytes,
    output: dict,
    data: Any,
    *,
    random_state: int,
    ci_bootstrap: int,
    cluster: str | None,
) -> None:
    """Attach the §S9.2 recovered-ATE numeric block (or a refusal).

    Reads the ``missing_data_recovery`` identification block already on the
    result: if its ``estimand`` is NOT recoverable, attaches a
    ``not_recoverable`` ``estimator_failure`` (the kernel refuses to invent
    a number identification says can't be recovered). If it IS recoverable,
    calls ``estimate_recovered_ate`` with the identified back-door set and
    attaches a ``recovered_ate`` numeric block — the conditional from
    complete cases per factor, P(Z) from its own, so the estimate is
    unbiased under MAR where naive listwise deletion is not.
    """
    from .missing_recovery import estimate_recovered_ate

    target = None
    block = None
    for result in output.get("results", []):
        ext = result.get("extensions") or {}
        if blocks.Block.MISSING_DATA_RECOVERY in ext:
            target = result
            block = ext[blocks.Block.MISSING_DATA_RECOVERY]
            break
    if target is None or block is None:
        return

    estimand = block.get("estimand") or {}
    if not estimand.get("recoverable", False):
        x, y = _effect_treatment_outcome(program, target.get("query_id"))
        target["estimator_failure"] = refusals.block(
            estimator="missing_data_recovery",
            failure_type=Refusal.NOT_RECOVERABLE,
            details={
                "estimand": (f"P({y}|do({x}))" if x and y
                             else estimand.get("target")),
                "mechanism": refusals.Recovery.FROM_MISSINGNESS,
            },
            # The identification layer's own note, which is prose written
            # one layer down and has a reader of its own on the block.
            recorded={"identification_reason": estimand.get("failure_reason")},
        )
        return

    treatment, outcome = _effect_treatment_outcome(
        program, target.get("query_id")
    )
    if treatment is None or outcome is None:
        return
    adjustment = tuple(block.get("adjustment_set") or [])

    try:
        est = estimate_recovered_ate(
            data, treatment=treatment, outcome=outcome, adjustment=adjustment,
            random_state=random_state, ci_bootstrap=ci_bootstrap,
            cluster=cluster,
        )
    except EstimatorFailure as exc:
        refusals.record(target, estimator="missing_data_recovery", exc=exc)
        return
    except (ValueError, KeyError) as exc:
        target["estimator_failure"] = refusals.block(
            estimator="missing_data_recovery",
            failure_type=Refusal.UNKNOWN,
            recorded={"diagnostic": str(exc)},
        )
        return

    numeric_estimate = {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": est.method,
        "assumptions": list(est.assumptions),
        "sample_size": est.n_total,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "treatment": est.treatment,
        "outcome": est.outcome,
        "adjustment": list(est.adjustment),
        "recovered_ate": {
            "point": est.point,
            "ci_lower": est.ci_lower,
            "ci_upper": est.ci_upper,
            "naive_listwise_ate": est.naive_listwise_ate,
            "adjustment": list(est.adjustment),
            "n_total": est.n_total,
            "n_complete_case": est.n_complete_case,
            "n_conditional_rows": est.n_conditional_rows,
            "n_marginal_rows": est.n_marginal_rows,
            "n_strata": est.n_strata,
            "missing_columns": list(est.missing_columns),
            # Per-stratum sufficient statistics for the numeric verifier:
            # verify_missing_data_numeric re-derives the recovered (and naive)
            # ATE from these counts + marginal tables independently.
            "sufficient_statistics": est.sufficient_statistics,
        },
    }
    target["numeric_estimate"] = numeric_estimate
    _attach_bootstrap_meta(target["numeric_estimate"], est.cluster, est.draws)
    _attach_precision_budget(target["numeric_estimate"])
    _attach_mechanism_audit(target, est, target=est.outcome)
    # This path returns before the shared prologue builds a data contract —
    # the columns it recovers from carry NaN, which the contract forbids —
    # and so returns before everything the prologue records. The contract
    # is genuinely out of reach; the run's own settings and what the
    # estimator hashed are not, and a reader who cannot see them cannot
    # tell a recovered ATE apart from one estimated on different rows with
    # a different seed. Written from the estimate rather than from a
    # contract, which is the only difference from the ordinary path.
    target.setdefault("estimation_context", {}).update({
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "sample_size": est.n_total,
        "random_state": random_state,
        "ci_bootstrap": ci_bootstrap,
    })
    _finalise_numeric_result(target)


def _resolve_cluster_option(
    program: dict | str | bytes, cluster: str | None,
) -> str | None:
    """Resolve the cluster column from the explicit kwarg (precedence)
    or the program AST's ``options.cluster``. Returns None when neither
    is set."""
    if cluster is not None:
        return cluster
    ast = _ensure_dict(program)
    options = ast.get("options")
    if isinstance(options, dict):
        opt_cluster = options.get("cluster")
        if isinstance(opt_cluster, str) and opt_cluster:
            return opt_cluster
    return None


_ATE_ESTIMATORS = frozenset({"gformula", "ipw", "aipw", "tmle"})


def _resolve_ate_estimator_option(
    program: dict | str | bytes, ate_estimator: str,
) -> str:
    """Resolve the backdoor ATE estimator from the explicit kwarg
    (precedence) or the program AST's ``options.ate_estimator``. Defaults
    to ``"gformula"``. Raises on an unknown value rather than silently
    falling back — a caller who asked for ``"aipw"`` and typo'd should be
    told, not handed the (different) g-formula number."""
    if ate_estimator != "gformula":
        if ate_estimator not in _ATE_ESTIMATORS:
            raise ValueError(
                f"ate_estimator must be one of {sorted(_ATE_ESTIMATORS)}; "
                f"got {ate_estimator!r}"
            )
        return ate_estimator
    ast = _ensure_dict(program)
    options = ast.get("options")
    if isinstance(options, dict):
        opt = options.get("ate_estimator")
        if isinstance(opt, str) and opt:
            if opt not in _ATE_ESTIMATORS:
                raise ValueError(
                    f"options.ate_estimator must be one of "
                    f"{sorted(_ATE_ESTIMATORS)}; got {opt!r}"
                )
            return opt
    return "gformula"


def _already_answered(result: dict) -> bool:
    """Whether an earlier estimation pass has already claimed this result.

    Phase 7.L: a longitudinal g-formula estimate runs before the cascade
    and attaches its number to the first effect query. The cross-sectional
    back-door ATE must NOT overwrite it — that static adjustment is exactly
    the biased estimator the g-formula exists to replace when a confounder
    is affected by past treatment.

    The test is a method-name residue rather than a declaration, which is
    the weakness slice 0 recorded: rename the method and the routing
    changes in silence. It stays a residue here on purpose. Making the
    longitudinal pass declare its claim is a behaviour question (what
    should happen when that pass refuses on identification grounds and
    leaves no method behind at all), not a table question, so it is logged
    rather than smuggled into a refactor. What the table does fix is that
    this is now visibly the DRIVER's business — no strategy guard reads it,
    because no strategy guard can see the result at all.
    """
    return (result.get("numeric_estimate") or {}).get("method") in (
        "longitudinal_gformula", "longitudinal_ipw_msm",
    )


def _estimate_effect_queries(
    program: dict | str | bytes,
    output: dict,
    contract: DataContract,
    *,
    random_state: int,
    ci_bootstrap: int,
    model: str,
    cluster: str | None = None,
    ate_estimator: str = "gformula",
    reference_data: Any = None,
    misclassification: dict | None = None,
    measurement_error: dict | None = None,
) -> list[Evaluation]:
    """Offer every effect query to the strategy table. Mutates ``output``.

    The routing itself lives in ``_EFFECT_STRATEGIES`` below; this function
    only assembles what a strategy is allowed to see. Returning the list of
    :class:`Evaluation` is additive — callers that ignore it are unchanged —
    and it is what turns "the cascade declined" from a control-flow event
    into an object that can be inspected, reported, and asserted on.
    """
    # Re-derive the graph + bidirected set once for the whole program;
    # results rely on the same structural facts the kernel already used.
    from ..input.semantic_validator import validate_program
    from ..input.syntactic_validator import validate_ast
    from ..runtime.graph_projection import project
    from ..runtime.instantiation import instantiate
    from ..runtime import structural_solver

    ast = _ensure_dict(program)
    ast = validate_ast(ast)
    prog = validate_program(ast)
    ground_statements = instantiate(prog)
    graph = project(ground_statements)
    bidirected = structural_solver.bidirected_from_ground(ground_statements)
    feedback = structural_solver.feedback_from_ground(ground_statements)

    dose_response_query_ids, dose_response_warnings = _dose_response_routing_plan(prog)
    _append_data_contract_warnings(output, dose_response_warnings)

    # Selection-bias recovery (§S9.1 numeric end): the value that defines
    # "selected" for each ObservationStatement, so the recovery estimator can
    # restrict the biased sample to S = selected.
    selection_values = _collect_selection_observation_values(prog)

    knobs = EffectKnobs(
        random_state=random_state,
        ci_bootstrap=ci_bootstrap,
        model=model,
        cluster=cluster,
        reference_data=reference_data,
        selection_values=selection_values,
        program=program,
    )

    evaluations: list[Evaluation] = []
    for q_stmt, result in _pair_effect_queries(prog, output):
        if q_stmt is None or _already_answered(result):
            continue
        facts = EffectFacts(
            q_stmt=q_stmt,
            graph=graph,
            bidirected=bidirected,
            feedback=feedback,
            prog=prog,
            contract=contract,
            ate_estimator=ate_estimator,
            misclassification=misclassification,
            measurement_error=measurement_error,
            # The identification layer's conclusion, snapshotted before any
            # strategy runs: §S9.1 attaches this block when the sample is
            # restricted on a selection collider. Nothing in the estimation
            # layer writes it, so reading it here is reading upstream, not
            # reading our own output.
            selection_recovery=(
                (result.get("extensions") or {}).get(blocks.Block.SELECTION_RECOVERY)
            ),
            dose_response_triggered=q_stmt.id in dose_response_query_ids,
        )
        evaluations.append(run_cascade(
            _EFFECT_STRATEGIES, facts, result, knobs, query_id=q_stmt.id,
        ))
    return evaluations


class _SpecIsNotAMapping(EstimatorFailure):
    """What the caller filed under a variable's name is not a spec at all.

    A class of its own rather than a bare :class:`EstimatorFailure` so that
    the row recording it catches exactly what :func:`_guarded_spec` raises.
    Any other refusal reaching that ``except`` would mean some handler's own
    plumbing has a hole, and filing it under "your spec is malformed" would
    put a confident wrong sentence on the envelope.
    """


def _guarded_spec(spec: object) -> dict:
    """A caller spec whose presence this row's route guard already decided.

    Four rows of the table below hand a measurement spec straight to their
    handler, and each is reached only through a guard that tested the very
    same :class:`EffectFacts` attribute for ``is not None``. The absent case
    is therefore not a case — but the guard lives in ``themis.routing``, so
    nothing in the run's own text said so, and the handler that receives it
    quite reasonably declares it is given a spec rather than a maybe-spec.

    Saying it here is what keeps the two halves of one decision from being
    edited apart: a guard loosened without its run is not a spec that
    quietly becomes ``None`` downstream, it is a raise naming the row.

    Presence is the only half of that contract a route guard can decide.
    The other half — that the value is a mapping of settings at all — was
    nobody's: ``EffectFacts`` annotates these attributes ``dict | None`` on
    the strength of a dict the caller handed in and no one read, which is
    why the parameter here is ``object``. ``dict`` is the claim this
    function exists to make true, not one it may assume. A caller who wrote
    ``measurement_error={"y": 0}`` has named a variable and then not
    described it, and that is a request to correct rather than an invariant
    to trust — so it leaves as a refusal saying so, not as whatever
    ``AttributeError`` the first ``.get`` in some handler happens to raise.
    """
    if spec is None:
        raise AssertionError(
            "a measurement-spec strategy ran without the spec its route "
            "guard tests for; the guard and the run read the same attribute, "
            "so they cannot disagree unless one of them was edited alone"
        )
    if not isinstance(spec, dict):
        raise _SpecIsNotAMapping(
            Refusal.MALFORMED_ARGUMENT,
            argument="a measurement spec",
            shape="{error_variance: …, confusion_matrix: …, study: …}",
            given=spec,
        )
    return spec


def _spec_row(
    estimator: str,
    run: Callable[[EffectFacts, dict, EffectKnobs], Claim],
) -> Callable[[EffectFacts, dict, EffectKnobs], Claim]:
    """One measurement-spec row, with a malformed spec recorded as a refusal.

    :func:`_guarded_spec` speaks for all four rows, but it is evaluated
    inside the handler's own argument list — before the handler exists to
    catch anything, and somewhere a ``return`` cannot say "this row is
    done". Those are the two things only the row knows: whose name the
    refusal carries, and that a refused spec ends the query here instead of
    leaving by the exception door the caller cannot read.
    """
    def row(f: EffectFacts, r: dict, k: EffectKnobs) -> Claim:
        try:
            return run(f, r, k)
        except _SpecIsNotAMapping as exc:
            refusals.record(r, estimator=estimator, exc=exc)
            return blocked('estimator_refused')
    return row


# ---------------------------------------------------------------------------
# The numeric end of every route that declares one.
#
# When a strategy applies, and how early, is not decided here — it is read
# from ``themis.routing``, the one table the identification layer reads too.
# What a row adds is what only this layer knows: whether the number competes
# for the query or comments beside it, what the number is an estimate OF, and
# the call that produces it.
#
# Guards see :class:`EffectFacts` and nothing else, so a row cannot branch on
# how far the cascade has already got.
# ---------------------------------------------------------------------------

_EFFECT_STRATEGIES = check_table((
    Strategy(
        # #450. First, because the loop is not a competing strategy but the
        # statement that the strategies below answer a question this model
        # does not pose. The estimand it produces says so.
        route=route("feedback_loop"),
        role=Role.CLAIM,
        produces=Estimand.STRUCTURAL_COEFFICIENT,
        run=lambda f, r, k: _try_iv_estimate(f, r, k, feedback=True),
    ),
    Strategy(
        route=route("joint_intervention"),
        role=Role.CLAIM,
        produces=Estimand.JOINT_CONTRAST,
        run=lambda f, r, k: _try_joint_estimate(
            f.q_stmt, r, f.contract, f.graph, f.bidirected,
            joint_sets=f.joint_adjustment_sets,
            vector_iv_candidates=f.vector_iv_candidates,
            vector_instruments=f.vector_instruments,
            random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
            model=k.model, cluster=k.cluster,
        ),
    ),
    Strategy(
        # The identification result stays structurally_solved; this adds the
        # number by post-stratification onto the declared target population.
        route=route("transport"),
        role=Role.CLAIM,
        produces=Estimand.TRANSPORTED_EFFECT,
        run=lambda f, r, k: _try_transport_estimate(
            f.q_stmt, r, f.contract, k.program,
            random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
            ci_level=0.95, cluster=k.cluster,
        ),
    ),
    Strategy(
        route=route("mediation_joint"),
        role=Role.CLAIM,
        produces=Estimand.DECOMPOSITION,
        run=lambda f, r, k: _try_mediation_joint_estimate(
            f.q_stmt, r, f.contract, f.graph, f.bidirected,
            random_state=k.random_state,
        ),
    ),
    Strategy(
        # Phase 7.4: single-mediator natural effects (Imai via statsmodels),
        # gated inside the handler on the identification layer's strategy
        # result — an absent decomposition block means identification did not
        # choose mediation for this query.
        route=route("mediation_single"),
        role=Role.CLAIM,
        produces=Estimand.DECOMPOSITION,
        run=lambda f, r, k: _try_mediation_estimate(
            f.q_stmt, r, f.contract, f.graph, f.bidirected,
            random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
            cluster=k.cluster,
        ),
    ),
    Strategy(
        # Either recovers the number from the biased sample plus external
        # reference data, or refuses while naming the external data needed —
        # and either way the query never reaches back-door.
        route=route("selection_recovery"),
        role=Role.CLAIM,
        produces=Estimand.QUERY_EFFECT,
        run=lambda f, r, k: _try_selection_recovery_estimate(
            f.q_stmt, r, f.contract, k.reference_data, k.selection_values,
            random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
            cluster=k.cluster,
        ),
    ),
    Strategy(
        route=route("measurement_correction_both_channels"),
        role=Role.CLAIM,
        produces=Estimand.QUERY_EFFECT,
        run=_spec_row(
            "combined_measurement_error_correction",
            lambda f, r, k: _try_combined_measurement_correction_estimate(
                f.q_stmt, r, f.contract, f.graph,
                adjustment_sets=f.adjustment_sets,
                front_door_sets=f.front_door_sets,
                iv_candidates=f.iv_candidates, given=f.given_atoms,
                spec_x=_guarded_spec(f.misclassification_exposure),
                spec_y=_guarded_spec(f.misclassification_outcome),
                random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
                cluster=k.cluster,
            ),
        ),
    ),
    Strategy(
        # The spec is a load-bearing external input (a validation study);
        # ordinary programs never reach this row. A refusal records an
        # estimator_failure rather than silently falling back to the biased
        # naive point — the caller explicitly asked for the corrected number.
        route=route("measurement_correction_outcome"),
        role=Role.CLAIM,
        produces=Estimand.QUERY_EFFECT,
        run=_spec_row(
            "measurement_error_correction",
            lambda f, r, k: _try_measurement_correction_estimate(
                f.q_stmt, r, f.contract, f.graph,
                adjustment_sets=f.adjustment_sets,
                front_door_sets=f.front_door_sets,
                iv_candidates=f.iv_candidates, given=f.given_atoms,
                spec=_guarded_spec(f.misclassification_outcome),
                random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
                cluster=k.cluster,
            ),
        ),
    ),
    Strategy(
        route=route("measurement_correction_exposure"),
        role=Role.CLAIM,
        produces=Estimand.QUERY_EFFECT,
        run=_spec_row(
            "exposure_measurement_error_correction",
            lambda f, r, k: _try_exposure_measurement_correction_estimate(
                f.q_stmt, r, f.contract, f.graph,
                adjustment_sets=f.adjustment_sets,
                front_door_sets=f.front_door_sets,
                iv_candidates=f.iv_candidates, given=f.given_atoms,
                spec=_guarded_spec(f.misclassification_exposure),
                random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
                cluster=k.cluster,
            ),
        ),
    ),
    Strategy(
        # This does NOT claim the query: the point still comes from the
        # ordinary routing below, including the exposure-side correction when
        # a spec names the exposure too. Only a spec the channel or the data
        # refuse stops the query.
        route=route("outcome_error_declaration"),
        role=Role.ANNOTATE,
        produces=Estimand.NONE,
        run=_spec_row(
            "outcome_measurement_error",
            lambda f, r, k: _try_outcome_error_declaration(
                r, f.contract, f.graph,
                x_atom=f.x_atom, y_atom=f.y_atom,
                # The same three facts the estimator rows below route on, so
                # the design judged here is the design that answers.
                adjustment_sets=f.adjustment_sets,
                front_door_sets=f.front_door_sets,
                iv_candidates=f.iv_candidates,
                spec=_guarded_spec(f.measurement_error_outcome),
            ),
        ),
    ),
    Strategy(
        # The other half, past the ladder: what the declared σ²_v costs the
        # answer that was produced. Same guard and same facts as the row
        # above — what differs is that β̂ exists by the time this one runs.
        route=route("outcome_error_precision_cost"),
        role=Role.ANNOTATE,
        produces=Estimand.NONE,
        run=_spec_row(
            "outcome_measurement_error",
            lambda f, r, k: _try_outcome_error_price(
                r, f.contract, f.graph,
                x_atom=f.x_atom, y_atom=f.y_atom,
                adjustment_sets=f.adjustment_sets,
                front_door_sets=f.front_door_sets,
                iv_candidates=f.iv_candidates,
                spec=_guarded_spec(f.measurement_error_outcome),
            ),
        ),
    ),
    Strategy(
        # The other error structure, past the ladder. ANNOTATE and not
        # CLAIM, and the role carries the finding: under Berkson error the
        # answer this rides beside is the causal slope already, so there is
        # nothing here to compete for. What it adds is the price.
        route=route("berkson_error_price"),
        role=Role.ANNOTATE,
        produces=Estimand.NONE,
        run=_spec_row(
            "berkson_error",
            lambda f, r, k: _try_berkson_error_price(
                r, f.contract, f.graph,
                x_atom=f.x_atom, y_atom=f.y_atom,
                adjustment_sets=f.adjustment_sets,
                front_door_sets=f.front_door_sets,
                iv_candidates=f.iv_candidates,
                spec=_guarded_spec(f.measurement_error_exposure),
            ),
        ),
    ),
    Strategy(
        # The other channel's version of the row below it, and it comes first
        # for the same reason: the outcome-error rows price a declaration
        # whose premise is that the error moves no conditional mean, and a
        # declared δ is that premise withdrawn. Answering there and pricing
        # here would ship the naive number with a caveat attached.
        route=route("differential_outcome_error"),
        role=Role.CLAIM,
        produces=Estimand.QUERY_EFFECT,
        run=lambda f, r, k: _try_differential_outcome_error_estimate(
            f.q_stmt, r, f.contract, f.graph,
            adjustment_sets=f.adjustment_sets,
            front_door_sets=f.front_door_sets,
            iv_candidates=f.iv_candidates, given=f.given_atoms,
            spec=_guarded_spec(f.measurement_error_outcome),
            differential_coefficient=f.outcome_error_differential,
            random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
            cluster=k.cluster,
        ),
    ),
    Strategy(
        # The same declared σ²_u with the non-differential premise withdrawn.
        # Ahead of both rows below because neither of them can be right when
        # it is: an error that tracks the outcome inflates the covariance as
        # well as the variance, and correcting only the second is what makes
        # a differential error bias away from the null.
        route=route("differential_error"),
        role=Role.CLAIM,
        produces=Estimand.QUERY_EFFECT,
        run=lambda f, r, k: _try_differential_error_estimate(
            f.q_stmt, r, f.contract, f.graph,
            adjustment_sets=f.adjustment_sets,
            front_door_sets=f.front_door_sets,
            iv_candidates=f.iv_candidates, given=f.given_atoms,
            spec=_guarded_spec(f.measurement_error_exposure),
            covariate_specs=f.measurement_error_covariates,
            differential_coefficient=f.exposure_error_differential,
            random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
            cluster=k.cluster,
        ),
    ),
    Strategy(
        # The same declared σ²_u on a declared NONLINEAR outcome model,
        # where the moment correction below is not an approximation of the
        # answer but an answer to another question. Ahead of it for that
        # reason, and reachable only on a declaration, never on a guess.
        route=route("simex"),
        role=Role.CLAIM,
        produces=Estimand.QUERY_EFFECT,
        run=lambda f, r, k: _try_simex_estimate(
            f.q_stmt, r, f.contract, f.graph,
            adjustment_sets=f.adjustment_sets,
            front_door_sets=f.front_door_sets,
            iv_candidates=f.iv_candidates, given=f.given_atoms,
            spec=_guarded_spec(f.measurement_error_exposure),
            covariate_specs=f.measurement_error_covariates,
            outcome_model=f.simex_outcome_model,
            random_state=k.random_state, cluster=k.cluster,
        ),
    ),
    Strategy(
        # De-attenuate by the RC moment correction instead of shipping the
        # biased naive slope. A continuous OUTCOME error is deferred; the
        # handler refuses such a spec honestly rather than ignoring it.
        route=route("regression_calibration"),
        role=Role.CLAIM,
        produces=Estimand.QUERY_EFFECT,
        run=lambda f, r, k: _try_regression_calibration_estimate(
            f.q_stmt, r, f.contract, f.graph,
            adjustment_sets=f.adjustment_sets,
            front_door_sets=f.front_door_sets,
            iv_candidates=f.iv_candidates, given=f.given_atoms,
            error_map=f.measurement_error_map,
            random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
            cluster=k.cluster,
        ),
    ),
    Strategy(
        route=route("dose_response_binary_fallback"),
        role=Role.ANNOTATE,
        produces=Estimand.NONE,
        run=lambda f, r, k: _try_dose_response_binary_fallback(f, r, k),
    ),
    Strategy(
        # Other strategies (front-door / IV / mediation) keep their
        # binary-effect path until a real case demands the curve there.
        route=route("dose_response_curve"),
        role=Role.CLAIM,
        produces=Estimand.DOSE_RESPONSE,
        run=lambda f, r, k: _try_dose_response_estimate(
            result=r,
            contract=f.contract,
            treatment=f.x_atom.predicate,
            outcome=f.y_atom.predicate,
            adjustment=f.adjustment_names,
            sampling_points=_resolve_dose_response_points(f.prog, f.x_atom),
            random_state=k.random_state,
            model=_resolve_dose_response_model(k.model),
            graph=f.graph, x=f.x_atom, y=f.y_atom,
            chosen=f.chosen_adjustment, given=f.given_atoms,
            cluster=k.cluster,
        ),
    ),
    Strategy(
        # The default leaves this row untaken and every existing result
        # byte-identical.
        route=route("doubly_robust"),
        role=Role.CLAIM,
        produces=Estimand.QUERY_EFFECT,
        run=lambda f, r, k: _try_doubly_robust_estimate(
            result=r, contract=f.contract,
            graph=f.graph, x=f.x_atom, y=f.y_atom,
            adjustment=f.chosen_adjustment,
            adjustment_names=f.adjustment_names,
            given=frozenset(f.given_atoms),
            estimator=f.ate_estimator,
            random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
            model=k.model, cluster=k.cluster,
        ),
    ),
    Strategy(
        route=route("backdoor"),
        role=Role.CLAIM,
        produces=Estimand.QUERY_EFFECT,
        run=lambda f, r, k: _try_backdoor_estimate(f, r, k),
    ),
    Strategy(
        route=route("frontdoor"),
        role=Role.CLAIM,
        produces=Estimand.QUERY_EFFECT,
        run=lambda f, r, k: _try_frontdoor_estimate(f, r, k),
    ),
    Strategy(
        route=route("general_id"),
        role=Role.CLAIM,
        produces=Estimand.QUERY_EFFECT,
        # The escalation this row's rank exists to guard: when do(X) is NOT
        # non-parametrically identified there is no assumption-free number to
        # be had, and the IV rows answer under monotonicity / effect
        # homogeneity instead — a complier contrast, not the population effect
        # the query names. That is a real substitution, taken deliberately and
        # disclosed on the answer (late_caveat, the estimand-fallback
        # warning); declaring it here is what keeps it from being taken by
        # accident somewhere else.
        defers_to=frozenset({"iv_overidentified", "iv_wald"}),
        run=lambda f, r, k: _try_general_id_estimate(
            f.q_stmt, r, f.contract, f.graph, f.bidirected,
            x_atom=f.x_atom, y_atom=f.y_atom, given_atoms=f.given_atoms,
            random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
            cluster=k.cluster,
        ),
    ),
    Strategy(
        # Falls through to the just-identified row when the over-ID design is
        # degenerate.
        route=route("iv_overidentified"),
        role=Role.CLAIM,
        produces=Estimand.COMPLIER_EFFECT,
        run=lambda f, r, k: _try_iv_overid_estimate(
            r, f.contract, f.graph,
            x=f.x_atom, y=f.y_atom,
            instruments=f.overid_instruments,
            conditioning=f.iv_candidates[0].conditioning,
            random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
            cluster=k.cluster,
        ),
    ),
    Strategy(
        route=route("iv_wald"),
        role=Role.CLAIM,
        produces=Estimand.COMPLIER_EFFECT,
        run=lambda f, r, k: _try_iv_estimate(f, r, k),
    ),
), covers=End.ESTIMATION)


def _try_dose_response_binary_fallback(
    facts: EffectFacts, result: dict, knobs: EffectKnobs,
) -> Claim:
    """Record that the curve degenerates here, and let the binary path answer."""
    result["estimator_fallback"] = {
        "from": "dose_response",
        "to": "binary_effect",
        "reason": (
            "处理是二值的；剂量-反应曲线会退化成"
            "两个点之间的对比"
        ),
    }
    _append_result_data_contract_warning(
        result,
        (
            "dose_response_query 退回到了二值效应，因为处理 "
            f"{facts.x_atom.predicate!r} 是二值的"
        ),
    )
    return annotated()


def _try_backdoor_estimate(
    facts: EffectFacts, result: dict, knobs: EffectKnobs,
) -> Claim:
    """Phase 7.1: the g-formula plug-in over the smallest adjustment set."""
    from .backdoor import estimate_backdoor_ate
    from ..output.result_orchestrator import (
        build_assumption_ledger,
    )

    x_atom, y_atom = facts.x_atom, facts.y_atom
    try:
        estimate = estimate_backdoor_ate(
            facts.contract.data,
            treatment=x_atom.predicate,
            outcome=y_atom.predicate,
            adjustment=facts.adjustment_names,
            ci_bootstrap=knobs.ci_bootstrap,
            random_state=knobs.random_state,
            model=knobs.model,  # type: ignore[arg-type]
            cluster=knobs.cluster,
        )
    except EstimatorFailure as exc:
        # The cascade's convention, which this strategy alone did not keep:
        # a refusal is an answer ABOUT the data and reaches a reader through
        # estimator_failure. Unwrapped, back-door's own guards left
        # themis.estimate as a traceback — a treatment column at a single
        # level has escaped the public entry point since that guard was
        # written, because no test went through this door and the sibling
        # door (ipw / aipw / tmle, dispatch.py:6057) does keep it.
        refusals.record(result, estimator="backdoor", exc=exc)
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "point": estimate.point,
        "ci_lower": estimate.ci_lower,
        "ci_upper": estimate.ci_upper,
        "ci_level": estimate.ci_level,
        "method": estimate.method,
        "assumptions": list(estimate.assumptions),
        "sample_size": estimate.sample_size,
        "data_hash": estimate.data_hash,
        "data_columns": list(estimate.data_columns),
        "adjustment": list(estimate.adjustment),
        "treatment": estimate.treatment,
        "outcome": estimate.outcome,
    }
    _attach_bootstrap_meta(result["numeric_estimate"], knobs.cluster, estimate.draws)
    ext = result.setdefault("extensions", {})
    _attach_mechanism_audit(
        result, estimate, target=estimate.outcome,
    )
    ledger = build_assumption_ledger(
        result, 
    )
    if ledger is not None:
        ext[blocks.Block.ASSUMPTION_LEDGER] = ledger
    _attach_precision_budget(result["numeric_estimate"])

    result["derivation"] = _build_numeric_derivation_dict(
        graph=facts.graph,
        x=x_atom, y=y_atom,
        adjustment=facts.chosen_adjustment,
        given=frozenset(facts.given_atoms),
        estimate=estimate,
    )
    _attach_e_value_if_binary(
        result, facts.contract,
        outcome=y_atom.predicate, treatment=x_atom.predicate,
    )
    _attach_ovb_sensitivity(
        result, facts.contract,
        treatment=x_atom.predicate,
        outcome=y_atom.predicate,
        adjustment=facts.adjustment_names,
        method=estimate.method,
    )
    _attach_propensity_overlap_warning(
        result, facts.contract,
        treatment=x_atom.predicate,
        adjustment=facts.adjustment_names,
    )
    _attach_outcome_separation_warning(
        result, facts.contract,
        treatment=x_atom.predicate,
        outcome=y_atom.predicate,
        adjustment=facts.adjustment_names,
    )
    _finalise_numeric_result(result)
    return answered()


def _try_frontdoor_estimate(
    facts: EffectFacts, result: dict, knobs: EffectKnobs,
) -> Claim:
    """Phase 7.2: the front-door formula over the smallest mediator set."""
    import networkx as nx

    from .frontdoor import estimate_frontdoor_ate

    x_atom, y_atom = facts.x_atom, facts.y_atom
    chosen_front = min(facts.front_door_sets, key=len)
    topo_mediators = tuple(
        n for n in nx.topological_sort(facts.graph) if n in chosen_front
    )
    mediator_names = tuple(a.predicate for a in topo_mediators)

    try:
        fd_estimate = estimate_frontdoor_ate(
            facts.contract.data,
            treatment=x_atom.predicate,
            outcome=y_atom.predicate,
            mediators=mediator_names,
            ci_bootstrap=knobs.ci_bootstrap,
            random_state=knobs.random_state,
            model=knobs.model,  # type: ignore[arg-type]
            cluster=knobs.cluster,
        )
    except EstimatorFailure as exc:
        # An arm with no rows in it, an unknown model name — what the
        # estimator checks for itself. A continuous mediator used to arrive
        # here too, and no longer does: it is answered by the estimator's
        # second plug-in rather than refused, which is why the two species
        # that said so are gone from the vocabulary entirely.
        refusals.record(result, estimator="frontdoor", exc=exc)
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "point": fd_estimate.point,
        "ci_lower": fd_estimate.ci_lower,
        "ci_upper": fd_estimate.ci_upper,
        "ci_level": fd_estimate.ci_level,
        "method": fd_estimate.method,
        "assumptions": list(fd_estimate.assumptions),
        "sample_size": fd_estimate.sample_size,
        "data_hash": fd_estimate.data_hash,
        "data_columns": list(fd_estimate.data_columns),
        "mediators": list(fd_estimate.mediators),
        "treatment": fd_estimate.treatment,
        "outcome": fd_estimate.outcome,
    }
    if fd_estimate.sufficient_statistics:
        # Present exactly when the empirical plug-in answered, because it is
        # the only one of the two whose arms are re-derivable at all. Keyed
        # off what the estimate CARRIES rather than off its method name: the
        # name and the statistics are one fact, and a second reading of it
        # here is where a route added later arrives with numbers nothing
        # publishes.
        result["numeric_estimate"]["front_door_empirical"] = dict(
            fd_estimate.sufficient_statistics)
    _attach_bootstrap_meta(result["numeric_estimate"], knobs.cluster, fd_estimate.draws)
    _attach_precision_budget(result["numeric_estimate"])
    _attach_mechanism_audit(result, fd_estimate, target=fd_estimate.outcome)

    result["derivation"] = _build_frontdoor_numeric_derivation_dict(
        graph=facts.graph,
        x=x_atom, y=y_atom,
        mediators=topo_mediators,
        estimate=fd_estimate,
    )
    _attach_e_value_if_binary(
        result, facts.contract,
        outcome=y_atom.predicate, treatment=x_atom.predicate,
    )
    _finalise_numeric_result(result)
    return answered()


def _try_iv_estimate(
    facts: EffectFacts, result: dict, knobs: EffectKnobs, *,
    feedback: bool = False,
) -> Claim:
    """One instrument, one number, whichever row asked for it.

    Phase 7.3 is the just-identified Wald ratio on the smallest candidate.
    #450 reaches the same arithmetic for a different reason: a declared
    loop between the treatment and the outcome makes the treatment
    endogenous by construction, so the instrument is not an escalation
    from a graph where adjustment happened to fail — it is the only route
    there is.

    Written once because the arithmetic IS one arithmetic — Wald,
    stratified where the instrument needs a conditioning set, with the
    Anderson-Rubin region beside it. Two copies would be two places for
    the weak-instrument disclosure and the bootstrap metadata to drift
    apart, and only one of them would get the next fix. Which row is
    calling is declared in the table rather than sniffed here, and the two
    things it decides — which candidate, and what the number is an
    estimate OF — are the two lines below that read ``feedback``.
    """
    from .iv import estimate_iv_ate

    x_atom, y_atom = facts.x_atom, facts.y_atom
    if feedback:
        # Off the two-equation shape, or on it with no instrument, this
        # row does not estimate at all: the identification layer has
        # already said what is missing, and a number here would sit under
        # a query it refused.
        if not facts.iv_candidates_under_the_loop:
            return blocked('design_unavailable')
        chosen_iv = facts.iv_candidates_under_the_loop[0]
    else:
        chosen_iv = facts.iv_candidates[0]  # already sorted by |W| asc
    try:
        iv_estimate = estimate_iv_ate(
            facts.contract.data,
            treatment=x_atom.predicate,
            outcome=y_atom.predicate,
            instrument=chosen_iv.instrument.predicate,
            conditioning=tuple(a.predicate for a in chosen_iv.conditioning),
            ci_bootstrap=knobs.ci_bootstrap,
            random_state=knobs.random_state,
            cluster=knobs.cluster,
        )
    except EstimatorFailure as exc:
        # A dead first stage, a stratum with one instrument arm, a resample
        # that never converged. This block is the only place the reason
        # appears: with it dropped, the query fell back to the
        # identification layer's standing advice — declare monotonicity —
        # which cannot help an instrument that moves nobody.
        refusals.record(result, estimator="iv_wald", exc=exc)
        return blocked('estimator_refused')

    iv_numeric_dict: dict[str, object] = {
        "point": iv_estimate.point,
        "ci_lower": iv_estimate.ci_lower,
        "ci_upper": iv_estimate.ci_upper,
        "ci_level": iv_estimate.ci_level,
        "method": iv_estimate.method,
        "assumptions": list(iv_estimate.assumptions),
        "sample_size": iv_estimate.sample_size,
        "data_hash": iv_estimate.data_hash,
        "data_columns": list(iv_estimate.data_columns),
        "instrument": iv_estimate.instrument,
        "conditioning": list(iv_estimate.conditioning),
        "treatment": iv_estimate.treatment,
        "outcome": iv_estimate.outcome,
    }
    if iv_estimate.first_stage_f_stat is not None:
        iv_numeric_dict["first_stage_f_stat"] = iv_estimate.first_stage_f_stat
    if iv_estimate.strata is not None:
        iv_numeric_dict["stratified_wald"] = {
            "conditioning_order": list(iv_estimate.conditioning),
            "outcome_shift": iv_estimate.outcome_shift,
            "treatment_shift": iv_estimate.treatment_shift,
            "strata": [
                {
                    # _w_levels sources these through .tolist(), so they are
                    # Python natives, not numpy scalars.
                    "values": list(s.values),
                    "weight": s.weight,
                    "n_obs": s.n_obs,
                    "n_instrument_high": s.n_instrument_high,
                    "n_instrument_low": s.n_instrument_low,
                    "outcome_shift": s.outcome_shift,
                    "treatment_shift": s.treatment_shift,
                    "shift_var_yy": s.shift_var_yy,
                    "shift_var_xy": s.shift_var_xy,
                    "shift_var_xx": s.shift_var_xx,
                }
                for s in iv_estimate.strata
            ],
        }
    if iv_estimate.acr is not None:
        iv_numeric_dict["acr_decomposition"] = _acr_to_dict(
            iv_estimate.acr, cluster=iv_estimate.cluster)
    if iv_estimate.acr_declined is not None:
        iv_numeric_dict["acr_declined"] = iv_estimate.acr_declined
    if iv_estimate.anderson_rubin is not None:
        iv_numeric_dict["anderson_rubin_confidence_set"] = _ar_set_to_dict(
            iv_estimate.anderson_rubin
        )
    if iv_estimate.stratified_anderson_rubin is not None:
        iv_numeric_dict["stratified_anderson_rubin_confidence_set"] = (
            _stratified_ar_set_to_dict(iv_estimate.stratified_anderson_rubin)
        )
    result["numeric_estimate"] = iv_numeric_dict
    _attach_bootstrap_meta(result["numeric_estimate"], knobs.cluster, iv_estimate.draws)
    _attach_precision_budget(result["numeric_estimate"])
    _attach_mechanism_audit(result, iv_estimate, target=iv_estimate.outcome)
    result["derivation"] = _build_iv_numeric_derivation_dict(
        graph=facts.graph,
        x=x_atom, y=y_atom,
        instrument=chosen_iv.instrument,
        conditioning=chosen_iv.conditioning,
        estimate=iv_estimate,
        loop=(sorted(facts.loops_reaching[0], key=lambda a: a.predicate)
              if feedback else None),
    )
    _attach_e_value_if_binary(
        result, facts.contract,
        outcome=y_atom.predicate, treatment=x_atom.predicate,
    )
    _attach_weak_iv_warning_if_low_f(result, iv_estimate)
    if not feedback:
        # The complier caveat belongs to the other caller only. Under a
        # declared loop the number is not a LATE at all, and what it IS
        # instead is said once, from the loop block, by the gap report —
        # which both this layer and the identification layer reach.
        _attach_iv_estimand_fallback_warning(result, iv_estimate)
    _finalise_numeric_result(result)
    return answered()


def _attach_numeric_bounds(
    program: dict | str | bytes,
    output: dict,
    contract: DataContract,
    *,
    random_state: int,
    ci_bootstrap: int,
    cluster: str | None = None,
) -> None:
    """Evaluate every symbolic row of ``bounds_results`` on data — the numeric end of the
    partial-identification layer.

    When point identification failed, the kernel attached a SYMBOLIC
    ``bounds_results`` (``lower_expression`` / ``upper_expression`` strings).
    This turns those symbols into an actual ``[lower_value, upper_value]``
    (+ percentile-bootstrap outer-band CI) using the estimator that matches
    the method the kernel already chose — so the numeric interval and the
    symbolic one describe the SAME method, never a different one.

    Purely additive: each symbolic row is preserved; only numeric
    fields are ADDED. Any refusal — a column absent from the data, a
    response-function partition larger than the LP is run at, a positivity
    failure, or an instrument the data refutes (the instrumental inequality)
    — leaves the symbolic interval untouched. Mirrors the ``method`` selection
    the kernel made in ``scheduler._attach_bounds_results`` (reuses the SAME
    instrument / monotonicity detectors), so numeric and symbolic never
    disagree on which method applies.
    """
    from ..input.semantic_validator import validate_program
    from ..input.syntactic_validator import validate_ast
    from ..runtime.scheduler import (
        _detect_iv_candidate_structural,
        _detect_monotonicity_for_query,
        _mtr_outcome_levels,
    )
    from .bounds_numeric import (
        evaluate_balke_pearl_bounds,
        evaluate_manski_natural_bounds,
        evaluate_manski_tamer_bounds,
    )

    ast = _ensure_dict(program)
    prog = validate_program(validate_ast(ast))
    cols = set(contract.data.columns)
    cluster_ok = cluster if (cluster is None or cluster in cols) else None

    for q_stmt, result in _pair_effect_queries(prog, output):
        if q_stmt is None:
            continue
        query = q_stmt.query
        x_pred = query.intervention.atom.predicate
        y_pred = query.target.atom.predicate
        # Every row is evaluated. They are different methods on the same
        # estimand, so one number cannot stand for the others, and a row
        # whose estimator refuses leaves the rest — and its own symbolic
        # interval — untouched.
        for bounds in result.get("bounds_results") or ():
            if not isinstance(bounds, dict):
                continue
            if bounds.get("lower_value") is not None:
                continue  # idempotent: already evaluated
            method = bounds.get("method")
            try:
                if method == "manski_natural":
                    nb = evaluate_manski_natural_bounds(
                        contract.data, treatment=x_pred, outcome=y_pred,
                        treatment_value=query.intervention.value,
                        outcome_value=query.target.value,
                        ci_bootstrap=ci_bootstrap, random_state=random_state,
                        cluster=cluster_ok,
                    )
                elif method == "manski_tamer_monotonicity":
                    mono = _detect_monotonicity_for_query(prog, query)
                    # The same two readers the symbolic layer used, so the
                    # numeric row cannot end up assuming a different order
                    # than the interval it is filling in.
                    levels = _mtr_outcome_levels(prog, query)
                    if mono is None or levels is None:
                        continue
                    nb = evaluate_manski_tamer_bounds(
                        contract.data, treatment=x_pred, outcome=y_pred,
                        monotonicity=mono.value,
                        outcome_levels=levels,
                        treatment_value=query.intervention.value,
                        outcome_value=query.target.value,
                        ci_bootstrap=ci_bootstrap, random_state=random_state,
                        cluster=cluster_ok,
                    )
                elif method == "balke_pearl_iv":
                    iv_ext = (result.get("extensions") or {}).get(
                        blocks.Block.IV_IDENTIFICATION)
                    instrument = None
                    if isinstance(iv_ext, dict):
                        instrument = iv_ext.get("instrument")
                    if instrument is None:
                        instrument = _detect_iv_candidate_structural(prog, query)
                    if instrument is None:
                        continue
                    nb = evaluate_balke_pearl_bounds(
                        contract.data, treatment=x_pred, outcome=y_pred,
                        instrument=instrument,
                        treatment_value=query.intervention.value,
                        outcome_value=query.target.value,
                        ci_bootstrap=ci_bootstrap, random_state=random_state,
                        cluster=cluster_ok,
                    )
                else:
                    continue
            except EstimatorFailure:
                # Honest refusal — the symbolic interval still stands.
                continue
            _fill_numeric_bounds(bounds, nb)


def _fill_numeric_bounds(bounds: dict, nb) -> None:
    """Add the numeric evaluation of a NumericBounds onto the symbolic
    bounds_result dict in place (schema: query_result boundsResult)."""
    bounds["estimand"] = nb.estimand
    bounds["lower_value"] = nb.lower_value
    bounds["upper_value"] = nb.upper_value
    bounds["width"] = nb.width
    bounds["numeric_uninformative"] = nb.width_is_trivial
    bounds["ci_lower"] = nb.ci_lower
    bounds["ci_upper"] = nb.ci_upper
    bounds["ci_level"] = nb.ci_level
    bounds["sample_size"] = nb.sample_size
    bounds["numeric_data_hash"] = nb.data_hash
    bounds["numeric_data_columns"] = list(nb.data_columns)
    if nb.instrument is not None:
        bounds["instrument"] = nb.instrument
    if nb.cluster is not None:
        bounds["numeric_cluster"] = nb.cluster
    # The band above is a quantile of the draws that survived, and a band
    # over 40 of 500 is a different claim from one over 500. Written here
    # rather than through ``_attach_bootstrap_meta`` because this route
    # fills a bounds_result and has no numeric_estimate to attach to.
    if nb.draws is not None:
        bounds["bootstrap"] = nb.draws.record(cluster=nb.cluster)
    if getattr(nb, "sufficient_statistics", None) is not None:
        bounds["sufficient_statistics"] = nb.sufficient_statistics
    if getattr(nb, "contrast", None) is not None:
        # The contrast is a second interval over a second quantity, and its
        # tightness is its own question: a method can bracket the arm
        # sharply and only outer-bound the difference. Asked per pair for
        # that reason (#419).
        bounds["contrast"] = {
            **nb.contrast,
            "tightness": str(intervals.tightness_of(
                bounds["method"], "contrast")),
        }


def _try_general_id_estimate(
    q_stmt, result: dict, contract, graph, bidirected, *,
    x_atom, y_atom, given_atoms, random_state: int,
    ci_bootstrap: int = 500, cluster: str | None = None,
) -> Claim:
    """Final identification fallback: evaluate a general-ID (c-factor)
    identified estimand on data by the non-parametric plug-in.

    Tried BEFORE the IV escalation because a c-factor estimand is
    ASSUMPTION-FREE, whereas the IV point estimate needs monotonicity /
    effect homogeneity. When ``do(X)`` is non-parametrically point-
    identified (Pearl's napkin is the canonical case) this is the honest
    answer; only when it is NOT (a genuine hedge) does the caller fall
    through to the under-assumption IV.

    Purely additive: returns True only when it ATTACHES a plug-in numeric
    estimate. On any refusal — not c-factor identified, out of the binary
    scope, or the data can't support the estimand (positivity) — it
    returns False and touches nothing, so the prior IV / cliff behavior
    stays byte-identical when the plug-in doesn't apply.
    """
    from .general_id import (
        estimate_general_id_ate,
        estimate_general_id_conditional_ate,
    )

    df = contract.data
    if x_atom.predicate not in df.columns or y_atom.predicate not in df.columns:
        return passed('required_columns_absent')

    # Conditional query P(Y | do(X), Z=z) → IDC plug-in (Shpitser–Pearl);
    # unconditional → the Tian c-factor plug-in. Both share the downstream
    # machinery (VE plug-in, bootstrap CI, derivation, metadata audit); only
    # the identification (identify_via_idc vs identify_via_tian) and the
    # recorded Z=z stratum differ.
    conditional = bool(given_atoms)
    try:
        if conditional:
            estimate = estimate_general_id_conditional_ate(
                df, graph=graph, bidirected=bidirected,
                treatment_atom=x_atom, outcome_atom=y_atom,
                given=tuple(q_stmt.query.given),
                ci_bootstrap=ci_bootstrap, random_state=random_state,
                cluster=cluster if (cluster is None or cluster in df.columns) else None,
            )
        else:
            estimate = estimate_general_id_ate(
                df, graph=graph, bidirected=bidirected,
                treatment_atom=x_atom, outcome_atom=y_atom,
                ci_bootstrap=ci_bootstrap, random_state=random_state,
                cluster=cluster if (cluster is None or cluster in df.columns) else None,
            )
    except EstimatorFailure:
        # Not (non-parametrically) c-factor / IDC identified here, out of the
        # plug-in's binary scope, or a positivity refusal — leave the
        # result untouched and fall through to the IV escalation.
        return passed('estimator_refused')

    result["numeric_estimate"] = {
        "point": estimate.point,
        "ci_lower": estimate.ci_lower,
        "ci_upper": estimate.ci_upper,
        "ci_level": estimate.ci_level,
        "method": estimate.method,
        "assumptions": list(estimate.assumptions),
        "sample_size": estimate.sample_size,
        "data_hash": estimate.data_hash,
        "data_columns": list(estimate.data_columns),
        "treatment": estimate.treatment,
        "outcome": estimate.outcome,
        "treatment_high": estimate.treatment_high,
        "treatment_low": estimate.treatment_low,
        "outcome_high": estimate.outcome_high,
    }
    if conditional:
        # Record the Z=z stratum the contrast is taken within — makes the
        # conditional estimand P(Y | do(X), Z=z) explicit in the trail. The
        # values are [predicate, value] pairs (JSON tuples).
        result["numeric_estimate"]["given"] = [
            [pred, val] for pred, val in estimate.given
        ]
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, estimate.draws)
    _attach_precision_budget(result["numeric_estimate"])

    from ..output.result_orchestrator import (
        build_assumption_ledger,
    )
    ext = result.setdefault("extensions", {})
    _attach_mechanism_audit(
        result, estimate, target=estimate.outcome,
    )
    ledger = build_assumption_ledger(
        result, 
    )
    if ledger is not None:
        ext[blocks.Block.ASSUMPTION_LEDGER] = ledger

    result["derivation"] = _build_general_id_numeric_derivation_dict(
        graph=graph, x=x_atom, y=y_atom, estimate=estimate,
    )
    _attach_e_value_if_binary(
        result, contract,
        outcome=y_atom.predicate, treatment=x_atom.predicate,
    )
    _finalise_numeric_result(result)
    return answered()


def _try_joint_general_id_estimate(
    result: dict, contract, graph, bidirected, *,
    treatment_atoms, y_atom, random_state: int,
    ci_bootstrap: int = 500, cluster: str | None = None,
) -> Claim:
    """Joint general-ID fallback: a latent-confounded JOINT effect
    do(A, B, …) with NO adjustment set, point-identified by the set-valued
    Shpitser-Pearl ID (front-door / c-component for a treatment SET) and
    evaluated by the non-parametric plug-in.

    The joint analog of :func:`_try_general_id_estimate`, and the same answer
    SHAPE as the joint back-door route: the all-hi / all-lo contrast, plus
    the K-way interaction across the treatment box when every corner of it
    is evaluable. Purely additive: attaches a joint general-ID numeric
    estimate and returns True only when the joint effect is c-factor
    point-identified AND the data support it; on any refusal returns False
    and touches nothing, so the structural refusal
    (joint_not_identifiable) stands byte-identical.
    """
    from .general_id import estimate_joint_general_id_ate

    df = contract.data
    treatment_names = tuple(t.predicate for t in treatment_atoms)
    if any(t not in df.columns for t in treatment_names):
        return passed('required_columns_absent')
    if y_atom.predicate not in df.columns:
        return passed('required_columns_absent')

    try:
        estimate = estimate_joint_general_id_ate(
            df, graph=graph, bidirected=bidirected,
            treatment_atoms=treatment_atoms, outcome_atom=y_atom,
            ci_bootstrap=ci_bootstrap, random_state=random_state,
            cluster=cluster if (cluster is None or cluster in df.columns) else None,
        )
    except EstimatorFailure:
        # Not (non-parametrically) set-ID identified here, out of the plug-in's
        # binary scope, or a positivity refusal — leave the result untouched
        # so the structural joint refusal stands.
        return passed('estimator_refused')

    result["numeric_estimate"] = {
        "ci_level": estimate.ci_level,
        "method": estimate.method,
        "assumptions": list(estimate.assumptions),
        "sample_size": estimate.sample_size,
        "data_hash": estimate.data_hash,
        "data_columns": list(estimate.data_columns),
        "treatment": treatment_names[0],   # primary; schema-required slot
        "treatments": list(estimate.treatments),
        "outcome": estimate.outcome,
        "outcome_high": estimate.outcome_high,
        "joint_effect": {
            "point": estimate.joint_point,
            "ci_lower": estimate.joint_ci_lower,
            "ci_upper": estimate.joint_ci_upper,
            "treated": dict(estimate.treated),
            "control": dict(estimate.control),
        },
        # The plug-in's own per-corner output, from which both reported
        # numbers are finite differences. Recorded so an auditor without
        # the data can re-derive them rather than re-read them.
        "corner_risks": [
            {"cell": dict(c.cell), "risk": c.risk}
            for c in estimate.corner_risks
        ],
    }
    _attach_interaction(result["numeric_estimate"], estimate)
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, estimate.draws)
    _attach_precision_budget_joint(result["numeric_estimate"])

    from ..output.result_orchestrator import (
        build_assumption_ledger,
    )
    ext = result.setdefault("extensions", {})
    _attach_mechanism_audit(
        result, estimate, target=estimate.outcome,
    )
    ledger = build_assumption_ledger(
        result,
    )
    if ledger is not None:
        ext[blocks.Block.ASSUMPTION_LEDGER] = ledger

    # Reuse the single-treatment general-ID derivation: the criterion step
    # (general_id_criterion) re-runs the SET ID off ctx.query, and the
    # primary treatment atom labels the x / treatment slots (matching the
    # numeric terminal's cross-check against the criterion's x).
    result["derivation"] = _build_joint_general_id_derivation_dict(
        graph=graph, treatments=treatment_atoms, y=y_atom, estimate=estimate,
    )
    _finalise_numeric_result(result)
    return answered()


def _attach_interaction(numeric_estimate: dict, estimate) -> None:
    """The K-way interaction, or the species that withheld it.

    A separate slot from the contrast because it rests on a stricter
    support requirement — every corner of the treatment box rather than
    two — so a result may legitimately carry one without the other. Never
    present holding null: a consumer reading ``interaction.point`` should
    not have to know that the field it is reading can be nothing.

    Shared by both joint routes, which write the same two keys because
    they answer in the same shape; the estimators differ in how they reach
    the corners, not in what a reader is owed about them.
    """
    order = len(estimate.treatments)
    if estimate.interaction_point is not None:
        numeric_estimate["interaction"] = {
            "point": estimate.interaction_point,
            "ci_lower": estimate.interaction_ci_lower,
            "ci_upper": estimate.interaction_ci_upper,
            "scale": "difference",
            # Interaction order = number of treatments (K-way, the highest-
            # order mixed finite difference). 2 for the classic A×B case.
            "order": order,
        }
        return
    block: dict = {
        "kind": estimate.interaction_unavailable,
        "order": order,
    }
    if estimate.interaction_unavailable == "corner_unsupported":
        block["unsupported_cells"] = [
            dict(cell) for cell in estimate.interaction_unsupported_cells
        ]
    else:
        block["cap"] = estimate.interaction_cap
    numeric_estimate["interaction_unavailable"] = block


def _build_joint_general_id_derivation_dict(*, graph, treatments, y, estimate):
    """Two-step derivation for a joint general-ID (c-factor plug-in)
    estimate:

        s1: general_id_criterion (structural witness — re-runs the SET ID
            off ctx.query to confirm point-identifiability)
        s2: numeric_joint_general_id_estimate (metadata audit — no re-fit;
            the two numbers are re-derived from the recorded corner risks
            by :func:`themis.verifier.verify_joint_general_id_numeric`)

    The criterion step's ``x`` is the primary treatment atom, matching the
    single-treatment builder: the rule reads the full treatment SET off
    ctx.query, so naming one here cannot narrow what it checks.
    """
    from ..types import DerivationStep, StepRef, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    # An absent interaction is declared, not merely missing: the audit must
    # be able to tell "no number because a corner was empty" from "no number
    # because someone dropped it on the way out".
    if estimate.interaction_point is not None:
        interaction_inputs = {
            "interaction_point": estimate.interaction_point,
            "interaction_ci_lower": estimate.interaction_ci_lower,
            "interaction_ci_upper": estimate.interaction_ci_upper,
        }
    else:
        interaction_inputs = {
            "interaction_unavailable": estimate.interaction_unavailable,
        }
    steps = (
        DerivationStep(
            rule="general_id_criterion",
            inputs={"graph": graph, "x": treatments[0], "y": y},
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="numeric_joint_general_id_estimate",
            inputs={
                "criterion": StepRef(step_id="s1"),
                "treatments": frozenset(treatments),
                "outcome": y,
                "method": estimate.method,
                "data_hash": estimate.data_hash,
                "sample_size": estimate.sample_size,
                "joint_point": estimate.joint_point,
                "joint_ci_lower": estimate.joint_ci_lower,
                "joint_ci_upper": estimate.joint_ci_upper,
                **interaction_inputs,
                "ci_level": estimate.ci_level,
            },
            output=StructuralResult(value=True),
            step_id="s2",
        ),
    )
    return derivation_to_dict(steps)


def _build_general_id_numeric_derivation_dict(*, graph, x, y, estimate):
    """Two-step derivation for a general-ID (c-factor plug-in) estimate:

        s1: general_id_criterion (structural witness — re-runs the ID
            engine to confirm point-identifiability)
        s2: numeric_general_id_estimate (metadata audit — no re-fit)
    """
    from ..types import DerivationStep, StepRef, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    steps = (
        DerivationStep(
            rule="general_id_criterion",
            inputs={"graph": graph, "x": x, "y": y},
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="numeric_general_id_estimate",
            inputs={
                "criterion": StepRef(step_id="s1"),
                "treatment": x,
                "outcome": y,
                "method": estimate.method,
                "data_hash": estimate.data_hash,
                "sample_size": estimate.sample_size,
                "point": estimate.point,
                "ci_lower": estimate.ci_lower,
                "ci_upper": estimate.ci_upper,
                "ci_level": estimate.ci_level,
            },
            output=StructuralResult(value=True),
            step_id="s2",
        ),
    )
    return derivation_to_dict(steps)


def _pair_ctf_conjunction_queries(prog, output):
    """Yield (QueryStatement, result_dict) pairs whose query is a
    CounterfactualConjunctionQuery. Alignment uses query_id."""
    from ..types import CounterfactualConjunctionQuery, QueryStatement

    id_to_stmt = {
        s.id: s for s in prog.statements
        if isinstance(s, QueryStatement)
        and isinstance(s.query, CounterfactualConjunctionQuery)
    }
    for result in output.get("results", []):
        if result.get("query_kind") != "counterfactual_conjunction":
            continue
        qid = result.get("query_id")
        yield id_to_stmt.get(qid), result


def _estimate_ctf_conjunction_queries(
    program: dict | str | bytes,
    output: dict,
    contract: DataContract,
    *,
    random_state: int,
    ci_bootstrap: int,
    cluster: str | None = None,
) -> None:
    """For each counterfactual-conjunction result, attach a plug-in
    ``numeric_estimate`` of P(γ) / P(γ|δ) when the ID*/IDC* estimand is
    identifiable and the data support it. Mutates ``output`` in place.

    Purely additive: a non-identifiable / UNDEFINED / positivity refusal
    leaves the structural result untouched (the identifiability verdict
    stays the primary answer for a counterfactual query)."""
    from ..input.semantic_validator import validate_program
    from ..input.syntactic_validator import validate_ast
    from ..runtime.graph_projection import project
    from ..runtime.instantiation import instantiate
    from ..runtime import structural_solver

    ast = _ensure_dict(program)
    ast = validate_ast(ast)
    prog = validate_program(ast)
    ground_statements = instantiate(prog)
    graph = project(ground_statements)
    bidirected = structural_solver.bidirected_from_ground(ground_statements)

    for q_stmt, result in _pair_ctf_conjunction_queries(prog, output):
        if q_stmt is None:
            continue
        _try_ctf_conjunction_estimate(
            q_stmt, result, contract, graph, bidirected,
            random_state=random_state, ci_bootstrap=ci_bootstrap,
            cluster=cluster,
        )


def _try_ctf_conjunction_estimate(
    q_stmt, result: dict, contract, graph, bidirected, *,
    random_state: int, ci_bootstrap: int = 500, cluster: str | None = None,
) -> Claim:
    """Evaluate an ID*/IDC*-identified counterfactual conjunction on data by
    the non-parametric plug-in (the counterfactual analogue of
    ``_try_general_id_estimate``).

    Returns True only when it ATTACHES a plug-in numeric estimate. On any
    refusal — not identifiable, UNDEFINED conditioning event, or the data
    can't support the estimand (positivity) — it returns False and touches
    nothing, so the structural (identifiability) answer stays primary."""
    from ..runtime.ctf_identify import CtfEvent
    from .ctf_conjunction import estimate_ctf_conjunction_prob

    def _to_ctf(events):
        return tuple(
            CtfEvent(
                variable=e.variable,
                subscript=frozenset((s.atom, s.value) for s in e.subscript),
                value=e.value,
            )
            for e in events
        )

    q = q_stmt.query
    gamma = _to_ctf(q.events)
    delta = _to_ctf(q.condition)
    df = contract.data

    try:
        estimate = estimate_ctf_conjunction_prob(
            df, graph=graph, bidirected=bidirected, gamma=gamma, delta=delta,
            ci_bootstrap=ci_bootstrap, random_state=random_state,
            cluster=cluster if (cluster is None or cluster in df.columns) else None,
        )
    except EstimatorFailure as exc:
        # Not identifiable, UNDEFINED, or a positivity refusal. The
        # structural answer stays primary — but it is not the answer to the
        # question a caller who supplied data asked, so the reason the
        # number is absent goes on the envelope beside it.
        refusals.record(result, estimator="ctf_conjunction", exc=exc)
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "point": estimate.point,
        "ci_lower": estimate.ci_lower,
        "ci_upper": estimate.ci_upper,
        "ci_level": estimate.ci_level,
        "method": estimate.method,
        "assumptions": list(estimate.assumptions),
        "sample_size": estimate.sample_size,
        "data_hash": estimate.data_hash,
        "data_columns": list(estimate.data_columns),
        "conditional": estimate.conditional,
        "estimand": estimate.estimand,
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, estimate.draws)
    _attach_precision_budget(result["numeric_estimate"])

    from ..output.result_orchestrator import (
        build_assumption_ledger,
    )
    ext = result.setdefault("extensions", {})
    _attach_mechanism_audit(
        result, estimate, target=estimate.estimand,
    )
    ledger = build_assumption_ledger(
        result, 
    )
    if ledger is not None:
        ext[blocks.Block.ASSUMPTION_LEDGER] = ledger

    result["derivation"] = _build_ctf_conjunction_numeric_derivation_dict(
        graph=graph, estimate=estimate,
    )
    _finalise_numeric_result(result)
    return answered()


def _build_ctf_conjunction_numeric_derivation_dict(*, graph, estimate):
    """Two-step derivation for a counterfactual-conjunction plug-in estimate:

        s1: ctf_conjunction_criterion (structural witness — re-runs ID*/IDC*
            to confirm the conjunction is identifiable)
        s2: numeric_ctf_conjunction_estimate (metadata audit — no re-fit)
    """
    from ..types import DerivationStep, StepRef, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    steps = (
        DerivationStep(
            rule="ctf_conjunction_criterion",
            inputs={"graph": graph},
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="numeric_ctf_conjunction_estimate",
            inputs={
                "criterion": StepRef(step_id="s1"),
                "method": estimate.method,
                "data_hash": estimate.data_hash,
                "sample_size": estimate.sample_size,
                "point": estimate.point,
                "ci_lower": estimate.ci_lower,
                "ci_upper": estimate.ci_upper,
                "ci_level": estimate.ci_level,
                "conditional": estimate.conditional,
            },
            output=StructuralResult(value=True),
            step_id="s2",
        ),
    )
    return derivation_to_dict(steps)


def _pair_scm_counterfactual_queries(prog, output):
    """Yield (QueryStatement, result_dict) pairs whose query is a
    SCMCounterfactualQuery. Alignment uses query_id."""
    from ..types import SCMCounterfactualQuery, QueryStatement

    id_to_stmt = {
        s.id: s for s in prog.statements
        if isinstance(s, QueryStatement)
        and isinstance(s.query, SCMCounterfactualQuery)
    }
    for result in output.get("results", []):
        if result.get("query_kind") != "scm_counterfactual":
            continue
        qid = result.get("query_id")
        yield id_to_stmt.get(qid), result


def _scm_observation_unit(prog) -> dict:
    """The unit's numeric factual values (Pearl's E=e) from the program's
    ObservationStatements — the same source the structural SCM-counterfactual
    path reads. Non-numeric observations are skipped (linear SCM = real-valued
    nodes)."""
    from ..types import ObservationStatement
    unit: dict = {}
    for s in prog.statements:
        if isinstance(s, ObservationStatement):
            try:
                unit[s.atom] = float(s.value)
            except (TypeError, ValueError):
                continue
    return unit


def _estimate_scm_counterfactual_queries(
    program: dict | str | bytes,
    output: dict,
    contract: DataContract,
    *,
    random_state: int,
    ci_bootstrap: int,
    cluster: str | None = None,
) -> None:
    """For each SCM-counterfactual result, attach a data-fitted
    ``numeric_estimate`` of the unit's counterfactual value: fit each linear
    structural equation from the DataFrame (per-node OLS on graph parents),
    abduct the unit's exogenous terms from its ObservationStatements, and
    predict under the intervention. Mutates ``output`` in place.

    Purely additive — the structural path (which needs the coefficients
    DECLARED on the edges) stays primary; this attaches a number only when
    the mechanisms are fittable from data and the unit is fully observed. On
    any refusal it touches nothing."""
    from ..input.semantic_validator import validate_program
    from ..input.syntactic_validator import validate_ast
    from ..runtime.graph_projection import project
    from ..runtime.instantiation import instantiate

    ast = _ensure_dict(program)
    ast = validate_ast(ast)
    prog = validate_program(ast)
    graph = project(instantiate(prog))
    observed_unit = _scm_observation_unit(prog)

    for q_stmt, result in _pair_scm_counterfactual_queries(prog, output):
        if q_stmt is None:
            continue
        _try_scm_counterfactual_estimate(
            q_stmt, result, contract, graph, observed_unit,
            random_state=random_state, ci_bootstrap=ci_bootstrap,
            cluster=cluster,
        )


def _try_scm_counterfactual_estimate(
    q_stmt, result: dict, contract, graph, observed_unit, *,
    random_state: int, ci_bootstrap: int = 500, cluster: str | None = None,
) -> Claim:
    """Fit a recursive linear SCM from data and compute the queried unit's
    counterfactual point (the data end of the abduction-action-prediction
    structural path). Returns True only when it ATTACHES a numeric estimate;
    on any refusal (query atoms missing, unit under-observed, rank-deficient
    fit, or the data can't support the fit) it returns False and touches
    nothing, so the structural result stays primary."""
    from .scm_counterfactual import estimate_scm_counterfactual_point

    q = q_stmt.query
    x_atom = q.intervention.atom
    y_atom = q.target

    try:
        estimate = estimate_scm_counterfactual_point(
            contract.data, graph=graph, observed_unit=observed_unit,
            intervention_atom=x_atom, intervention_value=float(q.intervention.value),
            target_atom=y_atom, ci_bootstrap=ci_bootstrap,
            random_state=random_state,
            cluster=cluster if (
                cluster is None or cluster in contract.data.columns
            ) else None,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="scm_counterfactual", exc=exc)
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "point": estimate.point,
        "ci_lower": estimate.ci_lower,
        "ci_upper": estimate.ci_upper,
        "ci_level": estimate.ci_level,
        "method": estimate.method,
        "assumptions": list(estimate.assumptions),
        "sample_size": estimate.sample_size,
        "data_hash": estimate.data_hash,
        "data_columns": list(estimate.data_columns),
        "target": estimate.target,
        "intervention_var": estimate.intervention_var,
        "intervention_value": estimate.intervention_value,
        # Verifier substrate: the per-node OLS moment matrices to re-solve and
        # the unit's observed values to re-run abduction-action-prediction.
        "node_fits": [
            {
                "node": f.node,
                "parents": list(f.parents),
                "coefficients": list(f.coefficients),
                "xtx": [list(row) for row in f.xtx],
                "xty": list(f.xty),
            }
            for f in estimate.node_fits
        ],
        "observed_unit": [[p, v] for p, v in estimate.observed_unit],
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, estimate.draws)
    _attach_precision_budget(result["numeric_estimate"])

    from ..output.result_orchestrator import (
        build_assumption_ledger,
    )
    ext = result.setdefault("extensions", {})
    _attach_mechanism_audit(
        result, estimate, target=estimate.target,
    )
    ledger = build_assumption_ledger(
        result, 
    )
    if ledger is not None:
        ext[blocks.Block.ASSUMPTION_LEDGER] = ledger
    # Human display copy (parity with the structural path's extension): the
    # counterfactual value + the abducted noise + post-intervention values.
    # Display-only — the verifier's authority is numeric_estimate; kernel.verify
    # cross-checks target_value == numeric_estimate.point so this cannot drift.
    ext[blocks.Block.SCM_COUNTERFACTUAL] = {
        "target": estimate.target,
        "target_value": estimate.point,
        "intervention": {
            "variable": estimate.intervention_var,
            "value": estimate.intervention_value,
        },
        "abducted_noise": {a: v for a, v in estimate.abducted_noise},
        "counterfactual_values": {a: v for a, v in estimate.counterfactual_values},
        # No ``estimated_from_data`` flag. Whether the coefficients were
        # declared or fitted is what separates these two paths, and since
        # the two paths are two derivation rules the fact has a home the
        # reader reaches: ``scm_abduction_action_prediction`` says "按你声明
        # 的结构方程系数", ``numeric_scm_counterfactual_estimate`` says the
        # coefficients were fitted by per-node OLS. A boolean beside them
        # was a third copy that nothing read, and it could sit here unnoticed
        # because this was the one block among the six carrying a citation
        # whose map was open — so nothing could say it was undeclared either.
        "reference": (
            "Pearl, Glymour & Jewell (2016) Primer §4.2 "
            "abduction-action-prediction; coefficients fitted by per-node OLS"
        ),
    }

    result["derivation"] = _build_scm_counterfactual_numeric_derivation_dict(
        x=x_atom, y=y_atom, estimate=estimate,
    )
    _finalise_numeric_result(result)
    return answered()


def _build_scm_counterfactual_numeric_derivation_dict(*, x, y, estimate):
    """Single-step derivation for a data-fitted SCM counterfactual:

        s1: numeric_scm_counterfactual_estimate (metadata audit — the strong
            re-solve of the OLS moments + re-run abduction-action-prediction
            lives in kernel.verify's verify_scm_counterfactual_numeric, since
            the moment matrices don't fit derivation-input serialization).
    """
    from ..types import DerivationStep, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    steps = (
        DerivationStep(
            rule="numeric_scm_counterfactual_estimate",
            inputs={
                "target": y,
                "intervention_var": x,
                "intervention_value": estimate.intervention_value,
                "method": estimate.method,
                "data_hash": estimate.data_hash,
                "sample_size": estimate.sample_size,
                "point": estimate.point,
                "ci_lower": estimate.ci_lower,
                "ci_upper": estimate.ci_upper,
                "ci_level": estimate.ci_level,
            },
            output=StructuralResult(value=True),
            step_id="s1",
        ),
    )
    return derivation_to_dict(steps)


def _pair_proximal_queries(prog, output):
    """Yield (QueryStatement, result_dict) pairs whose query is a
    ProximalEffectQuery. Alignment uses query_id."""
    from ..types import ProximalEffectQuery, QueryStatement

    id_to_stmt = {
        s.id: s for s in prog.statements
        if isinstance(s, QueryStatement)
        and isinstance(s.query, ProximalEffectQuery)
    }
    for result in output.get("results", []):
        if result.get("query_kind") != "proximal_effect":
            continue
        qid = result.get("query_id")
        yield id_to_stmt.get(qid), result


def _estimate_proximal_queries(
    program: dict | str | bytes,
    output: dict,
    contract: DataContract,
    *,
    random_state: int,
    ci_bootstrap: int,
    cluster: str | None = None,
) -> None:
    """For each proximal-effect result, attach a matrix plug-in
    ``numeric_estimate`` of the ATE (Miao formula (5)) when the effect is
    proximal-identifiable and the data support it. Mutates ``output`` in place.

    Purely additive: a non-identifiable / rank / positivity refusal leaves the
    structural (identifiability) result untouched."""
    from ..input.semantic_validator import validate_program
    from ..input.syntactic_validator import validate_ast
    from ..runtime.graph_projection import project
    from ..runtime.instantiation import instantiate
    from ..runtime import structural_solver

    ast = _ensure_dict(program)
    ast = validate_ast(ast)
    prog = validate_program(ast)
    ground_statements = instantiate(prog)
    graph = project(ground_statements)
    bidirected = structural_solver.bidirected_from_ground(ground_statements)

    for q_stmt, result in _pair_proximal_queries(prog, output):
        if q_stmt is None:
            continue
        _try_proximal_estimate(
            q_stmt, result, contract, graph, bidirected,
            random_state=random_state, ci_bootstrap=ci_bootstrap,
            cluster=cluster,
        )


def _try_proximal_estimate(
    q_stmt, result: dict, contract, graph, bidirected, *,
    random_state: int, ci_bootstrap: int = 500, cluster: str | None = None,
) -> Claim:
    """Recover the proximal ATE on data by Miao's discrete formula (5).

    Returns True only when it ATTACHES a numeric estimate. On any refusal —
    not identifiable, proxy-cardinality mismatch, a singular measurement
    channel (rank), or an empty stratum (positivity) — it returns False and
    touches nothing, so the identifiability answer stays primary."""
    from .proximal import estimate_proximal_ate

    q = q_stmt.query
    df = contract.data
    try:
        estimate = estimate_proximal_ate(
            df, graph=graph, bidirected=bidirected,
            treatment=q.treatment, outcome=q.outcome, latent=q.latent,
            treatment_proxy=q.treatment_proxy, outcome_proxy=q.outcome_proxy,
            covariates=q.covariates, channel=q.channel,
            ci_bootstrap=ci_bootstrap, random_state=random_state,
            cluster=cluster if (cluster is None or cluster in df.columns) else None,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="proximal", exc=exc)
        _record_proxy_coarsening_gap(result, q, exc)
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "point": estimate.point,
        "ci_lower": estimate.ci_lower,
        "ci_upper": estimate.ci_upper,
        "ci_level": estimate.ci_level,
        "method": estimate.method,
        "assumptions": list(estimate.assumptions),
        "sample_size": estimate.sample_size,
        "data_hash": estimate.data_hash,
        "data_columns": list(estimate.data_columns),
        "treatment": estimate.treatment,
        "outcome": estimate.outcome,
        "treatment_proxy": list(estimate.treatment_proxy),
        "outcome_proxy": list(estimate.outcome_proxy),
        "covariates": list(estimate.covariates),
        # Which channel was run is NOT restated here. It is the identification
        # block's ``channel``, which is present whenever this is, and a second
        # copy of a declaration is a declaration that can disagree with itself
        # — ``latent_cardinality`` sat in both until it had a sibling shape to
        # be wrong about.
        "do_prob_treated": estimate.do_prob_treated,
        "do_prob_control": estimate.do_prob_control,
    }
    if estimate.dose_response_curve:
        # The curve REPLACES the contrast keys rather than joining them.
        # ``point`` with a curve beside it would be two answers to one
        # question, and every surface that leads with a point would lead
        # with whichever pair of levels this layer had picked.
        for key in ("point", "ci_lower", "ci_upper",
                    "do_prob_treated", "do_prob_control"):
            result["numeric_estimate"].pop(key)
        result["numeric_estimate"].update(
            sampling_points=list(estimate.sampling_points),
            reference_point=estimate.reference_point,
            dose_response_curve=[dict(p) for p in estimate.dose_response_curve],
        )
    if estimate.no_effect_test is not None:
        # Replaces the same keys the curve does, for a sharper version of the
        # same reason: here there is no number at all, and a ``point`` of
        # ``None`` sitting beside a test would be read by every surface that
        # leads with a point as an effect that came out empty rather than as
        # a question that was never answered.
        for key in ("point", "ci_lower", "ci_upper",
                    "do_prob_treated", "do_prob_control"):
            result["numeric_estimate"].pop(key)
        result["numeric_estimate"]["no_effect_test"] = dict(
            estimate.no_effect_test)
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, estimate.draws)
    _attach_precision_budget(result["numeric_estimate"])

    from ..output.result_orchestrator import (
        build_assumption_ledger,
    )
    target = f"P({estimate.outcome}|do({estimate.treatment}))"
    ext = result.setdefault("extensions", {})
    _attach_mechanism_audit(
        result, estimate, target=target,
    )
    ledger = build_assumption_ledger(
        result, 
    )
    if ledger is not None:
        ext[blocks.Block.ASSUMPTION_LEDGER] = ledger

    result["derivation"] = _build_proximal_numeric_derivation_dict(
        graph=graph, estimate=estimate,
    )
    _record_regularisation_gap(result, estimate)
    _record_treatment_bridge_range_gap(result, estimate)
    _record_only_the_null_was_tested_gap(result, q, estimate)
    _finalise_numeric_result(result)
    return answered()


def _record_only_the_null_was_tested_gap(result: dict, q, estimate) -> None:
    """Say that the question shrank, and which question is now answered.

    Filed rather than left to the renderer because the shape of the answer
    is not the shape that was asked for, and that mismatch is a finding
    about THIS run — the same standing this layer gives a penalty that moved
    the answer or a bridge that left its range. A surface reading only
    ``no_effect_test`` would render a p-value correctly and never say that a
    number was wanted.

    The reason branches on the species that blocked the point, because the
    two branches send a reader to different places: a channel that will not
    invert is a measurement to go and make, and a treatment with too many
    arms is a channel Themis already has. Collapsing them into one sentence
    would have to be vague enough to be true of both, and neither reader
    would learn what to do.
    """
    test = estimate.no_effect_test
    if test is None:
        return
    channel = estimate.channel
    blocked = channel["point_blocked_by"]
    (zcol,) = estimate.treatment_proxy
    (wcol,) = estimate.outcome_proxy
    k = estimate.declared_channel.latent_cardinality
    latent = q.latent.predicate
    treatment, outcome = estimate.treatment, estimate.outcome
    if blocked == Refusal.TREATMENT_NOT_BINARY:
        levels = len({cell["x"] for cell in channel["cells"]})
        why = _sentence(Sentence.THE_DISCRETE_CONTRAST_NEEDS_TWO_ARMS,
                        treatment=treatment, outcome=outcome, levels=levels)
        route = _gaps.route(Route.USE_A_BRIDGE_CHANNEL_FOR_MORE_THAN_TWO_ARMS,
                            treatment=treatment, levels=levels)
    elif blocked == Refusal.RANK_CONDITION_VIOLATED:
        why = _sentence(Sentence.THE_PROXY_CHANNEL_IS_SINGULAR,
                        z=zcol, w=wcol, k=k, latent=latent)
        route = _gaps.route(Route.ENRICH_A_PROXY_TO_GET_A_NUMBER, k=k, z=zcol)
    else:
        why = _sentence(
            Sentence.THE_PROXIES_SHOW_FEWER_STATES_THAN_THE_LATENT_HAS,
            treatment=treatment, outcome=outcome, z=zcol, w=wcol, k=k,
            latent=latent, z_levels=len(channel["z_levels"]))
        route = _gaps.route(Route.ENRICH_A_PROXY_TO_GET_A_NUMBER, k=k, z=zcol)
    _file_gaps(result, [DataGap(
        kind=GapKind.ANSWER_IS_A_TEST_NOT_AN_EFFECT_SIZE,
        severity=GapSeverity.BLOCKING,
        blocks=GapBlocks.POINT_ESTIMATE,
        describes=(
            why,
            _sentence(Sentence.A_TEST_OF_THE_NULL_IS_WHAT_IS_LEFT,
                      treatment=treatment, outcome=outcome, latent=latent),
        ),
        alternative_paths=(route,),
        provenance=_verifier_check(f"no_effect_test:{treatment}"),
    )])


def _record_regularisation_gap(result: dict, estimate) -> None:
    """Say when the number a reader is about to read is the penalty's.

    Filed here rather than by the report's classifier because the finding is
    arithmetic on the ladder, and the ladder is a sufficient statistic that
    the estimate carries — a classifier reading the envelope would be
    re-deriving what the producer already knows, and would have to be kept
    in step with the estimator's own thresholds. What the report does with
    the finding is the report's; whether there is one is this layer's.

    Two doors into one gap, and both are stated when both are open: the
    penalty moved the answer further than sampling does, and a lighter
    penalty has no solution here. The second is the stronger claim, so a run
    where only it fires still gets a sentence saying so rather than an
    unexplained warning.
    """
    from .proximal_bridge import penalty_verdict

    channel = estimate.channel
    rungs = channel.get("penalty_ladder")
    if estimate.method != "proximal_bridge" or not rungs:
        return
    noise = channel.get("standard_error")
    verdict = penalty_verdict(rungs, estimate.point, noise)
    if not verdict["the_penalty_is_doing_the_work"]:
        return
    describes = [_sentence(
        Sentence.THE_BRIDGE_EQUATION_HAS_NO_SOLUTION_WITHOUT_A_PENALTY)]
    if (noise is not None and verdict["bend"] is not None
            and verdict["bend"] > noise):
        describes.append(_sentence(
            Sentence.THE_PENALTY_MOVED_IT_FURTHER_THAN_NOISE_DID,
            bend=_lang.occasion(verdict["bend"]),
            noise=_lang.occasion(noise),
            treatment=estimate.treatment, outcome=estimate.outcome))
    if verdict["unsolved"]:
        describes.append(_sentence(
            Sentence.A_LIGHTER_PENALTY_HAS_NO_SOLUTION_HERE))
    _file_gaps(result, [DataGap(
        kind=GapKind.REGULARISATION_IS_MOVING_THE_ANSWER,
        severity=GapSeverity.IMPORTANT,
        # INTERPRETATION and not POINT_ESTIMATE: a point WAS produced and is
        # the best this sieve gives. What is impaired is reading it as the
        # sample's answer rather than as the sample's answer at this penalty.
        blocks=GapBlocks.INTERPRETATION,
        describes=tuple(describes),
        alternative_paths=(
            _gaps.route(Route.NAME_A_LIGHTER_PENALTY),
            _gaps.route(Route.THIN_THE_SIEVE),
            _gaps.route(Route.READ_THE_PENALTY_LADDER_AS_THE_ANSWER),
        ),
        provenance=_verifier_check(
            f"regularisation:{estimate.treatment}|{estimate.outcome}"),
    )])


#: Below this share of a bridge's rows, a negative fit is arithmetic noise
#: around a boundary rather than a span that cannot reach the function. At
#: one in two hundred rows the inverse-probability average is still an
#: average of the outcome to within rounding; by one in a hundred it is not,
#: and the measured cases sit two orders of magnitude above either.
_Q_NEGATIVE_SHARE = 0.005


def _record_treatment_bridge_range_gap(result: dict, estimate) -> None:
    """Say when the fitted treatment bridge stopped being a probability.

    ``q`` is one over a propensity and is therefore at least one everywhere;
    the sieve solving for it is linear in its parameters and cannot know
    that. Where the declared span will not hold a function of the right
    shape, the fit dips below zero and the inverse-probability weights stop
    being weights — which no amount of data repairs, because the span is a
    declaration rather than an estimate.

    Filed off the recorded SHARE rather than off the rows, and filed here
    rather than by the report's classifier for the reason the penalty gap is:
    the finding is arithmetic on a statistic the estimate already carries,
    and a classifier reading the envelope would be re-deriving what the
    producer knows and would have to be kept in step with its threshold.
    """
    bridge = (estimate.channel or {}).get("treatment_bridge")
    if estimate.method != "proximal_bridge" or not isinstance(bridge, dict):
        return
    # A curve's arms are its levels and are keyed by them; a contrast's two
    # are keyed by name. Read both here rather than filing two gaps, because
    # the finding is the same one and only the naming differs — which is
    # what the two statements below are for.
    arms = bridge.get("arms")
    if isinstance(arms, dict):
        shares = {level: float((block or {}).get("q_negative_fraction", 0.0))
                  for level, block in arms.items()}
    else:
        shares = {arm: float((bridge.get(arm) or {}).get(
            "q_negative_fraction", 0.0)) for arm in ("treated", "control")}
    if not shares or max(shares.values()) <= _Q_NEGATIVE_SHARE:
        return
    if isinstance(arms, dict):
        worst = max(shares, key=lambda level: shares[level])
        _file_gaps(result, [DataGap(
            kind=GapKind.TREATMENT_BRIDGE_LEAVES_ITS_RANGE,
            severity=GapSeverity.IMPORTANT,
            blocks=GapBlocks.INTERPRETATION,
            describes=(
                _sentence(Sentence.A_RECIPROCAL_PROBABILITY_CANNOT_BE_NEGATIVE),
                _sentence(
                    Sentence.THE_FITTED_TREATMENT_BRIDGE_WENT_NEGATIVE_AT_A_LEVEL,
                    share=f"{shares[worst]:.1%}", level=worst,
                    levels=len(shares), treatment=estimate.treatment,
                    outcome=estimate.outcome),
            ),
            alternative_paths=(
                _gaps.route(Route.WIDEN_THE_TREATMENT_BRIDGE),
                _gaps.route(Route.READ_THE_DOUBLY_ROBUST_ANSWER_INSTEAD),
            ),
            provenance=_verifier_check(
                f"treatment_bridge_range:{estimate.treatment}"
                f"|{estimate.outcome}"),
        )])
        return
    _file_gaps(result, [DataGap(
        kind=GapKind.TREATMENT_BRIDGE_LEAVES_ITS_RANGE,
        severity=GapSeverity.IMPORTANT,
        # INTERPRETATION and not POINT_ESTIMATE: a point WAS produced, and
        # where the estimator is the doubly robust one it is not even the
        # worse for this. What is impaired is reading an inverse-probability
        # average as an average.
        blocks=GapBlocks.INTERPRETATION,
        describes=(
            _sentence(Sentence.A_RECIPROCAL_PROBABILITY_CANNOT_BE_NEGATIVE),
            _sentence(
                Sentence.THE_FITTED_TREATMENT_BRIDGE_WENT_NEGATIVE,
                # Formatted here rather than carried raw, by the rule the
                # other share-bearing gaps follow: these two fields are a
                # reader's text and nothing re-derives from them, while the
                # number a checker wants is on the channel already as
                # ``q_negative_fraction``. A bare float would reach the page
                # as ``0.254494``, which is not a share anyone reads.
                treated=f"{shares['treated']:.1%}",
                control=f"{shares['control']:.1%}",
                treatment=estimate.treatment, outcome=estimate.outcome),
        ),
        alternative_paths=(
            _gaps.route(Route.WIDEN_THE_TREATMENT_BRIDGE),
            _gaps.route(Route.READ_THE_DOUBLY_ROBUST_ANSWER_INSTEAD),
        ),
        provenance=_verifier_check(
            f"treatment_bridge_range:{estimate.treatment}|{estimate.outcome}"),
    )])


def _record_proxy_coarsening_gap(result: dict, q, exc) -> None:
    """Say what declaration would unblock a proxy-cardinality refusal.

    The refusal on its own is honest and incomplete: it reports that the
    declaration and the data disagree, and leaves the reader with no name for
    the thing that would settle it. That was not an oversight in the wording
    — until the query had a ``proxy_coarsening`` there was no such thing to
    name, so the estimator could only say "these do not match".

    Filed only where the caller has NOT already declared a grouping. A
    coarsening that is declared and still does not resolve to k has its own
    refusal, and sending that reader to write a field they have written is
    an errand that cannot be run.
    """
    # ``getattr`` on the CHANNEL and not on the query: a bridge channel has
    # no grouping to have declared, and reaching for one on it is the same
    # question with the honest answer "there is none" rather than a shape
    # error. The refusal above cannot fire in that regime anyway — the
    # guard is the reason it cannot fire QUIETLY.
    channel = q.channel
    if (exc.failure_type != Refusal.PROXY_CARDINALITY_MISMATCH
            or getattr(channel, "proxy_coarsening", None) is not None):
        return
    # One proxy per side, because only the discrete channel gets here and
    # the door refuses that channel more than one; unpacking says so where
    # an index would have quietly taken the first of however many.
    (zcol,) = (a.predicate for a in q.treatment_proxy)
    (wcol,) = (a.predicate for a in q.outcome_proxy)
    k = channel.latent_cardinality
    slots = {
        "k": k,
        "latent": q.latent.predicate,
        "z": zcol,
        "w": wcol,
        "z_levels": exc.details.get("z"),
        "w_levels": exc.details.get("w"),
    }
    _file_gaps(result, [DataGap(
        kind=GapKind.PROXY_COARSENING_UNDECLARED,
        severity=GapSeverity.BLOCKING,
        blocks=GapBlocks.POINT_ESTIMATE,
        describes=(
            _sentence(
                Sentence.THE_PROXIES_ARE_FINER_THAN_THE_DECLARED_CARDINALITY,
                **slots),
            _sentence(Sentence.WHICH_LEVELS_ARE_ONE_STATE_IS_NOT_IN_THE_DATA,
                      k=k, z=zcol),
        ),
        # Written out rather than iterated: the two branches take different
        # slots because they are different things to do, and a loop over
        # them would have to ask each which it is.
        alternative_paths=(
            _gaps.route(Route.DECLARE_A_PROXY_COARSENING, k=k, z=zcol, w=wcol),
            _gaps.route(Route.RECONSIDER_THE_LATENT_CARDINALITY),
        ),
        provenance=_verifier_check(f"proxy_coarsening:{zcol}|{wcol}"),
    )])


def _build_proximal_numeric_derivation_dict(*, graph, estimate):
    """Two-step derivation for a proximal estimate:

        s1: proximal_criterion (structural witness — re-runs identify_proximal
            to confirm the effect is proximal-identifiable)
        s2: the regime's own re-derivation — ``numeric_proximal_estimate``
            replays formula (5) from the recorded Z×W counts;
            ``numeric_proximal_bridge_estimate`` re-solves the sieve from the
            recorded cross-moments at every penalty on the ladder.

    Two rules rather than one with a branch inside it, because they are two
    different computations checked by two different identities. A single rule
    that took either payload would have to decide which it was looking at,
    and a verifier that guesses what it is verifying is a verifier that can
    be handed the wrong thing.

    Which is why the two names are written at two call sites and not chosen
    inside one. Every census over rule names reads literals — the glossary
    that owes each of them a sentence among them — so a name assembled here
    is a name no census can see, and both of these were reported as glossary
    entries nothing writes. The payload is still built once: what differs
    between the regimes is the identity that checks it, not what travels.
    """
    from ..types import DerivationStep, StepRef, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    recorded = {
        "criterion": StepRef(step_id="s1"),
        "method": estimate.method,
        "data_hash": estimate.data_hash,
        "sample_size": estimate.sample_size,
        "point": estimate.point,
        "ci_lower": estimate.ci_lower,
        "ci_upper": estimate.ci_upper,
        "ci_level": estimate.ci_level,
        "do_prob_treated": estimate.do_prob_treated,
        "do_prob_control": estimate.do_prob_control,
        # The sufficient statistics, so the rule can re-derive the number
        # rather than audit its metadata. Here and not on numeric_estimate
        # because this result HAS a derivation: selection-recovery and
        # missing-data put theirs on the block precisely because theirs do
        # not, and the audit path is all they have. One key for both
        # regimes — what a channel IS differs, and that it is the thing the
        # number came out of does not.
        "measurement_channel": dict(estimate.channel),
    }
    if estimate.dose_response_curve:
        # The same swap the envelope makes, for the same reason and so that
        # the two cannot drift: a step carrying both a null point and a
        # curve would let a rule check the shape that happens to be there
        # and pass a producer that shipped neither.
        for key in ("point", "ci_lower", "ci_upper",
                    "do_prob_treated", "do_prob_control"):
            recorded.pop(key)
        recorded["sampling_points"] = list(estimate.sampling_points)
        recorded["reference_point"] = estimate.reference_point
        recorded["dose_response_curve"] = [
            dict(p) for p in estimate.dose_response_curve]
    if estimate.no_effect_test is not None:
        for key in ("point", "ci_lower", "ci_upper",
                    "do_prob_treated", "do_prob_control"):
            recorded.pop(key)
        recorded["no_effect_test"] = dict(estimate.no_effect_test)
    criterion = DerivationStep(
        rule="proximal_criterion",
        inputs={"graph": graph},
        output=True,
        step_id="s1",
    )
    if estimate.method == "proximal_bridge":
        replay = DerivationStep(
            rule="numeric_proximal_bridge_estimate",
            inputs=recorded,
            output=StructuralResult(value=True),
            step_id="s2",
        )
    elif estimate.method == "proximal_null_test":
        replay = DerivationStep(
            rule="numeric_proximal_null_test",
            inputs=recorded,
            output=StructuralResult(value=True),
            step_id="s2",
        )
    else:
        replay = DerivationStep(
            rule="numeric_proximal_estimate",
            inputs=recorded,
            output=StructuralResult(value=True),
            step_id="s2",
        )
    return derivation_to_dict((criterion, replay))


def _pair_causation_queries(prog, output):
    """Yield (QueryStatement, result_dict) pairs whose query is a
    CausationQuery. Alignment uses query_id."""
    from ..types import CausationQuery, QueryStatement

    id_to_stmt = {
        s.id: s for s in prog.statements
        if isinstance(s, QueryStatement) and isinstance(s.query, CausationQuery)
    }
    for result in output.get("results", []):
        if result.get("query_kind") != "causation":
            continue
        qid = result.get("query_id")
        yield id_to_stmt.get(qid), result


def _estimate_causation_queries(
    program: dict | str | bytes,
    output: dict,
    contract: DataContract,
    *,
    random_state: int,
    ci_bootstrap: int,
    cluster: str | None = None,
) -> None:
    """For each causation (PN/PS/PNS) result, attach a data-based
    ``numeric_estimate`` when the quantities are point-identified (monotone)
    and the do-risks are back-door / experimentally available. Mutates
    ``output`` in place.

    Purely additive: without monotonicity, or on any estimator refusal, the
    structural (bounds / needs-experiment) answer is left untouched — the
    data-based bounds overlay is a follow-up on the bounds_results channel."""
    from ..input.semantic_validator import validate_program
    from ..input.syntactic_validator import validate_ast
    from ..runtime.graph_projection import project
    from ..runtime.instantiation import instantiate
    from ..runtime import structural_solver

    ast = _ensure_dict(program)
    ast = validate_ast(ast)
    prog = validate_program(ast)
    ground_statements = instantiate(prog)
    graph = project(ground_statements)
    bidirected = structural_solver.bidirected_from_ground(ground_statements)

    for q_stmt, result in _pair_causation_queries(prog, output):
        if q_stmt is None:
            continue
        _try_causation_estimate(
            q_stmt, result, contract, graph, bidirected,
            random_state=random_state, ci_bootstrap=ci_bootstrap,
            cluster=cluster,
        )


def _try_causation_estimate(
    q_stmt, result: dict, contract, graph, bidirected, *,
    random_state: int, ci_bootstrap: int = 500, cluster: str | None = None,
) -> Claim:
    """Recover PN/PS/PNS on data (empirical joint + g-formula do-risks →
    Tian-Pearl) and attach them as the numeric answer.

    The answer is always the three identified intervals; monotonicity only
    decides whether they collapse to points (Tian-Pearl 40-42 vs 24-26), i.e.
    whether the result carries a headline PN point or is interval-tier. This
    mirrors the theta path, where ``_dispatch_causation`` likewise returns
    COUNTERFACTUAL_BOUNDED rather than declining when there is no point.

    Returns True only when it ATTACHES a numeric estimate. On a refusal — not
    back-door identifiable, non-binary cause/effect, a positivity hole — it
    returns False and touches nothing, so the structural answer stays primary."""
    from .causation import estimate_causation_probabilities

    q = q_stmt.query
    df = contract.data
    try:
        estimate = estimate_causation_probabilities(
            df, graph=graph, bidirected=bidirected,
            cause=q.cause, effect=q.effect, monotonic=q.monotonic,
            experimental_risk_treated=q.experimental_risk_treated,
            experimental_risk_control=q.experimental_risk_control,
            ci_bootstrap=ci_bootstrap, random_state=random_state,
            cluster=cluster if (cluster is None or cluster in df.columns) else None,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="causation", exc=exc)
        return blocked('estimator_refused')

    # The causation data answer is ALWAYS the three Tian-Pearl intervals; under
    # monotonicity they collapse to points. When a point is point-identified the
    # reported per-quantity CI is the point's bootstrap CI; otherwise (bounds
    # only) it is the OUTER band on the identified set (Manski / Balke-Pearl
    # data-bounds convention). One channel, one status — the monotonicity flag
    # only decides whether a headline point is present.
    is_point = estimate.pn_point is not None

    def _quantity(point, lower, upper, pt_ci_lo, pt_ci_hi, band_lo, band_hi):
        # The estimator carries the two under separate names and this is
        # where they merge into one pair of keys. Which one went in used to
        # be discarded here, and three reader surfaces recovered it
        # afterwards from ``point is not None`` — correctly, and each on
        # its own. It is stated instead (#419): the width of a point's
        # bootstrap interval is a fact about the sample, the width of the
        # band on [lower, upper] is not, and "collect more data" is advice
        # that only one of them can take.
        pinned = point is not None
        ci_lo, ci_hi = (pt_ci_lo, pt_ci_hi) if pinned else (band_lo, band_hi)
        return {
            "point": point, "lower": lower, "upper": upper,
            "ci_lower": ci_lo, "ci_upper": ci_hi,
            intervals.CI_WIDTH_FIELD: (
                None if ci_lo is None or ci_hi is None
                else str(intervals.Width.SAMPLING if pinned
                         else intervals.Width.OUTER_BAND)
            ),
        }

    poc_block = {
        "monotonic": estimate.monotonic,
        "interventional_risk_provenance": estimate.interventional_risk_provenance,
        "adjustment": list(estimate.adjustment),
        # Which column the answer leaned on, when it leaned on an instrument
        # instead of a pair of risks. A reader asking "where did these three
        # intervals come from" gets the licence from the provenance and the
        # column from here.
        "instrument": estimate.instrument,
        "p_y_do_x1": estimate.p_y_do_x1,
        "p_y_do_x0": estimate.p_y_do_x0,
        "observational_joint": {
            "p_x1_y1": estimate.p_x1_y1, "p_x1_y0": estimate.p_x1_y0,
            "p_x0_y1": estimate.p_x0_y1, "p_x0_y0": estimate.p_x0_y0,
        },
        "pn": _quantity(estimate.pn_point, estimate.pn_lower, estimate.pn_upper,
                        estimate.pn_point_ci_lower, estimate.pn_point_ci_upper,
                        estimate.pn_bounds_ci_lower, estimate.pn_bounds_ci_upper),
        "ps": _quantity(estimate.ps_point, estimate.ps_lower, estimate.ps_upper,
                        estimate.ps_point_ci_lower, estimate.ps_point_ci_upper,
                        estimate.ps_bounds_ci_lower, estimate.ps_bounds_ci_upper),
        "pns": _quantity(estimate.pns_point, estimate.pns_lower, estimate.pns_upper,
                         estimate.pns_point_ci_lower, estimate.pns_point_ci_upper,
                         estimate.pns_bounds_ci_lower, estimate.pns_bounds_ci_upper),
    }
    numeric_estimate = {
        "ci_level": estimate.ci_level,
        "method": estimate.method,
        "assumptions": list(estimate.assumptions),
        "sample_size": estimate.sample_size,
        "data_hash": estimate.data_hash,
        "data_columns": list(estimate.data_columns),
        "treatment": estimate.cause,
        "outcome": estimate.effect,
        "probabilities_of_causation": poc_block,
    }
    if is_point:
        # Headline = PN (necessity) point + its CI. (numeric_estimate.point is
        # number-only in the schema, so it is OMITTED for the bounds answer.)
        numeric_estimate["point"] = estimate.pn_point
        numeric_estimate["ci_lower"] = estimate.pn_point_ci_lower
        numeric_estimate["ci_upper"] = estimate.pn_point_ci_upper
    result["numeric_estimate"] = numeric_estimate
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, estimate.draws)
    if is_point:
        _attach_precision_budget(result["numeric_estimate"])

    # Headline numeric_result reflects the DATA PN point (not the stale theta
    # one, if any); for the bounds answer there is no point — value is null and
    # the identified intervals live in numeric_estimate.probabilities_of_causation.
    result["numeric_result"] = {
        "value": (
            float(estimate.pn_point)
            if estimate.pn_point is not None else None
        )
    }

    # Display copy: the explainer reads extensions.causation. Overwrite the
    # (theta-based, if any) structural envelope with the data envelope so all
    # surfaces show the same audited numbers; verify_causation_numeric
    # cross-checks it against the derivation inputs.
    ext = result.setdefault("extensions", {})
    ext[blocks.Block.CAUSATION] = {
        "monotonic": estimate.monotonic,
        "interventional_risk_provenance": estimate.interventional_risk_provenance,
        "instrument": estimate.instrument,
        "p_y_do_x1": estimate.p_y_do_x1,
        "p_y_do_x0": estimate.p_y_do_x0,
        "observational_joint": poc_block["observational_joint"],
        "pn": {"lower": estimate.pn_lower, "upper": estimate.pn_upper, "point": estimate.pn_point},
        "ps": {"lower": estimate.ps_lower, "upper": estimate.ps_upper, "point": estimate.ps_point},
        "pns": {"lower": estimate.pns_lower, "upper": estimate.pns_upper, "point": estimate.pns_point},
    }

    from ..output.result_orchestrator import (
        build_assumption_ledger,
    )
    _attach_mechanism_audit(
        result, estimate, target=f"PN({estimate.effect}|{estimate.cause})",
    )
    ledger = build_assumption_ledger(
        result, 
    )
    if ledger is not None:
        ext[blocks.Block.ASSUMPTION_LEDGER] = ledger

    result["derivation"] = _build_causation_numeric_derivation_dict(
        q_stmt=q_stmt, estimate=estimate,
    )
    if is_point:
        _finalise_numeric_result(result)
    else:
        _finalise_numeric_bounds_result(result)
    return answered()


def _finalise_numeric_bounds_result(result: dict) -> None:
    """Finalise a data-recovered PN/PS/PNS BOUNDS answer (non-monotone).

    Like ``_finalise_numeric_result`` the data DID produce an audited numeric
    object (the three Tian-Pearl intervals), so the status flips to
    ``numerically_solved`` and the verifier re-derives it. BUT the answer is an
    INTERVAL, not a point — so the gap-report is reconciled to
    ``answer_tier='interval'`` (not 'point'): the distributional gaps the
    identification pass raised are satisfied by the supplied data, while the
    bounds framing (a point would need monotonicity) stays honest."""
    result["status"] = "numerically_solved"
    result["structural_result"] = {"value": True}
    result.pop("missing_information", None)
    report = result.get("data_gap_report")
    if not isinstance(report, dict):
        return
    # The supplied data satisfied the theta-distribution needs (missing_distribution
    # etc.); drop them and the parameter investigation_requests they cite, but keep
    # the answer at the INTERVAL tier — a point still needs an untestable assumption.
    requests = result.get("investigation_requests")
    if isinstance(requests, list):
        kept = [r for r in requests if r.get("group") != "parameter"]
        if kept:
            result["investigation_requests"] = kept
        else:
            result.pop("investigation_requests", None)
    _set_gaps(
        result,
        [
            g for g in report.get("gaps", [])
            if g.get("kind") not in _NUMERIC_SATISFIED_GAP_KINDS
        ],
        answer_tier="interval",
    )


def _build_causation_numeric_derivation_dict(*, q_stmt, estimate):
    """Single-step derivation for a data-based PN/PS/PNS estimate:

        numeric_causation_estimate — re-applies the Tian-Pearl theorem
        (verifier's own transcription) to the reported empirical joint +
        do-risks, re-derives the adjustment set on the graph, and audits
        metadata. No separate structural criterion step: for causation the
        theorem re-application on the reported inputs IS the check.
    """
    from ..types import DerivationStep, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    q = q_stmt.query
    # Headline CI: the PN point's bootstrap CI when point-identified, else the
    # PN OUTER band on the identified set — the verifier sanity-checks it against
    # the reported PN point / interval accordingly.
    if estimate.pn_point is not None:
        head_ci_lower, head_ci_upper = estimate.pn_point_ci_lower, estimate.pn_point_ci_upper
    else:
        head_ci_lower, head_ci_upper = estimate.pn_bounds_ci_lower, estimate.pn_bounds_ci_upper
    steps = (
        DerivationStep(
            rule="numeric_causation_estimate",
            inputs={
                "cause": q.cause, "effect": q.effect,
                "p_x1_y1": estimate.p_x1_y1, "p_x1_y0": estimate.p_x1_y0,
                "p_x0_y1": estimate.p_x0_y1, "p_x0_y0": estimate.p_x0_y0,
                "p_y_do_x1": estimate.p_y_do_x1, "p_y_do_x0": estimate.p_y_do_x0,
                "monotonic": estimate.monotonic,
                "interventional_risk_provenance": estimate.interventional_risk_provenance,
                # comma-joined scalar (serializer does not take a str tuple).
                "adjustment": ",".join(estimate.adjustment),
                # The instrument route's sufficient statistic. The verifier
                # re-solves the three response-function programs from exactly
                # these, so the level list travels with the table: a |Z|x2x2
                # array read against a different level order re-derives
                # different intervals and calls an honest producer a liar.
                "instrument": estimate.instrument,
                "instrument_levels": estimate.instrument_levels,
                "p_xyz": estimate.p_xyz,
                "p_z": estimate.p_z,
                # Present only when the risks came from the general ID
                # algorithm; the verifier re-derives one per arm, because
                # identifying the easy arm and evaluating it twice would
                # otherwise be indistinguishable from having identified both.
                "risk_formula_treated": estimate.risk_formula_treated,
                "risk_formula_control": estimate.risk_formula_control,
                "pn_lower": estimate.pn_lower, "pn_upper": estimate.pn_upper,
                "pn_point": estimate.pn_point,
                "ps_lower": estimate.ps_lower, "ps_upper": estimate.ps_upper,
                "ps_point": estimate.ps_point,
                "pns_lower": estimate.pns_lower, "pns_upper": estimate.pns_upper,
                "pns_point": estimate.pns_point,
                "method": estimate.method,
                "data_hash": estimate.data_hash,
                "sample_size": estimate.sample_size,
                "ci_lower": head_ci_lower,
                "ci_upper": head_ci_upper,
                # ...and which of the two objects that pair is, on the
                # audited record and not only on the block. A claim a
                # reader acts on ("collect more" vs "assume more") that
                # nothing re-derives is a claim, and the verifier can
                # re-derive this one — it sees whether a point came out.
                intervals.CI_WIDTH_FIELD: (
                    None if head_ci_lower is None or head_ci_upper is None
                    else str(intervals.Width.SAMPLING
                             if estimate.pn_point is not None
                             else intervals.Width.OUTER_BAND)
                ),
            },
            output=StructuralResult(value=True),
            step_id="s1",
        ),
    )
    return derivation_to_dict(steps)


def _pair_counterfactual_cell_queries(prog, output):
    """Yield (QueryStatement, result_dict) pairs whose query is a
    CounterfactualQuery. Alignment uses query_id."""
    from ..types import CounterfactualQuery, QueryStatement

    id_to_stmt = {
        s.id: s for s in prog.statements
        if isinstance(s, QueryStatement) and isinstance(s.query, CounterfactualQuery)
    }
    for result in output.get("results", []):
        if result.get("query_kind") != "counterfactual":
            continue
        qid = result.get("query_id")
        yield id_to_stmt.get(qid), result


def _estimate_counterfactual_cell_queries(
    program: dict | str | bytes,
    output: dict,
    contract: DataContract,
    *,
    random_state: int,
    ci_bootstrap: int,
    cluster: str | None = None,
) -> None:
    """For each binary counterfactual-cell result, attach a data-based
    ``numeric_estimate``. Mutates ``output`` in place.

    Purely additive: on any estimator refusal — non-binary, the needed do-risk
    neither back-door identifiable nor supplied, empirical inputs that admit no
    SCM — the structural answer is left untouched."""
    from ..input.semantic_validator import validate_program
    from ..input.syntactic_validator import validate_ast
    from ..runtime.graph_projection import project
    from ..runtime.instantiation import instantiate
    from ..runtime import structural_solver

    ast = _ensure_dict(program)
    ast = validate_ast(ast)
    prog = validate_program(ast)
    ground_statements = instantiate(prog)
    graph = project(ground_statements)
    bidirected = structural_solver.bidirected_from_ground(ground_statements)

    for q_stmt, result in _pair_counterfactual_cell_queries(prog, output):
        if q_stmt is None:
            continue
        _try_counterfactual_cell_estimate(
            q_stmt, result, contract, graph, bidirected,
            random_state=random_state, ci_bootstrap=ci_bootstrap,
            cluster=cluster,
        )


def _try_counterfactual_cell_estimate(
    q_stmt, result: dict, contract, graph, bidirected, *,
    random_state: int, ci_bootstrap: int = 500, cluster: str | None = None,
) -> Claim:
    """Recover one binary counterfactual cell on data (empirical joint +
    g-formula do-risk → the consistency identity) and attach it as the numeric
    answer, with a bootstrap the theta path cannot produce.

    The answer is a point when the identified set collapses (the consistency
    case, the ETT identity, or an interval a declared monotonicity pins) and an
    interval otherwise — mirroring the theta path, which likewise returns
    COUNTERFACTUAL_BOUNDED rather than declining when there is no point.

    Returns True only when it ATTACHES an estimate; on a refusal it returns
    False and touches nothing."""
    from .counterfactual_cell import estimate_counterfactual_cell

    df = contract.data
    try:
        estimate = estimate_counterfactual_cell(
            df, graph=graph, bidirected=bidirected, query=q_stmt.query,
            ci_bootstrap=ci_bootstrap, random_state=random_state,
            cluster=cluster if (cluster is None or cluster in df.columns) else None,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="counterfactual_cell", exc=exc)
        return blocked('estimator_refused')

    is_point = estimate.point is not None
    cell_block = {
        "observed_x": estimate.x_observed,
        "counterfactual_x": estimate.x_counterfactual,
        "target_y": estimate.y_star,
        "factual_y": estimate.factual_target_known,
        "monotonicity": estimate.monotonicity,
        "interventional_risk_provenance": estimate.interventional_risk_provenance,
        "adjustment": list(estimate.adjustment),
        # Which column the answer leaned on, when it leaned on an instrument
        # instead of a risk. A reader asking "where did this interval come
        # from" gets the licence from the provenance and the column from here.
        "instrument": estimate.instrument,
        "p_y_do_x_cf": estimate.p_y_do_x_cf,
        "observational_joint": {
            "p_x1_y1": estimate.p_x1_y1, "p_x1_y0": estimate.p_x1_y0,
            "p_x0_y1": estimate.p_x0_y1, "p_x0_y0": estimate.p_x0_y0,
        },
        "lower": estimate.low,
        "upper": estimate.high,
        "point": estimate.point,
        "ci_lower": estimate.ci_lower,
        "ci_upper": estimate.ci_upper,
        # The cell's twin of the causation case above: the same pair of keys
        # is the point's bootstrap interval when the polytope pinned one and
        # a band on [lower, upper] when it did not, and only what ran here
        # knows which (#419).
        # The one discarded-draw count with a reader-facing meaning, as the
        # share it is. A resample whose feasible set is empty under the
        # declared monotonicity is that resample refuting the assumption,
        # and monotonicity is the one usually called untestable — so this
        # is the nearest thing to a test of it, and it belongs to the cell
        # that declared the assumption rather than to the generic record it
        # is derived from. Null where the question does not arise; a zero
        # would tell every reader about an assumption their data never
        # touched. The denominator is the draws that ANSWERED, since a draw
        # lost to a thin stratum was not a vote against monotonicity.
        "monotonicity_refuted_share": share_lost_to(
            estimate.draws.record(cluster=cluster) if estimate.draws else None,
            refusals.Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE,
        ),
        intervals.CI_WIDTH_FIELD: (
            None if estimate.ci_lower is None or estimate.ci_upper is None
            else str(intervals.Width.SAMPLING if is_point
                     else intervals.Width.OUTER_BAND)
        ),
    }
    numeric_estimate = {
        "ci_level": estimate.ci_level,
        "method": estimate.method,
        "assumptions": list(estimate.assumptions),
        "sample_size": estimate.sample_size,
        "data_hash": estimate.data_hash,
        "data_columns": list(estimate.data_columns),
        "treatment": estimate.cause,
        "outcome": estimate.effect,
        "counterfactual_cell": cell_block,
    }
    if is_point:
        numeric_estimate["point"] = estimate.point
        numeric_estimate["ci_lower"] = estimate.ci_lower
        numeric_estimate["ci_upper"] = estimate.ci_upper
    result["numeric_estimate"] = numeric_estimate
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, estimate.draws)
    if is_point:
        _attach_precision_budget(result["numeric_estimate"])

    # Headline numeric_result reflects the DATA cell, replacing the theta one.
    # The interval answer keeps its interval here (not only inside
    # numeric_estimate) because that is the channel the counterfactual rung's
    # answer_tier and renderers read.
    if is_point:
        result["numeric_result"] = {"value": estimate.point}
    else:
        result["numeric_result"] = {
            "value": None,
            "interval": {"low": estimate.low, "high": estimate.high},
        }

    # Display copy: the explainer reads extensions.counterfactual_cell and
    # prefers it over the status-only rendering, so every surface shows the
    # same audited numbers. ONE dict into both places — which is why the
    # refuted share is a field on the cell and not a second copy of the
    # resampling record beside it: a ``QueryResult`` carries no
    # ``numeric_estimate``, so a fact the explainer needs has to be on the
    # cell, and the fact it needs is the share, not the counts.
    ext = result.setdefault("extensions", {})
    ext[blocks.Block.COUNTERFACTUAL_CELL] = cell_block

    from ..output.result_orchestrator import (
        build_assumption_ledger,
    )
    _attach_mechanism_audit(
        result, estimate, target=(
            f"P({estimate.effect}_{{{estimate.cause}="
            f"{int(estimate.x_counterfactual)}}}={int(estimate.y_star)}"
            f"|{estimate.cause}={int(estimate.x_observed)})"
        ),
    )
    ledger = build_assumption_ledger(
        result, 
    )
    if ledger is not None:
        ext[blocks.Block.ASSUMPTION_LEDGER] = ledger

    result["derivation"] = _build_counterfactual_cell_numeric_derivation_dict(
        estimate=estimate,
    )
    if is_point:
        _finalise_numeric_result(result)
    else:
        _finalise_numeric_bounds_result(result)
    return answered()


def _build_counterfactual_cell_numeric_derivation_dict(*, estimate):
    """Single-step derivation for a data-based counterfactual cell:

        numeric_counterfactual_cell_estimate — re-solves the consistency
        identity (the verifier's own transcription) on the reported empirical
        joint + do-risk, re-derives on the graph whatever licensed that risk
        (the adjustment set, or the general-ID estimand for the arm the query
        asks about), and re-checks that the declared risk provenance survives
        an independent reading of whether this cell needs a do-risk at all.
    """
    from ..types import DerivationStep, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    steps = (
        DerivationStep(
            rule="numeric_counterfactual_cell_estimate",
            inputs={
                "p_x1_y1": estimate.p_x1_y1, "p_x1_y0": estimate.p_x1_y0,
                "p_x0_y1": estimate.p_x0_y1, "p_x0_y0": estimate.p_x0_y0,
                "p_y_do_x_cf": estimate.p_y_do_x_cf,
                "interventional_risk_provenance": estimate.interventional_risk_provenance,
                # comma-joined scalar (serializer does not take a str tuple).
                "adjustment": ",".join(estimate.adjustment),
                # The instrument route's sufficient statistic. The verifier
                # re-solves the response-function LP from exactly these, so the
                # level list travels with the table: a |Z|×2×2 array read
                # against a different level order re-derives a different
                # interval and calls an honest producer a liar.
                "instrument": estimate.instrument,
                "instrument_levels": estimate.instrument_levels,
                "p_xyz": estimate.p_xyz,
                "p_z": estimate.p_z,
                # Present only when the risk came from the general ID
                # algorithm; the verifier re-derives it for the asked arm.
                "risk_formula": estimate.risk_formula,
                "lower": estimate.low, "upper": estimate.high,
                "point": estimate.point,
                "method": estimate.method,
                "data_hash": estimate.data_hash,
                "sample_size": estimate.sample_size,
                "ci_lower": estimate.ci_lower,
                "ci_upper": estimate.ci_upper,
                # The cell's twin of the causation step above.
                intervals.CI_WIDTH_FIELD: (
                    None if estimate.ci_lower is None
                    or estimate.ci_upper is None
                    else str(intervals.Width.SAMPLING
                             if estimate.point is not None
                             else intervals.Width.OUTER_BAND)
                ),
            },
            output=StructuralResult(value=True),
            step_id="s1",
        ),
    )
    return derivation_to_dict(steps)


def _try_mediation_estimate(
    q_stmt, result: dict, contract, graph, bidirected, *, random_state: int,
    ci_bootstrap: int = 500, cluster: str | None = None,
) -> Claim:
    """Phase 7.4 — attach a mediation numeric estimate when the
    identification layer has cleared NDE/NIE for the requested mediator.

    Reads ``result.extensions.mediation_decomposition`` to decide
    whether to fit. Only the ``nde_nie`` strategy is wired in 7.4 —
    CDE numeric estimation is deferred (the reference mediator value
    isn't expressible cleanly in the statsmodels Mediation API).

    When the OUTCOME is binary, a ratio-scale (excess relative risk)
    four-way block is attached alongside the difference-scale one
    (VanderWeele eAppendix §3.4/§3.3); ``ci_bootstrap`` sizes its CI.
    """
    from .mediation import estimate_mediation

    # The return value answers "is this query mine", NOT "did I produce a
    # number" — and the two differ in exactly one place. No mediation block
    # means the IDENTIFICATION layer routed this query to another strategy
    # (a query naming both a mediator and a target_population goes to
    # transport there), so this handler must stand down and let that
    # strategy's branch run. Any other exit still CLAIMS the query: the
    # identification layer did choose mediation and it merely could not be
    # carried through, and falling onward would answer the total effect for
    # a question about a decomposition — a different estimand, silently.
    extensions = result.get("extensions") or {}
    decomp = extensions.get(blocks.Block.MEDIATION_DECOMPOSITION)
    if decomp is None:
        return passed('identification_chose_another_strategy')
    strategy = decomp.get("strategy")
    if strategy == "cde":
        # The natural effects did not survive this graph and the controlled
        # one did. That is not a degenerate case to decline: the CDE's
        # conditions are STRICTLY weaker — over every labelled DAG on four
        # nodes with a valid mediator, 256 identify the controlled effect
        # and not the natural ones, and none the other way round — so this
        # branch is where the identification layer's own answer lands most
        # often once the natural route fails. It used to end here as
        # ``numeric_end_not_built`` while a written, exported, separately
        # tested estimator for exactly this sat in ``mediation.py``, unable
        # to be reached from ``themis.estimate`` by any program at all.
        return _controlled_direct_estimate(
            q_stmt, result, contract, decomp,
            random_state=random_state, ci_bootstrap=ci_bootstrap,
            cluster=cluster,
        )
    if strategy == "none":
        return blocked('not_identified')
    if strategy != "nde_nie":
        return blocked('numeric_end_not_built')

    nde_nie_block = decomp.get("nde_nie", {})
    if not nde_nie_block.get("identifiable"):
        return blocked('not_identified')
    # The identification layer emits adjustment atoms in their string
    # form (predicate(args)). Strip back to bare predicates so the
    # estimator can index DataFrame columns.
    adjustment = tuple(
        a.split("(", 1)[0] for a in nde_nie_block.get("adjustment", ())
    )

    x_pred = q_stmt.query.intervention.atom.predicate
    y_pred = q_stmt.query.target.atom.predicate
    m_pred = q_stmt.query.mediator.predicate

    # Skip cleanly when adjustment columns aren't all in the data
    # contract (defensive — should be enforced upstream)
    missing_cols = [c for c in adjustment if c not in contract.data.columns]
    if missing_cols:
        return blocked('required_columns_absent')

    try:
        med_estimate = estimate_mediation(
            contract.data,
            treatment=x_pred,
            outcome=y_pred,
            mediator=m_pred,
            adjustment=adjustment,
            random_state=random_state,
            cluster=cluster,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="mediation", exc=exc)
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "method": med_estimate.method,
        "ci_level": med_estimate.ci_level,
        "assumptions": list(med_estimate.assumptions),
        "sample_size": med_estimate.sample_size,
        "data_hash": med_estimate.data_hash,
        "data_columns": list(med_estimate.data_columns),
        "treatment": med_estimate.treatment,
        "outcome": med_estimate.outcome,
        "mediator": med_estimate.mediator,
        "adjustment": list(med_estimate.adjustment),
        "decomposition": {
            "nde": {
                "point": med_estimate.nde_point,
                "ci_lower": med_estimate.nde_ci_lower,
                "ci_upper": med_estimate.nde_ci_upper,
            },
            "nie": {
                "point": med_estimate.nie_point,
                "ci_lower": med_estimate.nie_ci_lower,
                "ci_upper": med_estimate.nie_ci_upper,
            },
            "te": {
                "point": med_estimate.te_point,
                "ci_lower": med_estimate.te_ci_lower,
                "ci_upper": med_estimate.te_ci_upper,
            },
            "proportion_mediated": {
                "point": med_estimate.proportion_mediated_point,
                "ci_lower": med_estimate.proportion_mediated_ci_lower,
                "ci_upper": med_estimate.proportion_mediated_ci_upper,
            },
        },
    }
    _attach_mechanism_audit(result, med_estimate, target=med_estimate.outcome)
    # VanderWeele 2014 four-way split (CDE + INTref + INTmed + PIE) of the
    # same total effect. Surfaced alongside NDE/NIE so the renderer can
    # report "how much is neither / only interaction / both / only
    # mediation". PNDE=CDE+INTref and TNIE=INTmed+PIE reconcile EXACTLY
    # with the nde/nie above on the LINEAR outcome path; on the logit path
    # they differ slightly because the existing nde/nie use a Monte-Carlo
    # Normal approximation over the mediator while the four-way uses the
    # exact m∈{0,1} cell means. None (with a reason) when the difference-
    # scale decomposition is invalid (continuous mediator + logit outcome).
    fw = med_estimate.four_way
    if fw is not None:
        def _comp(c) -> dict:
            return {
                "point": c.point,
                "ci_lower": c.ci_lower,
                "ci_upper": c.ci_upper,
            }
        result["numeric_estimate"]["four_way_decomposition"] = {
            "cde": _comp(fw.cde),
            "intref": _comp(fw.intref),
            "intmed": _comp(fw.intmed),
            "pie": _comp(fw.pie),
            "te": _comp(fw.te),
            "prop_mediated": _comp(fw.prop_mediated),
            "prop_interaction": _comp(fw.prop_interaction),
            "additive_interaction": fw.additive_interaction_point,
            "scale": fw.scale,
            "cde_mediator_reference": fw.cde_mediator_reference,
            # The standardized cell means the split was built from. Recorded
            # as sufficient statistics so verify_mediation_numeric re-derives
            # every component (and, on the linear path, NDE/NIE) from them —
            # the difference-scale analog of four_way_ratio's coefficients.
            "sufficient_statistics": {"cell_means": dict(fw.cell_means)},
            "reference": (
                "VanderWeele 2014 (Explanation in Causal Inference Ch.14); "
                "TE = CDE + INTref + INTmed + PIE"
            ),
        }
    elif med_estimate.four_way_unavailable_reason is not None:
        result["numeric_estimate"]["four_way_unavailable"] = {
            "reason": med_estimate.four_way_unavailable_reason,
        }
    # VanderWeele 2014 eAppendix §3.4/§3.3 ratio-scale (excess relative risk)
    # four-way split — attached when the OUTCOME is binary (the ratio scale
    # is only defined then). For a binary outcome the multiplicative scale is
    # the natural one; the difference-scale block above is a collapsible
    # linear combination, the ratio-scale block a NON-collapsible function of
    # the logistic coefficients. Binary mediator → §3.4, continuous → §3.3.
    _attach_four_way_ratio(
        result, contract, treatment=x_pred, outcome=y_pred, mediator=m_pred,
        adjustment=adjustment, random_state=random_state,
        ci_bootstrap=ci_bootstrap, cluster=cluster,
    )
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, med_estimate.draws)
    _attach_precision_budget_decomposition(result["numeric_estimate"])
    _attach_e_value_if_binary(
        result, contract,
        outcome=y_pred, treatment=x_pred,
    )

    # NOTE: status stays "structurally_solved" — the identification
    # answer (strategy=nde_nie + adjustment) is the primary result; the
    # numeric_estimate block is supplementary detail. The existing
    # mediation derivation (mediation_*_check + identify_via_mediation)
    # already passes verify_effect_structural. Flipping to
    # numerically_solved would break that round-trip.
    return answered()


def _controlled_direct_estimate(
    q_stmt, result: dict, contract, decomp: dict, *,
    random_state: int, ci_bootstrap: int, cluster: str | None,
) -> Claim:
    """The controlled direct effect, at the levels the mediator's own
    support offers.

    The level is not a parameter this route can default. A CDE is indexed
    by where the mediator is held, and under an exposure-mediator
    interaction it varies with that index — so choosing one level here
    would be the package deciding a policy question on the reader's
    behalf, and choosing zero would report a number whose meaning depends
    on something nobody stated. The curve says both: what the direct
    effect is at each level the data can speak about, and whether it is
    the same everywhere.
    """
    from .mediation import estimate_cde_curve
    from .support import levels_over_support

    cde_block = decomp.get("cde") or {}
    if not cde_block.get("identifiable"):
        return blocked('not_identified')
    # The identification layer emits adjustment atoms in string form; strip
    # to bare predicates the way the natural-effect branch does.
    adjustment = tuple(
        a.split("(", 1)[0] for a in cde_block.get("adjustment", ())
    )
    x_pred = q_stmt.query.intervention.atom.predicate
    y_pred = q_stmt.query.target.atom.predicate
    m_pred = q_stmt.query.mediator.predicate

    missing_cols = [c for c in (*adjustment, m_pred)
                    if c not in contract.data.columns]
    if missing_cols:
        return blocked('required_columns_absent')

    levels, observed = levels_over_support(
        contract.data[m_pred].to_numpy(dtype=float)
    )
    try:
        est = estimate_cde_curve(
            contract.data,
            treatment=x_pred,
            outcome=y_pred,
            mediator=m_pred,
            mediator_values=levels,
            adjustment=adjustment,
            ci_bootstrap=ci_bootstrap,
            random_state=random_state,
            cluster=cluster,
            levels_observed=observed,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="controlled_direct", exc=exc)
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "method": est.method,
        "ci_level": est.ci_level,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "treatment": est.treatment,
        "outcome": est.outcome,
        "mediator": est.mediator,
        "adjustment": list(est.adjustment),
        "controlled_direct_effect": {
            "levels": [
                {
                    "mediator_level": lv.mediator_level,
                    "point": lv.point,
                    "ci_lower": lv.ci_lower,
                    "ci_upper": lv.ci_upper,
                    "risk_treated": lv.risk_treated,
                    "risk_control": lv.risk_control,
                }
                for lv in est.levels
            ],
            # What the auditor re-derives the curve from rather than
            # re-checking it against itself.
            "sufficient_statistics": est.sufficient_statistics,
            # Whether every level is one the sample holds, or the curve was
            # read at quantiles of a continuum. Two different claims, and
            # the count of levels cannot tell them apart.
            "levels_observed": est.levels_observed,
            # The exposure-mediator interaction's visible consequence. A
            # flat curve says holding the mediator anywhere gives the same
            # direct effect, which is an answer and not an absence of one.
            "varies_with_level": est.varies,
            "reference": (
                "VanderWeele 2015 §2.3.3 (controlled direct effect); "
                "identified by the back-door criterion for do(X, M)"
            ),
        },
    }
    _attach_mechanism_audit(result, est, target=est.outcome)
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, est.draws)
    # NOTE: status stays "structurally_solved" for the reason the
    # natural-effect branch gives — the identification answer is primary
    # and the numeric block is supplementary detail on the same result.
    return answered()


def _try_mediation_joint_estimate(
    q_stmt, result: dict, contract, graph, bidirected, *, random_state: int,
    cluster: str | None = None,
) -> Claim:
    """Attach a JOINT multi-mediator numeric estimate when the joint
    identification layer has cleared the block NDE/NIE for the mediator
    set (VanderWeele-Vansteelandt 2014).

    Reads ``result.extensions.mediation_joint_decomposition``; proceeds
    when its ``nde_nie`` block is identifiable (so both the ``nde_nie`` and
    ``nde_nie+cde`` strategies qualify). Serializes a ``decomposition``
    block whose ``sufficient_statistics`` (outcome coefficients + per-
    mediator standardized means) let verify_mediation_numeric re-derive the
    joint NDE/NIE independently on the linear path. No four-way block — that
    split is single-mediator-specific.

    Attaching the estimate does not itself change the status, same as the
    single-mediator path: a theta-evaluated block already arrives
    ``numerically_solved`` and keeps its numeric derivation, while a block
    identified structurally only stays ``structurally_solved``.
    """
    from .mediation import estimate_mediation_joint

    extensions = result.get("extensions") or {}
    decomp = extensions.get(blocks.Block.MEDIATION_JOINT_DECOMPOSITION)
    # Same claim rule as the single-mediator handler: only an ABSENT block
    # means identification routed this query elsewhere. Every other exit
    # claims it rather than letting a different estimand answer in its place.
    if decomp is None:
        return passed('identification_chose_another_strategy')

    # The joint natural-effect numeric rides on the NDE/NIE block being
    # structurally identified (strategy is "nde_nie" or "nde_nie+cde"); the
    # CDE-for-a-set numeric is attached below as a sub-block of the same
    # estimate when it too is identified with a compatible adjustment.
    nde_nie_block = decomp.get("nde_nie", {})
    if not nde_nie_block.get("identifiable"):
        # The single-mediator handler answers the mirror-image case from
        # ``estimate_cde_curve``, and this one does not, for a reason about
        # the ANSWER and not about the estimator: a set's controlled direct
        # effect is held at a VECTOR of levels, and the curve shape the
        # single-mediator route reports indexes its rows by one number.
        # Reporting a vector through that field would need a second way of
        # saying the same thing, so the set case waits for the shape it
        # actually has rather than borrowing one that nearly fits.
        return blocked('numeric_end_not_built')
    adjustment = tuple(
        a.split("(", 1)[0] for a in nde_nie_block.get("adjustment", ())
    )

    x_pred = q_stmt.query.intervention.atom.predicate
    y_pred = q_stmt.query.target.atom.predicate
    m_preds = tuple(a.predicate for a in q_stmt.query.mediators)

    needed = [*m_preds, *adjustment]
    missing_cols = [c for c in needed if c not in contract.data.columns]
    if missing_cols:
        return blocked('required_columns_absent')

    try:
        est = estimate_mediation_joint(
            contract.data,
            treatment=x_pred,
            outcome=y_pred,
            mediators=m_preds,
            adjustment=adjustment,
            random_state=random_state,
            cluster=cluster,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="mediation_joint", exc=exc)
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "method": est.method,
        "ci_level": est.ci_level,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "treatment": est.treatment,
        "outcome": est.outcome,
        "mediators": list(est.mediators),
        "adjustment": list(est.adjustment),
        "decomposition": {
            "nde": {
                "point": est.nde_point,
                "ci_lower": est.nde_ci_lower,
                "ci_upper": est.nde_ci_upper,
            },
            "nie": {
                "point": est.nie_point,
                "ci_lower": est.nie_ci_lower,
                "ci_upper": est.nie_ci_upper,
            },
            "te": {
                "point": est.te_point,
                "ci_lower": est.te_ci_lower,
                "ci_upper": est.te_ci_upper,
            },
            "proportion_mediated": {
                "point": est.proportion_mediated_point,
                "ci_lower": est.proportion_mediated_ci_lower,
                "ci_upper": est.proportion_mediated_ci_upper,
            },
            # Outcome coefficients + per-mediator standardized means. On the
            # LINEAR path verify_mediation_numeric re-derives NDE / NIE from
            # these independently (the joint analog of four_way_ratio's
            # recorded coefficients); on the logit path only the construction
            # identities are re-checkable (the honest ceiling).
            "sufficient_statistics": est.sufficient_statistics,
            "reference": (
                "VanderWeele & Vansteelandt 2014 (Mediation analysis with "
                "multiple mediators); joint NDE/NIE through the mediator set."
            ),
        },
    }
    _attach_mechanism_audit(result, est, target=est.outcome)

    # CDE-for-a-set (controlled direct effect holding the whole block fixed
    # at a reference level), reported at m*=0 / m*=1. Attach the numeric only
    # when the CDE is structurally identified with the SAME adjustment the
    # joint model was fit under, so the reported numbers correspond to a
    # back-door-valid W. When the CDE needs a different adjustment than the
    # NDE/NIE, its structural identifiability is still surfaced in the
    # mediation_joint_decomposition extension; the numeric at that other
    # adjustment is a declared follow-on. On the LINEAR path
    # verify_mediation_numeric re-derives CDE(m*=0)=beta_x and
    # CDE(m*=1)=beta_x+sum_j gamma_j from the recorded coefficients.
    cde_ext = decomp.get("cde") or {}
    if (
        cde_ext.get("identifiable")
        and sorted(cde_ext.get("adjustment", []))
        == sorted(nde_nie_block.get("adjustment", []))
    ):
        result["numeric_estimate"]["decomposition"]["cde"] = est.cde

    _attach_bootstrap_meta(result["numeric_estimate"], cluster, est.draws)

    # NOTE: status stays "structurally_solved" — the joint identification
    # answer is primary; the numeric_estimate is supplementary, mirroring
    # the single-mediator path.
    return answered()


# Upper bound on the supplementary ratio-scale four-way bootstrap (a
# second double-model bootstrap beside the primary Imai one). The other
# auto-attached supplementary blocks (E-value, OVB) are closed-form and
# cheap; this one needs a bootstrap, so it is capped so a mediation estimate
# with the default ci_bootstrap (500) never silently pays a full 500×
# double-fit for a supplementary audit block. The POINT decomposition (the
# value) is exact regardless; only the supplementary CIs use the bounded
# bootstrap — a declared cost↔precision trade-off.
_RATIO_BOOTSTRAP_CAP = 200


def _reference_level_as_number(level: object) -> float:
    """The number a declared reference LEVEL stands for.

    The estimators keep the level the caller declared rather than the number
    they derived from it, and they are right to: an atom value is as often a
    label as a number, so the field is ``object`` and says so. The audit
    block below records the number the closed form was actually evaluated
    at, which means re-making the estimator's own conversion here — and a
    level that is no kind of number is a malformed request, not a zero.
    """
    if isinstance(level, (int, float, str)):
        return float(level)
    raise TypeError(
        f"a reference level must name a number; got {level!r}"
    )


def _attach_four_way_ratio(
    result: dict, contract, *, treatment: str, outcome: str, mediator: str,
    adjustment: tuple[str, ...], random_state: int, ci_bootstrap: int,
    cluster: str | None,
) -> None:
    """Attach the ratio-scale (excess relative risk) four-way block to a
    mediation numeric_estimate when the OUTCOME is binary.

    VanderWeele eAppendix §3.4 (binary mediator, logistic model) / §3.3
    (continuous mediator, linear model + residual variance). Silent no-op
    when the outcome is continuous (the estimator raises
    ``outcome_not_binary``), a level is degenerate, or a model fit fails —
    the difference-scale block already attached stays the primary detail.
    """
    import numpy as np

    from .four_way_ratio import estimate_four_way_ratio

    ne = result.get("numeric_estimate")
    if ne is None:
        return
    # The ratio block is SUPPLEMENTARY audit detail sitting beside the
    # primary NDE/NIE; its CI is a second, independent double-model
    # bootstrap. Bounding it (a declared cost↔precision trade-off) keeps a
    # single mediation estimate from silently paying a full 500× double-fit
    # bootstrap on top of the Imai one — the point decomposition (the value)
    # is exact regardless of this cap.
    ratio_bootstrap = min(ci_bootstrap, _RATIO_BOOTSTRAP_CAP)
    try:
        est = estimate_four_way_ratio(
            contract.data, treatment=treatment, outcome=outcome,
            mediator=mediator, adjustment=adjustment,
            ci_bootstrap=ratio_bootstrap, random_state=random_state,
            cluster=cluster,
        )
    except EstimatorFailure:
        # Only the refusal. A failed model fit already arrives as one
        # (four_way_ratio converts the solver's ValueError / LinAlgError
        # itself, which is where that decision belongs); anything else
        # reaching here is not a refusal, and a supplementary block that
        # vanishes is how it would go unnoticed.
        return

    def _p(pt, lo, hi) -> dict:
        return {"point": pt, "ci_lower": lo, "ci_upper": hi}

    block: dict[str, object] = {
        "mediator_scale": est.mediator_scale,
        "err_cde": _p(est.err_cde_point, est.err_cde_ci_lower, est.err_cde_ci_upper),
        "err_intref": _p(est.err_intref_point, est.err_intref_ci_lower, est.err_intref_ci_upper),
        "err_intmed": _p(est.err_intmed_point, est.err_intmed_ci_lower, est.err_intmed_ci_upper),
        "err_pie": _p(est.err_pie_point, est.err_pie_ci_lower, est.err_pie_ci_upper),
        "total_err": _p(est.total_err_point, est.total_err_ci_lower, est.total_err_ci_upper),
        "total_rr": _p(est.total_rr_point, est.total_rr_ci_lower, est.total_rr_ci_upper),
        "prop_mediated": _p(est.prop_mediated_point, est.prop_mediated_ci_lower, est.prop_mediated_ci_upper),
        "prop_interaction": _p(est.prop_interaction_point, est.prop_interaction_ci_lower, est.prop_interaction_ci_upper),
        "prop_eliminated": _p(est.prop_eliminated_point, est.prop_eliminated_ci_lower, est.prop_eliminated_ci_upper),
        "reference": (
            "VanderWeele 2014 eAppendix §3.4 (binary mediator) / §3.3 "
            "(continuous mediator); excess relative risk = CDE + INTref + "
            "INTmed + PIE"
        ),
    }
    if est.ss_m is not None:
        block["mediator_residual_variance"] = est.ss_m
    # Record the fitted coefficients the VanderWeele closed form was
    # evaluated at — the sufficient statistics verify_four_way_ratio
    # re-derives every err_* / prop_* from. Without them the ratio block
    # (the answer) would ride on a structurally_solved result with no
    # numeric audit at all.
    block["coefficients"] = {
        "t1": est.t1, "t2": est.t2, "t3": est.t3,
        "b0": est.b0, "b1": est.b1, "bcc": est.bcc,
        "mediator_reference": _reference_level_as_number(est.mediator_reference),
    }
    # This block's OWN draws, not the mediation estimate's: it is a second
    # bootstrap, capped separately above, and a reader told the enclosing
    # estimate used 480 of 500 would be reading it about the wrong loop.
    if est.draws is not None:
        block["bootstrap"] = est.draws.record(cluster=est.cluster)
    ne["four_way_ratio"] = block


def _try_joint_estimate(
    q_stmt, result: dict, contract, graph, bidirected,
    *, joint_sets, vector_iv_candidates, vector_instruments,
    random_state: int, ci_bootstrap: int, model: str,
    cluster: str | None = None,
) -> Claim:
    """Joint multi-treatment effect estimate: do(A=a, B=b, ...).

    Re-derives the joint (treatment-set) back-door adjustment set, fits
    the joint g-formula (outcome regression with the A:B interaction),
    and attaches a ``numeric_estimate`` with a ``joint_effect`` block AND
    an ``interaction`` block (additive scale). Mirrors the backdoor
    numeric path: status flips to numerically_solved with an independent
    joint derivation the verifier re-checks.

    Latent (bidirected) confounding is supported when the joint effect is
    adjustment-identifiable: ``minimal_adjustment_sets_joint`` returns a
    valid ADMG adjustment set (m-separation) and the g-formula plug-in
    standardizes over it exactly as in the DAG case. A latent joint effect
    with no valid adjustment set returns no set → silent no-op below.

    Silent no-op (leaves the structural result untouched) when:
    - no joint adjustment set exists (incl. latent effects that are not
      adjustment-identifiable);
    - a treatment is non-binary (v1 scope);
    - the treatment vector has fewer than two distinct atoms, or more than
      the estimator's cap (NotImplementedError → honest capability gap,
      structural result stands);
    - the joint estimator refuses (EstimatorFailure → estimator_failure
      block, mirroring transport / dose-response).
    """
    from ..runtime import structural_solver
    from .joint import estimate_joint_effect

    q = q_stmt.query
    x_atom = q.intervention.atom
    y_atom = q.target.atom
    extra_atoms = tuple(iv.atom for iv in q.extra_interventions)
    treatment_atoms = (x_atom, *extra_atoms)
    given_atoms = tuple(g.atom for g in q.given)

    # v1 scope: K ≥ 2 distinct binary treatments, no mediator / transport.
    # A repeated atom is a malformed joint vector (handled honestly by the
    # structural dispatch); the K upper bound is enforced by the estimator
    # (NotImplementedError, caught below).
    if q.mediator is not None or q.target_population is not None:
        return blocked('combination_out_of_scope')
    if len(set(treatment_atoms)) < 2 or len(set(treatment_atoms)) != len(treatment_atoms):
        return blocked('combination_out_of_scope')

    if not joint_sets:
        # Adjustment fails — but the joint effect may still be point-
        # identified by the set-valued Shpitser-Pearl ID (latent confounding
        # neutralized with NO adjustment set). Try the joint general-ID
        # plug-in as the escape layer, mirroring the single-treatment
        # general-ID fallback. Unconditional only (v1). Purely additive: a
        # no-op leaves the structural refusal (joint_not_identifiable)
        # standing byte-identical.
        general_id_answered = False
        if not given_atoms:
            general_id_answered = _try_joint_general_id_estimate(
                result, contract, graph, bidirected,
                treatment_atoms=treatment_atoms, y_atom=y_atom,
                random_state=random_state, ci_bootstrap=ci_bootstrap,
                cluster=cluster,
            ).answered
        # Second escape on the same ladder: instruments valid for the whole
        # vector give an Anderson-Rubin confidence REGION for the coefficient
        # vector — an answer where general-ID had none, under linearity.
        # Inline for the reason the general-ID escape is: this row owns a
        # SHAPE of query, and every route below it in the table is written
        # for a single treatment, so passing the query down would offer a
        # joint question to rows that answer about one treatment.
        region_answered = False
        if vector_instruments and not general_id_answered:
            region_answered = _try_vector_iv_estimate(
                result, contract, graph,
                treatments=treatment_atoms, y=y_atom,
                candidates=vector_iv_candidates,
                instruments=vector_instruments,
                cluster=cluster,
            ).answered
        if region_answered:
            return answered()
        return blocked('design_unavailable')

    chosen = min(joint_sets, key=len)
    adjustment_names = tuple(a.predicate for a in _topo_order(graph, chosen))
    treatment_names = tuple(t.predicate for t in treatment_atoms)
    outcome_name = y_atom.predicate

    df = contract.data
    if any(t not in df.columns for t in treatment_names):
        return blocked('required_columns_absent')
    if outcome_name not in df.columns:
        return blocked('required_columns_absent')
    if not all(_is_binary_treatment(df, t) for t in treatment_names):
        return blocked('design_unavailable')

    # Treated cell = the query's intervention values; control cell = the
    # binary baseline (all-False / 0). Joint contrast is do(treated) −
    # do(control).
    iv_value_by_pred = {x_atom.predicate: q.intervention.value}
    for iv in q.extra_interventions:
        iv_value_by_pred[iv.atom.predicate] = iv.value
    treated_values = {t: iv_value_by_pred[t] for t in treatment_names}
    control_values = {t: False for t in treatment_names}

    try:
        estimate = estimate_joint_effect(
            df,
            treatments=treatment_names,
            outcome=outcome_name,
            adjustment=adjustment_names,
            treated_values=treated_values,
            control_values=control_values,
            ci_bootstrap=ci_bootstrap,
            random_state=random_state,
            model=model,  # type: ignore[arg-type]
            cluster=cluster if (cluster is None or cluster in df.columns) else None,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="joint_backdoor", exc=exc)
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "method": estimate.method,
        "ci_level": estimate.ci_level,
        "assumptions": list(estimate.assumptions),
        "sample_size": estimate.sample_size,
        "data_hash": estimate.data_hash,
        "data_columns": list(estimate.data_columns),
        "adjustment": list(estimate.adjustment),
        "treatments": list(estimate.treatments),
        "treatment": x_atom.predicate,   # primary; schema-required slot
        "outcome": estimate.outcome,
        "joint_effect": {
            "point": estimate.joint_point,
            "ci_lower": estimate.joint_ci_lower,
            "ci_upper": estimate.joint_ci_upper,
            "treated": {k: bool(v) for k, v in estimate.treated},
            "control": {k: bool(v) for k, v in estimate.control},
        },
    }
    _attach_mechanism_audit(result, estimate, target=estimate.outcome)
    _attach_interaction(result["numeric_estimate"], estimate)
    # Cluster-bootstrap provenance (both the joint contrast and the
    # interaction ride the same clustered resample). No-op when i.i.d.,
    # keeping the cluster=None surface byte-identical.
    _attach_bootstrap_meta(result["numeric_estimate"], estimate.cluster, estimate.draws)
    _attach_precision_budget_joint(result["numeric_estimate"])

    result["derivation"] = _build_joint_numeric_derivation_dict(
        graph=graph,
        treatments=treatment_atoms,
        y=y_atom,
        adjustment=chosen,
        given=frozenset(given_atoms),
        estimate=estimate,
    )
    _finalise_numeric_result(result)
    return answered()


def _build_joint_numeric_derivation_dict(
    *, graph, treatments, y, adjustment, given, estimate,
):
    """Two-step derivation for a data-based joint effect estimate:

        s1: joint_backdoor_criterion (structural witness, treatment set)
        s2: numeric_joint_backdoor_estimate (metadata audit — no re-fit)
    """
    from ..types import DerivationStep, StepRef, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    treatments_set = frozenset(treatments)
    # An absent interaction is declared, not merely missing: the audit must
    # be able to tell "no number because the corners were empty" from "no
    # number because someone dropped it on the way out".
    if estimate.interaction_point is not None:
        interaction_inputs = {
            "interaction_point": estimate.interaction_point,
            "interaction_ci_lower": estimate.interaction_ci_lower,
            "interaction_ci_upper": estimate.interaction_ci_upper,
        }
    else:
        interaction_inputs = {
            "interaction_unavailable": estimate.interaction_unavailable,
        }
    steps = (
        DerivationStep(
            rule="joint_backdoor_criterion",
            inputs={
                "graph": graph,
                "treatments": treatments_set,
                "y": y,
                "z": frozenset(adjustment),
                "given": given,
            },
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="numeric_joint_backdoor_estimate",
            inputs={
                "criterion": StepRef(step_id="s1"),
                "treatments": treatments_set,
                "outcome": y,
                "adjustment": frozenset(adjustment),
                "method": estimate.method,
                "data_hash": estimate.data_hash,
                "sample_size": estimate.sample_size,
                "joint_point": estimate.joint_point,
                "joint_ci_lower": estimate.joint_ci_lower,
                "joint_ci_upper": estimate.joint_ci_upper,
                **interaction_inputs,
                "ci_level": estimate.ci_level,
            },
            output=StructuralResult(value=True),
            step_id="s2",
        ),
    )
    return derivation_to_dict(steps)


def _attach_e_value_if_binary(
    result: dict, contract, outcome: str, treatment: str,
) -> None:
    """Phase 8.2 — compute the E-value sensitivity for the
    result's numeric estimate and attach it under
    ``numeric_estimate.sensitivity_analysis``.

    Two paths:
    - **Binary outcome**: VanderWeele-Ding 2017 — convert ATE to RR
      via observed baseline rate.
    - **Continuous outcome**: Chinn 2000 — convert ATE to
      SMD via outcome SD, then RR ≈ exp(0.91·SMD), then E-value.

    Mediation results carry a ``decomposition`` block rather than a
    flat ``point`` — for those we attach the E-value to the TE
    component (the most directly comparable summary).

    Function name kept for backward compatibility; the ``_if_binary``
    suffix predates the continuous-outcome extension. Behaviour is now
    "if outcome is dispatchable" (binary OR continuous with finite SD).
    """
    import pandas as pd
    from .sensitivity import (
        e_value_from_ate_binary,
        e_value_from_ate_continuous,
    )

    estimate = result.get("numeric_estimate")
    if estimate is None:
        return

    df = contract.data
    if outcome not in df.columns:
        return

    outcome_series = df[outcome]
    # bool-vs-not is the whole partition: the contract leaves every model
    # column as bool or float64. A third arm keyed on is_numeric_dtype asks a
    # question the contract has already answered, so it can never run.
    is_binary = pd.api.types.is_bool_dtype(outcome_series)

    if "decomposition" in estimate:
        te = estimate["decomposition"]["te"]
        ate = te["point"]
        ci_bound = _closer_to_null(te["ci_lower"], te["ci_upper"])
    else:
        ate = estimate.get("point")
        if ate is None:
            return
        ci_bound = _closer_to_null(
            estimate.get("ci_lower"), estimate.get("ci_upper"))

    outcome_sd = None
    if is_binary:
        treated_mask = df[treatment].to_numpy().astype(bool)
        if treated_mask.all() or (~treated_mask).all():
            return  # no untreated arm — can't compute baseline rate
        baseline_rate = float(df.loc[~treated_mask, outcome].mean())
        e_result = e_value_from_ate_binary(
            ate=ate, baseline_rate=baseline_rate, ci_bound=ci_bound,
        )
        path = "binary"
    else:
        outcome_sd = float(outcome_series.std(ddof=1))
        if outcome_sd <= 0 or not (outcome_sd == outcome_sd):  # NaN-safe
            return
        e_result = e_value_from_ate_continuous(
            ate=ate, outcome_sd=outcome_sd, ci_bound=ci_bound,
        )
        path = "continuous"

    # Record the conversion INPUTS (path + baseline_rate / outcome_sd) next to
    # the outputs so the verifier can re-derive the risk ratio and BOTH
    # E-values from first principles — pairing them with the audited headline
    # ATE — without needing the DataFrame. Same reason the OVB block records
    # the raw t-value + dof rather than only the robustness value.
    block: dict = {
        "e_value": e_result.e_value,
        "e_value_ci_bound": e_result.e_value_ci_bound,
        "risk_ratio": e_result.risk_ratio,
        "baseline_rate": e_result.baseline_rate,
        "outcome_sd": outcome_sd,
        "path": path,
        "interpretation_band": e_result.interpretation_band,
        "band_basis": e_result.band_basis,
    }
    if e_result.undefined_because is not None:
        block["undefined_because"] = e_result.undefined_because
    estimate["sensitivity_analysis"] = block


def _nan_to_none(x):
    """JSON has no NaN; a void benchmark's adjusted_* are NaN → null."""
    return None if (x is None or x != x) else float(x)


def _attach_ovb_sensitivity(
    result: dict, contract, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], method: str,
) -> None:
    """Cinelli-Hazlett omitted-variable-bias sensitivity — the
    regression-scale complement to the E-value, attached under
    ``numeric_estimate.ovb_sensitivity``.

    Only for ``backdoor_linear`` (the OLS coefficient framework the
    robustness value / partial R² / bias bounds are defined on). It is a
    closed form of the fit's t-value + residual dof, so the block records
    those raw statistics and the per-covariate partial R²s, letting the
    verifier re-derive every number from first principles. Never allowed
    to break the main estimate — any failure just skips the block.
    """
    if method != "backdoor_linear":
        return
    estimate = result.get("numeric_estimate")
    if estimate is None:
        return
    from .sensitivity_ovb import estimate_ovb_sensitivity

    try:
        s = estimate_ovb_sensitivity(
            contract.data, treatment=treatment, outcome=outcome,
            adjustment=adjustment,
        )
    except Exception:
        # Singular design, missing column, degenerate fit — sensitivity
        # is supplementary; leave the point estimate untouched.
        return

    estimate["ovb_sensitivity"] = {
        "estimate": s.estimate,
        "se": s.se,
        "t_statistic": s.t_statistic,
        "dof": s.dof,
        "q": s.q,
        "alpha": s.alpha,
        "partial_r2": s.partial_r2,
        "robustness_value_q": s.robustness_value_q,
        "robustness_value_qa": s.robustness_value_qa,
        "benchmarks": [
            {
                "covariate": b.covariate,
                "kd": b.kd,
                "ky": b.ky,
                "r2dxj_x": b.r2dxj_x,
                "r2yxj_dx": b.r2yxj_dx,
                "r2dz_x": b.r2dz_x,
                "r2yz_dx": b.r2yz_dx,
                "adjusted_estimate": _nan_to_none(b.adjusted_estimate),
                "adjusted_se": _nan_to_none(b.adjusted_se),
                "adjusted_t": _nan_to_none(b.adjusted_t),
                "valid": b.valid,
            }
            for b in s.benchmarks
        ],
    }


def _try_transport_estimate(
    q_stmt, result: dict, contract, program,
    *, random_state: int, ci_bootstrap: int, ci_level: float,
    cluster: str | None = None,
) -> Claim:
    """Phase 9 §T9.2 — numeric transport via post-stratification.

    Runs ``estimate_transport`` when:
    1. result.extensions.transport_identification is present (Phase 9
       §T9.1 already produced structural identification with adjustment_set)
    2. program.extensions.target_marginal is supplied
    3. data has the required columns

    Mutates ``result`` in place: adds ``numeric_estimate`` with the
    transport_post_stratification method. Status remains
    structurally_solved unless the post-stratification numeric path
    succeeds, in which case it flips to numerically_solved alongside
    the structural derivation.

    Failures (missing target_marginal / missing data column / empty
    stratum) are silent — the structural transport result remains
    valid; the numeric layer just doesn't attach.
    """
    from .transport import estimate_transport

    transport_block = (result.get("extensions") or {}).get(blocks.Block.TRANSPORT_IDENTIFICATION)
    if not isinstance(transport_block, dict):
        return blocked('identification_chose_another_strategy')
    # A transporting route per source domain, and the DataFrame is ONE
    # source's data with nothing on it saying which. So this path runs
    # when exactly one domain transports and the choice is not a choice;
    # with several it declines rather than picking, because picking would
    # be reading the wrong population's strata as if they were the right
    # one. The structural answer, which names every route, stands either
    # way (#326).
    routes = [
        r for r in (transport_block.get("sources") or [])
        if isinstance(r, dict) and r.get("transportable")
    ]
    if len(routes) != 1:
        return blocked('design_unavailable')
    adjustment_atoms = routes[0].get("adjustment_set") or []
    if not adjustment_atoms:
        return blocked('design_unavailable')
    names: list[str] = []
    for atom in adjustment_atoms:
        if not isinstance(atom, dict):
            continue
        predicate = atom.get("predicate")
        if not isinstance(predicate, str) or not predicate:
            # The block is the identification layer's own output, where an
            # adjustment entry is an atom and an atom has a predicate. An
            # entry that names no column is a broken design, not a missing
            # column, so it refuses here rather than downstream.
            return blocked('design_unavailable')
        names.append(predicate)
    if not names:
        return blocked('design_unavailable')
    adjustment_names = tuple(names)

    program_extensions = _extract_program_extensions(program)
    target_marginal = program_extensions.get("target_marginal")
    if not isinstance(target_marginal, dict):
        return blocked('design_unavailable')
    target_marginal = _coerce_target_marginal_keys(target_marginal)

    treatment = q_stmt.query.intervention.atom.predicate
    outcome = q_stmt.query.target.atom.predicate

    df = contract.data
    if treatment not in df.columns or outcome not in df.columns:
        return blocked('required_columns_absent')
    if not all(name in df.columns for name in adjustment_names):
        return blocked('required_columns_absent')

    try:
        estimate = estimate_transport(
            df,
            treatment=treatment,
            outcome=outcome,
            adjustment=adjustment_names,
            target_marginal=target_marginal,
            ci_bootstrap=ci_bootstrap,
            ci_level=ci_level,
            random_state=random_state,
            cluster=cluster if (cluster is None or cluster in df.columns) else None,
        )
    except EstimatorFailure as exc:
        # Which refusal this is comes from the estimator, which knew. It
        # used to be reconstructed here by looking for a phrase in the
        # message, and the phrase only matched one of the two positivity
        # guards — the other arrived under the catch-all species this
        # package no longer has, telling a caller their request was
        # malformed when what had happened was that their source data held
        # no contrast in a stratum the target marginal weights.
        refusals.record(result, estimator="transport_post_stratification",
                        exc=exc)
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "point": estimate.point,
        "ci_lower": estimate.ci_lower,
        "ci_upper": estimate.ci_upper,
        "ci_level": estimate.ci_level,
        "method": estimate.method,
        "assumptions": list(estimate.assumptions),
        "sample_size": estimate.source_sample_size,
        "data_hash": estimate.data_hash,
        "data_columns": list(estimate.data_columns),
        "adjustment": list(estimate.adjustment),
        "treatment": estimate.treatment,
        "outcome": estimate.outcome,
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, estimate.draws)
    _attach_precision_budget(result["numeric_estimate"])
    _attach_mechanism_audit(result, estimate, target=estimate.outcome)
    # Flip status to numerically_solved AND reconcile the gap report so it
    # no longer ships the pre-data transport data-need gaps next to the
    # computed number (mirrors backdoor / front-door). The structural
    # transport derivation (s_admissibility_check / transport_formula /
    # identify_via_transport) is preserved — the verifier accepts that
    # terminal for a transport-numeric result.
    _finalise_numeric_result(result)
    return answered()


def _coerce_target_marginal_keys(target_marginal: dict) -> dict:
    """Normalise the stratum-weight keys of a target marginal to bool.

    JSON object keys are always strings, so a target marginal supplied via
    a JSON program arrives as ``{"true": .7, "false": .3}`` while
    ``estimate_transport`` keys the stratum weights on bool ``{True: .7,
    False: .3}``. Without this, the JSON path raised "marginal must sum to
    1" (the bool lookups missed) and produced no number. Coerce string
    boolean keys back to bool so the JSON and in-process paths behave
    identically; already-bool and non-boolean keys pass through unchanged.
    """
    marginal = target_marginal.get("marginal")
    if not isinstance(marginal, dict):
        return target_marginal
    coerced: dict = {}
    for k, v in marginal.items():
        if isinstance(k, bool):
            coerced[k] = v
        elif isinstance(k, str) and k.strip().lower() in ("true", "false"):
            coerced[k.strip().lower() == "true"] = v
        else:
            coerced[k] = v
    return {**target_marginal, "marginal": coerced}


def _collect_selection_observation_values(prog) -> dict:
    """Map each ObservationStatement predicate → its observed value.

    These are the values that define "selected" for the selection-bias
    recovery estimator (it restricts the biased sample to S = selected)."""
    from ..types import ObservationStatement
    out: dict = {}
    for st in getattr(prog, "statements", ()):
        if isinstance(st, ObservationStatement):
            out[st.atom.predicate] = st.value
    return out


def _try_selection_recovery_estimate(
    q_stmt, result: dict, contract, reference_data, selection_values: dict,
    *, random_state: int, ci_bootstrap: int, cluster: str | None = None,
) -> Claim:
    """§S9.1 numeric end + honest gate for selection bias.

    Fires when the result carries a ``selection_recovery`` block (the sample is
    restricted on a selection collider). Three outcomes, none of which is a
    silently-biased back-door number:

    - NOT recoverable via SBD → ``estimator_failure`` (no number); the
      structural non-recoverability verdict stands.
    - Recoverable but the required external unbiased data was not supplied
      (no ``reference_data``) → ``estimator_failure`` naming exactly the
      external data the ledger demands. This is the bug fix: the ordinary
      back-door point on the biased sample is withheld, not shipped.
    - Recoverable AND ``reference_data`` supplied → evaluate the Theorem-3.5
      recovery formula, attach the recovered ``numeric_estimate``, flip to
      numerically_solved.
    """
    from .selection import estimate_selection_recovery

    block = (result.get("extensions") or {}).get(blocks.Block.SELECTION_RECOVERY) or {}
    x = q_stmt.query.intervention.atom.predicate
    y = q_stmt.query.target.atom.predicate

    if not block.get("recoverable"):
        result["estimator_failure"] = refusals.block(
            estimator="selection_backdoor_recovery",
            failure_type=Refusal.NOT_RECOVERABLE,
            details={"estimand": f"P({y}|do({x}))",
                     "mechanism": refusals.Recovery.FROM_SELECTION},
            recorded={"identification_reason": block.get("failure_reason")},
        )
        return blocked('not_identified')

    external = list(block.get("external_data_needed") or [])
    z_plus = tuple(block.get("z_plus") or ())
    z_minus = tuple(block.get("z_minus") or ())
    selection_nodes = tuple(block.get("selection_nodes") or ())

    if reference_data is None:
        # Recoverable only with external unbiased data we don't have. Refuse —
        # the biased back-door number would be silently wrong.
        # What is missing, as the statements the block already carries.
        # A hole holds a list and the seam between its items belongs to
        # whoever is reading; this was `"; ".join(...)`, which is a kernel
        # picking the reader's punctuation around sentences it had
        # rendered. The stand-in when the ledger names nothing specific is
        # a member of the same set rather than a phrase written here.
        from ..runtime.selection_recovery import External
        need = list(external) or [_lang.state(External.THE_WEIGHTS)]
        result["estimator_failure"] = refusals.block(
            estimator="selection_backdoor_recovery",
            failure_type=Refusal.EXTERNAL_DATA_REQUIRED,
            details={"exposure": x, "outcome": y, "needed": need},
            remedies=[(refusals.Remedy.SUPPLY_INPUT, "reference_data=")],
        )
        return blocked('design_unavailable')

    sel_vals = {s: selection_values.get(s, True) for s in selection_nodes}
    try:
        est = estimate_selection_recovery(
            contract.data, reference_data,
            treatment=x, outcome=y,
            z_plus=z_plus, z_minus=z_minus,
            selection_nodes=selection_nodes, selected_values=sel_vals,
            ci_bootstrap=ci_bootstrap, random_state=random_state,
            cluster=cluster if (cluster is None or cluster in contract.data.columns) else None,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="selection_backdoor_recovery", exc=exc)
        return blocked('estimator_refused')
    except (ValueError, KeyError) as exc:
        result["estimator_failure"] = refusals.block(
            estimator="selection_backdoor_recovery",
            failure_type=Refusal.UNKNOWN,
            recorded={"diagnostic": str(exc)},
        )
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": est.method,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "adjustment": list(est.z_plus) + list(est.z_minus),
        "treatment": est.treatment,
        "outcome": est.outcome,
        # selection-backdoor recovery detail (audit trail + verifier inputs)
        "selection_recovery_numeric": {
            "reference_sample_size": est.reference_sample_size,
            "reference_data_hash": est.reference_data_hash,
            "reference_data_columns": list(est.reference_data_columns),
            "z_plus": list(est.z_plus),
            "z_minus": list(est.z_minus),
            "selected_values": est.selected_values,
            "mu_treated": est.mu_treated,
            "mu_control": est.mu_control,
            "form": est.form,
            "sufficient_statistics": est.sufficient_statistics,
        },
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, est.draws)
    _attach_mechanism_audit(result, est, target=est.outcome)
    _finalise_numeric_result(result)
    return answered()


def _refuse_without_back_door(
    result: dict, *, estimator: str, x_atom, y_atom,
    front_door_sets, iv_candidates,
) -> None:
    """No back-door set, said as the two different pieces of news it is.

    Four rows of this family stopped on ``if not adjustment_sets`` and filed
    one species for it. Two facts live under that test. The graph may still
    identify the effect another way, and then what is missing is a route this
    package has not built this correction onto — an honest gap, and the
    reader's move is to ask for the number the other route gives. Or the graph
    may identify it no way at all, and then no correction in this family is
    reachable, no amount of the same data changes that, and what has to change
    is the graph or the question.

    The fifth row already had all three facts and already said the second one
    in prose — under the first one's species, which is what made the species'
    kind a claim it had no evidence for.

    Writes the block and hands the Claim back to the row. What the row claims
    is about the cascade — whether the query is still in flight — and that is
    the row's to say; which of the two facts stopped it is what has to have
    one author.
    """
    identified = bool(front_door_sets or iv_candidates)
    result["estimator_failure"] = refusals.block(
        estimator=estimator,
        failure_type=(Refusal.REQUIRES_BACKDOOR_IDENTIFICATION if identified
                      else Refusal.NO_IDENTIFYING_DESIGN),
        details={"exposure": x_atom.predicate, "outcome": y_atom.predicate},
    )


def _try_measurement_correction_estimate(
    q_stmt, result: dict, contract, graph, *,
    adjustment_sets, front_door_sets, iv_candidates, given, spec: dict,
    random_state: int, ci_bootstrap: int, cluster: str | None = None,
) -> Claim:
    """Frontier E numeric end + honest gate for a misclassified outcome.

    Fires when the caller supplied a validated confusion matrix for this
    query's outcome. Two outcomes, neither a silently-attenuated back-door
    number:

    - Not back-door identified, or the correction refuses (singular / non-
      stochastic matrix, positivity, non-binary treatment) → ``estimator_
      failure`` (no number); the caller asked for the corrected point, so the
      biased naive g-formula is withheld, not shipped.
    - Back-door identified AND the correction succeeds → invert the confusion
      matrix per stratum, attach the de-attenuated ``numeric_estimate`` (with
      the naive point kept for contrast), flip to numerically_solved.
    """
    from .measurement import estimate_measurement_correction

    x_atom = q_stmt.query.intervention.atom
    y_atom = q_stmt.query.target.atom
    target_value = q_stmt.query.target.value

    if not adjustment_sets:
        _refuse_without_back_door(
            result, estimator="measurement_error_correction", x_atom=x_atom, y_atom=y_atom,
            front_door_sets=front_door_sets, iv_candidates=iv_candidates)
        return blocked('design_unavailable')

    chosen = min(adjustment_sets, key=len)
    adjustment_names = tuple(a.predicate for a in _topo_order(graph, chosen))

    try:
        est = estimate_measurement_correction(
            contract.data,
            treatment=x_atom.predicate, outcome=y_atom.predicate,
            adjustment=adjustment_names,
            confusion_matrix=spec.get("confusion_matrix"),
            states=spec.get("states"),
            target_value=(
                spec["target_value"] if "target_value" in spec else target_value
            ),
            differential=bool(spec.get("differential", False)),
            differential_by=spec.get("differential_by"),
            confusion_matrices=spec.get("confusion_matrices"),
            differential_levels=spec.get("differential_levels"),
            ci_bootstrap=ci_bootstrap, ci_level=0.95,
            random_state=random_state,
            cluster=cluster if (cluster is None or cluster in contract.data.columns) else None,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="measurement_error_correction", exc=exc)
        return blocked('estimator_refused')
    except (ValueError, KeyError, TypeError) as exc:
        result["estimator_failure"] = refusals.block(
            estimator="measurement_error_correction",
            failure_type=Refusal.UNKNOWN,
            recorded={"diagnostic": str(exc)},
        )
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": est.method,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "adjustment": list(est.adjustment),
        "treatment": est.treatment,
        "outcome": est.outcome,
        # Confusion-matrix correction detail (audit trail + verifier inputs).
        # The matrix + per-stratum value-count vectors don't fit derivation-
        # input serialization, so they live here and are re-inverted by
        # verify_measurement_correction_numeric (kernel-called).
        "measurement_correction": _measurement_correction_block(est),
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, est.draws)
    _attach_precision_budget(result["numeric_estimate"])

    _attach_mechanism_audit(
        result, est, target=f"P({est.outcome}={est.target_value}|do({est.treatment}))",
    )

    result["derivation"] = _build_measurement_correction_derivation_dict(
        graph=graph, x=x_atom, y=y_atom, adjustment=chosen,
        given=frozenset(given), estimate=est,
    )
    _finalise_numeric_result(result)
    return answered()


def _measurement_correction_block(est) -> dict:
    """The ``measurement_correction`` audit/verifier block for an outcome-,
    exposure- or both-sided estimate, differential or not. Under differential
    misclassification the single ``confusion_matrix`` / ``det`` are replaced by
    the per-level ``confusion_matrices`` the inversion actually used; a combined
    (both-channel) estimate carries one matrix per channel and is non-
    differential by construction.

    A matrix counted in a validation study carries that study's tally beside
    it, wherever the matrix itself sits — taken from the estimate's own
    sufficient statistics rather than restated here, because a tally and the
    matrix it normalises to are one declaration and a block that could carry
    one without the other is a block where they can disagree."""
    counted = est.sufficient_statistics
    block = {
        "naive_point": est.naive_point,
        "out_of_simplex": est.out_of_simplex,
        "states": list(est.states),
        "target_value": est.target_value,
        "differential": bool(getattr(est, "differential", False)),
        "form": est.form,
        "sufficient_statistics": est.sufficient_statistics,
    }
    # The risk at each exposure level — what the corrected contrasts are read
    # off. Recorded for every side, including the outcome side (where it is the
    # two arms), so one audit block does not describe two different things.
    risks = getattr(est, "risks", ())
    if risks:
        block["risks"] = [float(v) for v in risks]
        block["naive_risks"] = [float(v) for v in est.naive_risks]
    form = getattr(est, "form", "")
    if form.startswith("combined"):
        # Two channels, so neither a single `confusion_matrix` nor a single
        # `det` is meaningful — each matrix is named by the channel it inverts.
        block["side"] = "combined"
        block["outcome_states"] = list(est.outcome_states)
        block["confusion_matrix_exposure"] = [
            list(row) for row in est.exposure_confusion_matrix
        ]
        block["confusion_matrix_outcome"] = [
            list(row) for row in est.outcome_confusion_matrix
        ]
        block["det_exposure"] = est.det_exposure
        block["det_outcome"] = est.det_outcome
        block["det_joint"] = est.det_joint
        for side in ("exposure", "outcome"):
            tally = counted.get(f"{side}_validation_counts")
            if tally is not None:
                block[f"{side}_validation_counts"] = tally
        return block
    if form.startswith("exposure"):
        block["side"] = "exposure"
        block["outcome_states"] = list(est.outcome_states)
    if est.differential:
        block["confusion_matrices"] = [dict(r) for r in est.confusion_matrices]
        if getattr(est, "differential_by", None) is not None:
            block["differential_by"] = est.differential_by
    else:
        block["det"] = est.det
        block["confusion_matrix"] = [list(row) for row in est.confusion_matrix]
        tally = counted.get("validation_counts")
        if tally is not None:
            block["validation_counts"] = tally
    return block


def _attach_exposure_dose_response(numeric_estimate: dict, est) -> None:
    """Attach the per-level curve when a misclassified exposure has more than
    two levels, and say so where the reader looks for the reference.

    Absent for a binary exposure: its curve would be one entry restating
    ``point``, and the shape declaration in :mod:`themis.answers` is about what
    a METHOD can produce, not what this run did — ``dose_response_curve``'s own
    ``detect`` is what decides which shape came out.
    """
    if est.point is None:
        # Absent, not null. ``point`` carries "the estimand's number", and the
        # shape detector reads its presence; a null would be a key claiming
        # there is a point whose value happens to be nothing, and the schema's
        # dependentRequired would then demand two interval bounds for it.
        for key in ("point", "ci_lower", "ci_upper"):
            numeric_estimate.pop(key, None)

    curve = getattr(est, "dose_response_curve", ())
    if not curve:
        return
    numeric_estimate["dose_response_curve"] = [
        {
            "x": point["level"],
            "effect": point["point"],
            "ci_lower": point["ci_lower"],
            "ci_upper": point["ci_upper"],
        }
        for point in curve
    ]
    numeric_estimate["reference_point"] = est.states[0]


def _try_exposure_measurement_correction_estimate(
    q_stmt, result: dict, contract, graph, *,
    adjustment_sets, front_door_sets, iv_candidates, given, spec: dict,
    random_state: int, ci_bootstrap: int, cluster: str | None = None,
) -> Claim:
    """Frontier E numeric end + honest gate for a misclassified binary EXPOSURE.

    Fires when the caller supplied a validated confusion matrix for this query's
    exposure. Mirrors the outcome handler; two outcomes, neither a silently-
    attenuated back-door number:

    - Not back-door identified, or the correction refuses (singular / non-
      stochastic matrix, positivity, non-binary exposure, degenerate recovered
      exposure) → ``estimator_failure`` (no number); the caller asked for the
      corrected point, so the biased naive back-door number is withheld.
    - Back-door identified AND the correction succeeds → invert the confusion
      matrix on the exposure margin per stratum, attach the de-attenuated
      ``numeric_estimate`` (with the naive point kept for contrast), flip to
      numerically_solved.
    """
    from .measurement import estimate_exposure_measurement_correction

    x_atom = q_stmt.query.intervention.atom
    y_atom = q_stmt.query.target.atom
    target_value = q_stmt.query.target.value

    if not adjustment_sets:
        _refuse_without_back_door(
            result, estimator="exposure_measurement_error_correction", x_atom=x_atom, y_atom=y_atom,
            front_door_sets=front_door_sets, iv_candidates=iv_candidates)
        return blocked('design_unavailable')

    chosen = min(adjustment_sets, key=len)
    adjustment_names = tuple(a.predicate for a in _topo_order(graph, chosen))

    try:
        est = estimate_exposure_measurement_correction(
            contract.data,
            treatment=x_atom.predicate, outcome=y_atom.predicate,
            adjustment=adjustment_names,
            confusion_matrix=spec.get("confusion_matrix"),
            states=spec.get("states"),
            target_value=(
                spec["target_value"] if "target_value" in spec else target_value
            ),
            differential=bool(spec.get("differential", False)),
            differential_by=spec.get("differential_by"),
            confusion_matrices=spec.get("confusion_matrices"),
            differential_levels=spec.get("differential_levels"),
            ci_bootstrap=ci_bootstrap, ci_level=0.95,
            random_state=random_state,
            cluster=cluster if (cluster is None or cluster in contract.data.columns) else None,
        )
    except EstimatorFailure as exc:
        refusals.record(
            result, estimator="exposure_measurement_error_correction", exc=exc)
        return blocked('estimator_refused')
    except (ValueError, KeyError, TypeError) as exc:
        result["estimator_failure"] = refusals.block(
            estimator="exposure_measurement_error_correction",
            failure_type=Refusal.UNKNOWN,
            recorded={"diagnostic": str(exc)},
        )
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": est.method,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "adjustment": list(est.adjustment),
        "treatment": est.treatment,
        "outcome": est.outcome,
        # Exposure confusion-matrix correction detail (audit trail + verifier
        # inputs). The matrix + per-stratum joint tables don't fit derivation-
        # input serialization, so they live here and are re-inverted by
        # verify_exposure_measurement_correction_numeric (kernel-called).
        "measurement_correction": _measurement_correction_block(est),
    }
    _attach_exposure_dose_response(result["numeric_estimate"], est)
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, est.draws)
    _attach_precision_budget(result["numeric_estimate"])

    _attach_mechanism_audit(
        result, est, target=f"P({est.outcome}={est.target_value}|do({est.treatment}))",
    )

    result["derivation"] = _build_measurement_correction_derivation_dict(
        graph=graph, x=x_atom, y=y_atom, adjustment=chosen,
        given=frozenset(given), estimate=est,
    )
    _finalise_numeric_result(result)
    return answered()


def _try_combined_measurement_correction_estimate(
    q_stmt, result: dict, contract, graph, *,
    adjustment_sets, front_door_sets, iv_candidates, given, spec_x: dict, spec_y: dict,
    random_state: int, ci_bootstrap: int, cluster: str | None = None,
) -> Claim:
    """Frontier E numeric end when BOTH channels are misclassified.

    Fires when the caller supplied a validated confusion matrix for this query's
    exposure AND its outcome. Neither single-channel correction may run in this
    situation — each would ship a point still carrying the other channel's bias
    — so the two inversions are composed on the same per-stratum (X, Y) joint.

    A DIFFERENTIAL matrix on either channel is refused rather than approximated:
    detection bias makes the outcome matrix depend on the true exposure and
    recall bias makes the exposure matrix depend on the true outcome, so the
    level that selects a matrix is the very quantity the other channel is
    mismeasuring and the observed table stops being a two-sided product.
    """
    from .measurement import estimate_combined_measurement_correction

    x_atom = q_stmt.query.intervention.atom
    y_atom = q_stmt.query.target.atom
    target_value = q_stmt.query.target.value

    if spec_x.get("differential") or spec_y.get("differential"):
        result["estimator_failure"] = refusals.block(
            estimator="combined_measurement_error_correction",
            failure_type=(
                Refusal.DIFFERENTIAL_COMBINED_MISCLASSIFICATION_DEFERRED),
            details={"exposure": x_atom.predicate,
                     "outcome": y_atom.predicate},
        )
        return blocked('design_unavailable')

    if not adjustment_sets:
        _refuse_without_back_door(
            result, estimator="combined_measurement_error_correction", x_atom=x_atom, y_atom=y_atom,
            front_door_sets=front_door_sets, iv_candidates=iv_candidates)
        return blocked('design_unavailable')

    chosen = min(adjustment_sets, key=len)
    adjustment_names = tuple(a.predicate for a in _topo_order(graph, chosen))

    try:
        est = estimate_combined_measurement_correction(
            contract.data,
            treatment=x_atom.predicate, outcome=y_atom.predicate,
            adjustment=adjustment_names,
            exposure_confusion_matrix=spec_x.get("confusion_matrix"),
            exposure_states=spec_x.get("states"),
            outcome_confusion_matrix=spec_y.get("confusion_matrix"),
            outcome_states=spec_y.get("states"),
            target_value=(
                spec_y["target_value"] if "target_value" in spec_y else target_value
            ),
            ci_bootstrap=ci_bootstrap, ci_level=0.95,
            random_state=random_state,
            cluster=cluster if (cluster is None or cluster in contract.data.columns) else None,
        )
    except EstimatorFailure as exc:
        refusals.record(
            result, estimator="combined_measurement_error_correction", exc=exc)
        return blocked('estimator_refused')
    except (ValueError, KeyError, TypeError) as exc:
        result["estimator_failure"] = refusals.block(
            estimator="combined_measurement_error_correction",
            failure_type=Refusal.UNKNOWN,
            recorded={"diagnostic": str(exc)},
        )
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": est.method,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "adjustment": list(est.adjustment),
        "treatment": est.treatment,
        "outcome": est.outcome,
        # Both matrices + per-stratum joint tables don't fit derivation-input
        # serialization, so they live here and are re-inverted by
        # verify_combined_measurement_correction_numeric (kernel-called).
        "measurement_correction": _measurement_correction_block(est),
    }
    _attach_exposure_dose_response(result["numeric_estimate"], est)
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, est.draws)
    _attach_precision_budget(result["numeric_estimate"])

    _attach_mechanism_audit(
        result, est, target=f"P({est.outcome}={est.target_value}|do({est.treatment}))",
    )

    result["derivation"] = _build_measurement_correction_derivation_dict(
        graph=graph, x=x_atom, y=y_atom, adjustment=chosen,
        given=frozenset(given), estimate=est,
    )
    _finalise_numeric_result(result)
    return answered()


def _try_berkson_error_price(
    result: dict, contract, graph, *,
    x_atom, y_atom, adjustment_sets, front_door_sets, iv_candidates,
    spec: dict,
) -> Claim:
    """Price what a declared BERKSON error cost the answer already given.

    An ANNOTATE row, and the role is the finding rather than a fact about
    where it was convenient to put it. Under Berkson error the truth
    scatters around the recorded nominal value, so ``E[X*|W,Z] = W`` and
    the ordinary back-door slope IS the causal slope. There is nothing to
    correct, and the correction is what would introduce the error — which
    is why the two continuous CORRECTION rows are guarded off a declared
    structure instead of dividing a right number through by a reliability
    ratio.

    After the answer, because the price is scaled by it: the scatter
    enters the residual as β̂²σ²_u, so a larger effect makes the same
    nominal-exposure error more expensive and there is no price before
    there is an effect.

    This row owns EVERY structure that is not ``classical``, its own
    included, and the reason is that the guard it shares with the two
    correction rows is a single fact read two ways. A word this package
    does not know keeps those rows off — the premise they correct under is
    exactly the one in doubt — and if it stopped there the declaration
    would reach no reader at all, on a result that looks in every other
    respect like one where nothing was declared. So an unrecognised
    structure is named here rather than dropped, and a query answered off
    the back door is told the price was not taken rather than left to
    infer it: the identity that saves the point is about a conditional
    mean of Y given the recorded exposure, and that is what a back-door
    answer is.
    """
    from .berkson import assess_berkson_error

    structure = spec.get("structure")
    if structure != STRUCTURE_BERKSON:
        result["estimator_failure"] = refusals.block(
            estimator="berkson_error",
            failure_type=Refusal.MALFORMED_ARGUMENT,
            details={
                "argument": f"measurement_error[{x_atom.predicate!r}]"
                            f"['structure']",
                "shape": f"one of {STRUCTURE_CLASSICAL!r}, "
                         f"{STRUCTURE_BERKSON!r}",
                "given": structure,
            },
        )
        return annotated()
    # Two premises that cannot both hold, and the row must not pick one. The
    # Berkson identity IS the independence of the error from the recorded
    # value; an error tracking the outcome is not independent of it, because
    # the outcome depends on the truth and the truth is the recorded value
    # plus that error. Pricing under one while the caller declared both would
    # be answering a question they did not ask.
    if spec.get("differential_coefficient") is not None:
        result["estimator_failure"] = refusals.block(
            estimator="berkson_error",
            failure_type=(
                Refusal.BERKSON_AND_DIFFERENTIAL_ARE_INCOMPATIBLE_PREMISES),
            details={"exposure": x_atom.predicate,
                     "coefficient": spec["differential_coefficient"]},
        )
        return annotated()
    if not adjustment_sets:
        _refuse_without_back_door(
            result, estimator="berkson_error",
            x_atom=x_atom, y_atom=y_atom,
            front_door_sets=front_door_sets, iv_candidates=iv_candidates,
        )
        return annotated()
    estimate = result.get("numeric_estimate")
    if not isinstance(estimate, dict) or estimate.get("point") is None:
        result["estimator_failure"] = refusals.block(
            estimator="berkson_error",
            failure_type=Refusal.REQUIRES_A_POINT_ESTIMATE,
            details={"exposure": x_atom.predicate,
                     "outcome": y_atom.predicate},
        )
        return annotated()

    chosen = min(adjustment_sets, key=len)
    adjustment_names = tuple(a.predicate for a in _topo_order(graph, chosen))

    try:
        assessment = assess_berkson_error(
            contract.data,
            treatment=x_atom.predicate, outcome=y_atom.predicate,
            adjustment=adjustment_names,
            treatment_coefficient=estimate["point"],
            error_variance=DeclaredVariance.from_spec(spec),
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="berkson_error", exc=exc)
        return annotated()
    except (ValueError, KeyError, TypeError) as exc:
        result["estimator_failure"] = refusals.block(
            estimator="berkson_error",
            failure_type=Refusal.UNKNOWN,
            recorded={"diagnostic": str(exc)},
        )
        return annotated()

    result["berkson_error"] = _berkson_block(assessment,
                                             source=spec.get("source"))
    return annotated()


def _berkson_block(assessment, *, source: object = None) -> dict:
    """The ``berkson_error`` block: the price and the moments behind it.

    Σ_D, Cov(D,Y), Var(Y), the design coefficients, σ²_u and β̂ — every
    scalar in the block is a closed-form function of those, so
    ``verify_berkson_error`` re-derives the whole of it without the data
    and without importing the estimator.
    """
    return {
        "exposure": assessment.exposure,
        "outcome": assessment.outcome,
        "design_vars": list(assessment.design_vars),
        "error_variance": assessment.error_variance,
        # The one quantity here that depends on the ANSWER, recorded rather
        # than left to be recomputed: it is what separates this price from
        # the outcome channel's, where the declared variance enters the
        # residual unscaled.
        "treatment_coefficient": assessment.treatment_coefficient,
        "scattered_variance": assessment.scattered_variance,
        "residual_variance": assessment.residual_variance,
        "signal_variance": assessment.signal_variance,
        "noise_share": assessment.noise_share,
        "se_inflation": assessment.se_inflation,
        # And what the study that measured the variance does to that
        # factor. Four keys rather than one, because the reader acts
        # on each: how far down it could be, how far up, whether
        # there IS an up, and how much of that study this data
        # already contradicts.
        "validation_df": assessment.validation_df,
        "se_inflation_lower": assessment.se_inflation_lower,
        "se_inflation_upper": assessment.se_inflation_upper,
        "inflation_refuted_share": assessment.inflation_refuted_share,
        "sample_size": assessment.sample_size,
        "data_hash": assessment.data_hash,
        "data_columns": list(assessment.data_columns),
        "assumptions": list(assessment.assumptions),
        "sufficient_statistics": assessment.sufficient_statistics,
        "source": source,
    }


def _simex_block(est) -> dict:
    """The ``simex`` audit/verifier block: the simulation ladder, the
    extrapolant's fitted coefficients, and the variance read off the same
    ladder.

    The ladder is what makes the block worth carrying rather than a trace
    of it. Only the FIRST of SIMEX's two stages is random, and its output
    is the second stage's sufficient statistic, so everything a reader is
    asked to believe downstream of the ladder — the coefficients, the
    point at λ = −1, the variance, the interval — is recomputed from what
    is written here by ``verify_simex_numeric``, without simulating
    anything and without importing the estimator.
    """
    return {
        "naive_point": est.naive_point,
        "outcome_model": est.outcome_model,
        # Whether the caller NAMED each lever, beside the value each lever
        # ended up at. The value alone cannot say: a defaulted "rational"
        # and a named one are the same string, and the ledger line that
        # offers the reader a lever to change is checked against this rather
        # than against its own reading of it.
        "outcome_model_was_declared": est.outcome_model_declared,
        "extrapolant": est.extrapolant,
        "extrapolant_was_declared": est.extrapolant_declared,
        "error_variance": est.error_variance,
        "exposure": est.treatment,
        "n_replicates": est.n_replicates,
        "random_state": est.random_state,
        "grid": [
            {
                "lambda": g.lam,
                "theta": g.theta,
                "replicate_variance": g.replicate_variance,
                "variance_mean": g.variance_mean,
                "replicates": g.replicates,
            }
            for g in est.grid
        ],
        "coefficients": list(est.coefficients),
        "variance_coefficients": list(est.variance_coefficients),
        "extrapolated_variance": est.extrapolated_variance,
        # Where the curve was read, and how much of the study reached past
        # where it can be. Both null when nobody said a study measured
        # σ²_u — which is the claim that λ = −1 is the reading point and
        # not a question with one answer.
        "validation_df": est.validation_df,
        "unreadable_share": est.unreadable_share,
        "no_interval_because": est.no_interval_because,
        "cluster": est.cluster,
        "form": est.form,
    }


def _try_simex_estimate(
    q_stmt, result: dict, contract, graph, *,
    adjustment_sets, front_door_sets, iv_candidates, given,
    spec: dict, covariate_specs: dict, outcome_model: str | None,
    random_state: int, cluster: str | None = None,
) -> Claim:
    """Numeric end for a continuously mismeasured exposure whose estimand
    the caller has placed in a NONLINEAR outcome model (SIMEX).

    Reachable only on that declaration. The moment correction one row
    below is an identity about a linear outcome; on a logistic one it does
    not compute a rougher version of this number, it computes a different
    one, and nothing in the data says which was wanted. So the caller
    names the model, and naming it is what routes here.

    Two outcomes, and the biased naive coefficient is not either of them:

    - Not back-door identified, a second mismeasured column named beside
      the exposure, or the correction refuses (non-positive σ²_u, a
      near-discrete exposure, an outcome that is not binary under
      ``logistic``, a grid that is not a ladder, a pole at λ = −1) →
      ``estimator_failure``, no number.
    - Back-door identified and the simulation runs → the extrapolated
      coefficient, with the naive one kept beside it for contrast.
    """
    from .simex import DEFAULT_LAMBDAS, estimate_simex

    if outcome_model is None:
        # The route fires on the declaration, so arriving without one means
        # the guard and the handler disagree about what this row is for —
        # and the estimator would read the absence as its own default,
        # which would tell the reader they chose a model they never named.
        raise AssertionError(
            "the simex row ran with no declared outcome model")

    x_atom = q_stmt.query.intervention.atom
    y_atom = q_stmt.query.target.atom

    if not adjustment_sets:
        _refuse_without_back_door(
            result, estimator="simex", x_atom=x_atom, y_atom=y_atom,
            front_door_sets=front_door_sets, iv_candidates=iv_candidates)
        return blocked('design_unavailable')

    # Simulation perturbs one column. A second declared σ²_u would need the
    # two errors' covariance to perturb them jointly, and a per-column
    # variance does not carry it — so the spec is refused rather than half
    # honoured, which would leave the covariate's bias in the number under
    # a heading that says the measurement was corrected.
    if covariate_specs:
        result["estimator_failure"] = refusals.block(
            estimator="simex",
            failure_type=Refusal.SIMEX_PERTURBS_ONE_MISMEASURED_COLUMN,
            details={"exposure": x_atom.predicate,
                     "others": sorted(covariate_specs)},
            # Either narrow the spec to the one column simulation can
            # perturb, or take the road whose moment correction handles
            # several mismeasured columns at once by construction.
            remedies=[
                (refusals.Remedy.CHANGE_INPUT, "measurement_error="),
                (refusals.Remedy.USE_METHOD, "regression_calibration")],
        )
        return blocked('estimator_refused')

    chosen = min(adjustment_sets, key=len)
    adjustment_names = tuple(a.predicate for a in _topo_order(graph, chosen))

    try:
        est = estimate_simex(
            contract.data,
            treatment=x_atom.predicate, outcome=y_atom.predicate,
            adjustment=adjustment_names,
            error_variance=DeclaredVariance.from_spec(spec),
            outcome_model=outcome_model,
            # Absent stays absent rather than becoming the default spelled
            # out here: the estimator's own resolution is what records who
            # settled the shape, and a default written at the call site
            # arrives indistinguishable from a caller who named it.
            extrapolant=spec.get("extrapolant"),
            lambdas=tuple(spec.get("lambdas", DEFAULT_LAMBDAS)),
            n_replicates=int(spec.get("n_replicates", 100)),
            ci_level=0.95,
            random_state=random_state,
            cluster=cluster if (cluster is None
                                or cluster in contract.data.columns) else None,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="simex", exc=exc)
        return blocked('estimator_refused')
    except (ValueError, KeyError, TypeError) as exc:
        result["estimator_failure"] = refusals.block(
            estimator="simex",
            failure_type=Refusal.UNKNOWN,
            recorded={"diagnostic": str(exc)},
        )
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": est.method,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "adjustment": list(est.adjustment),
        "treatment": est.treatment,
        "outcome": est.outcome,
        "simex": _simex_block(est),
    }
    # No bootstrap block: this interval is not one, and a declared cluster
    # column withholds the interval rather than widening it. Saying
    # "cluster-robust" over a model-based variance is the one claim the
    # estimator went out of its way not to make.
    _attach_precision_budget(result["numeric_estimate"])

    link = "logit " if est.outcome_model == "logistic" else ""
    _attach_mechanism_audit(
        result, est,
        target=f"d{link}E[{est.outcome}|do({est.treatment}),Z]"
               f"/d{est.treatment}",
    )

    result["derivation"] = _build_measurement_correction_derivation_dict(
        graph=graph, x=x_atom, y=y_atom, adjustment=chosen,
        given=frozenset(given), estimate=est,
    )
    _finalise_numeric_result(result)
    return answered()


def _differential_error_block(est) -> dict:
    """The ``differential_error`` audit/verifier block.

    Two numbers the classical block has no counterpart for, and they are the
    two the reader has to see to know what happened:
    ``outcome_tracking_covariance`` is δ·Var(Y|Z), the part of the observed
    exposure-outcome covariance that is the error rather than the effect, and
    ``nondifferential_variance`` is what is left of the declared σ²_u once
    that part is taken out. ``reliability`` is the same ratio the classical
    correction reports and means the same thing, which is what lets a reader
    put the two side by side.

    ``validation_df`` appears only where a study estimated σ²_u and said how
    big it was, because its absence is the claim that none did. Written as a
    missing key rather than as a null, so a run declaring nothing ships the
    block it shipped before the field existed.
    """
    block = {
        "naive_point": est.naive_point,
        "exposure": est.treatment,
        "differential_by": est.differential_by,
        "differential_coefficient": est.differential_coefficient,
        "error_variance": est.error_variance,
        "nondifferential_variance": est.nondifferential_variance,
        "outcome_tracking_covariance": est.outcome_tracking_covariance,
        "exposure_variance": est.exposure_variance,
        "reliability": est.reliability,
        "design_vars": list(est.design_vars),
        "form": est.form,
        "sufficient_statistics": est.sufficient_statistics,
    }
    if est.validation_df is not None:
        block["validation_df"] = est.validation_df
    # Present exactly when that same study also measured δ, which is what
    # separates the two declarations without writing the df down twice.
    if est.tracking_standard_error is not None:
        block["tracking_standard_error"] = est.tracking_standard_error
    return block


def _try_differential_error_estimate(
    q_stmt, result: dict, contract, graph, *,
    adjustment_sets, front_door_sets, iv_candidates, given, spec: dict,
    covariate_specs: dict, differential_coefficient: object,
    random_state: int, ci_bootstrap: int, cluster: str | None = None,
) -> Claim:
    """Numeric end for a mismeasured exposure whose error tracks the outcome.

    The classical correction below assumes the error is non-differential, and
    that premise is not a technicality it is robust to: a differential error
    inflates the observed exposure-outcome covariance as well as the exposure's
    variance, so de-attenuating alone moves one of the two things that moved.
    Which is why this row runs AHEAD of it rather than beside it, and why the
    caller reaches it by declaring δ rather than by anything in the data — a δ
    and a βx enter the observed covariance identically, so the sample cannot
    tell them apart.

    A second mismeasured column is refused rather than absorbed. The closed
    form partials the adjustment set out of both the exposure and the outcome
    and so needs that set measured exactly; a mismeasured covariate beside the
    exposure would need the covariance between the two errors, which a
    per-column variance does not carry.
    """
    from .differential_error import estimate_differential_error

    if differential_coefficient is None:
        raise AssertionError(
            "the differential row ran with no coefficient; its route guard "
            "tests the same attribute, so the two cannot disagree unless one "
            "of them was edited alone"
        )

    x_atom = q_stmt.query.intervention.atom
    y_atom = q_stmt.query.target.atom

    if not adjustment_sets:
        _refuse_without_back_door(
            result, estimator="differential_error", x_atom=x_atom,
            y_atom=y_atom, front_door_sets=front_door_sets,
            iv_candidates=iv_candidates)
        return blocked('design_unavailable')

    if covariate_specs:
        result["estimator_failure"] = refusals.block(
            estimator="differential_error",
            failure_type=Refusal.DIFFERENTIAL_AXIS_IS_NOT_THE_OUTCOME,
            details={"axis": sorted(covariate_specs),
                     "outcome": y_atom.predicate,
                     "adjustment": []},
        )
        return blocked('combination_out_of_scope')

    chosen = min(adjustment_sets, key=len)
    adjustment_names = tuple(a.predicate for a in _topo_order(graph, chosen))

    try:
        est = estimate_differential_error(
            contract.data,
            treatment=x_atom.predicate, outcome=y_atom.predicate,
            adjustment=adjustment_names,
            error_variance=DeclaredVariance.from_spec(spec),
            # An absent axis is a refusal rather than a guess. The correction
            # is written for one axis, but a caller who never named it has not
            # said their error tracks that one — and this row is reachable on
            # a coefficient alone.
            differential_by=spec.get("differential_by"),
            # The DECLARATION rather than the number routing read out of it:
            # a δ declared with the regression that measured it is a δ whose
            # interval carries that regression, and the route only ever needed
            # to know there was one.
            differential_coefficient=spec.get("differential_coefficient"),
            ci_bootstrap=ci_bootstrap, ci_level=0.95,
            random_state=random_state,
            cluster=cluster if (cluster is None
                                or cluster in contract.data.columns) else None,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="differential_error", exc=exc)
        return blocked('estimator_refused')
    except (ValueError, KeyError, TypeError) as exc:
        result["estimator_failure"] = refusals.block(
            estimator="differential_error",
            failure_type=Refusal.UNKNOWN,
            recorded={"diagnostic": str(exc)},
        )
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": est.method,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "adjustment": list(est.adjustment),
        "treatment": est.treatment,
        "outcome": est.outcome,
        "differential_error": _differential_error_block(est),
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, est.draws)
    _attach_precision_budget(result["numeric_estimate"])
    _attach_mechanism_audit(
        result, est,
        target=f"dE[{est.outcome}|do({est.treatment}),Z]/d{est.treatment}",
    )
    result["derivation"] = _build_measurement_correction_derivation_dict(
        graph=graph, x=x_atom, y=y_atom, adjustment=chosen,
        given=frozenset(given), estimate=est,
    )
    _finalise_numeric_result(result)
    return answered()


def _differential_outcome_error_block(est) -> dict:
    """The ``differential_outcome_error`` audit/verifier block.

    Shorter than its sibling by exactly the terms that do not exist here.
    ``exposure_tracking_variance`` is δ²·Var(X|Z) — the variance the tracking
    part alone puts into the RECORDED outcome — and ``nondifferential_
    variance`` is what the declared σ²_v has left over, which is the quantity
    a precision cost is properly priced on. There is no reliability ratio and
    no corrected variance: the outcome's error is not in a regressor, so
    nothing is attenuated and the whole correction is one subtraction.
    """
    block = {
        "naive_point": est.naive_point,
        "outcome": est.outcome,
        "differential_by": est.differential_by,
        "differential_coefficient": est.differential_coefficient,
        "error_variance": est.error_variance,
        "nondifferential_variance": est.nondifferential_variance,
        "exposure_tracking_variance": est.exposure_tracking_variance,
        "exposure_variance": est.exposure_variance,
        "design_vars": list(est.design_vars),
        "form": est.form,
        "sufficient_statistics": est.sufficient_statistics,
    }
    if est.validation_df is not None:
        block["validation_df"] = est.validation_df
    if est.tracking_standard_error is not None:
        block["tracking_standard_error"] = est.tracking_standard_error
    return block


def _try_differential_outcome_error_estimate(
    q_stmt, result: dict, contract, graph, *,
    adjustment_sets, front_door_sets, iv_candidates, given, spec: dict,
    differential_coefficient: object,
    random_state: int, ci_bootstrap: int, cluster: str | None = None,
) -> Claim:
    """Numeric end for a mismeasured OUTCOME whose error tracks the exposure.

    The two rows below this one read an outcome-error declaration and price
    what it costs in precision, on the stated ground that a classical
    additive error on the outcome moves no conditional mean. A declared δ
    withdraws exactly that ground: Y = Y* + δX + f makes the ordinary
    back-door fit consistent for βx + δ, so the number those rows would let
    through is wrong by δ and nothing on the envelope would say so.

    It OWNS the query rather than annotating, which is the difference
    between the two channels' rows here: pricing is a caveat beside someone
    else's answer, and this is the answer.
    """
    from .differential_error import estimate_differential_outcome_error

    if differential_coefficient is None:
        raise AssertionError(
            "the differential outcome row ran with no coefficient; its route "
            "guard tests the same attribute, so the two cannot disagree "
            "unless one of them was edited alone"
        )

    x_atom = q_stmt.query.intervention.atom
    y_atom = q_stmt.query.target.atom

    if not adjustment_sets:
        _refuse_without_back_door(
            result, estimator="differential_outcome_error", x_atom=x_atom,
            y_atom=y_atom, front_door_sets=front_door_sets,
            iv_candidates=iv_candidates)
        return blocked('design_unavailable')

    chosen = min(adjustment_sets, key=len)
    adjustment_names = tuple(a.predicate for a in _topo_order(graph, chosen))

    try:
        est = estimate_differential_outcome_error(
            contract.data,
            treatment=x_atom.predicate, outcome=y_atom.predicate,
            adjustment=adjustment_names,
            error_variance=DeclaredVariance.from_spec(spec),
            differential_by=spec.get("differential_by"),
            differential_coefficient=spec.get("differential_coefficient"),
            ci_bootstrap=ci_bootstrap, ci_level=0.95,
            random_state=random_state,
            cluster=cluster if (cluster is None
                                or cluster in contract.data.columns) else None,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="differential_outcome_error", exc=exc)
        return blocked('estimator_refused')
    except (ValueError, KeyError, TypeError) as exc:
        result["estimator_failure"] = refusals.block(
            estimator="differential_outcome_error",
            failure_type=Refusal.UNKNOWN,
            recorded={"diagnostic": str(exc)},
        )
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": est.method,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "adjustment": list(est.adjustment),
        "treatment": est.treatment,
        "outcome": est.outcome,
        "differential_outcome_error": _differential_outcome_error_block(est),
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, est.draws)
    _attach_precision_budget(result["numeric_estimate"])
    _attach_mechanism_audit(
        result, est,
        target=f"dE[{est.outcome}|do({est.treatment}),Z]/d{est.treatment}",
    )
    result["derivation"] = _build_measurement_correction_derivation_dict(
        graph=graph, x=x_atom, y=y_atom, adjustment=chosen,
        given=frozenset(given), estimate=est,
    )
    _finalise_numeric_result(result)
    return answered()


def _regression_calibration_block(est) -> dict:
    """The ``regression_calibration`` audit/verifier block: the naive
    (attenuated) slope, the reliability ratio λ (continuous det(M)), σ²_u, the
    design variable order, and the sufficient statistics
    ``verify_regression_calibration_numeric`` re-derives the corrected point
    from (the design covariance matrix Σ_WZ + Cov((W,Z),Y) + σ²_u).

    ``validation_df`` names only the columns whose σ²_u came from a study
    that said how big it was — a subset of ``error_variances``, and empty
    for the run that declares none. Absent rather than empty in that case,
    so such a run ships the block it shipped before the field existed."""
    block = {
        "naive_point": est.naive_point,
        "reliability": est.reliability,
        "error_variance": est.error_variance,
        "error_variances": dict(est.error_variances),
        "reliabilities": dict(est.reliabilities),
        "exposure": est.treatment,
        "design_vars": list(est.design_vars),
        "naive_slope": list(est.naive_slope),
        "corrected_slope": list(est.corrected_slope),
        "form": est.form,
        "sufficient_statistics": est.sufficient_statistics,
    }
    if est.validation_df:
        block["validation_df"] = dict(est.validation_df)
    return block


def _try_regression_calibration_estimate(
    q_stmt, result: dict, contract, graph, *,
    adjustment_sets, front_door_sets, iv_candidates, given, error_map: dict,
    random_state: int, ci_bootstrap: int, cluster: str | None = None,
) -> Claim:
    """Continuous-mismeasurement numeric end + honest gate for a mismeasured
    continuous EXPOSURE and/or back-door COVARIATE (regression calibration).

    Fires when the caller supplied known classical additive error variances σ²_u
    for this query's exposure and/or covariates (``error_map`` = {name → σ²_u}).
    Two outcomes, neither a silently-biased back-door slope:

    - Not back-door identified, a named mismeasured covariate absent from the
      adjustment set, or the correction refuses (non-positive / degenerate σ²_u,
      near-discrete variable, singular design) → ``estimator_failure`` (no
      number); the caller asked for the corrected slope, so the biased naive
      slope is withheld, not shipped.
    - Back-door identified AND the correction succeeds → de-attenuate by the RC
      moment correction, attach the corrected ``numeric_estimate`` (with the
      naive slope kept for contrast), flip to numerically_solved.
    """
    from .regression_calibration import estimate_regression_calibration

    x_atom = q_stmt.query.intervention.atom
    y_atom = q_stmt.query.target.atom

    if not adjustment_sets:
        _refuse_without_back_door(
            result, estimator="regression_calibration", x_atom=x_atom, y_atom=y_atom,
            front_door_sets=front_door_sets, iv_candidates=iv_candidates)
        return blocked('design_unavailable')

    # A mismeasured covariate must be adjusted for to be corrected; prefer a
    # back-door set that contains every named covariate, else fall back to the
    # smallest and let the design check below refuse.
    named_covs = {k for k in error_map if k != x_atom.predicate}

    def _covers(aset):
        return named_covs <= {a.predicate for a in aset}

    candidates = [a for a in adjustment_sets if _covers(a)] or list(adjustment_sets)
    chosen = min(candidates, key=len)
    adjustment_names = tuple(a.predicate for a in _topo_order(graph, chosen))

    design_names = {x_atom.predicate, *adjustment_names}
    not_in_design = sorted(k for k in error_map if k not in design_names)
    if not_in_design:
        result["estimator_failure"] = refusals.block(
            estimator="regression_calibration",
            failure_type=Refusal.MISMEASURED_COVARIATE_NOT_IN_ADJUSTMENT,
            details={"variable": not_in_design,
                     "adjustment": list(adjustment_names)},
        )
        return blocked('design_unavailable')

    try:
        est = estimate_regression_calibration(
            contract.data,
            treatment=x_atom.predicate, outcome=y_atom.predicate,
            adjustment=adjustment_names,
            error_variance=error_map,
            ci_bootstrap=ci_bootstrap, ci_level=0.95,
            random_state=random_state,
            cluster=cluster if (cluster is None or cluster in contract.data.columns) else None,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="regression_calibration", exc=exc)
        return blocked('estimator_refused')
    except (ValueError, KeyError, TypeError) as exc:
        result["estimator_failure"] = refusals.block(
            estimator="regression_calibration",
            failure_type=Refusal.UNKNOWN,
            recorded={"diagnostic": str(exc)},
        )
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": est.method,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "adjustment": list(est.adjustment),
        "treatment": est.treatment,
        "outcome": est.outcome,
        # Regression-calibration detail (audit trail + verifier inputs). The
        # design covariance matrix + Cov((W,Z),Y) + σ²_u don't fit derivation-
        # input serialization, so they live here and the corrected/naive slope
        # is re-derived by verify_regression_calibration_numeric (kernel-called).
        "regression_calibration": _regression_calibration_block(est),
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, est.draws)
    _attach_precision_budget(result["numeric_estimate"])

    _attach_mechanism_audit(
        result, est, target=f"dE[{est.outcome}|do({est.treatment}),Z]/d{est.treatment}",
    )

    result["derivation"] = _build_measurement_correction_derivation_dict(
        graph=graph, x=x_atom, y=y_atom, adjustment=chosen,
        given=frozenset(given), estimate=est,
    )
    _finalise_numeric_result(result)
    return answered()


def _outcome_error_design(
    graph, *, adjustment_sets, front_door_sets, iv_candidates,
) -> tuple["OutcomeErrorDesign", dict] | None:
    """Which design's residual this query's σ²_v is priced against, and the
    COLUMNS that design is built from — or ``None`` when the query has no
    design this package can name.

    The order is the estimation cascade's own (back-door 150, front-door 160,
    IV 180/190) and shares its facts, because the assessment prices the
    design that PRODUCES the number: chosen on any other order it would price
    a design the reader was never given. Sharing the facts is what makes that
    identity rather than resemblance — ``min(..., key=len)`` here and in the
    estimator are the same selection over the same tuple.

    Columns only, and that is what lets one function serve both halves of the
    assessment. What the instrumental-variable design additionally needs — β̂,
    and which instruments the premise is about — are properties of the
    ANSWER, so the caller that has one supplies them and the caller that runs
    before any estimator does not have to invent them.
    """
    from .outcome_error import OutcomeErrorDesign

    def _names(atoms) -> tuple[str, ...]:
        return tuple(a.predicate for a in _topo_order(graph, atoms))

    if adjustment_sets:
        return OutcomeErrorDesign.BACK_DOOR, {
            "adjustment": _names(min(adjustment_sets, key=len)),
        }
    if front_door_sets:
        # The raw mediator columns: the assessment expands each into the
        # drop-first indicators the front-door outcome model spans, and doing
        # that expansion twice is how the two spans come to differ.
        return OutcomeErrorDesign.FRONT_DOOR, {
            "mediators": _names(min(front_door_sets, key=len)),
        }
    if iv_candidates:
        # W, the instrument's own conditioning set, which enters the
        # structural equation Y = βX + γ'W + e as ordinary covariates. The
        # instrument itself does not: it names the premise, not the design.
        return OutcomeErrorDesign.INSTRUMENTAL_VARIABLE, {
            "adjustment": _names(iv_candidates[0].conditioning),
        }
    return None


def _iv_design_from_the_answer(result: dict) -> dict | None:
    """β̂, the conditioning set it was taken around, and the instruments the
    premise is about — or ``None`` when no point estimate was produced.

    Read from what the answering row recorded rather than re-derived. Two IV
    rows can answer this query, and they need not pick the same candidate or
    the same number of instruments, so a design re-derived here would be a
    second record of the shipped one, free to disagree with it. Reading it
    back is what makes "the design priced is the design that answered"
    identity rather than resemblance.
    """
    ne = result.get("numeric_estimate")
    if not isinstance(ne, dict) or ne.get("point") is None:
        return None
    instruments = ne.get("instruments")
    if instruments is None:
        one = ne.get("instrument")
        instruments = [one] if one is not None else []
    if not instruments:
        return None
    return {
        "adjustment": tuple(ne.get("conditioning") or ()),
        "instruments": tuple(instruments),
        "treatment_coefficient": ne["point"],
    }






def _try_outcome_error_declaration(
    result: dict,
    contract: DataContract,
    graph,
    *,
    x_atom,
    y_atom,
    adjustment_sets,
    front_door_sets,
    iv_candidates,
    spec: dict,
) -> Claim:
    """Judge whether a declared classical outcome-error variance can be true
    of this sample, and say whether the query may proceed.

    On success this row ANNOTATES: a non-differential additive outcome error
    moves no conditional mean, so there is no correction to apply and no
    estimand of its own to answer — whoever answers the query answers it.

    Ownership is a property of the row, not of the outcome, so the two exits
    that stop the query stop it for a reason about the ANSWER rather than
    about this row: the spec named the wrong channel (a discrete outcome is
    misclassification, which DOES attenuate and IS correctable), or the
    declared variance does not fit under the residual variation the data show
    — and that second one puts in doubt the very independence premise that
    made the point safe, so no number is shipped.

    A design this package has no split for is the opposite case. Nothing has
    been learned about the answer; what is missing is this row's own reach.
    Stopping there took the query away from the handler that would have
    answered it, so the exit passes; the refusal is still recorded, because
    the report puts a refusal below the numeric branches precisely so a
    supplementary one can sit beside an answer that stands.

    There used to be a third exit, recording nothing at all, for the span
    check the front-door design once carried: a mediator with no level set
    refused here about a column rather than about the declared variance, and
    the estimator it belonged to said the same thing two rows down in its own
    name. Both halves of that reasoning are gone — the front door answers
    such a query now, by a second plug-in, and this row builds its design over
    the same mediator the same way. So there is nothing left to hand back and
    nothing left to be quiet about.

    Nothing is written here on success either. What the noise COSTS is taken
    once the query has been answered, by ``outcome_error_precision_cost``:
    two halves of one assessment, split where they have to be, since this one
    can stop the query and that one needs the query answered first.
    """
    from .outcome_error import check_outcome_error_declaration

    selected = _outcome_error_design(
        graph,
        adjustment_sets=adjustment_sets,
        front_door_sets=front_door_sets,
        iv_candidates=iv_candidates,
    )
    if selected is None:
        result["estimator_failure"] = refusals.block(
            estimator="outcome_measurement_error",
            failure_type=Refusal.NO_DESIGN_TO_SPLIT_AROUND,
            details={"exposure": x_atom.predicate,
                     "outcome": y_atom.predicate},
        )
        return passed('numeric_end_not_built')
    _design, design_columns = selected

    # σ²_v is the spec's one required key, and whether the declared value is
    # usable — positive, finite, and small enough to fit under the residual
    # variation — is the estimator's judgement, along with the refusal that
    # names it. So an omitted key is handed on as absent rather than being
    # re-adjudicated here under a second set of words. Absent is ``None``,
    # which is what the refusal then quotes back: a default of ``nan`` reads
    # to the caller as a number they declared, and they declared nothing.
    #
    # Inside the try, because building it can itself refuse: a validation
    # df that is not a df is a fact about the declaration, and the reader
    # must meet it as this row's recorded refusal rather than as a raise
    # through the cascade.
    try:
        declared_variance = DeclaredVariance.from_spec(spec)
        check_outcome_error_declaration(
            contract.data,
            treatment=x_atom.predicate, outcome=y_atom.predicate,
            error_variance=declared_variance,
            # Handed on for the same reason ``error_variance`` is: the spec's
            # keys are the estimator's to judge, and the one that says the
            # error tracks the exposure decides which part of the declared
            # variance this residual has to hold. Read here and dropped, the
            # gate below would stop a query the declaration never contradicts.
            differential_coefficient=spec.get("differential_coefficient"),
            **design_columns,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="outcome_measurement_error", exc=exc)
        return blocked('estimator_refused')
    except (ValueError, KeyError, TypeError) as exc:
        result["estimator_failure"] = refusals.block(
            estimator="outcome_measurement_error",
            failure_type=Refusal.UNKNOWN,
            recorded={"diagnostic": str(exc)},
        )
        return blocked('estimator_refused')

    return annotated()


def _try_outcome_error_price(
    result: dict,
    contract: DataContract,
    graph,
    *,
    x_atom,
    y_atom,
    adjustment_sets,
    front_door_sets,
    iv_candidates,
    spec: dict,
) -> Claim:
    """What the declared σ²_v costs the answer that was actually produced.

    Runs after the answer, which is the only place it can: the
    instrumental-variable design takes its split around the STRUCTURAL
    residual Var(Y − βX − γ'W), and β̂ is the answer. The declaration was
    already judged usable by ``outcome_error_declaration``, so everything
    left here is arithmetic about a number that exists.

    Nothing here can stop the query, and that is not a restraint on this row
    but a fact about where it stands: a veto after the fact would mean
    withdrawing an answer already written. So an assessment that cannot be
    produced is recorded as a refusal BESIDE the number — which is exactly
    what the report renders under an answer that stands.

    The declaration check is taken around the ordinary least-squares residual
    on these same columns, and least squares minimises that residual, so it
    is never larger than the one priced here. A σ²_v that fit under it fits
    under this one too: the refusal below is reachable only through a design
    the answering row named and the earlier check did not see.
    """
    from .outcome_error import OutcomeErrorDesign, assess_outcome_error

    selected = _outcome_error_design(
        graph,
        adjustment_sets=adjustment_sets,
        front_door_sets=front_door_sets,
        iv_candidates=iv_candidates,
    )
    if selected is None:
        # The declaration row already recorded why, in the same words.
        return annotated()
    design, arguments = selected
    arguments = dict(arguments)

    if design == OutcomeErrorDesign.INSTRUMENTAL_VARIABLE:
        from_the_answer = _iv_design_from_the_answer(result)
        if from_the_answer is None:
            result["estimator_failure"] = refusals.block(
                estimator="outcome_measurement_error",
                failure_type=Refusal.REQUIRES_A_POINT_ESTIMATE,
                details={"exposure": x_atom.predicate,
                         "outcome": y_atom.predicate},
            )
            return annotated()
        arguments.update(from_the_answer)

    try:
        assessment = assess_outcome_error(
            contract.data,
            treatment=x_atom.predicate, outcome=y_atom.predicate,
            design_kind=design,
            error_variance=DeclaredVariance.from_spec(spec),
            differential_coefficient=spec.get("differential_coefficient"),
            **arguments,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="outcome_measurement_error", exc=exc)
        return annotated()
    except (ValueError, KeyError, TypeError) as exc:
        result["estimator_failure"] = refusals.block(
            estimator="outcome_measurement_error",
            failure_type=Refusal.UNKNOWN,
            recorded={"diagnostic": str(exc)},
        )
        return annotated()

    result["outcome_error"] = _outcome_error_block(
        assessment, source=spec.get("source"))
    return annotated()


def _outcome_error_block(assessment, *, source: object) -> dict:
    """The ``outcome_error`` block, as its twin one channel over is
    written.

    A function rather than a literal at the one call site, for the
    reason ``_berkson_block`` already is one: the audit that re-derives
    this block has to read what the producer writes, and a test that
    transcribes the shape instead is a test the producer would pass
    while short a field.
    """
    return {
        "outcome": assessment.outcome,
        "treatment": assessment.treatment,
        # Which residual the split was taken around. Every other number in
        # this block is read against it — the same σ²_v prices differently on
        # a design that conditions on the mediator — and it is also the only
        # record of whether se_inflation is the factor or a ceiling on it.
        "design_kind": assessment.design_kind,
        "design_vars": list(assessment.design_vars),
        "error_variance": assessment.error_variance,
        "residual_variance": assessment.residual_variance,
        "signal_variance": assessment.signal_variance,
        "noise_share": assessment.noise_share,
        "se_inflation": assessment.se_inflation,
        # Present exactly where the caller withdrew the non-differential
        # premise, and the three of them together say what the four numbers
        # above are about: the design absorbed δ·(X − E[X|rest]) into the
        # exposure's coefficient, so the share and the factor price the
        # remainder rather than the declared total. Written as missing keys
        # rather than as nulls, so a run that declares no δ ships the block it
        # shipped before they existed.
        **({} if assessment.differential_coefficient is None else {
            "differential_coefficient": assessment.differential_coefficient,
            "exposure_tracking_variance": assessment.exposure_tracking_variance,
            "residual_error_variance": assessment.residual_error_variance,
        }),
        # And what the study that measured the variance does to that
        # factor. Four keys rather than one, because the reader acts
        # on each: how far down it could be, how far up, whether
        # there IS an up, and how much of that study this data
        # already contradicts.
        "validation_df": assessment.validation_df,
        "se_inflation_lower": assessment.se_inflation_lower,
        "se_inflation_upper": assessment.se_inflation_upper,
        "inflation_refuted_share": assessment.inflation_refuted_share,
        "sample_size": assessment.sample_size,
        "data_hash": assessment.data_hash,
        "data_columns": list(assessment.data_columns),
        "assumptions": list(assessment.assumptions),
        # Σ_D, Cov(D, Y), Var(Y), σ²_v, n — the split is a closed-form function
        # of these, so verify_outcome_error re-derives it without the data.
        "sufficient_statistics": assessment.sufficient_statistics,
        "source": source,
    }


def _build_measurement_correction_derivation_dict(
    *, graph, x, y, adjustment, given, estimate,
):
    """Two-step derivation for a confusion-matrix-corrected estimate:

        s1: backdoor_criterion (structural witness — P(y|do(x)) is back-door
            identified with this adjustment set; the correction standardises
            over it)
        s2: numeric_measurement_correction_estimate (metadata + structural
            licensing terminal; the matrix inversion / point re-derivation from
            the recorded confusion matrix + value-count vectors is
            verify_measurement_correction_numeric, called from the kernel —
            those matrices don't fit derivation-input serialization)
    """
    from ..types import DerivationStep, StepRef, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    steps = (
        DerivationStep(
            rule="backdoor_criterion",
            inputs={
                "graph": graph,
                "x": x, "y": y,
                "z": frozenset(adjustment),
                "given": given,
            },
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="numeric_measurement_correction_estimate",
            inputs={
                "criterion": StepRef(step_id="s1"),
                "treatment": x,
                "outcome": y,
                "adjustment": frozenset(adjustment),
                "method": estimate.method,
                "data_hash": estimate.data_hash,
                "sample_size": estimate.sample_size,
                # Absent when the estimate answered with a curve: the step
                # witnesses the number the run produced, and there is no one
                # number when the exposure has more than two levels. The curve
                # is re-derived row by row by the numeric verifier, so nothing
                # goes unchecked by leaving this out.
                **({} if estimate.point is None
                   else {"point": estimate.point,
                         "ci_lower": estimate.ci_lower,
                         "ci_upper": estimate.ci_upper}),
                "ci_level": estimate.ci_level,
            },
            output=StructuralResult(value=True),
            step_id="s2",
        ),
    )
    return derivation_to_dict(steps)


def _extract_program_extensions(program) -> dict:
    """program may be dict or string here — kernel.estimate accepts
    both shapes; coerce to a dict so we can read .extensions safely."""
    import json
    if isinstance(program, (str, bytes)):
        program = json.loads(program)
    if not isinstance(program, dict):
        return {}
    ext = program.get("extensions")
    return ext if isinstance(ext, dict) else {}


WEAK_IV_F_THRESHOLD = 10.0  # Stock & Yogo (2005), single-instrument

PROPENSITY_OVERLAP_LOWER = 0.05
PROPENSITY_OVERLAP_UPPER = 0.95
PROPENSITY_OVERLAP_VIOLATION_FRACTION = 0.05  # 5% of sample outside bounds

OUTCOME_SATURATION_LOWER = 0.01
OUTCOME_SATURATION_UPPER = 0.99
OUTCOME_SATURATION_FRACTION = 0.10  # 10% of fitted P(Y|X,Z) outside bounds


def _attach_outcome_separation_warning(
    result: dict, contract, treatment: str, outcome: str,
    adjustment: tuple[str, ...],
) -> None:
    """Fit a logistic outcome model E[Y|X,Z] on the same
    data the backdoor estimator used, count fitted probabilities
    saturated near 0/1, and surface
    ``outcome_model_quasi_separation`` if more than
    ``OUTCOME_SATURATION_FRACTION`` of the sample lies outside
    [OUTCOME_SATURATION_LOWER, OUTCOME_SATURATION_UPPER].

    Distinct from ``propensity_overlap_violation`` —
    that inspects the treatment-assignment model P(X=1|Z); this
    inspects the outcome model P(Y=1|X,Z). Saturation of P(Y|X,Z)
    is the classic quasi-separation signal: the logistic fit's
    coefficients blow up, gradients near-singular, point estimate
    of the contrast is fine on average but the CI underestimates
    uncertainty and bias toward extreme outcomes is large.

    Skipped (no gap added):
    - non-binary outcome — only logistic outcome models can saturate
      this way; continuous regressions surface different pathology
    - logistic fit fails (singular, sample too small) — None means
      'could not assess'
    - empty adjustment AND single-arm treatment — not enough variation
      to estimate
    """
    import numpy as np
    import pandas as pd
    from sklearn.linear_model import LogisticRegression

    df = contract.data
    if outcome not in df.columns or treatment not in df.columns:
        return
    if not pd.api.types.is_bool_dtype(df[outcome]):
        return
    if not pd.api.types.is_bool_dtype(df[treatment]):
        return

    y = df[outcome].to_numpy().astype(int)
    if len(np.unique(y)) < 2:
        return  # only one outcome value — model can't fit

    feature_cols = [treatment, *adjustment]
    try:
        feats = _declared.design_block(df, feature_cols)
        clf = LogisticRegression(max_iter=1000, solver="lbfgs")
        clf.fit(feats, y)
        p_hat = clf.predict_proba(feats)[:, 1]
    except (ValueError, np.linalg.LinAlgError):
        return

    out_of_bounds = (
        (p_hat < OUTCOME_SATURATION_LOWER)
        | (p_hat > OUTCOME_SATURATION_UPPER)
    )
    fraction_outside = float(out_of_bounds.mean())
    if fraction_outside <= OUTCOME_SATURATION_FRACTION:
        return

    n_outside = int(out_of_bounds.sum())
    n_total = int(len(p_hat))
    p_min = float(p_hat.min())
    p_max = float(p_hat.max())

    feature_names = ", ".join(feature_cols)
    gap = DataGap(
        kind=GapKind.OUTCOME_MODEL_QUASI_SEPARATION,
        severity=GapSeverity.INFORMATIONAL,
        blocks=GapBlocks.INTERPRETATION,
        describes=(_sentence(
            Sentence.THE_OUTCOME_MODEL_IS_QUASI_SEPARATED,
            outcome=outcome, features=feature_names,
            outside=n_outside, total=n_total,
            share=f"{fraction_outside:.1%}",
            lower=OUTCOME_SATURATION_LOWER, upper=OUTCOME_SATURATION_UPPER,
            low=f"{p_min:.3f}", high=f"{p_max:.3f}",
        ),),
        alternative_paths=(
            _gaps.route(Route.COLLECT_IN_THE_SATURATED_STRATA),
            _gaps.route(Route.USE_A_SEPARATION_ROBUST_FIT),
            _gaps.route(Route.KNOW_THE_BOOTSTRAP_IS_ALSO_STRAINED),
            _gaps.route(Route.GO_BAYESIAN_WITH_A_WEAK_PRIOR),
        ),
        provenance=_verifier_check(
            f"outcome_separation:{outcome}|{treatment}:"
            f"{','.join(adjustment) if adjustment else '<none>'}"
        ),
    )
    _file_gaps(result, [gap])


def _attach_propensity_overlap_warning(
    result: dict, contract, treatment: str, adjustment: tuple[str, ...],
) -> None:
    """Surface a ``propensity_overlap_violation`` gap, by either witness.

    The kind's own definition is a COUNT — "every confounder stratum has both
    treated and untreated units" — so where the strata can be enumerated the
    count answers it directly, and that is the first witness. The fitted
    propensity is the second, and it is a proxy: a logistic model smooths
    across cells, and on the measured frame it handed a stratum whose
    empirical treated rate is 0.000 a comfortable 0.091, so a quarter of the
    sample sat in a never-treated stratum and this gap did not fire. Where
    the adjustment set is continuous there are no cells to count and the
    proxy is the only witness there is.

    The old docstring, and the branch under it: fit P(X=1|Z) on the same
    data the backdoor estimator used, count observations whose estimated
    propensity falls outside [PROPENSITY_OVERLAP_LOWER,
    PROPENSITY_OVERLAP_UPPER], and surface the gap if more than
    ``PROPENSITY_OVERLAP_VIOLATION_FRACTION`` of the sample is
    out-of-support.

    Skipped (no gap added):
    - empty adjustment — there's nothing to overlap on
    - propensity model fit fails (singular, sample too small) — None
      means "could not assess"
    - non-binary treatment — overlap diagnostic doesn't generalise
      cleanly to multi-arm in v1

    INFORMATIONAL severity, must-disclose channel — the backdoor
    estimate is still attached; this just adds the caveat that part
    of the estimate is extrapolation from the regression model.
    """
    import numpy as np
    import pandas as pd
    from sklearn.linear_model import LogisticRegression

    from .. import refusals as _refusals
    from .support import arm_support

    if not adjustment:
        return
    df = contract.data
    if treatment not in df.columns:
        return

    support = arm_support(df, treatment, adjustment)
    if support.violated:
        slots = {
            "adjustment": ", ".join(adjustment),
            "cells": support.cells,
            "bad": len(support.one_armed),
            "share": f"{support.share:.1%}",
            "strata": _lang.describe(list(support.one_armed)),
        }
        _record_overlap_gap(
            result,
            describes=(_sentence(
                Sentence.EVERY_STRATUM_SHOULD_HAVE_BOTH_ARMS_AND_SOME_DO_NOT,
                **slots), ),
            ref_id=f"stratum_overlap:{treatment}|{','.join(adjustment)}",
        )
        return

    if not pd.api.types.is_bool_dtype(df[treatment]):
        return

    try:
        z = _declared.design_block(df, adjustment)
        x = df[treatment].to_numpy().astype(int)
        if len(np.unique(x)) < 2:
            return  # only one arm represented; weak_iv-equivalent edge case
        clf = LogisticRegression(max_iter=1000, solver="lbfgs")
        clf.fit(z, x)
        p_hat = clf.predict_proba(z)[:, 1]
    except (ValueError, np.linalg.LinAlgError):
        return

    out_of_bounds = (
        (p_hat < PROPENSITY_OVERLAP_LOWER)
        | (p_hat > PROPENSITY_OVERLAP_UPPER)
    )
    fraction_outside = float(out_of_bounds.mean())
    if fraction_outside <= PROPENSITY_OVERLAP_VIOLATION_FRACTION:
        return

    n_outside = int(out_of_bounds.sum())
    p_min = float(p_hat.min())
    p_max = float(p_hat.max())
    n_total = int(len(p_hat))

    # Only the sentence: which kind this is, how severe, and what it blocks
    # are ``_record_overlap_gap``'s to say, and they were spelled here too —
    # a third copy that nothing read, sitting in a dict shaped exactly like
    # the entry the other witness builds.
    unsupported = _sentence(
        Sentence.THE_FITTED_PROPENSITY_LEAVES_PART_OF_THE_SAMPLE_UNSUPPORTED,
        treatment=treatment, adjustment=", ".join(adjustment),
        outside=n_outside, total=n_total,
        lower=PROPENSITY_OVERLAP_LOWER, upper=PROPENSITY_OVERLAP_UPPER,
        share=f"{fraction_outside:.1%}",
        low=f"{p_min:.3f}", high=f"{p_max:.3f}",
    )

    _record_overlap_gap(
        result,
        describes=(unsupported,),
        ref_id=f"propensity_overlap:{treatment}|{','.join(adjustment)}",
    )


#: What a reader can do about either witness.
#:
#: The remedies do not depend on how the violation was SEEN — trimming to the
#: overlap region, a method that tolerates thin support, a coarser adjustment
#: set, or bounds where support runs out are the same four moves whether the
#: witness was a count of cells or a fitted score. One list, so the two
#: witnesses cannot drift into offering different advice about one condition.
_OVERLAP_WAYS_OUT = (
    _gaps.route(Route.TRIM_TO_THE_OVERLAP_REGION),
    _gaps.route(Route.USE_AN_OVERLAP_ROBUST_METHOD),
    _gaps.route(Route.LOOSEN_THE_ADJUSTMENT_SET),
    _gaps.route(Route.BOUND_THE_UNSUPPORTED_REGION),
)


def _record_overlap_gap(
    result: dict, *, describes: tuple, ref_id: str,
) -> None:
    """File one overlap finding, whichever witness saw it.

    Both witnesses are about the same condition and offer the same ways out,
    so they are one entry shape, and what each of them says about itself is
    the one thing they hand over. Keeping the filing in one place is what
    stops the two from disagreeing about severity, about what blocks, or
    about what the reader should do next.
    """
    _file_gaps(result, [DataGap(
        kind=GapKind.PROPENSITY_OVERLAP_VIOLATION,
        severity=GapSeverity.INFORMATIONAL,
        blocks=GapBlocks.INTERPRETATION,
        describes=describes,
        alternative_paths=_OVERLAP_WAYS_OUT,
        provenance=_verifier_check(ref_id),
    )])


def _acr_to_dict(acr, *, cluster: str | None) -> dict:
    """Serialise an AcrDecomposition to the numeric_estimate sub-block.

    ``cells`` is the whole block's evidence: per instrument level, the
    counts and sums every covariance, weight and the point itself are
    re-derivable from. It travels so the verifier can recompute the table
    without being handed the table — the sums are small enough to carry,
    unlike the moment matrices the over-identified route has to leave
    behind.

    ``bootstrap`` is this table's own record and not the estimate's: a
    resample with a dead first stage carries no weights and still carries
    a Wald ratio, so the two loops keep different counts, and which rule
    decided ``monotonicity_refuted`` turns on whether these margins got
    intervals at all.
    """
    return {
        "margins": [
            {
                "from_dose": m.from_dose,
                "to_dose": m.to_dose,
                "step": m.step,
                "covariance": m.covariance,
                "weight": m.weight,
                "share_moved": m.share_moved,
                "ci_lower": m.ci_lower,
                "ci_upper": m.ci_upper,
            }
            for m in acr.margins
        ],
        "first_stage_covariance": acr.first_stage_covariance,
        "outcome_covariance": acr.outcome_covariance,
        "levels": list(acr.levels),
        "instrument_levels": list(acr.instrument_levels),
        "monotonicity_refuted": acr.monotonicity_refuted,
        "refuting_margins": list(acr.refuting_margins),
        "ci_level": acr.ci_level,
        "cells": [dict(c) for c in acr.cells],
        **({"bootstrap": acr.draws.record(cluster=cluster)}
           if acr.draws is not None else {}),
    }


def _ar_set_to_dict(ar) -> dict:
    """Serialise an ARConfidenceSet to the numeric_estimate sub-block."""
    return {
        "kind": ar.kind,
        "lower": ar.lower,
        "upper": ar.upper,
        "ci_level": ar.ci_level,
        "point": ar.point,
    }


def _overid_ar_set_to_dict(ar) -> dict:
    """Serialise a multi-instrument OverIDARConfidenceSet to the numeric_estimate
    sub-block. Same shape as the single-instrument set plus the ``F(q, m)``
    critical value ``kappa = q·F(q, m)`` and its degrees of freedom — the
    verifier re-derives the set from the recorded moment matrices and cross-checks
    kappa against F(dof_num, dof_denom)."""
    return {
        "kind": ar.kind,
        "lower": ar.lower,
        "upper": ar.upper,
        "ci_level": ar.ci_level,
        "point": ar.point,
        "kappa": ar.kappa,
        "dof_num": ar.dof_num,
        "dof_denom": ar.dof_denom,
    }


def _stratified_ar_set_to_dict(s) -> dict:
    """Serialise a StratifiedARSet to the numeric_estimate sub-block.

    Same five shapes as the single-instrument set, but inverted on the
    stratified Wald's own moment, so ``point`` here IS the headline point
    rather than the linear IV coefficient. The aggregate moment and its
    variance coefficients travel along so the verifier can re-solve the
    quadratic from the record — and cross-check them against the stratum
    table, which carries the same quantities per cell.
    """
    return {
        "kind": s.kind,
        "lower": s.lower,
        "upper": s.upper,
        "ci_level": s.ci_level,
        "point": s.point,
        "kappa": s.kappa,
        "outcome_shift": s.outcome_shift,
        "treatment_shift": s.treatment_shift,
        "var_yy": s.var_yy,
        "var_xy": s.var_xy,
        "var_xx": s.var_xx,
        "n_obs": s.n_obs,
        "n_strata": s.n_strata,
        "dof": s.dof,
    }


def _robust_ar_set_to_dict(r) -> dict:
    """Serialise a heteroskedasticity-robust RobustARConfidenceSet to the
    numeric_estimate sub-block. ``segments`` is the set as a list of intervals
    (``lower``/``upper`` null on an open side); ``crossings`` the finite boundary
    points; ``asymptote`` the shared tail value of ``AR_r``; ``crit = χ²(q)``. The
    verifier re-evaluates ``AR_r`` from the recorded S0/S1/S2 matrices."""
    return {
        "kind": r.kind,
        "segments": [{"lower": lo, "upper": hi} for (lo, hi) in r.segments],
        "crossings": list(r.crossings),
        "asymptote": r.asymptote,
        "crit": r.crit,
        "ci_level": r.ci_level,
        "dof": r.dof,
        "point": r.point,
        "cluster_robust": r.cluster_robust,
    }


def _render_robust_ar_set(r) -> str:
    """Human-readable rendering of a robust-AR set, honouring its segment list."""
    def fmt(v):
        return "−∞" if v is None else (f"{v:.4g}")
    if r.kind == "empty":
        return "∅"
    if r.kind == "whole_line":
        return "(−∞, +∞) — 工具太弱无法约束效应"
    parts = []
    for lo, hi in r.segments:
        lo_s = "−∞" if lo is None else f"{lo:.4g}"
        hi_s = "+∞" if hi is None else f"{hi:.4g}"
        left = "(" if lo is None else "["
        right = ")" if hi is None else "]"
        parts.append(f"{left}{lo_s}, {hi_s}{right}")
    return " ∪ ".join(parts)


def _render_ar_set(ar) -> str:
    """Human-readable rendering of an Anderson-Rubin confidence set,
    honouring its shape (bounded / disconnected / ray / whole line)."""
    lo = "" if ar.lower is None else f"{ar.lower:.4g}"
    hi = "" if ar.upper is None else f"{ar.upper:.4g}"
    if ar.kind == "bounded":
        return f"[{lo}, {hi}]"
    if ar.kind == "disconnected":
        return f"(-∞, {lo}] ∪ [{hi}, +∞)"
    if ar.kind == "unbounded_below":
        return f"(-∞, {hi}]"
    if ar.kind == "unbounded_above":
        return f"[{lo}, +∞)"
    if ar.kind == "whole_line":
        return "(-∞, +∞) — 整条实线，工具太弱无法约束效应"
    return "∅"


def _attach_iv_estimand_fallback_warning(result: dict, iv_estimate) -> None:
    """Disclose that a conditional binary IV design fell back from the
    stratified Wald to 2SLS, and that this changed the estimand.

    Same posture as ``_attach_weak_iv_warning_if_low_f``: INFORMATIONAL,
    the estimate is still surfaced, and the caveat is filed as a gap a
    reader surface has to lead with. The point of the
    disclosure is not that the number is worse — 2SLS is a fine estimator
    — but that it answers a different question than the identification
    layer named, and a substitution nobody can see is indistinguishable
    from an error.
    """
    reason = getattr(iv_estimate, "stratification_fallback", None)
    if reason is None:
        return

    w = ", ".join(iv_estimate.conditioning) or "∅"
    unstratified = _sentence(
        Sentence.THE_SAMPLE_COULD_NOT_BE_CUT_INTO_THE_STRATA_THE_WALD_NEEDS,
        instrument=iv_estimate.instrument, conditioning=w, reason=reason,
    )
    gap = DataGap(
        kind=GapKind.IV_ESTIMAND_FALLBACK_TO_LINEAR,
        severity=GapSeverity.INFORMATIONAL,
        blocks=GapBlocks.INTERPRETATION,
        describes=(unstratified,),
        required_data=GapRequiredData(
            data_type=RequiredDataType.IPD,
            population=(
                "条件集里目前只带一条工具臂（或一条都没有）"
                "的那些分层"
            ),
            variables=(
                iv_estimate.instrument,
                iv_estimate.treatment,
                iv_estimate.outcome,
                *iv_estimate.conditioning,
            ),
        ),
        alternative_paths=(
            _gaps.route(Route.COLLECT_IN_THE_ONE_ARMED_STRATA),
            _gaps.route(Route.COARSEN_THE_CONDITIONING_SET),
            _gaps.route(Route.ACCEPT_THE_VARIANCE_WEIGHTED_2SLS),
        ),
        provenance=_verifier_check(
            f"iv_estimand_fallback:{iv_estimate.instrument}|{w}"
        ),
    )
    _file_gaps(result, [gap])


def _attach_weak_iv_warning_if_low_f(result: dict, iv_estimate) -> None:
    """When the first-stage F-statistic is below the
    Stock-Yogo (2005) threshold (10 by default for single-instrument
    2SLS / Wald), attach a ``weak_iv_instrument`` gap so the renderer
    can disclose that the IV estimate's bias toward OLS is non-trivial
    and standard 2SLS asymptotics give misleading CIs.

    INFORMATIONAL severity, must-disclose channel — the estimate is
    still computed and surfaced; this just adds the caveat. F = None
    (degenerate first stage / sample too small) is treated as
    "could not assess" — no gap added rather than assuming weak.
    """
    f_stat = getattr(iv_estimate, "first_stage_f_stat", None)
    if f_stat is None:
        return
    if f_stat >= WEAK_IV_F_THRESHOLD:
        return

    # Whichever weak-robust set this estimand carries. The linear and the
    # stratified sets are never both populated, and both render through the
    # same five shapes — a weak first stage is precisely when the caller
    # needs the set, so this disclosure must not go blind on the path whose
    # set is not the linear one.
    ar = (
        getattr(iv_estimate, "anderson_rubin", None)
        or getattr(iv_estimate, "stratified_anderson_rubin", None)
    )
    said = [_sentence(
        Sentence.THE_FIRST_STAGE_IS_WEAK,
        instrument=iv_estimate.instrument, f=f"{f_stat:.2f}",
        threshold=f"{WEAK_IV_F_THRESHOLD:.0f}",
    )]
    # No set on this estimate means one could not be formed from this sample,
    # not that the reader forgot to look — so this branch must not send them
    # to a block the envelope does not carry.
    ar_alt = _gaps.route(Route.AR_SET_NOT_CONSTRUCTIBLE)
    if ar is not None:
        rendered = _render_ar_set(ar)
        pct = int(round(ar.ci_level * 100))
        said.append(_sentence(Sentence.THE_ANDERSON_RUBIN_SET_IS_THIS,
                              level=pct, interval=rendered))
        ar_alt = _gaps.route(
            Route.USE_THE_AR_SET, level=pct, interval=rendered)

    gap = DataGap(
        kind=GapKind.WEAK_IV_INSTRUMENT,
        severity=GapSeverity.INFORMATIONAL,
        blocks=GapBlocks.INTERPRETATION,
        describes=tuple(said),
        alternative_paths=(
            _gaps.route(Route.FIND_A_STRONGER_INSTRUMENT),
            ar_alt,
            _gaps.route(Route.FALL_BACK_TO_IV_BOUNDS),
        ),
        provenance=_verifier_check(
            f"weak_iv:{iv_estimate.instrument}->{iv_estimate.treatment}"
        ),
    )
    _file_gaps(result, [gap])

def _closer_to_null(ci_lower, ci_upper):
    """The point of this interval nearest the null, or None if there is no
    interval.

    An interval that straddles the null returns 0.0. The end nearest the
    null IS the null there, the E-value on it is 1, and that is a fact about
    the estimate rather than a missing input — returning None made the
    reading fall back to the point estimate, so exactly the results whose
    interval already reaches the null were the ones read as most robust.

    The point estimate is not an argument: an interval's nearest approach to
    zero is a fact about the interval. It was one while the two agreed —
    every real interval contains its own point estimate — and dropping it
    is what makes that agreement unnecessary rather than assumed.
    """
    if ci_lower is None or ci_upper is None:
        return None
    if ci_lower > 0:
        return ci_lower
    if ci_upper < 0:
        return ci_upper
    return 0.0


# Gap kinds the supplied DataFrame + computed point estimate make stale.
# Both directly contradict a numerically_solved point result:
#   - missing_distribution: the θ it asks for was supplied via the df.
#   - answer_is_bounds_not_point_estimate: a point was computed, so the
#     bounds are no longer THE answer.
# Structural caveats (ambiguous_variable, unmeasured_confounder_risk,
# ill_defined_intervention, ...) and estimator-time gaps (weak_iv,
# propensity_overlap, outcome_separation) are NOT dropped — still true.
#
# What this set claims and `_SAMPLE_SETTLED_GAPS` does not: a number came
# out, so whatever the identification pass wanted was supplied from
# somewhere. That is a stronger warrant and covers what the per-item pass
# leaves behind on purpose — an ask over a named population, an ask
# naming something the contract does not certify. Reaching a point
# estimate settles both; a DataFrame arriving does not.
_NUMERIC_SATISFIED_GAP_KINDS: frozenset[str] = frozenset({
    "missing_distribution",
    "answer_is_bounds_not_point_estimate",
    # Transport post-stratification consumed both the source stratum
    # conditionals (from the DataFrame) and the target marginal P*(Z)
    # (from program.extensions) — the two transport data-need gaps the
    # structural pass raised are now satisfied.
    "transport_source_conditional_unknown",
    "transport_target_distribution_unknown",
    # The dose-response curve was computed from the supplied data; the
    # "Themis 不算曲线（用 EconML / …）" gap is stale once the curve exists.
    "dose_response_data_required",
})


def _finalise_numeric_result(result: dict) -> None:
    """A point estimate for the query's own estimand came out: claim
    ``numerically_solved``, set a truthy structural_result, and withdraw
    what the number answered — the stale ``missing_information`` entries
    and the gaps in the report that still ask for what was just
    estimated, on every surface at once.

    Every route that attaches a number for the query's own estimand ends
    here. The two that once did not were the recovery estimators, on the
    reasoning that a result with no derivation cannot claim
    ``numerically_solved`` because ``verify`` refuses to audit one. Half
    of that was already false — selection recovery claimed it anyway —
    and the other half rests on ``verify`` being the only auditor, which
    :mod:`themis.audits` says it is not: each recovery estimator has a
    registered auditor that recomputes its number from the sufficient
    statistics the envelope carries. What a result may claim rests on
    whether its answer can be re-derived, not on which function re-derives
    it. The withdrawal is not separable from the claim either: split off,
    it was simply absent on the route that skipped this, and a recovered
    ATE shipped beside four blocking gaps naming the conditionals it had
    just estimated.
    """
    result["status"] = "numerically_solved"
    result["structural_result"] = {"value": True}
    result.pop("missing_information", None)
    _reconcile_gap_report_after_numeric_solve(result)


#: Gap species an ESTIMATOR files to say that what came out is not a number
#: for the estimand. The identification-time tier cannot know about these —
#: it is computed before the data arrive, and by then identification has
#: already succeeded — so a run reaching here with one of them would
#: otherwise be reconciled to ``point`` on the strength of having produced
#: an answer, and promise a number the envelope does not contain.
#:
#: Distinct from the gate below, which names the species that make this
#: whole reconciliation wrong: there the identification-time report is
#: already right and is left alone, and here it is already wrong.
_NO_POINT_CAME_OUT = frozenset({
    GapKind.ANSWER_IS_A_TEST_NOT_AN_EFFECT_SIZE,
})


def _reconcile_gap_report_after_numeric_solve(result: dict) -> None:
    """An answer for the query's own estimand was computed from the supplied
    data. The gap report was built by the identification pass BEFORE the data
    arrived, so it may still advertise ``missing_distribution: blocking`` and
    ``answer_is_bounds_not_point_estimate`` — both now false for a genuine
    non-parametric point. Drop those gaps, drop the parameter
    ``investigation_requests`` they cite (so the auditor's T10-2
    completeness check doesn't then demand a gap for data we already have
    — keeping the dual surfaces consistent), set the tier to what came out,
    and recompute the one-line summary.

    What came out is usually a point and is not always one, which is why the
    tier is read off the gaps rather than assumed: an estimator that ran to
    completion and produced something other than a number for the estimand
    says so in a gap, and that gap is the only thing on the envelope which
    knows it.
    """
    report = result.get("data_gap_report")
    if not isinstance(report, dict):
        return
    # Gate: when non-parametric point identification FAILED (the
    # ``unidentifiable_no_admissible_set`` gap is present), the attached
    # number is an under-assumption estimate — an IV LATE under
    # monotonicity, say — and the honest non-parametric answer is still
    # the interval. Do NOT claim tier='point' or drop the bounds framing;
    # leave the identification-time report, whose 'interval' tier +
    # assumption caveat are correct. Reconciling here would make tier
    # contradict the retained unidentifiable gap.
    gap_kinds = {g.get("kind") for g in report.get("gaps", [])}
    if "unidentifiable_no_admissible_set" in gap_kinds:
        return

    # Drop the satisfied parameter investigation_requests (data supplied),
    # keeping framing / structure requests.
    requests = result.get("investigation_requests")
    if isinstance(requests, list):
        kept = [r for r in requests if r.get("group") != "parameter"]
        if kept:
            result["investigation_requests"] = kept
        else:
            result.pop("investigation_requests", None)

    _set_gaps(
        result,
        [
            g for g in report.get("gaps", [])
            if g.get("kind") not in _NUMERIC_SATISFIED_GAP_KINDS
        ],
        answer_tier="none" if gap_kinds & _NO_POINT_CAME_OUT else "point",
    )


# A gap species that a sample of the study population settles by
# existing. Deliberately not the wider `_NUMERIC_SATISFIED_GAP_KINDS`:
# that set is justified by a number having come out, which proves the
# data held whatever the identification pass wanted. This one is
# justified by the contract alone, so it may only name species whose
# repair IS a measurement — and it is checked per item against what the
# item says it needs, not applied to the species wholesale.
_SAMPLE_SETTLED_GAPS: frozenset[str] = frozenset({"missing_distribution"})


def _settle_asks_the_sample_answers(
    result: dict, columns: "tuple[str, ...]",
) -> None:
    """Drop the identification pass's θ asks that the arriving sample answers.

    The identification pass reads its numbers out of theta, so when theta
    is short it says so — "Theta 中缺条目 P(x=True|z=True)". The caller
    then supplies a DataFrame, which is the other channel those numbers
    come from, and the contract has just certified a column for every
    declared variable. From that moment the ask is answered, and it is
    answered whether or not an estimator goes on to produce a number:
    what the data supplies and what came out of it are different facts,
    resting on different premises.

    They used to be one fact, reconciled in one place, gated on a point
    estimate having been computed. So a query the estimator refused kept
    the entire list — the envelope asked for P(x=True|z=True) beside a
    refusal block reporting its value, 0.5 — and so did an IV query that
    succeeded, because the gate that correctly keeps "this point is
    assumption-laden, the honest tier is still interval" skipped the θ
    half on its way out.

    Only asks over the population under study are settled here, and only
    when the sample measures every variable they name. A named
    population is a different sample, which this one does not stand in
    for however many of the variables it happens to hold.
    """
    items = result.get("missing_information")
    if not isinstance(items, list):
        return
    have = set(columns)
    settled = {
        item["name"]
        for item in items
        if item.get("gap") in _SAMPLE_SETTLED_GAPS
        and isinstance(item.get("observable"), dict)
        and item["observable"].get("population") is None
        and set(item["observable"].get("variables", ())) <= have
    }
    if not settled:
        return
    priority_of = {item["name"]: item["priority"] for item in items}

    kept_items = [i for i in items if i["name"] not in settled]
    if kept_items:
        result["missing_information"] = kept_items
    else:
        result.pop("missing_information", None)

    _drop_investigation_items(result, settled, priority_of)
    _drop_gaps_citing(result, settled)


def _withdraw_asks_estimating_supersedes(result: dict) -> None:
    """Drop the identification pass's asks that estimating has settled.

    An ask can be a precondition rather than a shortfall: the
    identification layer will not write the Wald estimand until
    monotonicity is declared, and says so in the one actionable sentence
    the query gets. Handed a DataFrame, the estimation layer answers the
    same query without reading that declaration — so whichever way it
    goes, the sentence stops being true. It ran, and the ledger discloses
    what the number rested on; or it refused, and no declaration reaches
    a first stage that does not move. The item says which of its asks
    are of this kind at the point it is raised, because only the pass
    imposing a precondition knows it was one.

    Read off ``investigation_requests``, not ``missing_information``:
    the number path pops the latter before this runs. That pop is how a
    delivered LATE went on advertising the declaration that would
    supposedly produce it — item gone, the gap it was pushed from still
    in the report, and the reader shown the surface that had not been
    reconciled.
    """
    if not (result.get("numeric_estimate") or result.get("estimator_failure")):
        return
    settled = {
        item["target"]
        for request in result.get("investigation_requests") or []
        for item in request.get("items") or []
        if item.get("superseded_by_estimation")
    }
    if not settled:
        return

    items = result.get("missing_information")
    items = items if isinstance(items, list) else []
    kept = [i for i in items if i["name"] not in settled]
    if kept:
        result["missing_information"] = kept
    elif items:
        result.pop("missing_information", None)

    _drop_investigation_items(
        result, settled, {i["name"]: i["priority"] for i in items},
    )
    _drop_gaps_citing(result, settled)


def _drop_investigation_items(
    result: dict, settled: "set[str]", priority_of: "dict[str, str]",
) -> None:
    """Remove settled items from their requests, re-summarising the rest.

    A request's target, note and priority describe the items it holds, so
    shrinking the items without re-deriving them leaves "parameter:
    4_items" over two of them. The rule lives with the pass that writes
    requests; this reads it rather than restating it.
    """
    requests = result.get("investigation_requests")
    if not isinstance(requests, list):
        return
    kept_requests: list[dict] = []
    for request in requests:
        items = request.get("items") or []
        kept = [i for i in items if i.get("target") not in settled]
        if len(kept) == len(items):
            kept_requests.append(request)
            continue
        if not kept:
            continue
        target, note, priority = summarise(
            request.get("group") or "",
            [
                (i["target"], _gaps.carried(i),
                 Priority(priority_of.get(i["target"], request["priority"])))
                for i in kept
            ],
        )
        rewritten = dict(request)
        rewritten["items"] = kept
        rewritten["target"] = target
        rewritten["priority"] = priority.value
        if note is not None:
            rewritten["note"] = note
        else:
            rewritten.pop("note", None)
        kept_requests.append(rewritten)
    if kept_requests:
        result["investigation_requests"] = kept_requests
    else:
        result.pop("investigation_requests", None)


def _drop_gaps_citing(result: dict, settled: "set[str]") -> None:
    """Drop the gaps that exist only to report a now-settled item.

    A gap goes when every signal it cites is a settled investigation
    item. One that also cites a derivation step stays: the step failed,
    and the completeness check reads gaps as the only place a failed step
    is accounted for — dropping its last citation would leave the report
    claiming a clean bill of health for something that did not work.
    """
    report = result.get("data_gap_report")
    if not isinstance(report, dict):
        return
    kept = []
    for gap in report.get("gaps", []):
        refs = gap.get("provenance") or []
        reports_only_settled_items = bool(refs) and all(
            ref.get("ref_kind") == "investigation_request"
            and ref.get("ref_id") in settled
            for ref in refs
        )
        if not reports_only_settled_items:
            kept.append(gap)
    if len(kept) != len(report.get("gaps", [])):
        _set_gaps(result, kept, answer_tier=report.get("answer_tier"))


def _set_gaps(
    result: dict, gaps: list[dict], *, answer_tier: str | None,
) -> None:
    """Put a reduced gap list on a result.

    Two surfaces used to be derived from the gaps and stored beside them,
    and each in turn was how a shrunken list went on being reported at its
    old size: the next-steps tail kept opening a settled report with "补
    P(y=True|w=True, x=True)", and the ⚠ lines kept telling the renderer,
    in a channel its prompt makes must-quote, that the answer was a
    symbolic interval on results that had just computed a number.

    Neither is derived here any more, because neither is stored any more —
    a reader assembles both from the gaps it is shown, so a gap this pass
    drops takes its every restatement with it. What is left to do is the
    one thing that is not a restatement.
    """
    report = result.get("data_gap_report")
    if not isinstance(report, dict):
        return
    report["gaps"] = gaps
    if answer_tier is not None:
        report["answer_tier"] = answer_tier


def _attach_mechanism_audit(result: dict, estimate, *, target: str) -> None:
    """Put the shape disclosure for ``estimate`` on ``result.extensions``.

    Fourteen call sites wrote this block out longhand, and the arguments
    were identical at all fourteen but for ``target`` — because there is
    nothing per-family to decide here. ``build_mechanism_audit`` selects the
    functional-form assumptions out of what the estimator declared, so the
    caller has no list to assemble and no sentence to write; what it knows
    that the builder does not is which quantity the shape was fitted for.

    A form-free estimator gets no block rather than an empty one, which is
    why this attaches conditionally: writing ``None`` into ``extensions``
    would put a key there that says a mechanism was audited and found to be
    nothing.
    """
    from ..output.result_orchestrator import build_mechanism_audit

    audit = build_mechanism_audit(
        target=target,
        form=estimate.form,
        method=estimate.method,
        assumptions=estimate.assumptions,
        # Both read off the estimate, never passed in. Who settled a shape is
        # a fact about the run that only the estimator holds, and fourteen
        # attach points writing the same literal was fourteen guesses at it —
        # wrong for every family whose form is fixed by the method. The second
        # is the same argument one level in: a family can have more levers than
        # the outcome model, and only it knows.
        form_provenance=estimate.form_provenance,
        shape_provenance=estimate.shape_provenance,
    )
    if audit is not None:
        result.setdefault("extensions", {})[blocks.Block.MECHANISM_AUDIT] = audit


def _file_gaps(result: dict, gaps: Sequence[DataGap]) -> None:
    """Put diagnostic gaps found DURING estimation onto the result.

    Five call sites repeated the same three moves — translate, create the
    report if this is the first gap, append if it is not — and each
    translated by hand, which is where absence stopped being spelled one way.
    They go through :func:`~themis.output.result_orchestrator.data_gap_to_dict`
    now, the same function the gaps found BEFORE the run go through, so the
    two roads a gap takes to the envelope are one road.

    Building a :class:`~themis.types.DataGap` rather than a dict is what makes
    the spelling unrepeatable rather than merely repaired: the dataclass has
    no way to say "the key is present and null", and ``kind`` / ``severity`` /
    ``blocks`` stop being strings nobody checks.

    The REPORT goes through its own door for the same reason the entries do.
    This function used to hand-write the report's key set when it was the
    first to file a gap, and that made it the second author of a shape the
    dataclass and the schema already state — so when the report lost its
    one-line summary (#442), the hand-written branch went on writing it,
    onto an envelope whose schema forbids the key.

    A route offering an interval is reconciled against the intervals this
    envelope already carries, the same judgement the identification pass
    makes and through the same function (#444). It was not made here, and
    an over-identification test that refuted the instruments went on
    saying "fall back to bounds that do not assume exclusion" beside a
    Manski interval already computed — four such gaps in one suite run.
    Nothing about that judgement belongs to either door: it needs which
    methods a route accepts and which methods produced an interval, and
    both are facts about the answer rather than about which representation
    of the report happens to be in hand. What this door does NOT claim is
    whether an attempt was made and returned nothing — by the time the
    estimator has run, the status the pass reads that off has been
    rewritten, so a promise nothing delivered is left standing here rather
    than withdrawn on a guess.
    """
    from dataclasses import replace

    from .. import gaps as _routes
    from ..output.result_orchestrator import (
        data_gap_report_to_dict, data_gap_to_dict,
    )
    from ..types import BoundsMethod

    if not gaps:
        return
    computed = [
        BoundsMethod(b["method"])
        for b in (result.get("bounds_results") or ())
        if isinstance(b, dict) and b.get("method") in set(BoundsMethod)
    ]
    settled = []
    for gap in gaps:
        # Asked of every gap, including when nothing was computed — the
        # judgement answers "nothing changes" there itself, and a caller
        # that short-circuits it instead is a caller deciding what an
        # empty list of intervals means.
        rewritten = _routes.past_the_bounds_in_hand(
            gap.alternative_paths, computed,
            blocking=gap.severity == GapSeverity.BLOCKING)
        settled.append(gap if rewritten is None
                       else replace(gap, alternative_paths=rewritten))
    gaps = settled
    report = result.get("data_gap_report")
    if report is None:
        result["data_gap_report"] = data_gap_report_to_dict(
            DataGapReport(gaps=tuple(gaps)))
    else:
        report.setdefault("gaps", []).extend(
            data_gap_to_dict(g) for g in gaps)


def _verifier_check(ref_id: str) -> tuple[GapProvenanceRef, ...]:
    """Where a diagnostic gap comes from: a check this layer ran."""
    return (GapProvenanceRef(ref_kind=GapRefKind.VERIFIER_CHECK,
                             ref_id=ref_id),)


def _attach_bootstrap_meta(
    numeric_estimate: dict, cluster: str | None, draws: "Draws | None",
) -> None:
    """Record how this interval's replicates were drawn, and how many were.

    The block used to appear only under a cluster column, so its absence
    carried the claim "i.i.d." — a fact stated by silence, which works
    exactly until a second fact needs saying. It does now: an interval is
    taken over the replicates whose refit succeeded, and where some failed
    the page shows the same two numbers as a run where none did. Two facts
    cannot share one absence, so the block is written whenever a bootstrap
    ran and absence means only that none did.

    ``draws`` is the estimator's own record, kept from the loop that made
    the interval — not a count reconstructed here from what the caller
    asked for. Estimators that report an interval from an analytic formula
    rather than a resample pass ``None`` and get no block, which is the
    same statement as before, now made by having nothing to say rather
    than by saying nothing.
    """
    if draws is None:
        return
    numeric_estimate["bootstrap"] = draws.record(cluster=cluster)


def _attach_precision_budget(numeric_estimate: dict) -> None:
    """Attach a ``precision_budget`` field to ``numeric_estimate`` that
    tells the caller how much more N would be needed to halve the CI.

    Aligns with VISION 2026-04-26 §"输出 (2)" requirement: "在子群 G
    做 RCT n=N 能把 CI 收缩到 ±δ" — for the most common ask (halve
    the CI), we always pre-compute. Caller can call
    ``estimate_n_for_target_ci_half_width`` directly for other targets.

    No-op when ci_lower / ci_upper / sample_size are not all present
    and finite — defensive: estimators that skip bootstrap or have
    NaN bounds shouldn't trigger a misleading hint.
    """
    pb = _compute_precision_budget(
        ci_lower=numeric_estimate.get("ci_lower"),
        ci_upper=numeric_estimate.get("ci_upper"),
        n=numeric_estimate.get("sample_size"),
        point=numeric_estimate.get("point"),
    )
    if pb is not None:
        numeric_estimate["precision_budget"] = pb


def _attach_precision_budget_curve(numeric_estimate: dict) -> None:
    """Dose-response variant: numeric_estimate has a
    ``dose_response_curve`` list where each point carries its own
    ci_lower / ci_upper. Compute a precision_budget per point using
    the SHARED top-level sample_size."""
    curve = numeric_estimate.get("dose_response_curve")
    n = numeric_estimate.get("sample_size")
    if not isinstance(curve, list) or n is None:
        return
    for point in curve:
        if not isinstance(point, dict):
            continue
        pb = _compute_precision_budget(
            ci_lower=point.get("ci_lower"),
            ci_upper=point.get("ci_upper"),
            n=n,
            point=point.get("effect"),
        )
        if pb is not None:
            point["precision_budget"] = pb


def _attach_precision_budget_joint(numeric_estimate: dict) -> None:
    """Joint variant: the contrast and the interaction each carry their own
    interval, so each gets its own budget off the SHARED top-level
    sample_size — the same arrangement the curve and the decomposition use.

    Both slots have declared a ``precision_budget`` in the schema since the
    joint block existed, and neither joint route had ever filled one: the
    flat helper reads ``numeric_estimate.point``, which a joint answer does
    not have, so the budget went missing wherever the answer was a contrast
    rather than a number.
    """
    n = numeric_estimate.get("sample_size")
    if n is None:
        return
    for key in ("joint_effect", "interaction"):
        block = numeric_estimate.get(key)
        if not isinstance(block, dict):
            continue
        pb = _compute_precision_budget(
            ci_lower=block.get("ci_lower"),
            ci_upper=block.get("ci_upper"),
            n=n,
            point=block.get("point"),
        )
        if pb is not None:
            block["precision_budget"] = pb


def _attach_precision_budget_decomposition(numeric_estimate: dict) -> None:
    """Mediation variant: numeric_estimate has a ``decomposition`` dict
    where each component (nde / nie / te / proportion_mediated) carries
    its own ci_lower / ci_upper. Compute a precision_budget per
    component using the SHARED top-level sample_size."""
    decomp = numeric_estimate.get("decomposition")
    n = numeric_estimate.get("sample_size")
    if not isinstance(decomp, dict) or n is None:
        return
    for comp_name, comp in decomp.items():
        if not isinstance(comp, dict):
            continue
        pb = _compute_precision_budget(
            ci_lower=comp.get("ci_lower"),
            ci_upper=comp.get("ci_upper"),
            n=n,
            point=comp.get("point"),
        )
        if pb is not None:
            comp["precision_budget"] = pb


def _compute_precision_budget(
    *, ci_lower, ci_upper, n, point=None,
) -> dict | None:
    """Shared core: compute precision_budget dict from raw CI bounds +
    N (and optionally point estimate, for relative_width).

    Returns None when inputs are not all valid (silent no-op
    semantics; callers attach only when not None).

    ``relative_width`` is present when ``point`` is
    supplied and non-zero — equals half_width / |point|. The
    response_rendering prompt's "surface when CI > 30% of point"
    heuristic becomes a mechanical comparison instead of LLM
    judgment. Omitted when point is None or ~0 (renderer falls back
    to its own qualitative call)."""
    if ci_lower is None or ci_upper is None or n is None:
        return None
    try:
        half_width = (float(ci_upper) - float(ci_lower)) / 2.0
    except (TypeError, ValueError):
        return None
    if half_width <= 0 or not math.isfinite(half_width):
        return None
    if not isinstance(n, int) or n < 1:
        return None
    target = half_width / 2.0
    out: dict = {
        "current_ci_half_width": round(half_width, 6),
        "n_to_halve_ci": estimate_n_for_target_ci_half_width(
            current_n=n,
            current_ci_half_width=half_width,
            target_ci_half_width=target,
        ),
    }
    if point is not None:
        try:
            p = float(point)
        except (TypeError, ValueError):
            p = None
        # Skip relative_width when point is ~0 (division blow-up,
        # ratio not meaningful for null-effect estimates).
        if p is not None and abs(p) > 1e-9 and math.isfinite(p):
            out["relative_width"] = round(half_width / abs(p), 4)
    return out


def _try_doubly_robust_estimate(
    *, result, contract, graph, x, y, adjustment, adjustment_names, given,
    estimator, random_state, ci_bootstrap, model, cluster,
) -> Claim:
    """Attach an IPW / AIPW numeric_estimate to a backdoor-identified
    effect result.

    Mirrors the g-formula path's envelope — mechanism audit, assumption
    ledger, e-value, overlap / separation warnings, precision budget,
    two-step derivation — but swaps in the doubly-robust estimator and
    adds the propensity-overlap disclosure (``propensity_summary``). The
    identification witness is the SAME backdoor_criterion step (the
    adjustment set is a valid backdoor set for all three estimators);
    only the numeric terminal differs (numeric_aipw_estimate /
    numeric_ipw_estimate).
    """
    from .aipw import AIPWEstimate, IPWEstimate, estimate_aipw_ate, estimate_ipw_ate
    from .tmle import TMLEEstimate, estimate_tmle_ate

    est: AIPWEstimate | TMLEEstimate | IPWEstimate
    try:
        if estimator == "aipw":
            est = estimate_aipw_ate(
                contract.data,
                treatment=x.predicate, outcome=y.predicate,
                adjustment=adjustment_names,
                outcome_model=model,
                ci_bootstrap=ci_bootstrap,
                random_state=random_state,
                cluster=cluster,
            )
        elif estimator == "tmle":
            est = estimate_tmle_ate(
                contract.data,
                treatment=x.predicate, outcome=y.predicate,
                adjustment=adjustment_names,
                ci_bootstrap=ci_bootstrap,
                random_state=random_state,
                cluster=cluster,
            )
        else:
            est = estimate_ipw_ate(
                contract.data,
                treatment=x.predicate, outcome=y.predicate,
                adjustment=adjustment_names,
                ci_bootstrap=ci_bootstrap,
                random_state=random_state,
                cluster=cluster,
            )
    except EstimatorFailure as exc:
        refusals.record(result, estimator=estimator, exc=exc)
        # The caller asked for THIS estimator by name. Falling through to
        # the g-formula would answer with a number they did not request and
        # cannot tell apart from the one they did.
        return blocked('estimator_refused')

    prop = est.propensity
    ne = {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": est.method,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "adjustment": list(est.adjustment),
        "treatment": est.treatment,
        "outcome": est.outcome,
        "propensity_summary": {
            "raw_min": prop.raw_min,
            "raw_max": prop.raw_max,
            "n_trimmed": prop.n_trimmed,
            "floor": prop.floor,
            "model": prop.model,
        },
    }
    if isinstance(est, (AIPWEstimate, TMLEEstimate)):
        ne["doubly_robust"] = True
        ne["std_error"] = est.std_error
        ne["ci_method"] = est.ci_method
        if isinstance(est, TMLEEstimate):
            # The fluctuation parameter — a transparency handle: ε≈0 means
            # the initial outcome fit was already well-targeted.
            ne["tmle_epsilon"] = est.epsilon
        if est.ci_method != "influence_function":
            _attach_bootstrap_meta(ne, cluster, est.draws)
        # The analytic path attaches nothing here. It used to write an
        # ``inference`` block restating two facts the envelope already
        # carries: its ``method`` was a one-member enum pinned by the branch
        # that wrote it and identical to ``ci_method`` two lines up, and its
        # ``cluster_robust`` flag was ``cluster is not None`` — which
        # ``estimation_context.cluster`` records at run level and the
        # estimator declares in its own assumptions, where it reaches a
        # reader as a sentence. Those are the two independent directions
        # ``verifier.cluster_inference_rules`` audits from; a third copy
        # written by the layer that passed the column in is from neither, and
        # because it recorded a boolean rather than the column name there was
        # nothing in it to corroborate.
    else:
        ne["stabilized"] = est.stabilized
        _attach_bootstrap_meta(ne, cluster, est.draws)

    result["numeric_estimate"] = ne

    from ..output.result_orchestrator import (
        build_assumption_ledger,
    )
    ext = result.setdefault("extensions", {})
    _attach_mechanism_audit(result, est, target=est.outcome)
    ledger = build_assumption_ledger(
        result, 
    )
    if ledger is not None:
        ext[blocks.Block.ASSUMPTION_LEDGER] = ledger

    _attach_precision_budget(ne)
    _DR_TERMINAL = {
        "aipw": "numeric_aipw_estimate",
        "tmle": "numeric_tmle_estimate",
        "ipw": "numeric_ipw_estimate",
    }
    result["derivation"] = _build_dr_numeric_derivation_dict(
        graph=graph, x=x, y=y, adjustment=adjustment, given=given,
        estimate=est, terminal_rule=_DR_TERMINAL[estimator],
    )
    _attach_e_value_if_binary(
        result, contract, outcome=y.predicate, treatment=x.predicate,
    )
    _attach_propensity_overlap_warning(
        result, contract, treatment=x.predicate, adjustment=adjustment_names,
    )
    _attach_outcome_separation_warning(
        result, contract, treatment=x.predicate, outcome=y.predicate,
        adjustment=adjustment_names,
    )
    _finalise_numeric_result(result)
    return answered()


def _build_dr_numeric_derivation_dict(
    *, graph, x, y, adjustment, given, estimate, terminal_rule,
):
    """Two-step derivation for a doubly-robust (IPW / AIPW / TMLE) estimate:

        s1: backdoor_criterion (same structural witness as g-formula —
            the adjustment set is a valid backdoor set)
        s2: numeric_aipw_estimate / numeric_tmle_estimate /
            numeric_ipw_estimate (metadata audit of the estimate +
            propensity disclosure — no re-fit)
    """
    from ..types import DerivationStep, StepRef, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    prop = estimate.propensity
    terminal_inputs = {
        "criterion": StepRef(step_id="s1"),
        "treatment": x,
        "outcome": y,
        "adjustment": frozenset(adjustment),
        "method": estimate.method,
        "data_hash": estimate.data_hash,
        "sample_size": estimate.sample_size,
        "point": estimate.point,
        "ci_lower": estimate.ci_lower,
        "ci_upper": estimate.ci_upper,
        "ci_level": estimate.ci_level,
        "propensity_raw_min": prop.raw_min,
        "propensity_raw_max": prop.raw_max,
        "propensity_n_trimmed": prop.n_trimmed,
        "propensity_floor": prop.floor,
    }
    if terminal_rule in ("numeric_aipw_estimate", "numeric_tmle_estimate"):
        terminal_inputs["doubly_robust"] = estimate.doubly_robust
        terminal_inputs["std_error"] = estimate.std_error
        terminal_inputs["ci_method"] = estimate.ci_method
    if terminal_rule == "numeric_tmle_estimate":
        terminal_inputs["tmle_epsilon"] = estimate.epsilon

    steps = (
        DerivationStep(
            rule="backdoor_criterion",
            inputs={
                "graph": graph,
                "x": x, "y": y,
                "z": frozenset(adjustment),
                "given": given,
            },
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule=terminal_rule,
            inputs=terminal_inputs,
            output=StructuralResult(value=True),
            step_id="s2",
        ),
    )
    return derivation_to_dict(steps)


def _build_numeric_derivation_dict(
    *, graph, x, y, adjustment, given, estimate,
):
    """Build a two-step derivation (backdoor_criterion + numeric_backdoor_estimate)
    and encode it to the JSON shape used by query_result.schema.json.
    """
    from ..types import DerivationStep, StepRef, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    steps = (
        DerivationStep(
            rule="backdoor_criterion",
            inputs={
                "graph": graph,
                "x": x, "y": y,
                "z": frozenset(adjustment),
                "given": given,
            },
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="numeric_backdoor_estimate",
            inputs={
                "criterion": StepRef(step_id="s1"),
                "treatment": x,
                "outcome": y,
                "adjustment": frozenset(adjustment),
                "method": estimate.method,
                "data_hash": estimate.data_hash,
                "sample_size": estimate.sample_size,
                "point": estimate.point,
                "ci_lower": estimate.ci_lower,
                "ci_upper": estimate.ci_upper,
                "ci_level": estimate.ci_level,
            },
            output=StructuralResult(value=True),
            step_id="s2",
        ),
    )
    return derivation_to_dict(steps)


def _build_iv_numeric_derivation_dict(
    *, graph, x, y, instrument, conditioning, estimate, loop=None,
):
    """Two-step derivation for a data-based IV estimate:

        s1: iv_criterion_check (structural witness, Phase 6.iv)
        s2: numeric_iv_estimate (metadata audit — no re-fit)

    ``loop`` prepends a third, and it is not decoration. This function
    REPLACES the identification layer's derivation on the shipped answer,
    so a licence recorded only there is a licence no audit of the shipped
    answer ever sees. Under #450 the licence in question is the one that
    withdrew back-door — the reason an instrument was reached at all —
    and without it the trail reads as an ordinary escalation from a graph
    where adjustment happened to fail.
    """
    from ..types import DerivationStep, StepRef, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    withdrawal = () if loop is None else (
        DerivationStep(
            rule="feedback_loop_withdraws_adjustment",
            inputs={"graph": graph, "x": x, "y": y,
                    "left": loop[0], "right": loop[1]},
            output=True,
            step_id="s_loop",
        ),
    )
    steps = withdrawal + (
        DerivationStep(
            rule="iv_criterion_check",
            inputs={
                "graph": graph,
                "x": x, "y": y,
                "instrument": instrument,
                "conditioning": frozenset(conditioning),
            },
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="numeric_iv_estimate",
            inputs={
                "criterion": StepRef(step_id="s1"),
                "treatment": x,
                "outcome": y,
                "instrument": instrument,
                "conditioning": frozenset(conditioning),
                "method": estimate.method,
                "data_hash": estimate.data_hash,
                "sample_size": estimate.sample_size,
                "point": estimate.point,
                "ci_lower": estimate.ci_lower,
                "ci_upper": estimate.ci_upper,
                "ci_level": estimate.ci_level,
                **_ar_derivation_inputs(estimate.anderson_rubin),
                **_stratified_wald_derivation_inputs(estimate),
                **_stratified_ar_derivation_inputs(
                    estimate.stratified_anderson_rubin
                ),
            },
            output=StructuralResult(value=True),
            step_id="s2",
        ),
    )
    return derivation_to_dict(steps)


def _stratified_wald_derivation_inputs(estimate) -> dict:
    """The per-stratum table as flat derivation inputs.

    Unlike the fitted-model paths, this estimator has a closed-form
    sufficient statistic: the point is a function of the stratum weights
    and shifts and nothing else. Recording them lifts the verifier above
    the usual metadata audit — it can recompute the aggregate as a ratio
    of averages and reject a point that is the average of the per-stratum
    ratios instead, which is the one wrong answer that looks right.

    The per-stratum variance coefficients ride along for the same reason:
    the stratified Anderson-Rubin set is a closed-form function of them,
    so recording them lets the verifier re-solve the SET too rather than
    take the producer's word for its endpoints.

    Empty on the marginal-Wald / 2SLS paths.
    """
    if estimate.strata is None:
        return {}
    return {
        "stratum_weights": tuple(s.weight for s in estimate.strata),
        "stratum_outcome_shifts": tuple(
            s.outcome_shift for s in estimate.strata
        ),
        "stratum_treatment_shifts": tuple(
            s.treatment_shift for s in estimate.strata
        ),
        "stratum_shift_var_yy": tuple(
            s.shift_var_yy for s in estimate.strata
        ),
        "stratum_shift_var_xy": tuple(
            s.shift_var_xy for s in estimate.strata
        ),
        "stratum_shift_var_xx": tuple(
            s.shift_var_xx for s in estimate.strata
        ),
        "aggregate_outcome_shift": estimate.outcome_shift,
        "aggregate_treatment_shift": estimate.treatment_shift,
    }


def _stratified_ar_derivation_inputs(sar) -> dict:
    """The stratified Anderson-Rubin set + the aggregate moment it was
    solved from, as flat derivation inputs. The verifier rebuilds the same
    aggregates from the stratum table, re-solves the quadratic, and pins
    the set's point to the headline point — the invariant that fails the
    moment a linear AR set is attached to a stratified estimate.
    Empty when no stratified AR set is attached."""
    if sar is None:
        return {}
    return {
        "sar_kind": sar.kind,
        "sar_lower": sar.lower,
        "sar_upper": sar.upper,
        "sar_ci_level": sar.ci_level,
        "sar_point": sar.point,
        "sar_kappa": sar.kappa,
        "sar_outcome_shift": sar.outcome_shift,
        "sar_treatment_shift": sar.treatment_shift,
        "sar_var_yy": sar.var_yy,
        "sar_var_xy": sar.var_xy,
        "sar_var_xx": sar.var_xx,
        "sar_n_obs": sar.n_obs,
        "sar_n_strata": sar.n_strata,
        "sar_dof": sar.dof,
    }


def _ar_derivation_inputs(ar) -> dict:
    """The Anderson-Rubin set + its residualised sufficient statistics as
    flat derivation inputs, so the verifier can independently re-solve the
    quadratic (and re-derive the point Szy/Szx) without the raw data.
    Empty when no AR set is attached (degenerate / not computed)."""
    if ar is None:
        return {}
    return {
        "ar_kind": ar.kind,
        "ar_lower": ar.lower,
        "ar_upper": ar.upper,
        "ar_ci_level": ar.ci_level,
        "ar_point": ar.point,
        "ar_kappa": ar.kappa,
        "ar_s_yy": ar.s_yy,
        "ar_s_xy": ar.s_xy,
        "ar_s_xx": ar.s_xx,
        "ar_s_zy": ar.s_zy,
        "ar_s_zx": ar.s_zx,
        "ar_s_zz": ar.s_zz,
        "ar_n_obs": ar.n_obs,
        "ar_n_exog": ar.n_exog,
    }


def _try_iv_overid_estimate(
    result, contract, graph, *, x, y, instruments, conditioning,
    random_state, ci_bootstrap, cluster,
) -> Claim:
    """Over-identified 2SLS (q ≥ 2 instruments) + Sargan test. Attaches the
    numeric block (with the Sargan over-identification test and the moment
    sufficient statistics), builds a derivation ending in
    ``numeric_iv_overid_estimate``, and finalises. Returns False on a
    degenerate design so the caller falls back to the just-identified path.

    ``instruments`` / ``conditioning`` are tuples of Atoms."""
    from .iv import estimate_iv_overid

    instrument_preds = tuple(a.predicate for a in instruments)
    cond_preds = tuple(a.predicate for a in conditioning)
    try:
        est = estimate_iv_overid(
            contract.data,
            treatment=x.predicate, outcome=y.predicate,
            instruments=instrument_preds, conditioning=cond_preds,
            ci_bootstrap=ci_bootstrap, random_state=random_state, cluster=cluster,
        )
    except EstimatorFailure:
        # Deliberately not recorded: the query stays in flight and the
        # just-identified path answers it. A block written here would name
        # a refusal beside the number that followed it.
        return passed('estimator_refused')

    sargan = est.sargan
    if sargan is None:
        # This row exists to report the over-identification test, so a
        # missing one is not a degenerate design to fall back from — it is
        # the estimate contradicting itself. `estimate_iv_overid` computes
        # the Sargan J on every path that returns, so the field's optional
        # type is the only thing that admits this at all.
        raise AssertionError(
            "the over-identified IV estimate carries no Sargan test; the "
            "estimator computes it on every path that returns an estimate"
        )
    over_identification: dict[str, object] = {
        "test": "sargan",
        "sargan_j": sargan.j_stat,
        "sargan_dof": sargan.dof,
        "sargan_p_value": sargan.p_value,
        "rejected_at_0_05": bool(sargan.p_value < 0.05),
        # Residualised second moments the point + J are closed forms of (plus
        # the robust weight matrix Ŝ when Hansen J was computed) — the
        # verifier re-derives everything from these without the raw data.
        "sufficient_statistics": est.moments,
    }
    numeric: dict[str, object] = {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": est.method,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "instruments": list(est.instruments),
        "conditioning": list(est.conditioning),
        "treatment": est.treatment,
        "outcome": est.outcome,
        "n_instruments": est.n_instruments,
        "over_identification": over_identification,
    }
    # Heteroskedasticity-robust (efficient two-step GMM) Hansen J, when the
    # robust weight matrix was non-singular. The headline point stays 2SLS;
    # hansen_gmm_point is the efficient-GMM byproduct.
    if est.hansen is not None:
        over_identification["hansen_j"] = est.hansen.j_stat
        over_identification["hansen_dof"] = est.hansen.dof
        over_identification["hansen_p_value"] = est.hansen.p_value
        over_identification["hansen_gmm_point"] = est.hansen.gmm_point
        over_identification["hansen_rejected_at_0_05"] = bool(
            est.hansen.p_value < 0.05
        )
    # Multi-instrument Anderson-Rubin weak-ID-robust set — the honest interval
    # when the joint first stage is weak (the bootstrap CI is not). The verifier
    # re-solves the quadratic from the moments already in sufficient_statistics.
    if est.anderson_rubin is not None:
        numeric["anderson_rubin_confidence_set"] = _overid_ar_set_to_dict(
            est.anderson_rubin,
        )
    # Heteroskedasticity-robust (Stock-Wright S) AR set — valid under weak-ID AND
    # heteroskedasticity/clustering. The robust weight matrices S0/S1/S2 the
    # verifier re-evaluates AR_r from are recorded in sufficient_statistics.
    if est.robust_anderson_rubin is not None:
        numeric["robust_anderson_rubin_confidence_set"] = _robust_ar_set_to_dict(
            est.robust_anderson_rubin,
        )
    if est.first_stage_f_stat is not None:
        numeric["first_stage_f_stat"] = est.first_stage_f_stat

    result["numeric_estimate"] = numeric
    _attach_bootstrap_meta(result["numeric_estimate"], cluster, est.draws)
    _attach_precision_budget(result["numeric_estimate"])
    _attach_mechanism_audit(result, est, target=est.outcome)
    result["derivation"] = _build_iv_overid_numeric_derivation_dict(
        graph=graph, x=x, y=y,
        instruments=instruments, conditioning=conditioning, estimate=est,
    )
    _attach_e_value_if_binary(
        result, contract, outcome=y.predicate, treatment=x.predicate,
    )
    _attach_overid_iv_warnings(result, est)
    _finalise_numeric_result(result)
    return answered()


def _vector_ar_region_to_dict(region) -> dict:
    """Serialise the region. The quadratic (``a_matrix`` / ``b_vector`` /
    ``c_scalar``) travels with it because the shape and the projections are
    claims ABOUT it: a verifier that re-classifies from the same quadratic is
    checking the classification, and one that re-derives the quadratic from
    the moments is checking the inversion. Both are wanted, and neither can be
    done from a shape name."""
    return {
        "treatments": list(region.treatments),
        "shape": region.shape,
        "bounded": region.bounded,
        "a_matrix": [list(row) for row in region.a_matrix],
        "b_vector": list(region.b_vector),
        "c_scalar": region.c_scalar,
        "center": None if region.center is None else list(region.center),
        "point": None if region.point is None else list(region.point),
        "projections": [
            {"treatment": p.treatment, "kind": p.kind,
             "lower": p.lower, "upper": p.upper}
            for p in region.projections
        ],
        "ci_level": region.ci_level,
        "kappa": region.kappa,
        "dof_num": region.dof_num,
        "dof_denom": region.dof_denom,
    }


def _try_vector_iv_estimate(
    result, contract, graph, *, treatments, y, candidates, instruments,
    cluster,
) -> Claim:
    """Anderson-Rubin confidence region for a vector of endogenous treatments.

    Whether this row owns the query is decided by the region and not by the
    row: a bounded region is an answer (k conservative intervals, so the
    interval tier), and an unbounded, empty or whole-space one is a fact ABOUT
    the answer that no other block carries — that the instruments leave some
    direction free, or refute the model outright — so it is attached beside
    the structural result rather than replacing it.
    """
    from .iv import estimate_iv_vector

    treatment_preds = tuple(t.predicate for t in treatments)
    w0 = candidates[0].conditioning if candidates else frozenset()
    cond_preds = tuple(sorted(a.predicate for a in w0))
    instrument_preds = tuple(z.predicate for z in instruments)

    df = contract.data
    needed = (*treatment_preds, y.predicate, *instrument_preds, *cond_preds)
    if any(c not in df.columns for c in needed):
        return passed('required_columns_absent')

    try:
        est = estimate_iv_vector(
            df,
            treatments=treatment_preds, outcome=y.predicate,
            instruments=instrument_preds, conditioning=cond_preds,
            cluster=cluster,
        )
    except EstimatorFailure:
        # Not recorded: the caller's own refusal is what the reader gets, and
        # a block written here would name a second one beside it.
        return passed('estimator_refused')

    region = est.region
    relevant_by_instrument = {
        c.instrument.predicate: sorted(a.predicate for a in c.relevant_to)
        for c in candidates if c.conditioning == w0
    }
    ext = dict(result.get("extensions") or {})
    ext[blocks.Block.VECTOR_IV_IDENTIFICATION] = {
        "kind": "vector_iv_identification",
        "treatments": list(treatment_preds),
        "outcome": y.predicate,
        "instruments": list(instrument_preds),
        "conditioning": list(cond_preds),
        "relevance": [
            {"instrument": z, "moves": relevant_by_instrument.get(z, [])}
            for z in instrument_preds
        ],
        "reference": "Anderson & Rubin 1949; Dufour & Taamouti 2005",
    }
    result["extensions"] = ext

    ext[blocks.Block.ANDERSON_RUBIN_REGION] = {
        "kind": "anderson_rubin_region",
        "method": est.method,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "treatments": list(est.treatments),
        "outcome": est.outcome,
        "instruments": list(est.instruments),
        "conditioning": list(est.conditioning),
        "region": _vector_ar_region_to_dict(region),
        # The residualised second moments the region is a closed form of —
        # the verifier re-derives the quadratic, the shape and every
        # projection from these without the raw data.
        "sufficient_statistics": est.moments,
    }
    result["extensions"] = ext
    _attach_mechanism_audit(result, est, target=est.outcome)
    if not region.bounded:
        # No derivation. A derivation is the chain THIS result stands on, and
        # its last step's output is the result — so a row that annotates must
        # not write one, or the envelope says the effect was established
        # (terminal True) and refused (structural_result False) at once. The
        # region is still audited: the kernel re-derives it off the extensions
        # map, which is where a fact attached beside a refusal belongs.
        return annotated()
    result["derivation"] = _build_vector_iv_derivation_dict(
        graph=graph, treatments=treatments, y=y,
        instruments=instruments, conditioning=w0, estimate=est,
    )
    _finalise_numeric_bounds_result(result)
    return answered()


def _build_vector_iv_derivation_dict(
    *, graph, treatments, y, instruments, conditioning, estimate,
):
    """Derivation for an Anderson-Rubin region:

        s_iv_0 .. s_iv_{q-1}: vector_iv_criterion_check (one structural
                              witness per instrument, re-verified against the
                              treatment SET rather than one treatment)
        s_num:                numeric_anderson_rubin_region (metadata +
                              structural licensing; the region itself is
                              re-derived from the recorded moments by
                              ``themis.verifier.verify_vector_iv_region``, which the
                              kernel calls — the moments are matrices that do
                              not fit derivation-input serialization)
    """
    from ..types import DerivationStep, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    steps = []
    for i, z in enumerate(instruments):
        steps.append(DerivationStep(
            rule="vector_iv_criterion_check",
            inputs={
                "graph": graph, "y": y,
                "treatments": frozenset(treatments),
                "instrument": z,
                "conditioning": frozenset(conditioning),
            },
            output=True,
            step_id=f"s_iv_{i}",
        ))
    steps.append(DerivationStep(
        rule="numeric_anderson_rubin_region",
        inputs={
            "treatments": frozenset(treatments), "outcome": y,
            "instruments": frozenset(instruments),
            "conditioning": frozenset(conditioning),
            "method": estimate.method,
            "data_hash": estimate.data_hash,
            "sample_size": estimate.sample_size,
            "shape": estimate.region.shape,
            "ci_level": estimate.region.ci_level,
        },
        output=StructuralResult(value=True),
        step_id="s_num",
    ))
    return derivation_to_dict(tuple(steps))


def _build_iv_overid_numeric_derivation_dict(
    *, graph, x, y, instruments, conditioning, estimate,
):
    """Derivation for an over-identified 2SLS estimate:

        s_iv_0 .. s_iv_{q-1}: iv_criterion_check (one structural witness per
                              instrument — each independently re-verified)
        s_num:                numeric_iv_overid_estimate (metadata + structural
                              licensing; the Sargan / point re-derivation from
                              the recorded moments is verify_iv_overid_numeric,
                              called from the kernel — the moments are matrices
                              that don't fit derivation-input serialization)
    """
    from ..types import DerivationStep, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    steps = []
    for i, z in enumerate(instruments):
        steps.append(DerivationStep(
            rule="iv_criterion_check",
            inputs={
                "graph": graph, "x": x, "y": y,
                "instrument": z,
                "conditioning": frozenset(conditioning),
            },
            output=True,
            step_id=f"s_iv_{i}",
        ))
    steps.append(DerivationStep(
        rule="numeric_iv_overid_estimate",
        inputs={
            "treatment": x, "outcome": y,
            "instruments": frozenset(instruments),
            "conditioning": frozenset(conditioning),
            "method": estimate.method,
            "data_hash": estimate.data_hash,
            "sample_size": estimate.sample_size,
            "point": estimate.point,
            "ci_lower": estimate.ci_lower,
            "ci_upper": estimate.ci_upper,
            "ci_level": estimate.ci_level,
            "n_instruments": estimate.n_instruments,
        },
        output=StructuralResult(value=True),
        step_id="s_num",
    ))
    return derivation_to_dict(tuple(steps))


def _attach_overid_iv_warnings(result: dict, est) -> None:
    """Surface two IV diagnostics for an over-identified estimate as
    caveats on the answer: a weak JOINT first stage (F < Stock-Yogo) and a
    REJECTED Sargan over-identification test (the data refute the
    instruments' joint validity). Both are informational — the point is
    still reported; these add the caveat."""
    inst = ", ".join(f"`{z}`" for z in est.instruments)
    gaps: list[DataGap] = []

    f_stat = est.first_stage_f_stat
    if f_stat is not None and f_stat < WEAK_IV_F_THRESHOLD:
        # When the joint first stage is weak, point to the multi-instrument
        # Anderson-Rubin set — the interval that stays valid whatever the
        # instrument strength — instead of the unreliable bootstrap CI (parity
        # with the just-identified _attach_weak_iv_warning_if_low_f).
        ar = est.anderson_rubin
        said = [_sentence(
            Sentence.THE_JOINT_FIRST_STAGE_IS_WEAK,
            instruments=inst, f=f"{f_stat:.2f}",
            threshold=f"{WEAK_IV_F_THRESHOLD:.0f}",
        )]
        ar_alt = _gaps.route(Route.AR_SET_FOR_THE_JOINT_STAGE)
        if ar is not None:
            rendered = _render_ar_set(ar)
            pct = int(round(ar.ci_level * 100))
            said.append(_sentence(
                Sentence.THE_MULTI_INSTRUMENT_ANDERSON_RUBIN_SET_IS_THIS,
                level=pct, interval=rendered))
            ar_alt = _gaps.route(
                Route.USE_THE_AR_SET, level=pct, interval=rendered)
        # Prefer the heteroskedasticity-robust (Stock-Wright S) AR set when it was
        # computed: it is valid under weak identification AND heteroskedasticity /
        # clustering, so it is the strongest interval to report here.
        rar = est.robust_anderson_rubin
        if rar is not None:
            rrendered = _render_robust_ar_set(rar)
            pct = int(round(rar.ci_level * 100))
            said.append(_sentence(
                Sentence
                .THE_HETEROSKEDASTICITY_ROBUST_ANDERSON_RUBIN_SET_IS_THIS,
                level=pct, interval=rrendered))
            ar_alt = _gaps.route(
                Route.USE_THE_ROBUST_AR_SET, level=pct, interval=rrendered)
        gaps.append(DataGap(
            kind=GapKind.WEAK_IV_INSTRUMENT,
            severity=GapSeverity.INFORMATIONAL,
            blocks=GapBlocks.INTERPRETATION,
            describes=tuple(said),
            alternative_paths=(
                _gaps.route(Route.FIND_STRONGER_INSTRUMENTS_JOINTLY),
                ar_alt,
                _gaps.route(Route.FALL_BACK_TO_IV_BOUNDS),
            ),
            provenance=_verifier_check(f"weak_iv_joint:{est.treatment}"),
        ))

    # Over-identification falsification. Prefer the heteroskedasticity-robust
    # Hansen J (the correct weight matrix) when it was computed; fall back to the
    # homoskedastic Sargan only when the robust weight was singular. Same
    # GapKind either way. Under homoskedasticity the two coincide, so this does
    # not change the conclusion on well-behaved data; on heteroskedastic data it
    # makes the falsification robust rather than reporting a test whose weighting
    # the data violate.
    sg = est.sargan
    hj = est.hansen
    if hj is not None:
        test_label, J_used, dof_used, p_used = (
            "Hansen J (heteroskedasticity-robust)", hj.j_stat, hj.dof, hj.p_value,
        )
    elif sg is not None:
        test_label, J_used, dof_used, p_used = (
            "Sargan", sg.j_stat, sg.dof, sg.p_value,
        )
    else:
        test_label = None
    if test_label is not None and p_used < 0.05:
        said = [_sentence(
            Sentence.THE_OVERIDENTIFICATION_TEST_REFUTED_THE_INSTRUMENTS,
            test=test_label, instruments=inst, j=f"{J_used:.2f}",
            df=dof_used, p=f"{p_used:.4g}",
        )]
        if hj is not None and sg is not None:
            said.append(_sentence(
                Sentence.THE_HOMOSKEDASTIC_SARGAN_SAYS_THE_SAME,
                j=f"{sg.j_stat:.2f}", p=f"{sg.p_value:.4g}"))
        gaps.append(DataGap(
            kind=GapKind.OVERIDENTIFICATION_REJECTED,
            severity=GapSeverity.IMPORTANT,
            blocks=GapBlocks.INTERPRETATION,
            describes=tuple(said),
            alternative_paths=(
                _gaps.route(Route.DROP_THE_SUSPECT_INSTRUMENT),
                _gaps.route(Route.REEXAMINE_THE_GRAPH_FOR_A_DIRECT_PATH),
                _gaps.route(Route.FALL_BACK_TO_BOUNDS_WITHOUT_EXCLUSION),
            ),
            provenance=_verifier_check(f"overid:{est.treatment}"),
        ))

    if not gaps:
        return
    _file_gaps(result, gaps)


def _build_frontdoor_numeric_derivation_dict(
    *, graph, x, y, mediators, estimate,
):
    """Build a two-step derivation for a front-door data estimate:

        s1: front_door_criterion (structural witness)
        s2: numeric_frontdoor_estimate (metadata audit only — no re-fit)
    """
    from ..types import DerivationStep, StepRef, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    steps = (
        DerivationStep(
            rule="front_door_criterion",
            inputs={
                "graph": graph,
                "x": x, "y": y,
                "z": frozenset(mediators),
            },
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="numeric_frontdoor_estimate",
            inputs={
                "criterion": StepRef(step_id="s1"),
                "treatment": x,
                "outcome": y,
                "mediators": frozenset(mediators),
                "method": estimate.method,
                "data_hash": estimate.data_hash,
                "sample_size": estimate.sample_size,
                "point": estimate.point,
                "ci_lower": estimate.ci_lower,
                "ci_upper": estimate.ci_upper,
                "ci_level": estimate.ci_level,
            },
            output=StructuralResult(value=True),
            step_id="s2",
        ),
    )
    return derivation_to_dict(steps)


def _pair_effect_queries(prog, output):
    """Yield (QueryStatement, result_dict) pairs whose query is an
    EffectQuery. Alignment uses query_id as the key to avoid order
    dependence.
    """
    from ..types import EffectQuery, QueryStatement

    id_to_stmt = {
        s.id: s for s in prog.statements
        if isinstance(s, QueryStatement) and isinstance(s.query, EffectQuery)
    }
    for result in output.get("results", []):
        if result.get("query_kind") != "effect":
            continue
        qid = result.get("query_id")
        yield id_to_stmt.get(qid), result


def _dose_response_routing_plan(prog) -> tuple[set[str], list[str]]:
    """Return (target_query_ids, warnings) for dose-response estimation.

    Resolution rule:
    1. Explicit ``query_id`` targets exactly that non-mediation effect
       query. Bad ids and mediation ids produce warnings instead of
       silently disappearing.
    2. Without explicit ``query_id``, route the first *non-mediation*
       effect query. This avoids the old leak where a leading mediation
       query consumed the dose-response ambiguity and the intended
       ordinary effect query was never estimated.
    3. If there is no eligible effect query, leave routing empty and
       emit a data-contract warning. The structural layer may still
       expose a ``dose_response_data_required`` gap on a non-effect
       query; the estimator must not stay silent.
    """
    from ..types import EffectQuery, QueryStatement

    extensions = getattr(prog, "extensions", None) or {}
    ambs = extensions.get("ambiguities") or []
    dose_ambs = [
        a for a in ambs
        if isinstance(a, dict) and a.get("kind") == "dose_response_query"
    ]
    if not dose_ambs:
        return set(), []

    # (statement id, the effect query itself). A statement's ``query`` is the
    # whole query union and only mediation queries have a ``mediator``, so
    # every reader below would have to re-establish what this comprehension
    # already decided. Carrying the narrowed query is that decision, kept.
    effect_queries: list[tuple[str, EffectQuery]] = [
        (s.id, s.query) for s in prog.statements
        if isinstance(s, QueryStatement) and isinstance(s.query, EffectQuery)
    ]
    query_by_id = dict(effect_queries)
    eligible_effect_ids = [
        qid for qid, query in effect_queries
        if query.mediator is None
    ]

    warnings: list[str] = []
    if not effect_queries:
        warnings.append(
            "程序里有 dose_response_query，却没有任何 effect 查询；"
            "估计量已跳过，该看数据缺口报告",
        )
        return set(), warnings
    if not eligible_effect_ids:
        warnings.append(
            "程序里有 dose_response_query，但所有 effect 查询都是中介查询；"
            "剂量-反应估计量需要一个非中介的 "
            "effect 查询",
        )
        return set(), warnings

    targets: set[str] = set()
    for a in dose_ambs:
        explicit = a.get("query_id")
        if explicit is not None:
            target_query = query_by_id.get(explicit)
            if target_query is None:
                warnings.append(
                    f"dose_response_query 的 query_id {explicit!r} "
                    "对不上任何一个 effect 查询；因为这个歧义，"
                    "估计量已跳过",
                )
            elif target_query.mediator is not None:
                warnings.append(
                    f"dose_response_query query_id {explicit!r} targets a "
                    "mediation effect query; dose-response estimator skipped",
                )
            else:
                targets.add(explicit)
        else:
            first_effect_id = effect_queries[0][0]
            first_eligible_id = eligible_effect_ids[0]
            if first_effect_id != first_eligible_id:
                warnings.append(
                    "dose_response_query 没有给 query_id，于是跳过了排在前面的"
                    f"中介 effect 查询 {first_effect_id!r}，"
                    f"路由到了 {first_eligible_id!r}",
                )
            targets.add(first_eligible_id)
    return targets, warnings


def _append_data_contract_warnings(output: dict, warnings: list[str]) -> None:
    if not warnings:
        return
    for result in output.get("results", []):
        for warning in warnings:
            _append_result_data_contract_warning(result, warning)


def _append_result_data_contract_warning(result: dict, warning: str) -> None:
    ctx = result.setdefault("estimation_context", {})
    existing = list(ctx.get("data_contract_warnings") or [])
    if warning not in existing:
        existing.append(warning)
    ctx["data_contract_warnings"] = existing


def _is_binary_treatment(data, treatment: str) -> bool:
    if treatment not in data.columns:
        return False
    series = data[treatment].dropna()
    if series.empty:
        return False
    try:
        if str(series.dtype) == "bool":
            return True
        values = set(series.unique().tolist())
    except Exception:
        return False
    return values.issubset({False, True, 0, 1}) and len(values) <= 2


def _resolve_dose_response_points(prog, x_atom):
    """Pick sampling points for the curve. Prefers the treatment
    variable's declared numeric domain (e.g. raise tiers [500, 1000,
    2000]); returns None to let the estimator fall back to quantiles
    when the domain is missing or non-numeric."""
    from ..types import VariableDeclaration

    for stmt in prog.statements:
        if not isinstance(stmt, VariableDeclaration):
            continue
        if stmt.predicate != x_atom.predicate:
            continue
        domain = stmt.domain
        if not domain:
            return None
        try:
            return tuple(sorted(float(v) for v in domain))
        except (TypeError, ValueError):
            return None
    return None


#: The closed set the envelope declares for ``estimation_context.
#: model_preference``. Two vocabularies meet in it: the binary-effect
#: entry takes 'auto' / 'linear' / 'logistic' and the dose-response one
#: takes 'auto' / 'linear' / 'forest' / 'drlearner'.
_DECLARED_MODELS = ("auto", "linear", "logistic", "forest", "drlearner")


def _declared_model(model: str) -> str:
    """The caller's ``model``, as the option rather than as typed.

    Casing and whitespace are facts about the call, not about the run, so
    they are settled once at the entry and neither the estimators nor the
    envelope see them. Before this, five places read the raw string and
    only two of them normalised: ``model='DRLearner'`` — the casing
    EconML's own class name invites — answered a dose-response query and
    was refused by the backdoor estimator, and either way the envelope
    recorded the spelling, outside the enum its schema declares.

    The set is the UNION of two vocabularies (the binary-effect entry
    knows 'logistic', the dose-response one knows 'forest' / 'drlearner'),
    because that is what this function can decide: a value belongs to
    ``estimate``'s option or it does not. Whether the route that ends up
    running accepts it is that route's own question, and each one still
    asks it.
    """
    if not isinstance(model, str):
        raise ValueError(f"model must be a string, got {type(model).__name__}")
    normalized = model.strip().lower()
    if normalized not in _DECLARED_MODELS:
        raise ValueError(
            f"unknown model {model!r}; expected one of "
            f"{' / '.join(repr(m) for m in _DECLARED_MODELS)} "
            f"(case-insensitive)"
        )
    return normalized


def _resolve_dose_response_model(model: str) -> str:
    """Map themis.estimate's ``model`` kwarg (binary-effect vocabulary:
    'auto'/'linear'/'logistic') to the dose-response vocabulary
    ('auto'/'linear'/'forest'/'drlearner'). 'logistic' has no
    dose-response counterpart — fall back to 'auto'.

    Round-2 subagent caught: 'DRLearner' (the natural casing — it
    matches EconML's class name LinearDRLearner) and ' drlearner '
    (trailing whitespace) were silently demoted to 'auto'. Normalize
    the input (strip + lowercase) before whitelisting so casing/
    whitespace typos hit the explicit ValueError below instead of
    quietly disappearing.
    """
    if not isinstance(model, str):
        raise ValueError(f"model must be a string, got {type(model).__name__}")
    normalized = model.strip().lower()
    if normalized in ("auto", "linear", "forest", "drlearner"):
        return normalized
    if normalized == "logistic":
        # Binary-effect vocabulary, no dose-response counterpart — fall
        # back to 'auto' rather than rejecting outright (logistic is a
        # legal value of the parent estimate() entry).
        return "auto"
    raise ValueError(
        f"unknown model {model!r}; expected one of "
        f"'auto' / 'linear' / 'forest' / 'drlearner' (case-insensitive)"
    )


def _try_dose_response_estimate(
    *,
    result, contract,
    treatment, outcome, adjustment,
    sampling_points, random_state, model,
    graph, x, y, chosen, given,
    cluster: str | None = None,
) -> Claim:
    """Fit the dose-response curve and attach to ``result``. Returns
    True when an estimate was attached (success OR structured-error),
    False when dispatch should fall through to the binary path."""
    from .dose_response import (
        EstimatorDependencyMissing,
        EstimatorFailure,
        estimate_dose_response,
    )

    estimator_label = (
        f"dose_response_{model}_dml" if model != "auto" else "dose_response_dml"
    )

    try:
        est = estimate_dose_response(
            contract.data,
            treatment=treatment,
            outcome=outcome,
            adjustment=tuple(adjustment),
            sampling_points=sampling_points,
            random_state=random_state,
            model=model,
            cluster=cluster,
        )
    except EstimatorDependencyMissing as exc:
        result["estimator_dependency_missing"] = {
            "package": exc.package,
            "install_hint": exc.install_hint,
            "estimator": estimator_label,
        }
        return blocked('estimator_dependency_missing')
    except EstimatorFailure as exc:
        # Slice c: structured failures with a typed cause and the
        # diagnostic detail block the estimator collected.
        refusals.record(result, estimator=estimator_label, exc=exc)
        return blocked('estimator_refused')
    except (ValueError, RuntimeError) as exc:
        # Fallback: untyped failure. Same shape, failure_type='unknown'.
        result["estimator_failure"] = refusals.block(
            estimator=estimator_label,
            failure_type=Refusal.UNKNOWN,
            recorded={"diagnostic": str(exc)},
        )
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "method": est.method,
        "ci_level": est.ci_level,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "data_columns": list(est.data_columns),
        "treatment": est.treatment,
        "outcome": est.outcome,
        "adjustment": list(est.adjustment),
        "sampling_points": list(est.sampling_points),
        "reference_point": est.reference_point,
        "dose_response_curve": [
            {
                "x": p.x,
                "effect": p.effect,
                "ci_lower": p.ci_lower,
                "ci_upper": p.ci_upper,
            }
            for p in est.curve
        ],
    }
    from ..output.result_orchestrator import (
        build_assumption_ledger,
    )
    ext = result.setdefault("extensions", {})
    _attach_mechanism_audit(
        result, est, target=est.outcome,
    )
    ledger = build_assumption_ledger(
        result, 
    )
    if ledger is not None:
        ext[blocks.Block.ASSUMPTION_LEDGER] = ledger
    _attach_precision_budget_curve(result["numeric_estimate"])
    result["derivation"] = _build_numeric_derivation_dict(
        graph=graph, x=x, y=y, adjustment=chosen, given=frozenset(given),
        estimate=_LinearDMLAdapter(est),
    )
    _finalise_numeric_result(result)
    return answered()


class _LinearDMLAdapter:
    """Shim so the existing _build_numeric_derivation_dict (which expects
    a flat point/ci_lower/ci_upper estimate) accepts a dose-response
    estimate. Surfaces only the metadata fields the derivation
    serializer reads — the curve itself is in numeric_estimate."""

    def __init__(self, est):
        self.method = est.method
        self.data_hash = est.data_hash
        self.sample_size = est.sample_size
        # Use the largest sampled effect as the headline scalar so the
        # derivation has a non-trivial point. Verifier doesn't gate on
        # this value — it's metadata only.
        last = est.curve[-1] if est.curve else None
        self.point = last.effect if last else 0.0
        self.ci_lower = last.ci_lower if last else None
        self.ci_upper = last.ci_upper if last else None
        self.ci_level = est.ci_level


def _topo_order(graph, atoms):
    """Return atoms in topological order (stable tiebreak by predicate name)."""
    import networkx as nx
    topo = list(nx.topological_sort(graph))
    ordered = [a for a in topo if a in atoms]
    # Safety: include any atoms not in the topo order (shouldn't happen
    # for well-formed adjustment sets) at the end, alphabetical.
    missing = sorted(
        (a for a in atoms if a not in ordered),
        key=lambda a: a.predicate,
    )
    return tuple(ordered + missing)


def _collect_required_columns(program: dict | str | bytes) -> set[str]:
    """Walk the program AST and collect every predicate that appears as
    a variable declaration. The contract requires the DataFrame to have
    a column per declared variable.

    Accepts either a dict AST, a JSON string, or bytes. Mirrors the
    tolerant entry shape of ``themis.run``.
    """
    ast = _ensure_dict(program)
    statements = ast.get("statements", [])
    columns: set[str] = set()
    proximal_latents: set[str] = set()
    for stmt in statements:
        kind = stmt.get("kind")
        if kind == "variable":
            pred = stmt.get("predicate")
            if isinstance(pred, str):
                columns.add(pred)
        elif kind == "query":
            q = stmt.get("query", {})
            if q.get("kind") == "proximal_effect":
                lat = q.get("latent", {}).get("predicate")
                if isinstance(lat, str):
                    proximal_latents.add(lat)
    # Proximal inference's confounder U is a graph node that is UNOBSERVED by
    # construction — it carries no data column. Exclude any node declared as a
    # proximal latent from the contract's required columns (this is the one
    # query whose graph legitimately contains a column-less node).
    return columns - proximal_latents


def _ensure_dict(program: dict | str | bytes) -> dict:
    import json
    if isinstance(program, (str, bytes)):
        return json.loads(program)
    return program


# --------------------------------------------------------------------------
# 2026-07-11 pre-flight data diagnostic (borrow-list #3): reconcile each
# model variable's DECLARED measurement type against the supplied column.
# --------------------------------------------------------------------------


def _declared_scale(scale, domain) -> str | None:
    """The POSITIVE declared measurement type, or None for "didn't say".

    The rule itself lives beside the declaration, in
    :class:`themis.estimation.declared.Declared`, because two components now
    decide from it: this diagnostic, which reports a disagreement, and
    ``conform``, which places a labelled column on the levels it names. Two
    readings of one declaration is how a diagnostic comes to pass a frame
    the step beside it refuses.
    """
    return _declared.Declared(
        scale=scale,
        domain=tuple(domain) if isinstance(domain, (list, tuple)) else None,
    ).positive


def _dtype_kind(col) -> str:
    """Coarse dtype family recorded as a verifier sufficient statistic so
    the observed-scale classification can be re-derived without the data."""
    import pandas as pd
    if pd.api.types.is_bool_dtype(col):
        return "bool"
    if pd.api.types.is_integer_dtype(col):
        return "integer"
    if pd.api.types.is_float_dtype(col):
        return "float"
    # ``isinstance`` rather than ``pd.api.types.is_categorical_dtype``, which
    # pandas deprecated. It went unnoticed because nothing reached this arm:
    # a labelled column ended the run at the contract before the diagnostic
    # ever saw it, which is the defect ``declared.conform`` fixes — the
    # warning arrived with the first frame that got this far.
    if isinstance(col.dtype, pd.CategoricalDtype):
        return "categorical"
    if pd.api.types.is_object_dtype(col):
        return "object"
    return "other"


def _classify_observed(n_unique: int, dtype_kind: str) -> str:
    """Pure (n_unique, dtype_kind) -> observed scale. Isolated so the
    verifier's independent twin re-derives the identical rule."""
    if n_unique <= 2:
        return "binary"
    if n_unique <= 20 and dtype_kind in (
        "integer", "bool", "object", "categorical"
    ):
        return "discrete"
    return "continuous"


def _observe_column(col):
    """Classify a real column by cardinality (mirrors discovery
    ``_classify_column`` but on the ORIGINAL, un-coerced data so integer
    discreteness survives). Returns (observed_scale, n_unique,
    observed_values, dtype_kind) — observed_values is the distinct set when
    small (verifier substrate) else None."""
    import pandas as pd

    n_unique = int(col.nunique(dropna=True))
    dtype_kind = _dtype_kind(col)
    observed = _classify_observed(n_unique, dtype_kind)
    if n_unique <= 20:
        observed_values = sorted(
            envelope_scalar(v) for v in pd.unique(col.dropna())
        )
    else:
        observed_values = None
    return observed, n_unique, observed_values, dtype_kind


def _reconcile_declared_observed(predicate, declared, domain, observed,
                                 n_unique, observed_values):
    """Compare declared vs observed. Returns (verdict, statement) — verdict
    is 'ok' | 'declared_continuous_data_discrete' | 'domain_violated', and
    the statement is which mismatch this is, in the shape every other gap
    says itself in.

    Four mismatches share three verdicts, so the verdict alone cannot say
    which sentence a reader is owed — this is where the two are known
    together, and passing the verdict on for someone downstream to re-derive
    the branch from ``declared_scale`` and ``observed_scale`` would be an
    inference from residue.
    """
    if declared == "continuous":
        if observed in ("binary", "discrete"):
            return "declared_continuous_data_discrete", _sentence(
                Sentence.DECLARED_CONTINUOUS_BUT_THE_COLUMN_IS_DISCRETE,
                variable=predicate, count=n_unique, values=observed_values)
        return ("ok", None)
    if declared == "binary":
        if n_unique > 2:
            return "domain_violated", _sentence(
                Sentence.DECLARED_BINARY_BUT_THE_COLUMN_HAS_MORE_LEVELS,
                variable=predicate, count=n_unique)
        return ("ok", None)
    # ``nominal`` reconciles as ``discrete`` and not beside it. What it adds
    # — that the levels have no order — is a claim about the variable that no
    # column can contradict, so a branch of its own could only ever have
    # repeated this one or invented a disagreement out of cardinality.
    if declared in ("discrete", "nominal"):
        if observed == "continuous":
            return "domain_violated", _sentence(
                Sentence.DECLARED_DISCRETE_BUT_THE_VALUES_FORM_A_CONTINUUM,
                variable=predicate, count=n_unique)
        if domain is not None and observed_values is not None:
            # The same question ``conform`` asks before it can code a
            # labelled column, asked through the same function: a value the
            # declaration does not list is unplaceable there and reportable
            # here, and the two must not be able to disagree about a frame.
            extra = _declared.outside_domain(observed_values, domain)
            if extra:
                return "domain_violated", _sentence(
                    Sentence
                    .THE_COLUMN_HOLDS_VALUES_THE_DECLARATION_DOES_NOT_LIST,
                    variable=predicate,
                    domain=sorted(envelope_scalar(x) for x in domain),
                    extra=extra)
        return ("ok", None)
    return ("ok", None)


def _attach_type_reconciliation(program, output, data) -> None:
    """Reconcile every model variable's declared measurement type
    (``scale`` / ``domain``) against the supplied column and, on
    disagreement, attach a ``declared_type_data_mismatch`` gap plus the
    reconciliation evidence in ``extensions.type_reconciliation`` (so the
    verifier can independently re-derive the verdict).

    Silent on consistent programs: only variables with a POSITIVE
    declaration (a ``scale`` or an enumerated ``domain``) are checked, and
    only genuine disagreements produce a gap. An undeclared variable is
    'didn't say', never 'said continuous' — it is skipped, so this adds
    nothing to the overwhelmingly common consistent case.
    """
    import pandas as pd

    if not isinstance(data, pd.DataFrame):
        return
    ast = _ensure_dict(program)
    declarations: dict[str, tuple] = {}
    for stmt in ast.get("statements", []):
        if stmt.get("kind") == "variable":
            pred = stmt.get("predicate")
            if isinstance(pred, str):
                declarations[pred] = (stmt.get("scale"), stmt.get("domain"))
    if not declarations:
        return

    checks: list[tuple[dict, object]] = []
    for pred, (scale, domain) in sorted(declarations.items()):
        if pred not in data.columns:
            continue
        declared = _declared_scale(scale, domain)
        if declared is None:
            continue  # no positive declaration → nothing to reconcile
        observed, n_unique, observed_values, dtype_kind = _observe_column(
            data[pred]
        )
        verdict, says = _reconcile_declared_observed(
            pred, declared, domain, observed, n_unique, observed_values
        )
        if verdict == "ok":
            continue
        checks.append(({
            "predicate": pred,
            "declared_scale": declared,
            "declared_domain": list(domain) if domain is not None else None,
            "observed_scale": observed,
            "n_unique": n_unique,
            "observed_values": observed_values,
            "dtype_kind": dtype_kind,
            "verdict": verdict,
            # The block's own reading of the same statement. It is a
            # rendering, and it is one because the field is declared a
            # string; what it is a rendering OF is the entry beside it,
            # so the two cannot say different things.
            "detail": _gaps.describe(says, _lang.DEFAULT),
        }, says))
    if not checks:
        return

    for result in output.get("results", []):
        ext = result.get("extensions")
        if not isinstance(ext, dict):
            ext = {}
            result["extensions"] = ext
        ext[blocks.Block.TYPE_RECONCILIATION] = {
            "checks": [dict(c) for c, _ in checks]}
        # The finding belongs to the PROGRAM and is true of every result;
        # the consequence belongs to THIS answer and is true only where the
        # column is one this answer stands on. Written as one gap, the two
        # could only be reported at the stronger of the pair, so a column
        # no query estimated blocked every point estimate there was.
        stands_on = _names_this_result_stands_on(result)
        _file_gaps(
            result,
            [_reconciliation_gap(c, says, c["predicate"] in stands_on)
             for c, says in checks],
        )


#: What each verdict blocks on an answer that DOES stand on the column.
#: Off it, the finding is about the program rather than about this number,
#: and interpretation is the whole of what it touches.
_TYPE_MISMATCH_BLOCKS = {
    "declared_continuous_data_discrete": "interpretation",
    "domain_violated": "point_estimate",
}


#: The suffix every fingerprint's denominator is spelled with, and the one
#: container whose denominator is the RUN's rather than an answer's.
_DENOMINATOR_SUFFIX = "data_columns"
_RUN_WIDE_DENOMINATOR = "estimation_context"


def _names_this_result_stands_on(result: dict) -> frozenset[str]:
    """Which columns this result's answer rests on, as the result has it.

    Two readings, because a result has one of two kinds of answer and
    only one of them states this outright.

    A NUMBER states it. Every fingerprint on the envelope travels with
    its denominator — the column set that hash was taken over, which is
    the set its estimator was handed — so the union of the answer-level
    denominators IS the set some number here was computed from. Read,
    not inferred, and a route that starts writing one joins this reading
    the day it does.

    An ESTIMAND does not. Where identification answered and no estimator
    ran, what the answer rests on is still only readable from the
    structural witness, and the envelope states THAT in about ten
    differently-named places — ``adjustment_set`` under four blocks, plus
    ``instrument``, ``conditioning``, ``mediator``, ``s_nodes``,
    ``selection_nodes``, ``design_vars`` — with no one of them being it.
    So the fallback stays what it was: every name the document mentions,
    an over-approximation kept on purpose, because a name found here
    keeps the stronger consequence and the direction this can be wrong
    in is the one that blocks MORE than it had to.

    The run-wide denominator is excluded from BOTH, and that exclusion is
    load-bearing rather than tidy. ``estimation_context`` fingerprints
    what ARRIVED: every predicate the program declared, including the
    ones no query estimated. Counting it makes the question say yes for
    everything — which is how a declared-but-unestimated column came to
    block every point estimate in the program.

    Two more containers are excluded from the fallback for the same
    reason: the reconciliation block names every declared predicate by
    construction, and the gap report is where the answer is about to be
    written.
    """
    skip = {str(blocks.Block.TYPE_RECONCILIATION), "data_gap_report"}
    declared: set[str] = set()
    mentioned: set[str] = set()

    def walk(node, run_wide: bool) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in skip:
                    continue
                if isinstance(key, str) \
                        and key.endswith(_DENOMINATOR_SUFFIX):
                    if not run_wide and isinstance(value, list):
                        declared.update(
                            c for c in value if isinstance(c, str))
                    continue
                walk(value, run_wide or key == _RUN_WIDE_DENOMINATOR)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value, run_wide)
        elif isinstance(node, str):
            mentioned.add(node)

    walk(result, False)
    return frozenset(declared or mentioned)


def _reconciliation_gap(check: dict, says, stands_on: bool) -> DataGap:
    """One mismatch, as this result has to read it.

    The finding is the same on every result; what changes is whether this
    answer stands on the column, which is a second statement rather than a
    second wording of the first.
    """
    from ..output import envelope_glossary

    pred = check["predicate"]
    if stands_on:
        severity = GapSeverity.IMPORTANT
        gap_blocks = GapBlocks(_TYPE_MISMATCH_BLOCKS[check["verdict"]])
        consequence = _sentence(
            Sentence.THE_NUMBER_ANSWERS_A_DIFFERENT_ESTIMAND_THAN_DECLARED)
    else:
        severity = GapSeverity.INFORMATIONAL
        gap_blocks = GapBlocks.INTERPRETATION
        consequence = _sentence(Sentence.THIS_COLUMN_IS_NOT_IN_THIS_ESTIMAND,
                                variable=pred)
    return DataGap(
        kind=GapKind.DECLARED_TYPE_DATA_MISMATCH,
        signature=check["verdict"],
        severity=severity,
        blocks=gap_blocks,
        describes=(says, consequence),
        alternative_paths=(
            _gaps.route(
                Route.FIX_THE_DATA_TO_MATCH_THE_DECLARATION,
                variable=pred,
                scale=envelope_glossary.Scale.named(check["declared_scale"]),
            ),
            _gaps.route(Route.FIX_THE_DECLARATION_TO_MATCH_THE_DATA),
        ),
        provenance=_verifier_check(f"type_reconciliation:{pred}"),
    )
