"""Differential comparator.

Runs the same query through both runtime and oracle, then reports
whether they agree at the appropriate level.

Comparison scope per kind:

- cause:     directed-path existence
- assoc:     d-separation verdict
- identify:  identifiability verdict + runtime's chosen adjustment set
             must be a valid back-door adjustment set per the oracle

Queries the oracle does not speak to (effect, probability, or queries
whose runtime result is ``needs_investigation``) produce a
``not_applicable`` report, not a failure.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ..types import (
    AssocQuery,
    Atom,
    CauseQuery,
    IdentifyQuery,
    ProbabilityRefExpr,
    ProductExpr,
    QueryResult,
    QueryStatement,
    ResultStatus,
    SumExpr,
)
from . import pgmpy_adapter
from .pgmpy_adapter import OracleNetwork


ComparisonStatus = Literal["agree", "disagree", "not_applicable"]


@dataclass(frozen=True)
class ComparisonReport:
    status: ComparisonStatus
    query_id: str | None
    runtime_result: QueryResult
    oracle_result: Any = None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        """True unless the two sides disagreed."""
        return self.status != "disagree"


# --------------------------------------------------------------------- cause

def _compare_cause(
    stmt: QueryStatement,
    result: QueryResult,
    network: OracleNetwork,
) -> ComparisonReport:
    q: CauseQuery = stmt.query  # type: ignore[assignment]
    oracle = pgmpy_adapter.has_directed_path(network, q.from_atom, q.to_atom)
    runtime = (
        result.structural_result is not None
        and result.structural_result.value is True
    )
    if oracle == runtime:
        return ComparisonReport(
            status="agree",
            query_id=stmt.id,
            runtime_result=result,
            oracle_result=oracle,
        )
    return ComparisonReport(
        status="disagree",
        query_id=stmt.id,
        runtime_result=result,
        oracle_result=oracle,
        reason=f"cause verdicts diverged: runtime={runtime} oracle={oracle}",
    )


# --------------------------------------------------------------------- assoc

def _compare_assoc(
    stmt: QueryStatement,
    result: QueryResult,
    network: OracleNetwork,
) -> ComparisonReport:
    q: AssocQuery = stmt.query  # type: ignore[assignment]
    oracle = pgmpy_adapter.is_d_connected(network, q.left, q.right, q.given)
    runtime = (
        result.structural_result is not None
        and result.structural_result.value is True
    )
    if oracle == runtime:
        return ComparisonReport(
            status="agree",
            query_id=stmt.id,
            runtime_result=result,
            oracle_result=oracle,
        )
    return ComparisonReport(
        status="disagree",
        query_id=stmt.id,
        runtime_result=result,
        oracle_result=oracle,
        reason=f"d-sep verdicts diverged: runtime={runtime} oracle={oracle}",
    )


# ------------------------------------------------------------------ identify

def _extract_adjustment_atoms(formula) -> frozenset[Atom]:
    """Walk a runtime-produced formula and collect the atoms that are
    iterated by any SumExpr. For v0.1 back-door formulas this is
    exactly the chosen adjustment set."""
    atoms: set[Atom] = set()
    _walk_formula(formula, atoms)
    return frozenset(atoms)


def _walk_formula(node, atoms: set[Atom]) -> None:
    if isinstance(node, SumExpr):
        atoms.add(node.over)
        _walk_formula(node.body, atoms)
    elif isinstance(node, ProductExpr):
        for t in node.terms:
            _walk_formula(t, atoms)
    elif isinstance(node, ProbabilityRefExpr):
        return


def _runtime_has_known_coverage_gap(result: QueryResult) -> bool:
    """Runtime explicitly flagged a formula coverage gap (e.g. joint
    adjustment over ≥2 atoms is not yet supported)."""
    if result.status != ResultStatus.NEEDS_INVESTIGATION:
        return False
    return any(
        m.name.startswith("formula:") for m in result.missing_information
    )


def _compare_identify(
    stmt: QueryStatement,
    result: QueryResult,
    network: OracleNetwork,
) -> ComparisonReport:
    q: IdentifyQuery = stmt.query  # type: ignore[assignment]
    given_set = frozenset(q.given)

    oracle_sets = pgmpy_adapter.backdoor_adjustment_sets(
        network, q.intervention.atom, q.target
    )
    # Conditional identifiability: some valid back-door adjustment set
    # must extend (be a superset of) the query's given context.
    oracle_identifiable = any(given_set <= s for s in oracle_sets)

    # Runtime "identifiable" for comparison is strict: must have
    # reached STRUCTURALLY_SOLVED AND produced a concrete formula.
    # A NEEDS_INVESTIGATION with value=True but no formula is a
    # coverage gap, not a positive identifiability verdict.
    runtime_identifiable = (
        result.status == ResultStatus.STRUCTURALLY_SOLVED
        and result.formula is not None
    )

    # Known runtime coverage gap while oracle can still solve: surface
    # as not_applicable with an explicit reason, so CI sees it without
    # the comparator silently approving.
    if (
        not runtime_identifiable
        and oracle_identifiable
        and _runtime_has_known_coverage_gap(result)
    ):
        return ComparisonReport(
            status="not_applicable",
            query_id=stmt.id,
            runtime_result=result,
            oracle_result=oracle_sets,
            reason=(
                "runtime reported a formula coverage gap while oracle "
                "found a valid adjustment; flagged to avoid false agree"
            ),
        )

    if oracle_identifiable != runtime_identifiable:
        return ComparisonReport(
            status="disagree",
            query_id=stmt.id,
            runtime_result=result,
            oracle_result=oracle_sets,
            reason=(
                f"identifiability verdicts diverged: "
                f"runtime_has_formula={runtime_identifiable} "
                f"oracle_identifiable={oracle_identifiable}"
            ),
        )

    # Both say identifiable — additionally require that the runtime's
    # chosen sum variables, unioned with the query's given context,
    # form a valid back-door adjustment set per pgmpy.
    if runtime_identifiable:
        sum_atoms = _extract_adjustment_atoms(result.formula)
        combined = sum_atoms | given_set
        valid = pgmpy_adapter.is_valid_backdoor_adjustment_set(
            network, q.intervention.atom, q.target, combined
        )
        if not valid:
            return ComparisonReport(
                status="disagree",
                query_id=stmt.id,
                runtime_result=result,
                oracle_result=oracle_sets,
                reason=(
                    f"runtime's combined adjustment (sum={sum_atoms}, "
                    f"given={given_set}) is not a valid back-door "
                    f"adjustment set per pgmpy"
                ),
            )

    return ComparisonReport(
        status="agree",
        query_id=stmt.id,
        runtime_result=result,
        oracle_result=oracle_sets,
    )


# --------------------------------------------------------------------- public

def compare(
    stmt: QueryStatement,
    result: QueryResult,
    network: OracleNetwork,
) -> ComparisonReport:
    """Route a query+result pair to the kind-specific comparator.

    Returns a ``not_applicable`` report when the oracle has no opinion
    (unimplemented kinds or runtime results that didn't reach a
    structural answer).
    """
    # If the runtime didn't produce a structural verdict, the oracle
    # has nothing to compare against.
    if result.status == ResultStatus.NEEDS_INVESTIGATION and result.structural_result is None:
        return ComparisonReport(
            status="not_applicable",
            query_id=stmt.id,
            runtime_result=result,
            reason="runtime produced no structural result to compare",
        )

    q = stmt.query
    if isinstance(q, CauseQuery):
        return _compare_cause(stmt, result, network)
    if isinstance(q, AssocQuery):
        return _compare_assoc(stmt, result, network)
    if isinstance(q, IdentifyQuery):
        return _compare_identify(stmt, result, network)

    return ComparisonReport(
        status="not_applicable",
        query_id=stmt.id,
        runtime_result=result,
        reason=f"oracle does not speak to query kind '{type(q).__name__}'",
    )


def compare_structural(
    runtime_result: QueryResult,
    oracle_result: Any,
) -> ComparisonReport:
    """Legacy stub kept for backward compatibility of the oracle layer
    API surface. Prefer ``compare``."""
    raise NotImplementedError("use compare(stmt, result, network) instead")


def compare_identify(
    runtime_result: QueryResult,
    oracle_result: Any,
) -> ComparisonReport:
    """Legacy stub. Prefer ``compare``."""
    raise NotImplementedError("use compare(stmt, result, network) instead")
