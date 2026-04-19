"""Construct well-formed formula ASTs from identification results.

The operator set is defined in formula_ast_spec_v0_1.md:
constant / probability_ref / product / sum.

All formulas produced here must satisfy:
- ``sum.over`` is ground
- every ``VarRef`` is bound by an enclosing ``SumExpr``
- no ``do`` node appears (identification consumes do by construction)
"""
from __future__ import annotations

from ..types import (
    Atom,
    BindDecl,
    FormulaExpr,
    ProbabilityRefExpr,
    ProductExpr,
    SumExpr,
    ValuedAtom,
    VarRef,
)


class FormulaSupportError(NotImplementedError):
    """Raised when the requested formula shape is not supported in
    this version (e.g. joint adjustment over >1 atoms)."""


def _fresh_bind_name(atom: Atom, taken: frozenset[str]) -> str:
    """Pick a stable, readable bind name for an atom, avoiding clashes."""
    args = "_".join(a.name for a in atom.args)
    base = f"z_{atom.predicate}_{args}" if args else f"z_{atom.predicate}"
    if base not in taken:
        return base
    i = 2
    while f"{base}_{i}" in taken:
        i += 1
    return f"{base}_{i}"


def fresh_bind_name(atom: Atom, taken: frozenset[str] = frozenset()) -> BindDecl:
    """Public helper: generate a fresh bound-variable name for an atom."""
    return BindDecl(name=_fresh_bind_name(atom, taken))


def _conditional(
    target: ValuedAtom,
    conditions: tuple[ValuedAtom, ...],
) -> ProbabilityRefExpr:
    return ProbabilityRefExpr(target=target, given=conditions)


def backdoor_formula(
    target: ValuedAtom,
    intervention: ValuedAtom,
    adjustment_set: tuple[Atom, ...],
    observed: tuple[ValuedAtom, ...] = (),
) -> FormulaExpr:
    """Build the standard back-door adjustment formula.

    The ``adjustment_set`` tuple is treated as ordered. Callers that
    have access to the DAG should pass it in topological order so the
    chain-rule factors of the joint P(Z1,...,Zk | observed) align with
    the structural parent relationships.

    adjustment_set = ():
        P(target | intervention, observed)

    adjustment_set = (Z,):
        ∑_z  P(target | intervention, Z=z, observed)
             · P(Z=z | observed)

    adjustment_set = (Z1, ..., Zk), k >= 2:
        Nested sums with the joint expanded via the chain rule:

        ∑_{z1} ... ∑_{zk}
            P(target | intervention, Z1=z1, ..., Zk=zk, observed)
            · ∏_i P(Zi=zi | Z1=z1, ..., Z_{i-1}=z_{i-1}, observed)

        The chain-rule factors are emitted as separate probability_ref
        terms inside the innermost product; no joint-target primitive
        is introduced, keeping the v0.1 formula AST unchanged.
    """
    if len(adjustment_set) == 0:
        return _conditional(target, (intervention,) + observed)

    # Allocate fresh bind names and build one ValuedAtom per Z atom.
    taken: set[str] = set()
    binds: list[tuple[Atom, BindDecl, ValuedAtom]] = []
    for z_atom in adjustment_set:
        bind = fresh_bind_name(z_atom, frozenset(taken))
        taken.add(bind.name)
        z_va = ValuedAtom(atom=z_atom, value=VarRef(name=bind.name))
        binds.append((z_atom, bind, z_va))

    z_valueds = tuple(vv for (_, _, vv) in binds)

    # Main conditional: P(target | intervention, Z1=z1, ..., Zk=zk, observed)
    conditional = _conditional(target, (intervention,) + z_valueds + observed)

    # Chain-rule factors for P(Z1,...,Zk | observed):
    #   P(Zi=zi | Z1=z1, ..., Z_{i-1}=z_{i-1}, observed)
    factors: list[ProbabilityRefExpr] = []
    for i, (_, _, z_va) in enumerate(binds):
        prior = z_valueds[:i]
        factors.append(_conditional(z_va, prior + observed))

    body: FormulaExpr = ProductExpr(terms=(conditional, *factors))

    # Wrap in sums in reverse so the first Z is the outermost sum.
    for z_atom, bind, _ in reversed(binds):
        body = SumExpr(bind=bind, over=z_atom, body=body)

    return body


# ---------------------------------------------------------------------------
# Read-only walkers — used by explainer / differential, never by builders.
# ---------------------------------------------------------------------------


def adjustment_atoms(formula: FormulaExpr) -> tuple[Atom, ...]:
    """Return every atom that a ``SumExpr.over`` node iterates in the
    formula, in outer-to-inner order.

    For a back-door adjustment produced by ``backdoor_formula``:

    - empty adjustment set → the formula is a flat ``ProbabilityRefExpr``
      and this function returns ``()``.
    - single adjustment atom → one-element tuple.
    - nested chain-rule sums over ``(z1, ..., zk)`` → ``(z1, ..., zk)``
      in the same order ``backdoor_formula`` nested them.

    Used by the explainer to render the full adjustment set (not only
    the outermost binder) and by the oracle comparator to verify that
    the chosen adjustment is valid per pgmpy.
    """
    collected: list[Atom] = []
    _walk_for_adjustments(formula, collected)
    return tuple(collected)


def _walk_for_adjustments(node: FormulaExpr, collected: list[Atom]) -> None:
    if isinstance(node, SumExpr):
        collected.append(node.over)
        _walk_for_adjustments(node.body, collected)
    elif isinstance(node, ProductExpr):
        for t in node.terms:
            _walk_for_adjustments(t, collected)
    # ConstantExpr / ProbabilityRefExpr: no adjustment atoms.
