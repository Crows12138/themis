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


def format_probability_key(key: ProbabilityKey) -> str:
    """Render a ``ProbabilityKey`` as ``P(pred=value|pred1=v1,pred2=v2)``.

    Single canonical form shared by the user-facing surfaces that quote
    the key: ``InsufficientTheta.reason`` and the ``parameter:...`` name
    built by ``scheduler._missing_parameter_from_key``. Kept here because
    ``ProbabilityKey`` lives here; importing it from the scheduler would
    reverse the dependency.
    """
    given_pairs = sorted(
        key.given,
        key=lambda pair: (pair[0].predicate, str(pair[1])),
    )
    given_repr = ",".join(f"{a.predicate}={v}" for a, v in given_pairs)
    body = f"{key.target_atom.predicate}={key.target_value}"
    if given_repr:
        body = f"{body}|{given_repr}"
    return f"P({body})"


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
                f"Theta 中缺条目 {format_probability_key(key)}",
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


# ------------------------------------------------------------- key enumeration

def enumerate_keys(
    formula: FormulaExpr,
    theta: Theta,
) -> tuple[ProbabilityKey, ...]:
    """Enumerate every ``ProbabilityKey`` that ``estimate_formula`` would
    look up for this formula under the given Theta's value domains.

    Read-only twin of ``estimate_formula``: walks the same AST shape,
    expands ``SumExpr`` over ``theta.domain_of(over)`` identically, but
    collects keys instead of multiplying / summing values. Used by the
    confidence collector (RFC §3.1) to enumerate slots without trying
    to actually evaluate.

    Keys may repeat across sum branches; callers dedupe as needed.

    Raises ``InsufficientTheta`` only for VarRef resolution failures
    (formula malformed). For query-bound ``None`` values the enclosing
    iteration skips that branch silently — enumerate_keys is meant to
    survive partial formulas.
    """
    keys: list[ProbabilityKey] = []
    _collect_keys(formula, theta, {}, keys)
    return tuple(keys)


def _collect_keys(
    expr: FormulaExpr,
    theta: Theta,
    subs: Mapping[str, AtomValue],
    keys: list,
) -> None:
    if isinstance(expr, ConstantExpr):
        return
    if isinstance(expr, ProbabilityRefExpr):
        try:
            key = _probability_ref_key(expr, subs)
        except InsufficientTheta:
            # Query-bound None that was not supplied externally —
            # this is not a key we can enumerate. Skip silently.
            return
        keys.append(key)
        return
    if isinstance(expr, ProductExpr):
        for t in expr.terms:
            _collect_keys(t, theta, subs, keys)
        return
    if isinstance(expr, SumExpr):
        for v in theta.domain_of(expr.over):
            new_subs = dict(subs)
            new_subs[expr.bind.name] = v
            _collect_keys(expr.body, theta, new_subs, keys)
        return
    raise TypeError(f"unknown formula node: {type(expr).__name__}")


# --------------------------------------------------------------------- theta

def empty_theta() -> Theta:
    """Return a fresh empty Theta. v0.1 uses this because probability
    statements cannot yet be compiled into Theta entries (their
    target/given atoms have no values in the current schema)."""
    return Theta()


# --------------------------------------------------- iter 171: derivable check

def can_derive_via_marginalization(
    missing_key: ProbabilityKey,
    theta: Theta,
    *,
    extra_atoms: tuple[Atom, ...] = (),
) -> bool:
    """Iter 171 — foundation for iter 168's option (b) auto-marginalization.

    Check whether ``missing_key`` could be derived by marginalizing
    over additional atoms not in its conditioning set. For example,
    if ``missing_key`` is P(Y|X) and theta contains every
    P(Y|X, Z=v_z) for v_z ∈ domain(Z), the missing CPT can be
    derived as Σ_z P(Y|X, Z=z) · P(Z=z|X).

    This function only returns True when:
    - For some atom Z (in ``extra_atoms`` or scanning theta keys),
      every (target_atom, target_value, given ∪ {(Z, z)}) for z in
      domain(Z) has a theta entry, AND
    - Every P(Z=z|conditioning) needed for the inner factor exists
      in theta.

    Iter 171 is just the SCAN / detection. Iter 172+ will wire the
    actual marginalization into _evaluate so the kernel auto-derives
    instead of raising InsufficientTheta. Splitting detection from
    derivation lets iter 171 be a pure helper that's testable in
    isolation.

    Returns False on the safe path; iter 172+ flips False → True
    handling case-by-case.
    """
    target_atom = missing_key.target_atom
    target_value = missing_key.target_value
    base_given = missing_key.given

    # Try each extra_atom as the marginalization variable. Scan first
    # in extra_atoms, then in theta's known atoms (collected from
    # entry keys' atoms).
    candidates: list[Atom] = list(extra_atoms)
    seen_in_extra = set(extra_atoms)
    for key in theta.entries:
        for ga, _gv in key.given:
            if ga != target_atom and ga not in seen_in_extra:
                candidates.append(ga)
                seen_in_extra.add(ga)
        if (
            key.target_atom != target_atom
            and key.target_atom not in seen_in_extra
        ):
            candidates.append(key.target_atom)
            seen_in_extra.add(key.target_atom)

    given_atoms = {ga for ga, _ in base_given}
    for z in candidates:
        if z == target_atom or z in given_atoms:
            continue
        domain = theta.domain_of(z)
        if not domain:
            continue
        # Check: every (target_atom, target_value, base_given ∪ {(z, v)})
        # exists for v in domain(z)?
        all_outer_present = True
        for v in domain:
            extended_given = frozenset(base_given | {(z, v)})
            outer_key = ProbabilityKey(
                target_atom=target_atom,
                target_value=target_value,
                given=extended_given,
            )
            if outer_key not in theta.entries:
                all_outer_present = False
                break
        if not all_outer_present:
            continue
        # Inner factor: P(Z=v | base_given) — must also exist for
        # each v. Conservative: require entries with the SAME
        # base_given conditioning. (More general: derive P(Z|cond)
        # by chain rule. Iter 172+ may extend.)
        all_inner_present = True
        for v in domain:
            inner_key = ProbabilityKey(
                target_atom=z, target_value=v, given=base_given,
            )
            if inner_key not in theta.entries:
                all_inner_present = False
                break
        if all_inner_present:
            return True
    return False
