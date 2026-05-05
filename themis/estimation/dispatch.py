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

from typing import Any

from .contract import DataContract, validate_data


def estimate_program(
    program: dict | str | bytes,
    data: Any,
    *,
    random_state: int = 42,
    ci_bootstrap: int = 500,
    model: str = "auto",
) -> dict:
    """See ``themis.estimate`` for the full contract."""
    from ..kernel import run as _run

    identification_output = _run(program)

    required_columns = _collect_required_columns(program)
    if not required_columns:
        return identification_output

    contract = validate_data(data, required_columns=required_columns)

    for result in identification_output.get("results", []):
        result.setdefault("estimation_context", {}).update({
            "data_hash": contract.data_hash,
            "sample_size": contract.sample_size,
            "data_contract_warnings": list(contract.warnings),
            "random_state": random_state,
            "ci_bootstrap": ci_bootstrap,
            "model_preference": model,
        })

    _estimate_effect_queries(
        program, identification_output, contract,
        random_state=random_state, ci_bootstrap=ci_bootstrap, model=model,
    )

    return identification_output


def _estimate_effect_queries(
    program: dict | str | bytes,
    output: dict,
    contract: DataContract,
    *,
    random_state: int,
    ci_bootstrap: int,
    model: str,
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
        dose_response_triggered = q_stmt.id in dose_response_query_ids
        # Phase 7.4: mediation queries route to the Imai-via-statsmodels
        # estimator, gated on the identification layer's strategy result.
        if q_stmt.query.mediator is not None:
            _try_mediation_estimate(
                q_stmt, result, contract, graph, bidirected,
                random_state=random_state,
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
            ):
                continue
            # Estimator unavailable / failed structurally — fall through
            # to the binary path so the user still gets *something*.
        if adjustment_sets:
            chosen = min(adjustment_sets, key=len)
            adjustment_names = tuple(a.predicate for a in _topo_order(graph, chosen))

            estimate = estimate_backdoor_ate(
                contract.data,
                treatment=x_atom.predicate,
                outcome=y_atom.predicate,
                adjustment=adjustment_names,
                ci_bootstrap=ci_bootstrap,
                random_state=random_state,
                model=model,  # type: ignore[arg-type]
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
            # Phase 7.3: try IV as the third fallback.
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
                )
            except (ValueError, NotImplementedError):
                # e.g. Wald denom is zero on this data, or the chosen
                # candidate's (Z, W) shape isn't supported in v1.
                continue

            result["numeric_estimate"] = {
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


def _try_mediation_estimate(
    q_stmt, result: dict, contract, graph, bidirected, *, random_state: int,
) -> None:
    """Phase 7.4 — attach a mediation numeric estimate when the
    identification layer has cleared NDE/NIE for the requested mediator.

    Reads ``result.extensions.mediation_decomposition`` to decide
    whether to fit. Only the ``nde_nie`` strategy is wired in 7.4 —
    CDE numeric estimation is deferred (the reference mediator value
    isn't expressible cleanly in the statsmodels Mediation API).
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


def _attach_e_value_if_binary(
    result: dict, contract, outcome: str, treatment: str,
) -> None:
    """Phase 8.2: compute the E-value sensitivity for the result's
    numeric estimate when the outcome is binary, and attach it under
    ``numeric_estimate.sensitivity_analysis``.

    Skips quietly for non-binary outcomes (continuous Y has no
    risk-ratio scale; future work could attach a different sensitivity
    statistic). Mediation results carry a ``decomposition`` block
    rather than a flat ``point`` — for those we attach the E-value to
    the TE component (the most directly comparable summary).
    """
    import pandas as pd
    from .sensitivity import e_value_from_ate_binary

    estimate = result.get("numeric_estimate")
    if estimate is None:
        return

    df = contract.data
    if outcome not in df.columns:
        return
    if not pd.api.types.is_bool_dtype(df[outcome]):
        return

    treated_mask = df[treatment].to_numpy().astype(bool)
    if treated_mask.all() or (~treated_mask).all():
        return  # no untreated arm — can't compute baseline rate
    baseline_rate = float(df.loc[~treated_mask, outcome].mean())

    if "decomposition" in estimate:
        # Mediation: use TE for the E-value summary.
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

    e_result = e_value_from_ate_binary(
        ate=ate, baseline_rate=baseline_rate, ci_bound=ci_bound,
    )
    estimate["sensitivity_analysis"] = {
        "e_value": e_result.e_value,
        "e_value_ci_bound": e_result.e_value_ci_bound,
        "risk_ratio": e_result.risk_ratio,
        "baseline_rate": e_result.baseline_rate,
        "note": e_result.note,
    }


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


def _finalise_numeric_result(result: dict) -> None:
    """Flip result status to numerically_solved, set a truthy
    structural_result, and drop stale missing_information entries.

    Shared between backdoor (7.1) and front-door (7.2) numeric paths.
    """
    result["status"] = "numerically_solved"
    result["structural_result"] = {"value": True}
    result.pop("missing_information", None)


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
    for stmt in statements:
        kind = stmt.get("kind")
        if kind == "variable":
            pred = stmt.get("predicate")
            if isinstance(pred, str):
                columns.add(pred)
    return columns


def _ensure_dict(program: dict | str | bytes) -> dict:
    import json
    if isinstance(program, (str, bytes)):
        return json.loads(program)
    return program
