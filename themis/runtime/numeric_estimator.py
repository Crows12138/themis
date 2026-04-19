"""Numeric estimation of probabilities and formulas.

Wiring (v0.1, after slice 6):

- ``Theta`` is a real parameter store: dict keyed by ``ProbabilityKey``
  plus per-atom value domains. The domains are populated by
  ``theta_builder`` from every literal value observed in the program's
  ``ValuedAtom`` positions (probability target / given, observation
  value); atoms that never appear in such positions fall back to the
  boolean default.
- ``estimate_formula`` recursively evaluates ``constant`` /
  ``probability_ref`` / ``product`` / ``sum`` nodes, substituting
  ``VarRef`` names bound by enclosing sums.
- ``InsufficientTheta`` is raised with the precise lookup key that
  failed, so the scheduler can build a ``MissingItem`` that points to
  the exact conditional the caller must still provide.

Behaviour in context:

- ``scheduler._dispatch_effect`` and ``_dispatch_probability`` run the
  evaluator against the Theta built from the program's probability
  statements. When every referenced conditional is present, the query
  resolves to ``NUMERICALLY_SOLVED``; otherwise it surfaces as
  ``NEEDS_INVESTIGATION`` with structured missing-parameter details.
- Query-bound target values (e.g. the ``Y`` in ``P(Y|do(X))``) are
  handled by the effect/probability query shapes: the query supplies a
  concrete ``target.value`` and the builder propagates it into the
  formula. A formula reaching the evaluator with a query-bound ``None``
  still raises ``InsufficientTheta`` — that path is defensive, not the
  documented usage.

See ``v0_1_scope.md`` for the full list of what the numeric layer
does and does not cover in v0.1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ..types import (
    Atom,
    ConstantExpr,
    FormulaExpr,
    ProbabilityRefExpr,
    ProductExpr,
    SumExpr,
    ValuedAtom,
    ValueExpr,
    VarRef,
)


AtomValue = bool | int | float | str


@dataclass(frozen=True)
class ProbabilityKey:
    """Canonical key for a conditional probability lookup in Theta.

    The target and given values must be concrete literals. VarRefs
    and None-valued atoms must be substituted away before building
    a key.
    """

    target_atom: Atom
    target_value: AtomValue
    given: frozenset[tuple[Atom, AtomValue]]


@dataclass
class Theta:
    """Model parameter store.

    entries: maps canonical ProbabilityKey to a conditional probability.
    domains: per-atom allowed values; defaults to boolean when absent.
    """

    entries: dict[ProbabilityKey, float] = field(default_factory=dict)
    domains: dict[Atom, tuple[AtomValue, ...]] = field(default_factory=dict)

    def get(self, key: ProbabilityKey) -> float | None:
        return self.entries.get(key)

    def domain_of(self, atom: Atom) -> tuple[AtomValue, ...]:
        """Return the declared value domain for ``atom``, defaulting to
        boolean when undeclared."""
        return self.domains.get(atom, (True, False))


class InsufficientTheta(Exception):
    """Raised when the formula evaluator needs a probability lookup
    that is not in Theta.

    The ``missing_key`` attribute carries the exact ProbabilityKey so
    the caller can report precisely which parameter must be supplied.
    """

    def __init__(self, missing_key: ProbabilityKey | None, reason: str):
        super().__init__(reason)
        self.missing_key = missing_key
        self.reason = reason


def _resolve(value: ValueExpr | None, subs: Mapping[str, AtomValue]) -> AtomValue:
    if value is None:
        raise InsufficientTheta(
            None,
            "formula contains a query-bound atom with no concrete value; "
            "v0.1 numeric layer cannot resolve it without an externally "
            "supplied substitution",
        )
    if isinstance(value, VarRef):
        if value.name not in subs:
            # Formal well-formedness should prevent this; treat as
            # programmer error, not user-facing InsufficientTheta.
            raise ValueError(
                f"unbound VarRef '{value.name}' during evaluation; "
                f"the formula should have been rejected by validate_formula"
            )
        return subs[value.name]
    return value  # concrete literal


def _probability_ref_key(
    node: ProbabilityRefExpr,
    subs: Mapping[str, AtomValue],
) -> ProbabilityKey:
    target_value = _resolve(node.target.value, subs)
    given_pairs = frozenset(
        (va.atom, _resolve(va.value, subs)) for va in node.given
    )
    return ProbabilityKey(
        target_atom=node.target.atom,
        target_value=target_value,
        given=given_pairs,
    )


def _evaluate(
    expr: FormulaExpr,
    theta: Theta,
    subs: Mapping[str, AtomValue],
) -> float:
    if isinstance(expr, ConstantExpr):
        return float(expr.value)

    if isinstance(expr, ProbabilityRefExpr):
        key = _probability_ref_key(expr, subs)
        value = theta.get(key)
        if value is None:
            raise InsufficientTheta(
                key,
                f"Theta missing entry for P({key.target_atom.predicate}="
                f"{key.target_value} | {sorted((a.predicate, v) for a, v in key.given)})",
            )
        return value

    if isinstance(expr, ProductExpr):
        result = 1.0
        for term in expr.terms:
            result *= _evaluate(term, theta, subs)
        return result

    if isinstance(expr, SumExpr):
        total = 0.0
        for v in theta.domain_of(expr.over):
            new_subs = dict(subs)
            new_subs[expr.bind.name] = v
            total += _evaluate(expr.body, theta, new_subs)
        return total

    raise TypeError(f"unknown formula node: {type(expr).__name__}")


def estimate_formula(formula: FormulaExpr, theta: Theta) -> float:
    """Evaluate a formula AST to a numeric value using Theta.

    Raises ``InsufficientTheta`` with a structured missing-key payload
    if any conditional probability referenced by the formula is not
    present in Theta, or if the formula contains query-bound atoms
    whose concrete value has not been supplied.
    """
    return _evaluate(formula, theta, {})


def estimate_probability(
    target: ValuedAtom,
    given: tuple[ValuedAtom, ...],
    theta: Theta,
) -> float:
    """Convenience: evaluate a single conditional probability lookup."""
    expr = ProbabilityRefExpr(target=target, given=given)
    return estimate_formula(expr, theta)


# --------------------------------------------------------------------- theta

def empty_theta() -> Theta:
    """Return a fresh empty Theta. v0.1 uses this because probability
    statements cannot yet be compiled into Theta entries (their
    target/given atoms have no values in the current schema)."""
    return Theta()
