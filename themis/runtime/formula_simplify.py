"""Algebraic simplification of identification formulas (Phase 16, slice 1).

The Shpitser-Pearl ID algorithm's nested lines (especially Line 7) produce
marginalized products of conditionals — ``Σ_v ∏_i P(Vi|Ci)`` — and IDC adds
ratios of these. Built naively, with no algebra pass *between* construction
steps, these expressions blow up EXPONENTIALLY: the same summed factor is
carried through layer after layer instead of being cancelled as soon as it
integrates to one. That blow-up (depth in the thousands on a 5-node graph)
is what stalled the first complete-Line-7 attempt.

This module is the cheap, graph-free canceller — the Themis port of the
load-bearing half of ``causaleffect::simplify.expression`` (Tikka &
Karvanen 2017, JMLR 18(36); the R source's lines 16-21). It implements ONE
identity, the one that does almost all the work:

    sum-to-one:   Σ_v P(v | C) · R  =  R       (when v ∉ C and v ∉ free(R))

i.e. summing out a variable whose ONLY occurrence is as the head of a
proper conditional distribution drops that factor and that sum. The guard
``v ∉ free(R)`` is what makes it value-preserving: if any other factor
conditions on ``v`` the sum does not factor and we must not touch it.

Slice 1 deliberately does NOT include the graph-aware ``join``/``insert``
elimination (JMLR Algorithm 1, needs d-separation) nor fraction
cancellation (``q-simplify``); those are the completeness layers and land
in later slices once this one is proven value-preserving by the semantic
probe. The function is a pure, total transformation: same input → same
output, no I/O, no graph.
"""
from __future__ import annotations

from ..types import (
    ConstantExpr,
    FractionExpr,
    ProbabilityRefExpr,
    ProductExpr,
    SumExpr,
    VarRef,
)

# Fixpoint guard: one collapse can expose another (nested sums), so we
# iterate to a fixpoint. The bound is generous — real ID formulas have
# far fewer summable layers than this — and exists only to make a logic
# bug surface as a stall rather than an infinite loop.
_MAX_PASSES = 256


def simplify_formula(expr):
    """Return an algebraically-equal, structurally-smaller formula.

    Applies the sum-to-one collapse to a fixpoint, bottom-up. Pure and
    total: the result computes the same number as ``expr`` under any Theta
    for which ``expr`` is well-defined, for every binding of its free
    variables.
    """
    cur = expr
    for _ in range(_MAX_PASSES):
        nxt = _simplify_once(cur)
        if nxt == cur:
            return cur
        cur = nxt
    return cur


def _simplify_once(expr):
    if isinstance(expr, (ConstantExpr, ProbabilityRefExpr)):
        return expr
    if isinstance(expr, FractionExpr):
        return FractionExpr(
            numerator=_simplify_once(expr.numerator),
            denominator=_simplify_once(expr.denominator),
        )
    if isinstance(expr, ProductExpr):
        return _flatten_product(
            tuple(_simplify_once(t) for t in expr.terms)
        )
    if isinstance(expr, SumExpr):
        body = _simplify_once(expr.body)
        return _collapse_sum(expr.bind, expr.over, body)
    return expr


def _flatten_product(terms):
    """Normalize a product: splice nested products in, drop unit factors,
    and unwrap a singleton. Keeps the canceller's structural assumptions
    (a product's terms are not themselves products) simple."""
    flat = []
    for t in terms:
        if isinstance(t, ProductExpr):
            flat.extend(t.terms)
        elif isinstance(t, ConstantExpr) and t.value == 1.0:
            continue
        else:
            flat.append(t)
    if not flat:
        return ConstantExpr(value=1.0)
    if len(flat) == 1:
        return flat[0]
    return ProductExpr(terms=tuple(flat))


def _collapse_sum(bind, over, body):
    """Apply ``Σ_v P(v|C)·R = R`` when valid; otherwise return the sum
    unchanged. ``v`` is the bound name ``bind.name``."""
    v = bind.name

    # Σ_v P(v|C) with v ∉ C  →  1.
    if isinstance(body, ProbabilityRefExpr):
        if _is_distribution_over(body, v):
            return ConstantExpr(value=1.0)
        return SumExpr(bind=bind, over=over, body=body)

    if isinstance(body, ProductExpr):
        dist_idx = [
            i for i, f in enumerate(body.terms)
            if _is_distribution_over(f, v)
        ]
        # Exactly one factor is the distribution P(v|C). More than one
        # would be a malformed factorization; zero means v is only ever
        # conditioned on, so the sum does not collapse by this rule.
        if len(dist_idx) == 1:
            i = dist_idx[0]
            rest = body.terms[:i] + body.terms[i + 1:]
            rest_expr = _flatten_product(rest)
            # Value-preserving iff v occurs nowhere in the remaining
            # factors — only then does Σ_v P(v|C) factor out as 1.
            if v not in _free_names(rest_expr):
                return rest_expr
        return SumExpr(bind=bind, over=over, body=body)

    return SumExpr(bind=bind, over=over, body=body)


def _is_distribution_over(factor, v: str) -> bool:
    """True iff ``factor`` is ``P(v | C)`` with ``v ∉ C`` — a proper
    conditional distribution in the summed variable, so ``Σ_v`` of it is
    exactly 1."""
    if not isinstance(factor, ProbabilityRefExpr):
        return False
    tv = factor.target.value
    if not (isinstance(tv, VarRef) and tv.name == v):
        return False
    for g in factor.given:
        if isinstance(g.value, VarRef) and g.value.name == v:
            return False
    return True


def _free_names(expr) -> frozenset[str]:
    """The set of VarRef names occurring free in ``expr`` (a SumExpr binds
    its own name, removing it from the body's free set)."""
    if isinstance(expr, ProbabilityRefExpr):
        names = set()
        if isinstance(expr.target.value, VarRef):
            names.add(expr.target.value.name)
        for g in expr.given:
            if isinstance(g.value, VarRef):
                names.add(g.value.name)
        return frozenset(names)
    if isinstance(expr, ProductExpr):
        out: set[str] = set()
        for t in expr.terms:
            out |= _free_names(t)
        return frozenset(out)
    if isinstance(expr, FractionExpr):
        return _free_names(expr.numerator) | _free_names(expr.denominator)
    if isinstance(expr, SumExpr):
        return _free_names(expr.body) - {expr.bind.name}
    return frozenset()
