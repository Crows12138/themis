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

    ast = _ensure_dict(program)
    ast = validate_ast(ast)
    prog = validate_program(ast)
    ground_statements = instantiate(prog)
    graph = project(ground_statements)
    bidirected = structural_solver.bidirected_from_ground(ground_statements)

    for q_stmt, result in _pair_effect_queries(prog, output):
        if q_stmt is None:
            continue
        # Skip mediation queries — they have their own decomposition
        # path that Phase 7.4 will implement.
        if q_stmt.query.mediator is not None:
            continue

        x_atom = q_stmt.query.intervention.atom
        y_atom = q_stmt.query.target.atom
        given_atoms = tuple(g.atom for g in q_stmt.query.given)

        adjustment_sets = structural_solver.minimal_adjustment_sets(
            graph, x_atom, y_atom,
            given=given_atoms,
            bidirected=bidirected or None,
        )
        if not adjustment_sets:
            # No backdoor strategy available — 7.2/7.3/7.4 will catch
            # front-door / IV / mediation cases. Skip for 7.1.
            continue

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
        # Flip status — numerical answer supersedes "needs_investigation"
        # for theta, which is no longer needed once we have data.
        result["status"] = "numerically_solved"


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
