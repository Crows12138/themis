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

from ..output.sample_size import estimate_n_for_target_ci_half_width
from .contract import DataContract, validate_data


def estimate_program(
    program: dict | str | bytes,
    data: Any,
    *,
    random_state: int = 42,
    ci_bootstrap: int = 500,
    model: str = "auto",
    cluster: str | None = None,
    ate_estimator: str = "gformula",
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
    """
    from ..kernel import run as _run

    identification_output = _run(program)

    cluster = _resolve_cluster_option(program, cluster)
    ate_estimator = _resolve_ate_estimator_option(program, ate_estimator)

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
    )

    _estimate_effect_queries(
        program, identification_output, contract,
        random_state=random_state, ci_bootstrap=ci_bootstrap, model=model,
        cluster=cluster, ate_estimator=ate_estimator,
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

    # Numeric end for the partial-identification layer: when point ID failed
    # and the kernel attached a SYMBOLIC bounds_result, evaluate it on data.
    # Runs after the point-estimate loop so it only ever ADDS numeric fields
    # to an already-symbolic bounds_result — never competes with a point.
    _attach_numeric_bounds(
        program, identification_output, contract,
        random_state=random_state, ci_bootstrap=ci_bootstrap, cluster=cluster,
    )

    return identification_output


def _maybe_estimate_longitudinal(
    program: dict | str | bytes,
    output: dict,
    contract: DataContract,
    *,
    random_state: int,
    ci_bootstrap: int,
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

    from .longitudinal import (
        estimate_longitudinal_gformula,
        estimate_longitudinal_ipw_msm,
    )
    from .dose_response import EstimatorFailure

    estimator = spec.get("estimator", "gformula")
    if estimator not in ("gformula", "ipw_msm"):
        target["estimator_failure"] = {
            "estimator": "longitudinal",
            "failure_type": "unknown",
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
        target["estimator_failure"] = {
            "estimator": method_name,
            "failure_type": (
                exc.failure_type
                if exc.failure_type in ("overlap_insufficient",
                                        "convergence_failure")
                else "unknown"
            ),
            "reason": str(exc),
        }
        return
    except (ValueError, KeyError) as exc:
        target["estimator_failure"] = {
            "estimator": method_name,
            "failure_type": "unknown",
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
    _attach_precision_budget(target["numeric_estimate"])


def _longitudinal_target_result(output: dict):
    """First effect-query result, else the first result, else None."""
    results = output.get("results", [])
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
    from .dose_response import EstimatorFailure

    target = None
    block = None
    for result in output.get("results", []):
        ext = result.get("extensions") or {}
        if "missing_data_recovery" in ext:
            target = result
            block = ext["missing_data_recovery"]
            break
    if target is None or block is None:
        return

    estimand = block.get("estimand") or {}
    if not estimand.get("recoverable", False):
        target["estimator_failure"] = {
            "estimator": "missing_data_recovery",
            "failure_type": "not_recoverable",
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
        target["estimator_failure"] = {
            "estimator": "missing_data_recovery",
            "failure_type": (
                "overlap_insufficient"
                if exc.failure_type == "insufficient_support" else "unknown"
            ),
            "reason": str(exc),
        }
        return
    except (ValueError, KeyError) as exc:
        target["estimator_failure"] = {
            "estimator": "missing_data_recovery",
            "failure_type": "unknown",
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
) -> None:
    """For each effect query result, attach a numeric_estimate when a
    supported identification strategy is available. Mutates ``output``
    in place.

    Phase 7.1: only backdoor adjustment is wired up. Unsupported
    strategies leave the result unchanged.
    """
    # Re-derive the graph + bidirected set once for the whole program;
    # results rely on the same structural facts the kernel already used.
    from ..input.semantic_validator import validate_program
    from ..input.syntactic_validator import validate_ast
    from ..runtime.graph_projection import project
    from ..runtime.instantiation import instantiate
    from ..runtime import structural_solver
    from .backdoor import estimate_backdoor_ate
    from .frontdoor import estimate_frontdoor_ate
    from .iv import estimate_iv_ate

    ast = _ensure_dict(program)
    ast = validate_ast(ast)
    prog = validate_program(ast)
    ground_statements = instantiate(prog)
    graph = project(ground_statements)
    bidirected = structural_solver.bidirected_from_ground(ground_statements)

    dose_response_query_ids, dose_response_warnings = _dose_response_routing_plan(prog)
    _append_data_contract_warnings(output, dose_response_warnings)

    for q_stmt, result in _pair_effect_queries(prog, output):
        if q_stmt is None:
            continue
        # Phase 7.L: a longitudinal g-formula estimate already claimed this
        # result. Do NOT overwrite it with the cross-sectional backdoor ATE
        # — that static adjustment is exactly the biased estimator the
        # g-formula exists to replace when a confounder is affected by past
        # treatment.
        if (result.get("numeric_estimate") or {}).get("method") in (
            "longitudinal_gformula", "longitudinal_ipw_msm",
        ):
            continue
        dose_response_triggered = q_stmt.id in dose_response_query_ids
        # Joint interventions: do(A=a, B=b, ...) over a treatment SET —
        # route to the joint g-formula estimator (joint contrast +
        # treatment×treatment interaction). Takes precedence over the
        # single-treatment / mediation / transport branches.
        if q_stmt.query.extra_interventions:
            _try_joint_estimate(
                q_stmt, result, contract, graph, bidirected,
                random_state=random_state, ci_bootstrap=ci_bootstrap,
                model=model, cluster=cluster,
            )
            continue
        # Phase 7.4: mediation queries route to the Imai-via-statsmodels
        # estimator, gated on the identification layer's strategy result.
        if q_stmt.query.mediator is not None:
            _try_mediation_estimate(
                q_stmt, result, contract, graph, bidirected,
                random_state=random_state, ci_bootstrap=ci_bootstrap,
                cluster=cluster,
            )
            continue

        # Phase 9 §T9.2 (iter 128): transport queries — when the kernel
        # already produced a transport_identification extension AND the
        # program declares a target marginal, run post-stratification
        # numeric transport. The identification result remains
        # structurally_solved; we add a numeric_estimate block.
        if q_stmt.query.target_population is not None:
            _try_transport_estimate(
                q_stmt, result, contract, program,
                random_state=random_state,
                ci_bootstrap=ci_bootstrap,
                ci_level=0.95,
                cluster=cluster,
            )
            continue

        x_atom = q_stmt.query.intervention.atom
        y_atom = q_stmt.query.target.atom
        given_atoms = tuple(g.atom for g in q_stmt.query.given)

        adjustment_sets = structural_solver.minimal_adjustment_sets(
            graph, x_atom, y_atom,
            given=given_atoms,
            bidirected=bidirected or None,
        )
        # Phase 14 slice a: when the program flagged a dose-response
        # query AND identification clears via backdoor, fit the curve
        # estimator instead of the binary-effect ATE estimator. Other
        # strategies (front-door / IV / mediation) keep their existing
        # binary-effect path until a real-case demands the curve there.
        if dose_response_triggered and _is_binary_treatment(
            contract.data, x_atom.predicate,
        ):
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
                    f"treatment {x_atom.predicate!r} is binary"
                ),
            )

        if dose_response_triggered and "estimator_fallback" not in result and adjustment_sets:
            chosen = min(adjustment_sets, key=len)
            adjustment_names = tuple(
                a.predicate for a in _topo_order(graph, chosen)
            )
            sampling_points = _resolve_dose_response_points(prog, x_atom)
            dr_model = _resolve_dose_response_model(model)
            if _try_dose_response_estimate(
                result=result,
                contract=contract,
                treatment=x_atom.predicate,
                outcome=y_atom.predicate,
                adjustment=adjustment_names,
                sampling_points=sampling_points,
                random_state=random_state,
                model=dr_model,
                graph=graph, x=x_atom, y=y_atom, chosen=chosen, given=given_atoms,
                cluster=cluster,
            ):
                continue
            # Estimator unavailable / failed structurally — fall through
            # to the binary path so the user still gets *something*.
        if adjustment_sets:
            chosen = min(adjustment_sets, key=len)
            adjustment_names = tuple(a.predicate for a in _topo_order(graph, chosen))

            # Doubly-robust opt-in: when the caller selected IPW / AIPW,
            # the backdoor-identified ATE is estimated by the propensity /
            # augmented estimator instead of the g-formula plug-in. Same
            # identification (the adjustment set is a valid backdoor set);
            # different estimator + inference. Default "gformula" leaves
            # this branch untaken and every existing result byte-identical.
            if ate_estimator in ("ipw", "aipw", "tmle"):
                _attach_doubly_robust_estimate(
                    result=result, contract=contract,
                    graph=graph, x=x_atom, y=y_atom,
                    adjustment=chosen, adjustment_names=adjustment_names,
                    given=frozenset(given_atoms),
                    estimator=ate_estimator,
                    random_state=random_state, ci_bootstrap=ci_bootstrap,
                    model=model, cluster=cluster,
                )
                continue

            estimate = estimate_backdoor_ate(
                contract.data,
                treatment=x_atom.predicate,
                outcome=y_atom.predicate,
                adjustment=adjustment_names,
                ci_bootstrap=ci_bootstrap,
                random_state=random_state,
                model=model,  # type: ignore[arg-type]
                cluster=cluster,
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
            _attach_bootstrap_meta(result["numeric_estimate"], cluster)
            from ..output.result_orchestrator import (
                build_assumption_ledger,
                build_mechanism_audit,
            )
            ext = result.setdefault("extensions", {})
            ext["mechanism_audit"] = build_mechanism_audit(
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
                ext["assumption_ledger"] = ledger
            _attach_precision_budget(result["numeric_estimate"])

            result["derivation"] = _build_numeric_derivation_dict(
                graph=graph,
                x=x_atom, y=y_atom,
                adjustment=chosen,
                given=frozenset(given_atoms),
                estimate=estimate,
            )
            _attach_e_value_if_binary(
                result, contract,
                outcome=y_atom.predicate, treatment=x_atom.predicate,
            )
            _attach_ovb_sensitivity(
                result, contract,
                treatment=x_atom.predicate,
                outcome=y_atom.predicate,
                adjustment=adjustment_names,
                method=estimate.method,
            )
            _attach_propensity_overlap_warning(
                result, contract,
                treatment=x_atom.predicate,
                adjustment=adjustment_names,
            )
            _attach_outcome_separation_warning(
                result, contract,
                treatment=x_atom.predicate,
                outcome=y_atom.predicate,
                adjustment=adjustment_names,
            )
            _finalise_numeric_result(result)
            continue

        # Phase 7.2: backdoor failed — try front-door when ``given`` is
        # empty (multi-mediator + conditioning isn't supported in the
        # front-door formula yet; mirrors the identification layer).
        front = None
        if not given_atoms:
            front = structural_solver.front_door_sets(
                graph, x_atom, y_atom, bidirected=bidirected or None,
            )
        if not front:
            # Phase 7.G: general-ID (c-factor) plug-in — the crown-jewel
            # non-parametric identification made numeric. Tried BEFORE IV
            # because a c-factor estimand is assumption-free, whereas the
            # IV point estimate needs monotonicity / effect homogeneity.
            # When do(X) is non-parametrically point-identified (e.g. the
            # napkin) this is the honest answer; only when it is NOT (a
            # genuine hedge) do we fall through to the under-assumption IV.
            if _try_general_id_estimate(
                q_stmt, result, contract, graph, bidirected,
                x_atom=x_atom, y_atom=y_atom, given_atoms=given_atoms,
                random_state=random_state, ci_bootstrap=ci_bootstrap,
                cluster=cluster,
            ):
                continue
            # Phase 7.3: try IV when NOT non-parametrically identified.
            iv_candidates = structural_solver.iv_sets(
                graph, x_atom, y_atom, bidirected=bidirected or None,
            )
            if not iv_candidates:
                # No strategy — 7.4 (mediation) remains. Skip for now.
                continue

            chosen_iv = iv_candidates[0]  # already sorted by |W| asc
            try:
                iv_estimate = estimate_iv_ate(
                    contract.data,
                    treatment=x_atom.predicate,
                    outcome=y_atom.predicate,
                    instrument=chosen_iv.instrument.predicate,
                    conditioning=tuple(
                        a.predicate for a in chosen_iv.conditioning
                    ),
                    ci_bootstrap=ci_bootstrap,
                    random_state=random_state,
                    cluster=cluster,
                )
            except (ValueError, NotImplementedError):
                # e.g. Wald denom is zero on this data, or the chosen
                # candidate's (Z, W) shape isn't supported in v1.
                continue

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
            result["numeric_estimate"] = iv_numeric_dict
            _attach_bootstrap_meta(result["numeric_estimate"], cluster)
            _attach_precision_budget(result["numeric_estimate"])
            result["derivation"] = _build_iv_numeric_derivation_dict(
                graph=graph,
                x=x_atom, y=y_atom,
                instrument=chosen_iv.instrument,
                conditioning=chosen_iv.conditioning,
                estimate=iv_estimate,
            )
            _attach_e_value_if_binary(
                result, contract,
                outcome=y_atom.predicate, treatment=x_atom.predicate,
            )
            _attach_weak_iv_warning_if_low_f(result, iv_estimate)
            _finalise_numeric_result(result)
            continue

        import networkx as nx
        chosen_front = min(front, key=len)
        topo_mediators = tuple(
            n for n in nx.topological_sort(graph) if n in chosen_front
        )
        mediator_names = tuple(a.predicate for a in topo_mediators)

        try:
            fd_estimate = estimate_frontdoor_ate(
                contract.data,
                treatment=x_atom.predicate,
                outcome=y_atom.predicate,
                mediators=mediator_names,
                ci_bootstrap=ci_bootstrap,
                random_state=random_state,
                model=model,  # type: ignore[arg-type]
                cluster=cluster,
            )
        except NotImplementedError:
            # e.g. continuous mediator in the current v1 restriction —
            # leave the result unchanged for now.
            continue

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
        _attach_bootstrap_meta(result["numeric_estimate"], cluster)
        _attach_precision_budget(result["numeric_estimate"])

        result["derivation"] = _build_frontdoor_numeric_derivation_dict(
            graph=graph,
            x=x_atom, y=y_atom,
            mediators=topo_mediators,
            estimate=fd_estimate,
        )
        _attach_e_value_if_binary(
            result, contract,
            outcome=y_atom.predicate, treatment=x_atom.predicate,
        )
        _finalise_numeric_result(result)


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
    from .dose_response import EstimatorFailure

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
                iv_ext = (result.get("extensions") or {}).get("iv_identification")
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
        except (EstimatorFailure, ValueError, NotImplementedError):
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


def _try_general_id_estimate(
    q_stmt, result: dict, contract, graph, bidirected, *,
    x_atom, y_atom, given_atoms, random_state: int,
    ci_bootstrap: int = 500, cluster: str | None = None,
) -> bool:
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
    from .dose_response import EstimatorFailure
    from .general_id import estimate_general_id_ate

    # v1 scope: unconditional effect only (IDC plug-in deferred).
    if given_atoms:
        return False
    df = contract.data
    if x_atom.predicate not in df.columns or y_atom.predicate not in df.columns:
        return False

    try:
        estimate = estimate_general_id_ate(
            df, graph=graph, bidirected=bidirected,
            treatment_atom=x_atom, outcome_atom=y_atom,
            ci_bootstrap=ci_bootstrap, random_state=random_state,
            cluster=cluster if (cluster is None or cluster in df.columns) else None,
        )
    except (EstimatorFailure, ValueError, NotImplementedError):
        # Not (non-parametrically) c-factor identified here, out of the
        # plug-in's binary scope, or a positivity refusal — leave the
        # result untouched and fall through to the IV escalation.
        return False

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
    _attach_bootstrap_meta(result["numeric_estimate"], cluster)
    _attach_precision_budget(result["numeric_estimate"])

    from ..output.result_orchestrator import (
        build_assumption_ledger,
        build_mechanism_audit,
    )
    ext = result.setdefault("extensions", {})
    ext["mechanism_audit"] = build_mechanism_audit(
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
        ext["assumption_ledger"] = ledger

    result["derivation"] = _build_general_id_numeric_derivation_dict(
        graph=graph, x=x_atom, y=y_atom, estimate=estimate,
    )
    _attach_e_value_if_binary(
        result, contract,
        outcome=y_atom.predicate, treatment=x_atom.predicate,
    )
    _finalise_numeric_result(result)
    return True


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
) -> bool:
    """Evaluate an ID*/IDC*-identified counterfactual conjunction on data by
    the non-parametric plug-in (the counterfactual analogue of
    ``_try_general_id_estimate``).

    Returns True only when it ATTACHES a plug-in numeric estimate. On any
    refusal — not identifiable, UNDEFINED conditioning event, or the data
    can't support the estimand (positivity) — it returns False and touches
    nothing, so the structural (identifiability) answer stays primary."""
    from ..runtime.ctf_identify import CtfEvent
    from .ctf_conjunction import estimate_ctf_conjunction_prob
    from .dose_response import EstimatorFailure

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
    except (EstimatorFailure, ValueError, NotImplementedError):
        # Not identifiable, UNDEFINED, or a positivity refusal — leave the
        # structural result untouched.
        return False

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
    ext["mechanism_audit"] = build_mechanism_audit(
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
        ext["assumption_ledger"] = ledger

    result["derivation"] = _build_ctf_conjunction_numeric_derivation_dict(
        graph=graph, estimate=estimate,
    )
    _finalise_numeric_result(result)
    return True


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
) -> bool:
    """Recover the proximal ATE on data by Miao's discrete formula (5).

    Returns True only when it ATTACHES a numeric estimate. On any refusal —
    not identifiable, proxy-cardinality mismatch, a singular measurement
    channel (rank), or an empty stratum (positivity) — it returns False and
    touches nothing, so the identifiability answer stays primary."""
    from .proximal import estimate_proximal_ate
    from .dose_response import EstimatorFailure

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
    except (EstimatorFailure, ValueError, NotImplementedError):
        return False

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
    ext["mechanism_audit"] = build_mechanism_audit(
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
        ext["assumption_ledger"] = ledger

    result["derivation"] = _build_proximal_numeric_derivation_dict(
        graph=graph, estimate=estimate,
    )
    _finalise_numeric_result(result)
    return True


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


def _try_mediation_estimate(
    q_stmt, result: dict, contract, graph, bidirected, *, random_state: int,
    ci_bootstrap: int = 500, cluster: str | None = None,
) -> None:
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

    extensions = result.get("extensions") or {}
    decomp = extensions.get("mediation_decomposition")
    if decomp is None or decomp.get("strategy") != "nde_nie":
        return

    nde_nie_block = decomp.get("nde_nie", {})
    if not nde_nie_block.get("identifiable"):
        return
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
        return

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
    except (ValueError, NotImplementedError):
        return

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

    from .dose_response import EstimatorFailure
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
    except (EstimatorFailure, ValueError, KeyError, np.linalg.LinAlgError):
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
    ne["four_way_ratio"] = block


def _try_joint_estimate(
    q_stmt, result: dict, contract, graph, bidirected,
    *, random_state: int, ci_bootstrap: int, model: str,
    cluster: str | None = None,
) -> None:
    """Joint multi-treatment effect estimate: do(A=a, B=b, ...).

    Re-derives the joint (treatment-set) back-door adjustment set, fits
    the joint g-formula (outcome regression with the A:B interaction),
    and attaches a ``numeric_estimate`` with a ``joint_effect`` block AND
    an ``interaction`` block (additive scale). Mirrors the backdoor
    numeric path: status flips to numerically_solved with an independent
    joint derivation the verifier re-checks.

    Silent no-op (leaves the structural result untouched) when:
    - bidirected (latent) edges are present — joint ADMG is out of scope;
    - no joint adjustment set exists;
    - a treatment is non-binary (v1 scope);
    - the joint estimator refuses (EstimatorFailure → estimator_failure
      block, mirroring transport / dose-response).
    """
    from ..runtime import structural_solver
    from .dose_response import EstimatorFailure
    from .joint import estimate_joint_effect

    q = q_stmt.query
    x_atom = q.intervention.atom
    y_atom = q.target.atom
    extra_atoms = tuple(iv.atom for iv in q.extra_interventions)
    treatment_atoms = (x_atom, *extra_atoms)
    given_atoms = tuple(g.atom for g in q.given)

    # v1 scope: exactly two binary treatments, no mediator / transport.
    if q.mediator is not None or q.target_population is not None:
        return
    if len(set(treatment_atoms)) != 2:
        return

    try:
        joint_sets = structural_solver.minimal_adjustment_sets_joint(
            graph, treatment_atoms, y_atom,
            given=given_atoms, bidirected=bidirected or None,
        )
    except NotImplementedError:
        return
    if not joint_sets:
        return

    chosen = min(joint_sets, key=len)
    adjustment_names = tuple(a.predicate for a in _topo_order(graph, chosen))
    treatment_names = tuple(t.predicate for t in treatment_atoms)
    outcome_name = y_atom.predicate

    df = contract.data
    if any(t not in df.columns for t in treatment_names):
        return
    if outcome_name not in df.columns:
        return
    if not all(_is_binary_treatment(df, t) for t in treatment_names):
        return

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
        result["estimator_failure"] = {
            "estimator": "joint_backdoor",
            "failure_type": exc.failure_type,
            "reason": str(exc),
        }
        return
    except (ValueError, NotImplementedError):
        return

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
        "interaction": {
            "point": estimate.interaction_point,
            "ci_lower": estimate.interaction_ci_lower,
            "ci_upper": estimate.interaction_ci_upper,
            "scale": "difference",
        },
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
                "interaction_point": estimate.interaction_point,
                "interaction_ci_lower": estimate.interaction_ci_lower,
                "interaction_ci_upper": estimate.interaction_ci_upper,
                "ci_level": estimate.ci_level,
            },
            output=StructuralResult(value=True),
            step_id="s2",
        ),
    )
    return derivation_to_dict(steps)


def _prepend_proportion_mediated_headline(
    result: dict, med_estimate,
) -> None:
    """Surface NIE / TE as a headline at the top of result.explanation.

    The user-side question shape that drives this is "X 占多少比例" (how
    much of the effect goes through the mediator). The number lives in
    decomposition.proportion_mediated; without a headline the renderer
    has to construct it from raw NIE/TE/CI fields. Prepending it here
    gives the renderer a deterministic single-line answer to quote.
    """
    point = med_estimate.proportion_mediated_point
    lo = med_estimate.proportion_mediated_ci_lower
    hi = med_estimate.proportion_mediated_ci_upper
    if point is None:
        return
    headline = (
        f"中介比例 (NIE/TE): {point * 100:.1f}% "
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

    if is_binary:
        treated_mask = df[treatment].to_numpy().astype(bool)
        if treated_mask.all() or (~treated_mask).all():
            return  # no untreated arm — can't compute baseline rate
        baseline_rate = float(df.loc[~treated_mask, outcome].mean())
        e_result = e_value_from_ate_binary(
            ate=ate, baseline_rate=baseline_rate, ci_bound=ci_bound,
        )
    elif is_numeric:
        outcome_sd = float(outcome_series.std(ddof=1))
        if outcome_sd <= 0 or not (outcome_sd == outcome_sd):  # NaN-safe
            return
        e_result = e_value_from_ate_continuous(
            ate=ate, outcome_sd=outcome_sd, ci_bound=ci_bound,
        )
    else:
        return  # categorical / object outcomes — out of scope this iter

    estimate["sensitivity_analysis"] = {
        "e_value": e_result.e_value,
        "e_value_ci_bound": e_result.e_value_ci_bound,
        "risk_ratio": e_result.risk_ratio,
        "baseline_rate": e_result.baseline_rate,
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
) -> None:
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

    transport_block = (result.get("extensions") or {}).get("transport_identification")
    if not isinstance(transport_block, dict):
        return
    adjustment_atoms = transport_block.get("adjustment_set") or []
    if not adjustment_atoms:
        return
    adjustment_names = tuple(
        a.get("predicate") for a in adjustment_atoms if isinstance(a, dict)
    )
    if not all(adjustment_names) or len(adjustment_names) != 1:
        # v1 single-Z scope; multi-Z is §T9.3+ follow-up.
        return

    program_extensions = _extract_program_extensions(program)
    target_marginal = program_extensions.get("target_marginal")
    if not isinstance(target_marginal, dict):
        return
    target_marginal = _coerce_target_marginal_keys(target_marginal)

    treatment = q_stmt.query.intervention.atom.predicate
    outcome = q_stmt.query.target.atom.predicate

    df = contract.data
    if treatment not in df.columns or outcome not in df.columns:
        return
    if adjustment_names[0] not in df.columns:
        return

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
    except (ValueError, NotImplementedError) as exc:
        # Surface the refusal as a structured estimator_failure instead of
        # silently dropping it. The common case is a positivity violation
        # — the target marginal demands a stratum the source has zero
        # support for — which is exactly the "pathological data without
        # disclosure" failure VISION forbids. Mirrors the dose-response
        # path: the consumer must tell "refused for a good reason" from
        # "didn't try".
        msg = str(exc)
        failure_type = (
            "not_implemented"
            if isinstance(exc, NotImplementedError)
            else "overlap_insufficient"
            if "no observations" in msg
            else "invalid_input"
        )
        result["estimator_failure"] = {
            "estimator": "transport_post_stratification",
            "failure_type": failure_type,
            "reason": msg,
        }
        return

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

    gap_entry = {
        "kind": "weak_iv_instrument",
        "severity": "informational",
        "blocks": "interpretation",
        "description": (
            f"First-stage F = {f_stat:.2f} for instrument "
            f"`{iv_estimate.instrument}` falls below the Stock-Yogo "
            f"(2005) threshold of {WEAK_IV_F_THRESHOLD:.0f}. "
            "The IV estimate's bias toward OLS scales with 1/F, "
            "and standard 2SLS / Wald asymptotic CIs underestimate "
            "uncertainty when the first stage is weak. Treat the "
            "point estimate as a rough guide, not a tight identification."
        ),
        "required_data": None,
        "alternative_paths": [
            "find a stronger instrument (higher first-stage partial "
            "correlation with treatment after conditioning)",
            "report the LIML or Anderson-Rubin CI instead of 2SLS — "
            "they are valid under weak-instrument asymptotics",
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
        "标准 CI 不可靠"
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


def _summary_from_gap_dicts(gaps: list[dict]) -> str:
    """Mirror ``output.data_gap_report._make_summary`` on already-sorted
    serialized gaps. Tier is ``point`` here, so no interval/none lead
    clause applies — just the most-blocking gap's description."""
    if not gaps:
        return ""
    head = gaps[0]
    blocking = sum(1 for g in gaps if g.get("severity") == "blocking")
    base = head.get("description", "")
    if blocking > 1:
        return f"{base}（共 {blocking} 个 blocking 缺口）"
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


def _attach_doubly_robust_estimate(
    *, result, contract, graph, x, y, adjustment, adjustment_names, given,
    estimator, random_state, ci_bootstrap, model, cluster,
):
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
        result["estimator_failure"] = {
            "estimator": estimator,
            "failure_type": exc.failure_type,
            "reason": str(exc),
        }
        return

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
    ext["mechanism_audit"] = build_mechanism_audit(
        target=est.outcome, form=est.form, method=est.method,
        assumption=est.model_assumption, provenance="default",
    )
    ledger = build_assumption_ledger(
        result, identification_specs=est.identification_assumptions,
    )
    if ledger is not None:
        ext["assumption_ledger"] = ledger

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
            },
            output=StructuralResult(value=True),
            step_id="s2",
        ),
    )
    return derivation_to_dict(steps)


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
) -> bool:
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
        return True
    except EstimatorFailure as exc:
        # Slice c: structured failures with a typed cause and the
        # diagnostic detail block the estimator collected.
        block = {
            "estimator": estimator_label,
            "failure_type": exc.failure_type,
            "reason": str(exc),
        }
        if exc.details:
            block["details"] = exc.details
        result["estimator_failure"] = block
        return True
    except (ValueError, RuntimeError) as exc:
        # Fallback: untyped failure. Same shape, failure_type='unknown'.
        result["estimator_failure"] = {
            "estimator": estimator_label,
            "failure_type": "unknown",
            "reason": str(exc),
        }
        return True

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
    ext["mechanism_audit"] = build_mechanism_audit(
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
        ext["assumption_ledger"] = ledger
    _attach_precision_budget_curve(result["numeric_estimate"])
    result["derivation"] = _build_numeric_derivation_dict(
        graph=graph, x=x, y=y, adjustment=chosen, given=frozenset(given),
        estimate=_LinearDMLAdapter(est),
    )
    _finalise_numeric_result(result)
    return True


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
