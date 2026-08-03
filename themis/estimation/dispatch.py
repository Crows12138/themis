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
from typing import Any

from .. import blocks, refusals
from ..output.sample_size import estimate_n_for_target_ci_half_width
from .claim import Claim, annotated, answered, blocked, passed
from .contract import DataContract, validate_data
from ..routing import End, route
from .strategy import (
    EffectFacts,
    EffectKnobs,
    Estimand,
    Evaluation,
    Role,
    Strategy,
    check_table,
    run_cascade,
)


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

    Three things hold here. Its declared assumptions reach the assumption
    ledger, the surface both the report assembler and the rendering bridge
    lead with. Every block it left on the envelope is one
    :mod:`themis.blocks` declares, so a new block cannot reach a reader
    the registry has never heard of. And a refusal leaves carrying both
    the species :mod:`themis.refusals` declares and the ``kind`` that
    says what the reader should do about it, so a consumer branches on a
    closed set rather than on whatever the estimator spelled.
    """
    from ..output.result_orchestrator import augment_assumption_ledger

    output = _estimate_program(
        program, data,
        random_state=random_state, ci_bootstrap=ci_bootstrap, model=model,
        cluster=cluster, ate_estimator=ate_estimator,
        reference_data=reference_data, misclassification=misclassification,
        measurement_error=measurement_error,
    )
    for result in output.get("results", []):
        augment_assumption_ledger(result)
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

    A spec on the OUTCOME is a different object, because what a mismeasured
    variable costs depends on the role it plays. A classical additive error on a
    continuous outcome leaves every conditional mean — and so every estimand here
    — unchanged, so nothing is de-attenuated and the ordinary number stands. What
    the declared σ²_v buys instead is the price: an ``outcome_error`` block
    splitting the residual variance into signal and measurement noise, and the
    factor by which that noise widens the interval (the part of the uncertainty
    more subjects cannot buy back). It composes with an exposure-side spec rather
    than displacing it. Deferred: Berkson / differential error, a nonlinear
    outcome (SIMEX).
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
    contract = validate_data(
        data,
        required_columns=required_columns,
        presence_columns=presence_columns,
    )

    for result in identification_output.get("results", []):
        result.setdefault("estimation_context", {}).update({
            "data_hash": contract.data_hash,
            "sample_size": contract.sample_size,
            "data_contract_warnings": list(contract.warnings),
            "random_state": random_state,
            "ci_bootstrap": ci_bootstrap,
            "model_preference": model,
        })

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
    # and the kernel attached a SYMBOLIC bounds_result, evaluate it on data.
    # Runs after the point-estimate loop so it only ever ADDS numeric fields
    # to an already-symbolic bounds_result — never competes with a point.
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
    ident = (target.get("extensions") or {}).get(blocks.LONGITUDINAL_IDENTIFICATION)
    if isinstance(ident, dict) and ident.get("identified") is False:
        target["estimator_failure"] = {
            "estimator": (
                "longitudinal_ipw_msm"
                if spec.get("estimator") == "ipw_msm"
                else "longitudinal_gformula"
            ),
            "failure_type": refusals.NOT_IDENTIFIED,
            "reason": (
                "the time-varying strategy effect is not identified by the "
                "g-formula: sequential exchangeability fails (an unblocked "
                "back-door from a treatment to the outcome given the measured "
                "history). No number is produced — the g-formula estimate "
                "would be biased."
            ),
        }
        return

    from .longitudinal import (
        estimate_longitudinal_gformula,
        estimate_longitudinal_ipw_msm,
    )
    from ..refusals import EstimatorFailure

    estimator = spec.get("estimator", "gformula")
    if estimator not in ("gformula", "ipw_msm"):
        target["estimator_failure"] = {
            "estimator": "longitudinal",
            "failure_type": refusals.INVALID_INPUT,
            "reason": (
                f"options.longitudinal.estimator must be 'gformula' or "
                f"'ipw_msm', got {estimator!r}"
            ),
        }
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
        target["estimator_failure"] = {
            "estimator": method_name,
            "failure_type": refusals.UNKNOWN,
            "reason": str(exc),
        }
        return

    numeric_estimate = {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": est.method,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "treatment": ",".join(est.treatments),
        "outcome": est.outcome,
    }
    if estimator == "gformula":
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
            "n_bootstrap": est.n_bootstrap,
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
            "n_bootstrap": est.n_bootstrap,
        }
    target["numeric_estimate"] = numeric_estimate
    # Stamp what the estimator REPORTS having resampled over, not what the
    # caller asked for — the claim and the fact then cannot drift apart.
    _attach_bootstrap_meta(target["numeric_estimate"], est.cluster)
    _attach_precision_budget(target["numeric_estimate"])
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
        if (result.get("extensions") or {}).get(blocks.LONGITUDINAL_IDENTIFICATION):
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
    from ..refusals import EstimatorFailure

    target = None
    block = None
    for result in output.get("results", []):
        ext = result.get("extensions") or {}
        if blocks.MISSING_DATA_RECOVERY in ext:
            target = result
            block = ext[blocks.MISSING_DATA_RECOVERY]
            break
    if target is None or block is None:
        return

    estimand = block.get("estimand") or {}
    if not estimand.get("recoverable", False):
        target["estimator_failure"] = {
            "estimator": "missing_data_recovery",
            "failure_type": refusals.NOT_RECOVERABLE,
            "reason": (
                estimand.get("failure_reason")
                or "the interventional estimand is not recoverable from this "
                "missing-data pattern via ordered factorization; no number is "
                "produced (Mohan-Pearl-Tian 2013)."
            ),
        }
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
        target["estimator_failure"] = {
            "estimator": "missing_data_recovery",
            "failure_type": refusals.UNKNOWN,
            "reason": str(exc),
        }
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
            "n_bootstrap": est.n_bootstrap,
            # Per-stratum sufficient statistics for the numeric verifier:
            # verify_missing_data_numeric re-derives the recovered (and naive)
            # ATE from these counts + marginal tables independently.
            "sufficient_statistics": est.sufficient_statistics,
        },
    }
    target["numeric_estimate"] = numeric_estimate
    _attach_precision_budget(target["numeric_estimate"])


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
                (result.get("extensions") or {}).get(blocks.SELECTION_RECOVERY)
            ),
            dose_response_triggered=q_stmt.id in dose_response_query_ids,
        )
        evaluations.append(run_cascade(
            _EFFECT_STRATEGIES, facts, result, knobs, query_id=q_stmt.id,
        ))
    return evaluations


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
        route=route("joint_intervention"),
        role=Role.CLAIM,
        produces=Estimand.JOINT_CONTRAST,
        run=lambda f, r, k: _try_joint_estimate(
            f.q_stmt, r, f.contract, f.graph, f.bidirected,
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
        run=lambda f, r, k: _try_combined_measurement_correction_estimate(
            f.q_stmt, r, f.contract, f.graph,
            adjustment_sets=f.adjustment_sets, given=f.given_atoms,
            spec_x=f.misclassification_exposure,
            spec_y=f.misclassification_outcome,
            random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
            cluster=k.cluster,
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
        run=lambda f, r, k: _try_measurement_correction_estimate(
            f.q_stmt, r, f.contract, f.graph,
            adjustment_sets=f.adjustment_sets, given=f.given_atoms,
            spec=f.misclassification_outcome,
            random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
            cluster=k.cluster,
        ),
    ),
    Strategy(
        route=route("measurement_correction_exposure"),
        role=Role.CLAIM,
        produces=Estimand.QUERY_EFFECT,
        run=lambda f, r, k: _try_exposure_measurement_correction_estimate(
            f.q_stmt, r, f.contract, f.graph,
            adjustment_sets=f.adjustment_sets, given=f.given_atoms,
            spec=f.misclassification_exposure,
            random_state=k.random_state, ci_bootstrap=k.ci_bootstrap,
            cluster=k.cluster,
        ),
    ),
    Strategy(
        # This does NOT claim the query: the point still comes from the
        # ordinary routing below, including the exposure-side correction when
        # a spec names the exposure too. Only a spec the channel or the data
        # refuse stops the query.
        route=route("outcome_error_precision_cost"),
        role=Role.ANNOTATE,
        produces=Estimand.NONE,
        run=lambda f, r, k: _try_outcome_error_assessment(
            r, f.contract, f.graph,
            x_atom=f.x_atom, y_atom=f.y_atom,
            adjustment_sets=f.adjustment_sets,
            spec=f.measurement_error_outcome,
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
            adjustment_sets=f.adjustment_sets, given=f.given_atoms,
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
        run=lambda f, r, k: _try_iv_wald_estimate(f, r, k),
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
            "treatment is binary; a dose-response curve would "
            "degenerate to a two-point contrast"
        ),
    }
    _append_result_data_contract_warning(
        result,
        (
            "dose_response_query fell back to binary effect because "
            f"treatment {facts.x_atom.predicate!r} is binary"
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
        build_mechanism_audit,
    )

    x_atom, y_atom = facts.x_atom, facts.y_atom
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

    result["numeric_estimate"] = {
        "point": estimate.point,
        "ci_lower": estimate.ci_lower,
        "ci_upper": estimate.ci_upper,
        "ci_level": estimate.ci_level,
        "method": estimate.method,
        "assumptions": list(estimate.assumptions),
        "sample_size": estimate.sample_size,
        "data_hash": estimate.data_hash,
        "adjustment": list(estimate.adjustment),
        "treatment": estimate.treatment,
        "outcome": estimate.outcome,
    }
    _attach_bootstrap_meta(result["numeric_estimate"], knobs.cluster)
    ext = result.setdefault("extensions", {})
    ext[blocks.MECHANISM_AUDIT] = build_mechanism_audit(
        target=estimate.outcome,
        form=estimate.form,
        method=estimate.method,
        assumption=estimate.model_assumption,
        provenance="default",
    )
    ledger = build_assumption_ledger(
        result, identification_specs=estimate.identification_assumptions,
    )
    if ledger is not None:
        ext[blocks.ASSUMPTION_LEDGER] = ledger
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

    from ..refusals import EstimatorFailure
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
        # A continuous mediator, or more strata than can be enumerated. The
        # estimator says which; before it had a species to say it with, this
        # caught NotImplementedError and the reason went nowhere.
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
        "mediators": list(fd_estimate.mediators),
        "treatment": fd_estimate.treatment,
        "outcome": fd_estimate.outcome,
    }
    _attach_bootstrap_meta(result["numeric_estimate"], knobs.cluster)
    _attach_precision_budget(result["numeric_estimate"])

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


def _try_iv_wald_estimate(
    facts: EffectFacts, result: dict, knobs: EffectKnobs,
) -> Claim:
    """Phase 7.3: the just-identified Wald ratio on the smallest candidate."""
    from ..refusals import EstimatorFailure
    from .iv import estimate_iv_ate

    x_atom, y_atom = facts.x_atom, facts.y_atom
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

    iv_numeric_dict = {
        "point": iv_estimate.point,
        "ci_lower": iv_estimate.ci_lower,
        "ci_upper": iv_estimate.ci_upper,
        "ci_level": iv_estimate.ci_level,
        "method": iv_estimate.method,
        "assumptions": list(iv_estimate.assumptions),
        "sample_size": iv_estimate.sample_size,
        "data_hash": iv_estimate.data_hash,
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
    if iv_estimate.anderson_rubin is not None:
        iv_numeric_dict["anderson_rubin_confidence_set"] = _ar_set_to_dict(
            iv_estimate.anderson_rubin
        )
    if iv_estimate.stratified_anderson_rubin is not None:
        iv_numeric_dict["stratified_anderson_rubin_confidence_set"] = (
            _stratified_ar_set_to_dict(iv_estimate.stratified_anderson_rubin)
        )
    result["numeric_estimate"] = iv_numeric_dict
    _attach_bootstrap_meta(result["numeric_estimate"], knobs.cluster)
    _attach_precision_budget(result["numeric_estimate"])
    result["derivation"] = _build_iv_numeric_derivation_dict(
        graph=facts.graph,
        x=x_atom, y=y_atom,
        instrument=chosen_iv.instrument,
        conditioning=chosen_iv.conditioning,
        estimate=iv_estimate,
    )
    _attach_e_value_if_binary(
        result, facts.contract,
        outcome=y_atom.predicate, treatment=x_atom.predicate,
    )
    _attach_weak_iv_warning_if_low_f(result, iv_estimate)
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
    """Evaluate a symbolic ``bounds_result`` on data — the numeric end of the
    partial-identification layer.

    When point identification failed, the kernel attached a SYMBOLIC
    ``bounds_result`` (``lower_expression`` / ``upper_expression`` strings).
    This turns those symbols into an actual ``[lower_value, upper_value]``
    (+ percentile-bootstrap outer-band CI) using the estimator that matches
    the method the kernel already chose — so the numeric interval and the
    symbolic one describe the SAME method, never a different one.

    Purely additive: the symbolic bounds_result is preserved; only numeric
    fields are ADDED. Any refusal — a column absent from the data, a
    non-binary variable where the method needs binary, a positivity failure,
    or an instrument the data refutes (Balke-Pearl instrumental inequalities)
    — leaves the symbolic interval untouched. Mirrors the ``method`` selection
    the kernel made in ``scheduler._attach_bounds_result`` (reuses the SAME
    instrument / monotonicity detectors), so numeric and symbolic never
    disagree on which method applies.
    """
    from ..input.semantic_validator import validate_program
    from ..input.syntactic_validator import validate_ast
    from ..runtime.scheduler import (
        _detect_iv_candidate_structural,
        _detect_monotonicity_for_query,
    )
    from .bounds_numeric import (
        evaluate_balke_pearl_ace_bounds,
        evaluate_manski_natural_bounds,
        evaluate_manski_tamer_bounds,
    )
    from ..refusals import EstimatorFailure

    ast = _ensure_dict(program)
    prog = validate_program(validate_ast(ast))
    cols = set(contract.data.columns)
    cluster_ok = cluster if (cluster is None or cluster in cols) else None

    for q_stmt, result in _pair_effect_queries(prog, output):
        if q_stmt is None:
            continue
        bounds = result.get("bounds_result")
        if not isinstance(bounds, dict):
            continue
        if bounds.get("lower_value") is not None:
            continue  # idempotent: already evaluated
        query = q_stmt.query
        method = bounds.get("method")
        x_pred = query.intervention.atom.predicate
        y_pred = query.target.atom.predicate
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
                if mono is None:
                    continue
                nb = evaluate_manski_tamer_bounds(
                    contract.data, treatment=x_pred, outcome=y_pred,
                    monotonicity=mono.value,
                    treatment_value=query.intervention.value,
                    outcome_value=query.target.value,
                    ci_bootstrap=ci_bootstrap, random_state=random_state,
                    cluster=cluster_ok,
                )
            elif method == "balke_pearl_iv":
                iv_ext = (result.get("extensions") or {}).get(blocks.IV_IDENTIFICATION)
                instrument = None
                if isinstance(iv_ext, dict):
                    instrument = iv_ext.get("instrument")
                if instrument is None:
                    instrument = _detect_iv_candidate_structural(prog, query)
                if instrument is None:
                    continue
                nb = evaluate_balke_pearl_ace_bounds(
                    contract.data, treatment=x_pred, outcome=y_pred,
                    instrument=instrument,
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
    if nb.instrument is not None:
        bounds["instrument"] = nb.instrument
    if nb.cluster is not None:
        bounds["numeric_cluster"] = nb.cluster
    if getattr(nb, "sufficient_statistics", None) is not None:
        bounds["sufficient_statistics"] = nb.sufficient_statistics


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
    from ..refusals import EstimatorFailure
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
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    _attach_precision_budget(result["numeric_estimate"])

    from ..output.result_orchestrator import (
        build_assumption_ledger,
        build_mechanism_audit,
    )
    ext = result.setdefault("extensions", {})
    ext[blocks.MECHANISM_AUDIT] = build_mechanism_audit(
        target=estimate.outcome,
        form=estimate.form,
        method=estimate.method,
        assumption=estimate.model_assumption,
        provenance="default",
    )
    ledger = build_assumption_ledger(
        result, identification_specs=estimate.identification_assumptions,
    )
    if ledger is not None:
        ext[blocks.ASSUMPTION_LEDGER] = ledger

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

    The joint analog of :func:`_try_general_id_estimate`. Reports the uniform
    all-hi / all-lo CONTRAST only — the K-way interaction needs a mixed
    corner (per-atom value binding), out of v1 scope. Purely additive:
    attaches a joint general-ID numeric estimate and returns True only when
    the joint effect is c-factor point-identified AND the data support it; on
    any refusal returns False and touches nothing, so the structural refusal
    (joint_not_identifiable) stands byte-identical.
    """
    from ..refusals import EstimatorFailure
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
        "point": estimate.point,
        "ci_lower": estimate.ci_lower,
        "ci_upper": estimate.ci_upper,
        "ci_level": estimate.ci_level,
        "method": estimate.method,
        "assumptions": list(estimate.assumptions),
        "sample_size": estimate.sample_size,
        "data_hash": estimate.data_hash,
        "treatment": estimate.treatment,
        "treatments": list(estimate.treatments),
        "outcome": estimate.outcome,
        "treatment_high": estimate.treatment_high,
        "treatment_low": estimate.treatment_low,
        "outcome_high": estimate.outcome_high,
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    _attach_precision_budget(result["numeric_estimate"])

    from ..output.result_orchestrator import (
        build_assumption_ledger,
        build_mechanism_audit,
    )
    ext = result.setdefault("extensions", {})
    ext[blocks.MECHANISM_AUDIT] = build_mechanism_audit(
        target=estimate.outcome,
        form=estimate.form,
        method=estimate.method,
        assumption=estimate.model_assumption,
        provenance="default",
    )
    ledger = build_assumption_ledger(
        result, identification_specs=estimate.identification_assumptions,
    )
    if ledger is not None:
        ext[blocks.ASSUMPTION_LEDGER] = ledger

    # Reuse the single-treatment general-ID derivation: the criterion step
    # (general_id_criterion) re-runs the SET ID off ctx.query, and the
    # primary treatment atom labels the x / treatment slots (matching the
    # numeric terminal's cross-check against the criterion's x).
    result["derivation"] = _build_general_id_numeric_derivation_dict(
        graph=graph, x=treatment_atoms[0], y=y_atom, estimate=estimate,
    )
    _finalise_numeric_result(result)
    return answered()


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
    from ..refusals import EstimatorFailure

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
        "conditional": estimate.conditional,
        "estimand": estimate.estimand,
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    _attach_precision_budget(result["numeric_estimate"])

    from ..output.result_orchestrator import (
        build_assumption_ledger,
        build_mechanism_audit,
    )
    ext = result.setdefault("extensions", {})
    ext[blocks.MECHANISM_AUDIT] = build_mechanism_audit(
        target=estimate.estimand,
        form=estimate.form,
        method=estimate.method,
        assumption=estimate.model_assumption,
        provenance="default",
    )
    ledger = build_assumption_ledger(
        result, identification_specs=estimate.identification_assumptions,
    )
    if ledger is not None:
        ext[blocks.ASSUMPTION_LEDGER] = ledger

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
    from ..refusals import EstimatorFailure
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
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    _attach_precision_budget(result["numeric_estimate"])

    from ..output.result_orchestrator import (
        build_assumption_ledger,
        build_mechanism_audit,
    )
    ext = result.setdefault("extensions", {})
    ext[blocks.MECHANISM_AUDIT] = build_mechanism_audit(
        target=estimate.target,
        form=estimate.form,
        method=estimate.method,
        assumption=estimate.model_assumption,
        provenance="default",
    )
    ledger = build_assumption_ledger(
        result, identification_specs=estimate.identification_assumptions,
    )
    if ledger is not None:
        ext[blocks.ASSUMPTION_LEDGER] = ledger
    # Human display copy (parity with the structural path's extension): the
    # counterfactual value + the abducted noise + post-intervention values.
    # Display-only — the verifier's authority is numeric_estimate; kernel.verify
    # cross-checks target_value == numeric_estimate.point so this cannot drift.
    ext[blocks.SCM_COUNTERFACTUAL] = {
        "target": estimate.target,
        "target_value": estimate.point,
        "intervention": {
            "variable": estimate.intervention_var,
            "value": estimate.intervention_value,
        },
        "abducted_noise": {a: v for a, v in estimate.abducted_noise},
        "counterfactual_values": {a: v for a, v in estimate.counterfactual_values},
        "estimated_from_data": True,
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
    from ..refusals import EstimatorFailure

    q = q_stmt.query
    df = contract.data
    try:
        estimate = estimate_proximal_ate(
            df, graph=graph, bidirected=bidirected,
            treatment=q.treatment, outcome=q.outcome, latent=q.latent,
            treatment_proxy=q.treatment_proxy, outcome_proxy=q.outcome_proxy,
            latent_cardinality=q.latent_cardinality,
            ci_bootstrap=ci_bootstrap, random_state=random_state,
            cluster=cluster if (cluster is None or cluster in df.columns) else None,
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="proximal", exc=exc)
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
        "treatment": estimate.treatment,
        "outcome": estimate.outcome,
        "treatment_proxy": estimate.treatment_proxy,
        "outcome_proxy": estimate.outcome_proxy,
        "latent_cardinality": estimate.latent_cardinality,
        "do_prob_treated": estimate.do_prob_treated,
        "do_prob_control": estimate.do_prob_control,
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    _attach_precision_budget(result["numeric_estimate"])

    from ..output.result_orchestrator import (
        build_assumption_ledger,
        build_mechanism_audit,
    )
    target = f"P({estimate.outcome}|do({estimate.treatment}))"
    ext = result.setdefault("extensions", {})
    ext[blocks.MECHANISM_AUDIT] = build_mechanism_audit(
        target=target,
        form=estimate.form,
        method=estimate.method,
        assumption=estimate.model_assumption,
        provenance="default",
    )
    ledger = build_assumption_ledger(
        result, identification_specs=estimate.identification_assumptions,
    )
    if ledger is not None:
        ext[blocks.ASSUMPTION_LEDGER] = ledger

    result["derivation"] = _build_proximal_numeric_derivation_dict(
        graph=graph, estimate=estimate,
    )
    _finalise_numeric_result(result)
    return answered()


def _build_proximal_numeric_derivation_dict(*, graph, estimate):
    """Two-step derivation for a proximal matrix plug-in estimate:

        s1: proximal_criterion (structural witness — re-runs identify_proximal
            to confirm the effect is proximal-identifiable)
        s2: numeric_proximal_estimate (metadata audit — no re-fit)
    """
    from ..types import DerivationStep, StepRef, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    steps = (
        DerivationStep(
            rule="proximal_criterion",
            inputs={"graph": graph},
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="numeric_proximal_estimate",
            inputs={
                "criterion": StepRef(step_id="s1"),
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
    data-based bounds overlay is a follow-up on the bounds_result channel."""
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
    from ..refusals import EstimatorFailure

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
        ci_lo, ci_hi = (pt_ci_lo, pt_ci_hi) if point is not None else (band_lo, band_hi)
        return {
            "point": point, "lower": lower, "upper": upper,
            "ci_lower": ci_lo, "ci_upper": ci_hi,
        }

    poc_block = {
        "monotonic": estimate.monotonic,
        "interventional_risk_provenance": estimate.interventional_risk_provenance,
        "adjustment": list(estimate.adjustment),
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
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    if is_point:
        _attach_precision_budget(result["numeric_estimate"])

    # Headline numeric_result reflects the DATA PN point (not the stale theta
    # one, if any); for the bounds answer there is no point — value is null and
    # the identified intervals live in numeric_estimate.probabilities_of_causation.
    result["numeric_result"] = {
        "value": float(estimate.pn_point) if is_point else None
    }

    # Display copy: the explainer reads extensions.causation. Overwrite the
    # (theta-based, if any) structural envelope with the data envelope so all
    # surfaces show the same audited numbers; verify_causation_numeric
    # cross-checks it against the derivation inputs.
    ext = result.setdefault("extensions", {})
    ext[blocks.CAUSATION] = {
        "monotonic": estimate.monotonic,
        "interventional_risk_provenance": estimate.interventional_risk_provenance,
        "p_y_do_x1": estimate.p_y_do_x1,
        "p_y_do_x0": estimate.p_y_do_x0,
        "observational_joint": poc_block["observational_joint"],
        "pn": {"lower": estimate.pn_lower, "upper": estimate.pn_upper, "point": estimate.pn_point},
        "ps": {"lower": estimate.ps_lower, "upper": estimate.ps_upper, "point": estimate.ps_point},
        "pns": {"lower": estimate.pns_lower, "upper": estimate.pns_upper, "point": estimate.pns_point},
    }

    from ..output.result_orchestrator import (
        build_assumption_ledger,
        build_mechanism_audit,
    )
    ext[blocks.MECHANISM_AUDIT] = build_mechanism_audit(
        target=f"PN({estimate.effect}|{estimate.cause})",
        form=estimate.form,
        method=estimate.method,
        assumption=estimate.model_assumption,
        provenance="default",
    )
    ledger = build_assumption_ledger(
        result, identification_specs=estimate.identification_assumptions,
    )
    if ledger is not None:
        ext[blocks.ASSUMPTION_LEDGER] = ledger

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
    gaps = [
        g for g in report.get("gaps", [])
        if g.get("kind") not in _NUMERIC_SATISFIED_GAP_KINDS
    ]
    report["gaps"] = gaps
    report["answer_tier"] = "interval"
    report["summary"] = _summary_from_gap_dicts(gaps, answer_tier="interval")


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
    from ..refusals import EstimatorFailure

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
        "bootstrap_draws_used": estimate.bootstrap_draws_used,
        "bootstrap_draws_infeasible": estimate.bootstrap_draws_infeasible,
    }
    numeric_estimate = {
        "ci_level": estimate.ci_level,
        "method": estimate.method,
        "assumptions": list(estimate.assumptions),
        "sample_size": estimate.sample_size,
        "data_hash": estimate.data_hash,
        "treatment": estimate.cause,
        "outcome": estimate.effect,
        "counterfactual_cell": cell_block,
    }
    if is_point:
        numeric_estimate["point"] = estimate.point
        numeric_estimate["ci_lower"] = estimate.ci_lower
        numeric_estimate["ci_upper"] = estimate.ci_upper
    result["numeric_estimate"] = numeric_estimate
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
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
    # same audited numbers.
    ext = result.setdefault("extensions", {})
    ext[blocks.COUNTERFACTUAL_CELL] = cell_block

    from ..output.result_orchestrator import (
        build_assumption_ledger,
        build_mechanism_audit,
    )
    ext[blocks.MECHANISM_AUDIT] = build_mechanism_audit(
        target=(
            f"P({estimate.effect}_{{{estimate.cause}="
            f"{int(estimate.x_counterfactual)}}}={int(estimate.y_star)}"
            f"|{estimate.cause}={int(estimate.x_observed)})"
        ),
        form=estimate.form,
        method=estimate.method,
        assumption=estimate.model_assumption,
        provenance="default",
    )
    ledger = build_assumption_ledger(
        result, identification_specs=estimate.identification_assumptions,
    )
    if ledger is not None:
        ext[blocks.ASSUMPTION_LEDGER] = ledger

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
    from ..refusals import EstimatorFailure
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
    decomp = extensions.get(blocks.MEDIATION_DECOMPOSITION)
    if decomp is None:
        return passed('identification_chose_another_strategy')
    if decomp.get("strategy") != "nde_nie":
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
        "treatment": med_estimate.treatment,
        "outcome": med_estimate.outcome,
        "mediator": med_estimate.mediator,
        "adjustment": list(med_estimate.adjustment),
        "n_rep": med_estimate.n_rep,
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
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    _attach_precision_budget_decomposition(result["numeric_estimate"])
    _attach_e_value_if_binary(
        result, contract,
        outcome=y_pred, treatment=x_pred,
    )
    _prepend_proportion_mediated_headline(result, med_estimate)

    # NOTE: status stays "structurally_solved" — the identification
    # answer (strategy=nde_nie + adjustment) is the primary result; the
    # numeric_estimate block is supplementary detail. The existing
    # mediation derivation (mediation_*_check + identify_via_mediation)
    # already passes verify_effect_structural. Flipping to
    # numerically_solved would break that round-trip.
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
    from ..refusals import EstimatorFailure
    from .mediation import estimate_mediation_joint

    extensions = result.get("extensions") or {}
    decomp = extensions.get(blocks.MEDIATION_JOINT_DECOMPOSITION)
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
        return blocked('not_identified')
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
        "treatment": est.treatment,
        "outcome": est.outcome,
        "mediators": list(est.mediators),
        "adjustment": list(est.adjustment),
        "n_rep": est.n_rep,
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

    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    _prepend_proportion_mediated_headline(
        result, est,
        through=tuple(str(m) for m in (decomp.get("mediators") or ())),
    )

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

    from ..refusals import EstimatorFailure
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

    block = {
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
        "mediator_reference": float(est.mediator_reference),
    }
    ne["four_way_ratio"] = block


def _try_joint_estimate(
    q_stmt, result: dict, contract, graph, bidirected,
    *, random_state: int, ci_bootstrap: int, model: str,
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
    from ..refusals import EstimatorFailure
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

    joint_sets = structural_solver.minimal_adjustment_sets_joint(
        graph, treatment_atoms, y_atom,
        given=given_atoms, bidirected=bidirected or None,
    )
    if not joint_sets:
        # Adjustment fails — but the joint effect may still be point-
        # identified by the set-valued Shpitser-Pearl ID (latent confounding
        # neutralized with NO adjustment set). Try the joint general-ID
        # plug-in as the escape layer, mirroring the single-treatment
        # general-ID fallback. Unconditional only (v1). Purely additive: a
        # no-op leaves the structural refusal (joint_not_identifiable)
        # standing byte-identical.
        if not given_atoms:
            _try_joint_general_id_estimate(
                result, contract, graph, bidirected,
                treatment_atoms=treatment_atoms, y_atom=y_atom,
                random_state=random_state, ci_bootstrap=ci_bootstrap,
                cluster=cluster,
            )
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
    # The interaction is a separate quantity with a separate positivity
    # requirement, so it gets a separate slot — present with a number, or
    # absent with the reason in its place. Never present holding null: a
    # consumer reading `interaction.point` should not have to know that the
    # field it is reading can be nothing.
    if estimate.interaction_point is not None:
        result["numeric_estimate"]["interaction"] = {
            "point": estimate.interaction_point,
            "ci_lower": estimate.interaction_ci_lower,
            "ci_upper": estimate.interaction_ci_upper,
            "scale": "difference",
            # Interaction order = number of treatments (K-way, the highest-
            # order mixed finite difference). 2 for the classic A×B case.
            "order": len(estimate.treatments),
        }
    else:
        result["numeric_estimate"]["interaction_unavailable"] = {
            "reason": estimate.interaction_unavailable_reason,
            "order": len(estimate.treatments),
            "unsupported_cells": [
                dict(cell) for cell in estimate.interaction_unsupported_cells
            ],
        }
    # Cluster-bootstrap provenance (both the joint contrast and the
    # interaction ride the same clustered resample). No-op when i.i.d.,
    # keeping the cluster=None surface byte-identical.
    _attach_bootstrap_meta(result["numeric_estimate"], estimate.cluster)

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
            "interaction_unavailable_reason":
                estimate.interaction_unavailable_reason,
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


def _prepend_proportion_mediated_headline(
    result: dict, med_estimate, *, through: tuple[str, ...] = (),
) -> None:
    """Surface NIE / TE as a headline at the top of result.explanation.

    The user-side question shape that drives this is "X 占多少比例" (how
    much of the effect goes through the mediator). The number lives in
    decomposition.proportion_mediated; without a headline the renderer
    has to construct it from raw NIE/TE/CI fields. Prepending it here
    gives the renderer a deterministic single-line answer to quote.

    ``through`` names a mediator BLOCK. A block's share is the share through
    the set taken as a whole and is NOT the sum of per-mediator shares (those
    are not identified at all), so the headline says which it is rather than
    letting a bare percentage be read as either.
    """
    point = med_estimate.proportion_mediated_point
    lo = med_estimate.proportion_mediated_ci_lower
    hi = med_estimate.proportion_mediated_ci_upper
    if point is None:
        return
    subject = (
        f"，通过 {{{', '.join(through)}}} 这一整组" if through else ""
    )
    headline = (
        f"中介比例 (NIE/TE{subject}): {point * 100:.1f}% "
        f"(95% CI [{lo * 100:.1f}%, {hi * 100:.1f}%])"
    )
    existing = result.get("explanation") or ""
    result["explanation"] = (
        f"{headline}\n{existing}".strip() if existing else headline
    )


def _attach_e_value_if_binary(
    result: dict, contract, outcome: str, treatment: str,
) -> None:
    """Phase 8.2 + iter 124 — compute the E-value sensitivity for the
    result's numeric estimate and attach it under
    ``numeric_estimate.sensitivity_analysis``.

    Two paths:
    - **Binary outcome**: VanderWeele-Ding 2017 — convert ATE to RR
      via observed baseline rate.
    - **Continuous outcome** (iter 124): Chinn 2000 — convert ATE to
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
    is_binary = pd.api.types.is_bool_dtype(outcome_series)
    is_numeric = pd.api.types.is_numeric_dtype(outcome_series) and not is_binary

    if "decomposition" in estimate:
        te = estimate["decomposition"]["te"]
        ate = te["point"]
        ci_bound = _closer_to_null(te["point"], te["ci_lower"], te["ci_upper"])
    else:
        ate = estimate.get("point")
        if ate is None:
            return
        ci_bound = _closer_to_null(
            estimate["point"],
            estimate.get("ci_lower"),
            estimate.get("ci_upper"),
        )

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
    elif is_numeric:
        outcome_sd = float(outcome_series.std(ddof=1))
        if outcome_sd <= 0 or not (outcome_sd == outcome_sd):  # NaN-safe
            return
        e_result = e_value_from_ate_continuous(
            ate=ate, outcome_sd=outcome_sd, ci_bound=ci_bound,
        )
        path = "continuous"
    else:
        return  # categorical / object outcomes — out of scope this iter

    # Record the conversion INPUTS (path + baseline_rate / outcome_sd) next to
    # the outputs so the verifier can re-derive the risk ratio and BOTH
    # E-values from first principles — pairing them with the audited headline
    # ATE — without needing the DataFrame. Same reason the OVB block records
    # the raw t-value + dof rather than only the robustness value.
    estimate["sensitivity_analysis"] = {
        "e_value": e_result.e_value,
        "e_value_ci_bound": e_result.e_value_ci_bound,
        "risk_ratio": e_result.risk_ratio,
        "baseline_rate": e_result.baseline_rate,
        "outcome_sd": outcome_sd,
        "path": path,
        "note": e_result.note,
    }


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
    """Phase 9 §T9.2 (iter 128) — numeric transport via post-stratification.

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
    from ..refusals import EstimatorFailure

    transport_block = (result.get("extensions") or {}).get(blocks.TRANSPORT_IDENTIFICATION)
    if not isinstance(transport_block, dict):
        return blocked('identification_chose_another_strategy')
    adjustment_atoms = transport_block.get("adjustment_set") or []
    if not adjustment_atoms:
        return blocked('design_unavailable')
    adjustment_names = tuple(
        a.get("predicate") for a in adjustment_atoms if isinstance(a, dict)
    )
    if not adjustment_names or not all(adjustment_names):
        return blocked('design_unavailable')

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
        # guards — the other arrived as `invalid_input`, telling a caller
        # their request was malformed when what had happened was that
        # their source data held no contrast in a stratum the target
        # marginal weights.
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
        "adjustment": list(estimate.adjustment),
        "treatment": estimate.treatment,
        "outcome": estimate.outcome,
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    _attach_precision_budget(result["numeric_estimate"])
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
    from ..refusals import EstimatorFailure

    block = (result.get("extensions") or {}).get(blocks.SELECTION_RECOVERY) or {}
    x = q_stmt.query.intervention.atom.predicate
    y = q_stmt.query.target.atom.predicate

    if not block.get("recoverable"):
        result["estimator_failure"] = {
            "estimator": "selection_backdoor_recovery",
            "failure_type": refusals.NOT_RECOVERABLE,
            "reason": (
                block.get("failure_reason")
                or "P(y|do(x)) is not recoverable from the selection bias via "
                   "the selection-backdoor criterion; no number is produced."
            ),
        }
        return blocked('not_identified')

    external = list(block.get("external_data_needed") or [])
    z_plus = tuple(block.get("z_plus") or ())
    z_minus = tuple(block.get("z_minus") or ())
    selection_nodes = tuple(block.get("selection_nodes") or ())

    if reference_data is None:
        # Recoverable only with external unbiased data we don't have. Refuse —
        # the biased back-door number would be silently wrong.
        need = "; ".join(external) if external else "external unbiased weights"
        result["estimator_failure"] = {
            "estimator": "selection_backdoor_recovery",
            "failure_type": refusals.EXTERNAL_DATA_REQUIRED,
            "reason": (
                f"P(y|do(x)) is recoverable from this selection bias only with "
                f"external unbiased data ({need}). Supply it as reference_data= "
                f"to compute the recovered ATE. The ordinary back-door estimate "
                f"on the collider-restricted sample would be biased and is "
                f"withheld."
            ),
            "external_data_needed": external,
            "recovery_formula": block.get("recovery_formula"),
        }
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
        result["estimator_failure"] = {
            "estimator": "selection_backdoor_recovery",
            "failure_type": refusals.INVALID_INPUT,
            "reason": str(exc),
        }
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
        "adjustment": list(est.z_plus) + list(est.z_minus),
        "treatment": est.treatment,
        "outcome": est.outcome,
        # selection-backdoor recovery detail (audit trail + verifier inputs)
        "selection_recovery_numeric": {
            "reference_sample_size": est.reference_sample_size,
            "reference_data_hash": est.reference_data_hash,
            "z_plus": list(est.z_plus),
            "z_minus": list(est.z_minus),
            "selected_values": est.selected_values,
            "mu_treated": est.mu_treated,
            "mu_control": est.mu_control,
            "form": est.form,
            "model_assumption": est.model_assumption,
            "sufficient_statistics": est.sufficient_statistics,
        },
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    _finalise_numeric_result(result)
    return answered()


def _try_measurement_correction_estimate(
    q_stmt, result: dict, contract, graph, *,
    adjustment_sets, given, spec: dict,
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
    from ..refusals import EstimatorFailure

    x_atom = q_stmt.query.intervention.atom
    y_atom = q_stmt.query.target.atom
    target_value = q_stmt.query.target.value

    if not adjustment_sets:
        result["estimator_failure"] = {
            "estimator": "measurement_error_correction",
            "failure_type": refusals.REQUIRES_BACKDOOR_IDENTIFICATION,
            "reason": (
                "confusion-matrix correction composes with back-door "
                "standardisation, but P(y|do(x)) is not back-door identified "
                "here; no corrected number is produced."
            ),
        }
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
        result["estimator_failure"] = {
            "estimator": "measurement_error_correction",
            "failure_type": refusals.INVALID_INPUT,
            "reason": str(exc),
        }
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
        "adjustment": list(est.adjustment),
        "treatment": est.treatment,
        "outcome": est.outcome,
        # Confusion-matrix correction detail (audit trail + verifier inputs).
        # The matrix + per-stratum value-count vectors don't fit derivation-
        # input serialization, so they live here and are re-inverted by
        # verify_measurement_correction_numeric (kernel-called).
        "measurement_correction": _measurement_correction_block(est),
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    _attach_precision_budget(result["numeric_estimate"])

    from ..output.result_orchestrator import build_mechanism_audit
    ext = result.setdefault("extensions", {})
    ext[blocks.MECHANISM_AUDIT] = build_mechanism_audit(
        target=f"P({est.outcome}={est.target_value}|do({est.treatment}))",
        form=est.form,
        method=est.method,
        assumption=est.model_assumption,
        provenance="default",
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
    differential by construction."""
    block = {
        "naive_point": est.naive_point,
        "out_of_simplex": est.out_of_simplex,
        "states": list(est.states),
        "target_value": est.target_value,
        "differential": bool(getattr(est, "differential", False)),
        "form": est.form,
        "model_assumption": est.model_assumption,
        "sufficient_statistics": est.sufficient_statistics,
    }
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
    return block


def _try_exposure_measurement_correction_estimate(
    q_stmt, result: dict, contract, graph, *,
    adjustment_sets, given, spec: dict,
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
    from ..refusals import EstimatorFailure

    x_atom = q_stmt.query.intervention.atom
    y_atom = q_stmt.query.target.atom
    target_value = q_stmt.query.target.value

    if not adjustment_sets:
        result["estimator_failure"] = {
            "estimator": "exposure_measurement_error_correction",
            "failure_type": refusals.REQUIRES_BACKDOOR_IDENTIFICATION,
            "reason": (
                "confusion-matrix correction composes with back-door "
                "standardisation, but P(y|do(x)) is not back-door identified "
                "here; no corrected number is produced."
            ),
        }
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
        result["estimator_failure"] = {
            "estimator": "exposure_measurement_error_correction",
            "failure_type": refusals.INVALID_INPUT,
            "reason": str(exc),
        }
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
        "adjustment": list(est.adjustment),
        "treatment": est.treatment,
        "outcome": est.outcome,
        # Exposure confusion-matrix correction detail (audit trail + verifier
        # inputs). The matrix + per-stratum joint tables don't fit derivation-
        # input serialization, so they live here and are re-inverted by
        # verify_exposure_measurement_correction_numeric (kernel-called).
        "measurement_correction": _measurement_correction_block(est),
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    _attach_precision_budget(result["numeric_estimate"])

    from ..output.result_orchestrator import build_mechanism_audit
    ext = result.setdefault("extensions", {})
    ext[blocks.MECHANISM_AUDIT] = build_mechanism_audit(
        target=f"P({est.outcome}={est.target_value}|do({est.treatment}))",
        form=est.form,
        method=est.method,
        assumption=est.model_assumption,
        provenance="default",
    )

    result["derivation"] = _build_measurement_correction_derivation_dict(
        graph=graph, x=x_atom, y=y_atom, adjustment=chosen,
        given=frozenset(given), estimate=est,
    )
    _finalise_numeric_result(result)
    return answered()


def _try_combined_measurement_correction_estimate(
    q_stmt, result: dict, contract, graph, *,
    adjustment_sets, given, spec_x: dict, spec_y: dict,
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
    from ..refusals import EstimatorFailure

    x_atom = q_stmt.query.intervention.atom
    y_atom = q_stmt.query.target.atom
    target_value = q_stmt.query.target.value

    if spec_x.get("differential") or spec_y.get("differential"):
        result["estimator_failure"] = {
            "estimator": "combined_measurement_error_correction",
            "failure_type": refusals.DIFFERENTIAL_COMBINED_MISCLASSIFICATION_DEFERRED,
            "reason": (
                "a confusion matrix was supplied for BOTH the exposure "
                f"{x_atom.predicate!r} and the outcome {y_atom.predicate!r}, and "
                "at least one of them is differential. The combined correction "
                "factorises the observed table as M_x · P_true · M_yᵀ, which "
                "holds only while each matrix is constant; a differential matrix "
                "is selected by a level the other channel mismeasures, so the "
                "factorisation — and the correction built on it — does not apply."
            ),
        }
        return blocked('design_unavailable')

    if not adjustment_sets:
        result["estimator_failure"] = {
            "estimator": "combined_measurement_error_correction",
            "failure_type": refusals.REQUIRES_BACKDOOR_IDENTIFICATION,
            "reason": (
                "confusion-matrix correction composes with back-door "
                "standardisation, but P(y|do(x)) is not back-door identified "
                "here; no corrected number is produced."
            ),
        }
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
        result["estimator_failure"] = {
            "estimator": "combined_measurement_error_correction",
            "failure_type": refusals.INVALID_INPUT,
            "reason": str(exc),
        }
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
        "adjustment": list(est.adjustment),
        "treatment": est.treatment,
        "outcome": est.outcome,
        # Both matrices + per-stratum joint tables don't fit derivation-input
        # serialization, so they live here and are re-inverted by
        # verify_combined_measurement_correction_numeric (kernel-called).
        "measurement_correction": _measurement_correction_block(est),
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    _attach_precision_budget(result["numeric_estimate"])

    from ..output.result_orchestrator import build_mechanism_audit
    ext = result.setdefault("extensions", {})
    ext[blocks.MECHANISM_AUDIT] = build_mechanism_audit(
        target=f"P({est.outcome}={est.target_value}|do({est.treatment}))",
        form=est.form,
        method=est.method,
        assumption=est.model_assumption,
        provenance="default",
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
    from (the design covariance matrix Σ_WZ + Cov((W,Z),Y) + σ²_u)."""
    return {
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
        "model_assumption": est.model_assumption,
        "sufficient_statistics": est.sufficient_statistics,
    }


def _try_regression_calibration_estimate(
    q_stmt, result: dict, contract, graph, *,
    adjustment_sets, given, error_map: dict,
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
    from ..refusals import EstimatorFailure

    x_atom = q_stmt.query.intervention.atom
    y_atom = q_stmt.query.target.atom

    if not adjustment_sets:
        result["estimator_failure"] = {
            "estimator": "regression_calibration",
            "failure_type": refusals.REQUIRES_BACKDOOR_IDENTIFICATION,
            "reason": (
                "regression calibration composes with back-door adjustment, but "
                "P(y|do(x)) is not back-door identified here; no corrected slope "
                "is produced."
            ),
        }
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
        result["estimator_failure"] = {
            "estimator": "regression_calibration",
            "failure_type": refusals.MISMEASURED_COVARIATE_NOT_IN_ADJUSTMENT,
            "reason": (
                f"a measurement-error variance was supplied for {not_in_design!r}, "
                f"which is neither the exposure nor a covariate in the back-door "
                f"adjustment set {list(adjustment_names)!r}; a confounder must be "
                f"adjusted for to be corrected."
            ),
        }
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
        result["estimator_failure"] = {
            "estimator": "regression_calibration",
            "failure_type": refusals.INVALID_INPUT,
            "reason": str(exc),
        }
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
        "adjustment": list(est.adjustment),
        "treatment": est.treatment,
        "outcome": est.outcome,
        # Regression-calibration detail (audit trail + verifier inputs). The
        # design covariance matrix + Cov((W,Z),Y) + σ²_u don't fit derivation-
        # input serialization, so they live here and the corrected/naive slope
        # is re-derived by verify_regression_calibration_numeric (kernel-called).
        "regression_calibration": _regression_calibration_block(est),
    }
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    _attach_precision_budget(result["numeric_estimate"])

    from ..output.result_orchestrator import build_mechanism_audit
    ext = result.setdefault("extensions", {})
    ext[blocks.MECHANISM_AUDIT] = build_mechanism_audit(
        target=f"dE[{est.outcome}|do({est.treatment}),Z]/d{est.treatment}",
        form=est.form,
        method=est.method,
        assumption=est.model_assumption,
        provenance="default",
    )

    result["derivation"] = _build_measurement_correction_derivation_dict(
        graph=graph, x=x_atom, y=y_atom, adjustment=chosen,
        given=frozenset(given), estimate=est,
    )
    _finalise_numeric_result(result)
    return answered()


def _try_outcome_error_assessment(
    result: dict,
    contract: DataContract,
    graph,
    *,
    x_atom,
    y_atom,
    adjustment_sets,
    spec: dict,
) -> Claim:
    """Assess what a declared classical outcome-error variance costs, and say
    whether the query may proceed.

    Returns True when the assessment succeeded — the caller falls through to
    the ordinary routing, because a non-differential additive outcome error
    moves no conditional mean and there is no correction to apply. Returns
    False after recording an ``estimator_failure``: the spec named the wrong
    channel (a discrete outcome is misclassification, which DOES attenuate and
    IS correctable), or the declared variance does not fit under the residual
    variation the data show — in which case the independence premise that made
    the point safe is itself in doubt, so no number is shipped.
    """
    from .outcome_error import assess_outcome_error
    from ..refusals import EstimatorFailure

    if not adjustment_sets:
        result["estimator_failure"] = {
            "estimator": "outcome_measurement_error",
            "failure_type": refusals.REQUIRES_BACKDOOR_IDENTIFICATION,
            "reason": (
                "the residual-variance split that quantifies a mismeasured "
                f"outcome is taken around the back-door design, but P("
                f"{y_atom.predicate}|do({x_atom.predicate})) is not back-door "
                "identified here; no assessment is issued."
            ),
        }
        return blocked('design_unavailable')

    chosen = min(adjustment_sets, key=len)
    adjustment_names = tuple(a.predicate for a in _topo_order(graph, chosen))

    try:
        assessment = assess_outcome_error(
            contract.data,
            treatment=x_atom.predicate, outcome=y_atom.predicate,
            adjustment=adjustment_names,
            error_variance=(spec or {}).get("error_variance"),
        )
    except EstimatorFailure as exc:
        refusals.record(result, estimator="outcome_measurement_error", exc=exc)
        return blocked('estimator_refused')
    except (ValueError, KeyError, TypeError) as exc:
        result["estimator_failure"] = {
            "estimator": "outcome_measurement_error",
            "failure_type": refusals.INVALID_INPUT,
            "reason": str(exc),
        }
        return blocked('estimator_refused')

    result["outcome_error"] = {
        "outcome": assessment.outcome,
        "treatment": assessment.treatment,
        "design_vars": list(assessment.design_vars),
        "error_variance": assessment.error_variance,
        "residual_variance": assessment.residual_variance,
        "signal_variance": assessment.signal_variance,
        "noise_share": assessment.noise_share,
        "se_inflation": assessment.se_inflation,
        "sample_size": assessment.sample_size,
        "data_hash": assessment.data_hash,
        "assumptions": list(assessment.assumptions),
        # Σ_D, Cov(D, Y), Var(Y), σ²_v, n — the split is a closed-form function
        # of these, so verify_outcome_error re-derives it without the data.
        "sufficient_statistics": assessment.sufficient_statistics,
        "source": (spec or {}).get("source"),
    }
    return annotated()


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
    """Iter 123 — fit a logistic outcome model E[Y|X,Z] on the same
    data the backdoor estimator used, count fitted probabilities
    saturated near 0/1, and surface
    ``outcome_model_quasi_separation`` if more than
    ``OUTCOME_SATURATION_FRACTION`` of the sample lies outside
    [OUTCOME_SATURATION_LOWER, OUTCOME_SATURATION_UPPER].

    Distinct from iter 121's ``propensity_overlap_violation`` —
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
        feats = df[feature_cols].to_numpy(dtype=float)
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
    gap_entry = {
        "kind": "outcome_model_quasi_separation",
        "severity": "informational",
        "blocks": "interpretation",
        "description": (
            f"Backdoor 后门 logistic 模型 P({outcome}=1 | "
            f"{feature_names}) 的训练集预测概率在 "
            f"{n_outside}/{n_total} ({fraction_outside:.1%}) 个观测上"
            f"落在 [{OUTCOME_SATURATION_LOWER}, "
            f"{OUTCOME_SATURATION_UPPER}] 之外（min={p_min:.3f}, "
            f"max={p_max:.3f}）。这是 quasi-separation 信号——结果在"
            f"某些 (treatment, confounder) 子层近乎确定，logistic "
            f"系数已饱和。点估计仍能算出但 CI 偏窄、对极端结局的"
            f"偏差放大。这是 outcome 模型的失败模式，跟 iter 121 "
            f"`propensity_overlap_violation` 检查的 treatment "
            f"assignment 模型互补。"
        ),
        "required_data": None,
        "alternative_paths": [
            "在饱和子层补样本（增加 rare-outcome 观测）—— Hosmer-"
            "Lemeshow rule of thumb：每个参数至少 10 events",
            "改用 Firth penalised logistic 或 exact logistic regression "
            "（非 sklearn 默认 L2）— 它们对 separation 稳健",
            "用 bootstrap CI 而不是 plug-in CI（已经在做，但 bootstrap "
            "本身在 saturation 下也不够稳定，可能产生 NaN draws）",
            "如果 treatment×confounder 组合稀疏到这种程度，考虑 "
            "Bayesian 方法 + 弱信息 prior 而不是 frequentist 估计",
        ],
        "provenance": [{
            "ref_kind": "verifier_check",
            "ref_id": (
                f"outcome_separation:{outcome}|{treatment}:"
                f"{','.join(adjustment) if adjustment else '<none>'}"
            ),
        }],
    }

    report = result.get("data_gap_report")
    if report is None:
        report = {
            "summary": "outcome 模型 quasi-separation 警告",
            "gaps": [gap_entry],
            "actionable_next_steps": [],
        }
        result["data_gap_report"] = report
    else:
        report.setdefault("gaps", []).append(gap_entry)

    headline = (
        f"⚠ outcome 回归 P({outcome}=1|{treatment},Z) 在 "
        f"{n_outside}/{n_total} ({fraction_outside:.1%}) 样本上"
        f"饱和到 [{OUTCOME_SATURATION_LOWER}, "
        f"{OUTCOME_SATURATION_UPPER}] 之外；quasi-separation 信号，"
        "logistic 拟合不稳定，CI 偏窄"
    )
    existing = result.get("explanation") or ""
    if headline not in existing:
        result["explanation"] = (
            f"{headline}\n{existing}".strip() if existing else headline
        )


def _attach_propensity_overlap_warning(
    result: dict, contract, treatment: str, adjustment: tuple[str, ...],
) -> None:
    """Iter 121 — fit a logistic propensity model P(X=1|Z) on the same
    data the backdoor estimator used, count observations whose
    estimated propensity falls outside [PROPENSITY_OVERLAP_LOWER,
    PROPENSITY_OVERLAP_UPPER], and surface a
    ``propensity_overlap_violation`` gap if more than
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

    if not adjustment:
        return
    df = contract.data
    if treatment not in df.columns:
        return
    if not pd.api.types.is_bool_dtype(df[treatment]):
        return

    try:
        z = df[list(adjustment)].to_numpy(dtype=float)
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

    gap_entry = {
        "kind": "propensity_overlap_violation",
        "severity": "informational",
        "blocks": "interpretation",
        "description": (
            f"Estimated propensity P({treatment}=1 | "
            f"{', '.join(adjustment)}) falls outside "
            f"[{PROPENSITY_OVERLAP_LOWER}, {PROPENSITY_OVERLAP_UPPER}] "
            f"for {n_outside}/{n_total} observations "
            f"({fraction_outside:.1%}; min={p_min:.3f}, "
            f"max={p_max:.3f}). Hernan & Robins ch.3 'positivity': "
            "every confounder stratum should have both treated and "
            "untreated units. The backdoor / g-formula estimate "
            "extrapolates the outcome regression into the off-support "
            "region — that part of the answer is not real causal "
            "estimation, just model assumption."
        ),
        "required_data": None,
        "alternative_paths": [
            "trim the sample to the overlap region (e.g. drop "
            "observations with propensity outside [0.05, 0.95]) and "
            "re-estimate — the answer becomes ATE on the overlap "
            "subset, not the full population",
            "switch to a method robust to limited overlap (matching "
            "with caliper, weighted ATT instead of ATE, "
            "stratified-on-propensity estimator)",
            "broaden the adjustment set so that the off-support "
            "stratum is no longer the same — but only if a defensible "
            "Z addition exists",
            "report a bounds-only answer for the off-support region",
        ],
        "provenance": [{
            "ref_kind": "verifier_check",
            "ref_id": (
                f"propensity_overlap:{treatment}|"
                f"{','.join(adjustment)}"
            ),
        }],
    }

    report = result.get("data_gap_report")
    if report is None:
        report = {
            "summary": "倾向得分 overlap 警告",
            "gaps": [gap_entry],
            "actionable_next_steps": [],
        }
        result["data_gap_report"] = report
    else:
        report.setdefault("gaps", []).append(gap_entry)

    # Mirror to explanation — same posture as weak_iv_instrument.
    headline = (
        f"⚠ 倾向得分 P({treatment}=1|Z) 在 "
        f"{n_outside}/{n_total} ({fraction_outside:.1%}) 样本上 "
        f"超出 [{PROPENSITY_OVERLAP_LOWER}, {PROPENSITY_OVERLAP_UPPER}]"
        "；后门估计在这部分依赖外推而非真实因果识别"
    )
    existing = result.get("explanation") or ""
    if headline not in existing:
        result["explanation"] = (
            f"{headline}\n{existing}".strip() if existing else headline
        )


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
    the estimate is still surfaced, and the caveat is mirrored into
    ``explanation`` so the renderer cannot drop it. The point of the
    disclosure is not that the number is worse — 2SLS is a fine estimator
    — but that it answers a different question than the identification
    layer named, and a substitution nobody can see is indistinguishable
    from an error.
    """
    reason = getattr(iv_estimate, "stratification_fallback", None)
    if reason is None:
        return

    w = ", ".join(iv_estimate.conditioning) or "∅"
    gap_entry = {
        "kind": "iv_estimand_fallback_to_linear",
        "severity": "informational",
        "blocks": "interpretation",
        "description": (
            f"Instrument `{iv_estimate.instrument}` is valid only given "
            f"{{{w}}}, which names the stratified Wald — the effect among "
            f"compliers. This sample cannot be cut that way: {reason}. The "
            f"reported number is therefore the 2SLS coefficient, which "
            f"weights each stratum's effect by how strongly the instrument "
            f"moves treatment there rather than by that stratum's share of "
            f"compliers. The two coincide only when the first stage is "
            f"equally strong in every stratum; otherwise they are different "
            f"quantities, not different estimates of one quantity."
        ),
        "required_data": {
            "data_type": "ipd",
            "population": (
                "the strata of the conditioning set that currently carry "
                "only one instrument arm (or none at all)"
            ),
            "variables": [
                iv_estimate.instrument,
                iv_estimate.treatment,
                iv_estimate.outcome,
                *iv_estimate.conditioning,
            ],
        },
        "if_provided": (
            "the stratified Wald runs and the reported quantity becomes the "
            "effect among compliers, the estimand the instrument identifies"
        ),
        "alternative_paths": [
            "collect observations in the strata that are missing an "
            "instrument arm, which restores the LATE directly",
            "coarsen the conditioning set (fewer or broader categories) so "
            "every cell carries both instrument arms — valid only if the "
            "coarser set still blocks the instrument-outcome backdoor",
            "report the 2SLS coefficient as-is, stating that it is a "
            "variance-weighted average of stratum effects rather than the "
            "effect among compliers",
        ],
        "provenance": [{
            "ref_kind": "verifier_check",
            "ref_id": (
                f"iv_estimand_fallback:{iv_estimate.instrument}|{w}"
            ),
        }],
    }

    report = result.get("data_gap_report")
    if report is None:
        result["data_gap_report"] = {
            "summary": "工具变量估计目标回退警告",
            "gaps": [gap_entry],
            "actionable_next_steps": [],
        }
    else:
        report.setdefault("gaps", []).append(gap_entry)

    headline = (
        f"⚠ 工具变量 `{iv_estimate.instrument}` 只在 {{{w}}} 之下有效，"
        f"本应走分层 Wald（compliers 上的 LATE），但本样本分不了层"
        f"（{reason}）；报出的是 2SLS 系数，它按各层工具强度加权而非按"
        f"complier 份额加权——两者只在各层一阶段力度相同时才是同一个量"
    )
    existing = result.get("explanation") or ""
    if headline not in existing:
        result["explanation"] = (
            f"{headline}\n{existing}".strip() if existing else headline
        )


def _attach_weak_iv_warning_if_low_f(result: dict, iv_estimate) -> None:
    """Iter 120 — when the first-stage F-statistic is below the
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
    ar_clause = ""
    ar_alt = (
        "report the Anderson-Rubin confidence set — it inverts a test "
        "with correct size regardless of first-stage strength"
    )
    if ar is not None:
        rendered = _render_ar_set(ar)
        pct = int(round(ar.ci_level * 100))
        ar_clause = (
            f" The Anderson-Rubin {pct}% weak-robust confidence set "
            f"(valid whatever the instrument strength) is {rendered}."
        )
        ar_alt = (
            f"use the Anderson-Rubin {pct}% weak-robust set {rendered} "
            "(already computed; valid under weak instruments) instead of "
            "the bootstrap CI"
        )

    gap_entry = {
        "kind": "weak_iv_instrument",
        "severity": "informational",
        "blocks": "interpretation",
        "description": (
            f"First-stage F = {f_stat:.2f} for instrument "
            f"`{iv_estimate.instrument}` falls below the Stock-Yogo "
            f"(2005) threshold of {WEAK_IV_F_THRESHOLD:.0f}. "
            "The IV estimate's bias toward OLS scales with 1/F, "
            "and the 2SLS / Wald bootstrap CI is unreliable when the "
            "first stage is weak. Treat the point estimate as a rough "
            f"guide, not a tight identification.{ar_clause}"
        ),
        "required_data": None,
        "alternative_paths": [
            "find a stronger instrument (higher first-stage partial "
            "correlation with treatment after conditioning)",
            ar_alt,
            "fall back to a bounds-only answer (Manski natural / "
            "Balke-Pearl IV are weak-instrument robust)",
        ],
        "provenance": [{
            "ref_kind": "verifier_check",
            "ref_id": (
                f"weak_iv:{iv_estimate.instrument}->{iv_estimate.treatment}"
            ),
        }],
    }

    report = result.get("data_gap_report")
    if report is None:
        report = {
            "summary": "弱工具变量警告",
            "gaps": [gap_entry],
            "actionable_next_steps": [],
        }
        result["data_gap_report"] = report
    else:
        report.setdefault("gaps", []).append(gap_entry)

    # Mirror to explanation so the renderer can't silently drop the
    # weak-IV caveat — same channel as scheduler._attach_structural_caveats
    # uses for must-disclose kinds. Done here rather than in scheduler
    # because weak_iv only becomes visible after the estimator runs.
    headline = (
        f"⚠ 工具变量 `{iv_estimate.instrument}` first-stage F = "
        f"{f_stat:.2f} 低于 Stock-Yogo 弱工具阈值 "
        f"{WEAK_IV_F_THRESHOLD:.0f}；IV 估计 bias 偏向 OLS、"
        "bootstrap CI 不可靠"
    )
    if ar is not None:
        pct = int(round(ar.ci_level * 100))
        headline = (
            f"{headline}；Anderson-Rubin {pct}% 稳健集 = "
            f"{_render_ar_set(ar)}"
        )
    existing = result.get("explanation") or ""
    if headline not in existing:
        result["explanation"] = (
            f"{headline}\n{existing}".strip() if existing else headline
        )


def _closer_to_null(point, ci_lower, ci_upper):
    """Return whichever CI bound is on the same side of zero as the
    point estimate but closer to zero. None if either bound is missing."""
    if ci_lower is None or ci_upper is None:
        return None
    if point >= 0:
        # Lower bound is closer to null (zero) for a positive effect
        return ci_lower if ci_lower >= 0 else None
    # Upper bound is closer to null for a negative effect
    return ci_upper if ci_upper <= 0 else None


# Gap kinds the supplied DataFrame + computed point estimate make stale.
# Both directly contradict a numerically_solved point result:
#   - missing_distribution: the θ it asks for was supplied via the df.
#   - answer_is_bounds_not_point_estimate: a point was computed, so the
#     bounds are no longer THE answer.
# Structural caveats (ambiguous_variable, unmeasured_confounder_risk,
# ill_defined_intervention, ...) and estimator-time gaps (weak_iv,
# propensity_overlap, outcome_separation) are NOT dropped — still true.
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
    """Flip result status to numerically_solved, set a truthy
    structural_result, drop stale missing_information entries, and
    reconcile the data_gap_report so it no longer contradicts the
    attached point estimate.

    Shared between backdoor (7.1) and front-door (7.2) numeric paths.
    """
    result["status"] = "numerically_solved"
    result["structural_result"] = {"value": True}
    result.pop("missing_information", None)
    _reconcile_gap_report_after_numeric_solve(result)


def _reconcile_gap_report_after_numeric_solve(result: dict) -> None:
    """A point estimate was computed from the supplied data. The gap
    report was built by the identification pass BEFORE the data arrived,
    so it may still advertise ``missing_distribution: blocking`` and
    ``answer_is_bounds_not_point_estimate`` — both now false for a genuine
    non-parametric point. Drop those gaps, drop the parameter
    ``investigation_requests`` they cite (so the auditor's T10-2
    completeness check doesn't then demand a gap for data we already have
    — keeping the dual surfaces consistent), set the tier to ``point``,
    and recompute the one-line summary.
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

    gaps = [
        g for g in report.get("gaps", [])
        if g.get("kind") not in _NUMERIC_SATISFIED_GAP_KINDS
    ]
    report["gaps"] = gaps
    report["answer_tier"] = "point"
    report["summary"] = _summary_from_gap_dicts(gaps)


def _summary_from_gap_dicts(gaps: list[dict], answer_tier: str = "point") -> str:
    """Mirror ``output.data_gap_report._make_summary`` on already-sorted
    serialized gaps. ``answer_tier='interval'`` leads with the interval-in-hand
    clause (so a prose renderer is not misled into "no answer"); ``'point'`` /
    ``'none'`` behave as the identification-time summary."""
    if not gaps:
        return ""
    head = gaps[0]
    blocking = sum(1 for g in gaps if g.get("severity") == "blocking")
    base = head.get("description", "")
    if blocking > 1:
        base = f"{base}（共 {blocking} 个 blocking 缺口）"
    if answer_tier == "interval":
        return f"可得区间估计（点识别被阻断，但有信息性 bounds）：{base}"
    if answer_tier == "none":
        return f"图+数据无法给出点或区间估计（需补假设或更强数据）：{base}"
    return base


def _attach_bootstrap_meta(numeric_estimate: dict, cluster: str | None) -> None:
    """Record the bootstrap resampling kind on a numeric_estimate.

    Only attached when a cluster column is in play — leaving it off the
    i.i.d. path keeps cluster=None output byte-identical (the absence of
    the block means the default i.i.d. bootstrap). When clustered,
    records ``{"kind": "cluster", "cluster_column": ...}`` so a consumer
    can tell the CI was widened to be cluster-robust.
    """
    if cluster is None:
        return
    numeric_estimate["bootstrap"] = {
        "kind": "cluster",
        "cluster_column": cluster,
    }


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
    the SHARED top-level sample_size. Iter 155."""
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


def _attach_precision_budget_decomposition(numeric_estimate: dict) -> None:
    """Mediation variant: numeric_estimate has a ``decomposition`` dict
    where each component (nde / nie / te / proportion_mediated) carries
    its own ci_lower / ci_upper. Compute a precision_budget per
    component using the SHARED top-level sample_size. Iter 154."""
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

    Iter 160: ``relative_width`` field added when ``point`` is
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
    n_for_halve, hint = estimate_n_for_target_ci_half_width(
        current_n=n,
        current_ci_half_width=half_width,
        target_ci_half_width=target,
    )
    out: dict = {
        "current_ci_half_width": round(half_width, 6),
        "n_to_halve_ci": n_for_halve,
        "hint": hint,
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
    from .aipw import estimate_aipw_ate, estimate_ipw_ate
    from .tmle import estimate_tmle_ate

    try:
        if estimator == "aipw":
            est = estimate_aipw_ate(
                contract.data,
                treatment=x.predicate, outcome=y.predicate,
                adjustment=adjustment_names,
                outcome_model=model,  # type: ignore[arg-type]
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
    if estimator in ("aipw", "tmle"):
        ne["doubly_robust"] = True
        ne["std_error"] = est.std_error
        ne["ci_method"] = est.ci_method
        if estimator == "tmle":
            # The fluctuation parameter — a transparency handle: ε≈0 means
            # the initial outcome fit was already well-targeted.
            ne["tmle_epsilon"] = est.epsilon
        if est.ci_method == "influence_function":
            # Analytic CI — no bootstrap. Record the inference kind so a
            # consumer knows the CI is Wald-from-influence-function (and
            # cluster-robust when a cluster column is in play).
            ne["inference"] = {
                "method": "influence_function",
                "cluster_robust": cluster is not None,
            }
        else:
            _attach_bootstrap_meta(ne, cluster)
    else:
        ne["stabilized"] = est.stabilized
        _attach_bootstrap_meta(ne, cluster)

    result["numeric_estimate"] = ne

    from ..output.result_orchestrator import (
        build_assumption_ledger,
        build_mechanism_audit,
    )
    ext = result.setdefault("extensions", {})
    ext[blocks.MECHANISM_AUDIT] = build_mechanism_audit(
        target=est.outcome, form=est.form, method=est.method,
        assumption=est.model_assumption, provenance="default",
    )
    ledger = build_assumption_ledger(
        result, identification_specs=est.identification_assumptions,
    )
    if ledger is not None:
        ext[blocks.ASSUMPTION_LEDGER] = ledger

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
    *, graph, x, y, instrument, conditioning, estimate,
):
    """Two-step derivation for a data-based IV estimate:

        s1: iv_criterion_check (structural witness, Phase 6.iv)
        s2: numeric_iv_estimate (metadata audit — no re-fit)
    """
    from ..types import DerivationStep, StepRef, StructuralResult
    from ..verifier.serialization import derivation_to_dict

    steps = (
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
    from ..refusals import EstimatorFailure
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

    numeric = {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": est.method,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
        "instruments": list(est.instruments),
        "conditioning": list(est.conditioning),
        "treatment": est.treatment,
        "outcome": est.outcome,
        "n_instruments": est.n_instruments,
        "over_identification": {
            "test": "sargan",
            "sargan_j": est.sargan.j_stat,
            "sargan_dof": est.sargan.dof,
            "sargan_p_value": est.sargan.p_value,
            "rejected_at_0_05": bool(est.sargan.p_value < 0.05),
            # Residualised second moments the point + J are closed forms of (plus
            # the robust weight matrix Ŝ when Hansen J was computed) — the
            # verifier re-derives everything from these without the raw data.
            "sufficient_statistics": est.moments,
        },
    }
    # Heteroskedasticity-robust (efficient two-step GMM) Hansen J, when the
    # robust weight matrix was non-singular. The headline point stays 2SLS;
    # hansen_gmm_point is the efficient-GMM byproduct.
    if est.hansen is not None:
        oid = numeric["over_identification"]
        oid["hansen_j"] = est.hansen.j_stat
        oid["hansen_dof"] = est.hansen.dof
        oid["hansen_p_value"] = est.hansen.p_value
        oid["hansen_gmm_point"] = est.hansen.gmm_point
        oid["hansen_rejected_at_0_05"] = bool(est.hansen.p_value < 0.05)
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
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    _attach_precision_budget(result["numeric_estimate"])
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
    must-disclose gaps (+ explanation mirror): a weak JOINT first stage
    (F < Stock-Yogo) and a REJECTED Sargan over-identification test (the data
    refute the instruments' joint validity). Both are informational — the
    point is still reported; these add the caveat."""
    inst = ", ".join(f"`{z}`" for z in est.instruments)
    gaps: list[dict] = []
    headlines: list[str] = []

    f_stat = est.first_stage_f_stat
    if f_stat is not None and f_stat < WEAK_IV_F_THRESHOLD:
        # When the joint first stage is weak, point to the multi-instrument
        # Anderson-Rubin set — the interval that stays valid whatever the
        # instrument strength — instead of the unreliable bootstrap CI (parity
        # with the just-identified _attach_weak_iv_warning_if_low_f).
        ar = est.anderson_rubin
        ar_clause = ""
        ar_alt = (
            "report the Anderson-Rubin confidence set — it inverts a test with "
            "correct size regardless of joint first-stage strength"
        )
        headline_ar = ""
        if ar is not None:
            rendered = _render_ar_set(ar)
            pct = int(round(ar.ci_level * 100))
            ar_clause = (
                f" The multi-instrument Anderson-Rubin {pct}% weak-robust "
                f"confidence set (valid whatever the instruments' joint strength) "
                f"is {rendered}."
            )
            ar_alt = (
                f"use the Anderson-Rubin {pct}% weak-robust set {rendered} "
                "(already computed; valid under weak instruments) instead of the "
                "bootstrap CI"
            )
            headline_ar = f"；Anderson-Rubin {pct}% 稳健集 = {rendered}"
        # Prefer the heteroskedasticity-robust (Stock-Wright S) AR set when it was
        # computed: it is valid under weak identification AND heteroskedasticity /
        # clustering, so it is the strongest interval to report here.
        rar = est.robust_anderson_rubin
        if rar is not None:
            rrendered = _render_robust_ar_set(rar)
            pct = int(round(rar.ci_level * 100))
            ar_clause = (
                f"{ar_clause} The heteroskedasticity-robust Anderson-Rubin {pct}% "
                f"set (valid under weak instruments AND heteroskedasticity) is "
                f"{rrendered}."
            )
            ar_alt = (
                f"use the heteroskedasticity-robust Anderson-Rubin {pct}% set "
                f"{rrendered} (valid under weak instruments and heteroskedasticity) "
                "instead of the bootstrap CI"
            )
            headline_ar = (
                f"{headline_ar}；异方差稳健 AR {pct}% 集 = {rrendered}"
            )
        gaps.append({
            "kind": "weak_iv_instrument",
            "severity": "informational",
            "blocks": "interpretation",
            "description": (
                f"Joint first-stage F = {f_stat:.2f} for instruments {inst} "
                f"falls below the Stock-Yogo (2005) threshold of "
                f"{WEAK_IV_F_THRESHOLD:.0f}. The over-identified 2SLS estimate "
                "is biased toward OLS and the bootstrap CI is unreliable when "
                f"the instruments are jointly weak.{ar_clause}"
            ),
            "alternative_paths": [
                "find stronger instruments (higher joint first-stage partial "
                "correlation with the treatment)",
                ar_alt,
                "fall back to a bounds-only answer (weak-instrument robust)",
            ],
            "provenance": [{
                "ref_kind": "verifier_check",
                "ref_id": f"weak_iv_joint:{est.treatment}",
            }],
        })
        headlines.append(
            f"⚠ 工具变量 {inst} 联合 first-stage F = {f_stat:.2f} 低于 "
            f"Stock-Yogo 弱工具阈值 {WEAK_IV_F_THRESHOLD:.0f}{headline_ar}"
        )

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
        also = ""
        also_cn = ""
        if hj is not None and sg is not None:
            also = (
                f" (the homoskedastic Sargan gives J = {sg.j_stat:.2f}, "
                f"p = {sg.p_value:.4g})"
            )
            also_cn = f"（同方差 Sargan：J = {sg.j_stat:.2f}, p = {sg.p_value:.4g}）"
        gaps.append({
            "kind": "overidentification_rejected",
            "severity": "important",
            "blocks": "interpretation",
            "description": (
                f"The {test_label} over-identification test REJECTS the joint "
                f"validity of instruments {inst} (J = {J_used:.2f}, "
                f"df = {dof_used}, p = {p_used:.4g}){also}. At least one exclusion "
                "restriction is inconsistent with the others in the data — the "
                "IV point estimate rests on an instrument set the data refute. "
                "This is a falsification, not a data-quantity gap: it will not "
                "go away with more of the same data."
            ),
            "alternative_paths": [
                "drop the instrument(s) whose exclusion is suspect and re-run "
                "(a subset may pass)",
                "reconsider the causal graph — a rejected over-ID test often "
                "means an assumed Z→X-only path actually reaches Y directly",
                "fall back to a bounds-only answer that does not assume "
                "exclusion (Manski natural)",
            ],
            "provenance": [{
                "ref_kind": "verifier_check",
                "ref_id": f"overid:{est.treatment}",
            }],
        })
        headlines.append(
            f"⚠ {test_label} 过度识别检验拒绝工具 {inst} 的联合有效性 "
            f"(J = {J_used:.2f}, df = {dof_used}, p = {p_used:.4g}){also_cn}；"
            "数据反驳了该工具集"
        )

    if not gaps:
        return
    report = result.get("data_gap_report")
    if report is None:
        result["data_gap_report"] = {
            "summary": "过度识别 IV 诊断",
            "gaps": gaps,
            "actionable_next_steps": [],
        }
    else:
        report.setdefault("gaps", []).extend(gaps)

    existing = result.get("explanation") or ""
    for headline in headlines:
        if headline not in existing:
            existing = f"{headline}\n{existing}".strip() if existing else headline
    result["explanation"] = existing


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

    effect_stmts = [
        s for s in prog.statements
        if isinstance(s, QueryStatement) and isinstance(s.query, EffectQuery)
    ]
    effect_by_id = {s.id: s for s in effect_stmts}
    eligible_effect_ids = [
        s.id for s in effect_stmts
        if s.query.mediator is None
    ]

    warnings: list[str] = []
    if not effect_stmts:
        warnings.append(
            "dose_response_query present but program has no effect query; "
            "estimator skipped and data-gap report should be used",
        )
        return set(), warnings
    if not eligible_effect_ids:
        warnings.append(
            "dose_response_query present but all effect queries are mediation "
            "queries; dose-response estimator requires a non-mediation "
            "effect query",
        )
        return set(), warnings

    targets: set[str] = set()
    for a in dose_ambs:
        explicit = a.get("query_id")
        if explicit is not None:
            target_stmt = effect_by_id.get(explicit)
            if target_stmt is None:
                warnings.append(
                    f"dose_response_query query_id {explicit!r} does not "
                    "match any effect query; estimator skipped for that "
                    "ambiguity",
                )
            elif target_stmt.query.mediator is not None:
                warnings.append(
                    f"dose_response_query query_id {explicit!r} targets a "
                    "mediation effect query; dose-response estimator skipped",
                )
            else:
                targets.add(explicit)
        else:
            first_effect_id = effect_stmts[0].id
            first_eligible_id = eligible_effect_ids[0]
            if first_effect_id != first_eligible_id:
                warnings.append(
                    "dose_response_query without query_id skipped leading "
                    f"mediation effect query {first_effect_id!r} and routed "
                    f"to {first_eligible_id!r}",
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
        result["estimator_failure"] = {
            "estimator": estimator_label,
            "failure_type": refusals.UNKNOWN,
            "reason": str(exc),
        }
        return blocked('estimator_refused')

    result["numeric_estimate"] = {
        "method": est.method,
        "ci_level": est.ci_level,
        "assumptions": list(est.assumptions),
        "sample_size": est.sample_size,
        "data_hash": est.data_hash,
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
        build_mechanism_audit,
    )
    ext = result.setdefault("extensions", {})
    ext[blocks.MECHANISM_AUDIT] = build_mechanism_audit(
        target=est.outcome,
        form=est.form,
        method=est.method,
        assumption=est.model_assumption,
        provenance="default",
    )
    ledger = build_assumption_ledger(
        result, identification_specs=est.identification_assumptions,
    )
    if ledger is not None:
        ext[blocks.ASSUMPTION_LEDGER] = ledger
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
    """
    ast = _ensure_dict(program)
    statements = ast.get("statements", [])
    columns: set[str] = set()
    for stmt in statements:
        if stmt.get("kind") == "variable":
            pred = stmt.get("predicate")
            if isinstance(pred, str):
                columns.add(pred)
    return columns


def _ensure_dict(program: dict | str | bytes) -> dict:
    import json
    if isinstance(program, (str, bytes)):
        return json.loads(program)
    return program


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


def _json_safe_value(v):
    """Numpy scalar -> Python scalar so distinct-value sets serialize."""
    import numpy as np
    if isinstance(v, np.generic):
        return v.item()
    return v


def _declared_scale(scale, domain) -> str | None:
    """Resolve the POSITIVE declared measurement type, or None for
    'didn't say'. ``scale`` (binary/discrete/continuous) wins when set;
    otherwise an enumerated ``domain`` implies binary (<=2 levels) or
    discrete (>2). Neither declared → None (never reconciled, no noise)."""
    if scale in ("binary", "discrete", "continuous"):
        return scale
    if domain is not None:
        return "binary" if len(domain) <= 2 else "discrete"
    return None


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
    if pd.api.types.is_categorical_dtype(col):
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
            _json_safe_value(v) for v in pd.unique(col.dropna())
        )
    else:
        observed_values = None
    return observed, n_unique, observed_values, dtype_kind


def _reconcile_declared_observed(declared, domain, observed, n_unique,
                                 observed_values):
    """Compare declared vs observed. Returns (verdict, detail) — verdict is
    'ok' | 'declared_continuous_data_discrete' | 'domain_violated'."""
    if declared == "continuous":
        if observed in ("binary", "discrete"):
            return (
                "declared_continuous_data_discrete",
                f"declared scale='continuous' but the column has only "
                f"{n_unique} distinct value(s) {observed_values} — any "
                f"dose-response estimand collapses to a discrete contrast, "
                f"not a continuous curve",
            )
        return ("ok", "")
    if declared == "binary":
        if n_unique > 2:
            return (
                "domain_violated",
                f"declared binary (2 levels) but the column has {n_unique} "
                f"distinct value(s) — the g-formula silently treats it as a "
                f"multi-level / continuous exposure, not a two-arm contrast",
            )
        return ("ok", "")
    if declared == "discrete":
        if observed == "continuous":
            return (
                "domain_violated",
                f"declared discrete but the column has {n_unique} distinct "
                f"value(s) on a continuous scale",
            )
        if domain is not None and observed_values is not None:
            domain_set = {_json_safe_value(x) for x in domain}
            extra = [v for v in observed_values if v not in domain_set]
            if extra:
                return (
                    "domain_violated",
                    f"the column contains value(s) {extra} outside the "
                    f"declared domain {sorted(domain_set)}",
                )
        return ("ok", "")
    return ("ok", "")


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

    checks: list[dict] = []
    for pred, (scale, domain) in sorted(declarations.items()):
        if pred not in data.columns:
            continue
        declared = _declared_scale(scale, domain)
        if declared is None:
            continue  # no positive declaration → nothing to reconcile
        observed, n_unique, observed_values, dtype_kind = _observe_column(
            data[pred]
        )
        verdict, detail = _reconcile_declared_observed(
            declared, domain, observed, n_unique, observed_values
        )
        if verdict == "ok":
            continue
        checks.append({
            "predicate": pred,
            "declared_scale": declared,
            "declared_domain": list(domain) if domain is not None else None,
            "observed_scale": observed,
            "n_unique": n_unique,
            "observed_values": observed_values,
            "dtype_kind": dtype_kind,
            "verdict": verdict,
            "detail": detail,
        })
    if not checks:
        return

    blocks_by_verdict = {
        "declared_continuous_data_discrete": "interpretation",
        "domain_violated": "point_estimate",
    }
    gaps = []
    for c in checks:
        gaps.append({
            "kind": "declared_type_data_mismatch",
            "signature": c["verdict"],
            "severity": "important",
            "blocks": blocks_by_verdict[c["verdict"]],
            "description": (
                f"Variable {c['predicate']!r}: {c['detail']}. The estimate is "
                f"still computed on the coerced data, but it answers a "
                f"different estimand than the declaration promises — reconcile "
                f"the declared scale/domain with the data before trusting the "
                f"number as the declared quantity."
            ),
            "alternative_paths": [
                f"if {c['predicate']!r} really is "
                f"{c['declared_scale']}, fix the data column (the supplied "
                f"values disagree)",
                f"if the data is right, correct the declaration "
                f"(scale/domain) so the estimand matches what you can measure",
            ],
            "provenance": [{
                "ref_kind": "verifier_check",
                "ref_id": f"type_reconciliation:{c['predicate']}",
            }],
        })

    for result in output.get("results", []):
        ext = result.get("extensions")
        if not isinstance(ext, dict):
            ext = {}
            result["extensions"] = ext
        ext[blocks.TYPE_RECONCILIATION] = {"checks": [dict(c) for c in checks]}
        report = result.get("data_gap_report")
        if report is None:
            result["data_gap_report"] = {
                "summary": "声明的变量类型与数据不符",
                "gaps": [dict(g) for g in gaps],
                "actionable_next_steps": [],
            }
        else:
            report.setdefault("gaps", []).extend(dict(g) for g in gaps)
