"""Phase 7.1 S.N.1 skeleton — estimate dispatch entry point.

This is the intentionally-thin orchestrator ``themis.estimate`` calls.
For the 7.1 slice it only:

1. Runs the identification pipeline via ``themis.run`` to get
   adjustment strategies for each query.
2. For any effect query resolved via backdoor with data provided,
   hands off to ``backdoor.estimate_backdoor_ate`` (stub until S.N.2).
3. Validates the data contract once up front — the same normalised
   DataFrame is reused across all queries to avoid re-hashing.

Kept deliberately minimal so later slices (7.2 / 7.3 / 7.4) can plug
in their estimators without touching the public surface.
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
    # Import the kernel lazily so ``import themis`` remains cheap for
    # callers that don't reach the estimation path.
    from ..kernel import run as _run

    identification_output = _run(program)

    required_columns = _collect_required_columns(program)
    if not required_columns:
        # No predicates to validate — program is degenerate; surface
        # identification output unchanged.
        return identification_output

    contract = validate_data(data, required_columns=required_columns)

    # Attach data contract metadata to each result so callers can see
    # what the estimator ran on even if no estimator fires in this slice.
    for result in identification_output.get("results", []):
        result.setdefault("estimation_context", {}).update({
            "data_hash": contract.data_hash,
            "sample_size": contract.sample_size,
            "data_contract_warnings": list(contract.warnings),
            "random_state": random_state,
            "ci_bootstrap": ci_bootstrap,
            "model_preference": model,
        })

    # S.N.2 will branch here based on result['query_kind'] and
    # result['extensions'] (identify strategy) to hand off to the right
    # estimator. For now the skeleton returns the identification output
    # with the data contract attached.
    return identification_output


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
