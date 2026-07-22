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
    ConstantExpr,
    FormulaExpr,
    FractionExpr,
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
    *,
    include_intervention: bool = True,
) -> FormulaExpr:
    """Build the standard back-door adjustment formula.

    The ``adjustment_set`` tuple is treated as ordered. Callers that
    have access to the DAG should pass it in topological order so the
    chain-rule factors of the joint P(Z1,...,Zk | observed) align with
    the structural parent relationships.

    ``include_intervention`` controls whether the intervention atom
    appears inside the main conditional. It must be False exactly when
    the intervention has no directed path to the target: then, given the
    back-door-blocking ``adjustment_set``, ``target ⊥ intervention`` so
    ``P(Y|X,Z) = P(Y|Z)`` — keeping X in the conditional would be both
    spurious and un-supplyable (X is not a parent of Y, so the validator
    rejects ``P(Y|X,...)``). The caller, which has the DAG, decides.

    adjustment_set = ():
        P(target | intervention, observed)       [include_intervention]
        P(target | observed)                      [not include_intervention]

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
    cond_prefix = (intervention,) if include_intervention else ()

    if len(adjustment_set) == 0:
        return _conditional(target, cond_prefix + observed)

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
    conditional = _conditional(target, cond_prefix + z_valueds + observed)

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


def front_door_formula(
    target: ValuedAtom,
    intervention: ValuedAtom,
    mediators: tuple[Atom, ...],
    observed: tuple[ValuedAtom, ...] = (),
) -> FormulaExpr:
    """Build Pearl's front-door adjustment formula.

    For a single mediator Z (``mediators == (Z,)``):

        ∑_z  P(Z=z | X=x, observed)
             · ∑_{x'}  P(Y=y | X=x', Z=z, observed) · P(X=x' | observed)

    The outer sum runs over Z's domain; the inner sum re-marginalises
    X against the mediator conditional. ``observed`` threads into every
    probability_ref the same way ``backdoor_formula`` handles it.

    Multi-mediator front-door (``mediators`` of length >= 2, in
    topological order): chain-rule factor the joint mediator
    conditional and nest the sums:

        ∑_{z1} ∑_{z2} ... ∑_{zk}
            ∏_i P(Zi = zi | Z_{<i}, X = x, observed)
            · ∑_{x'} P(Y = y | X = x', Z1=z1, ..., Zk=zk, observed)
                    · P(X = x' | observed)

    where ``Z_{<i}`` means the mediators earlier in the topological
    order. This generalises the single-mediator case: when k=1 the
    chain rule degenerates to ``P(Z1|X)`` and the formula reduces to
    Pearl's textbook form above.

    Phase 6.front-door-multi: the scheduler passes ``mediators`` in
    topological order so the chain-rule factors are well-formed
    without extra graph consultation in this function.
    """
    if len(mediators) == 0:
        raise FormulaSupportError(
            "front_door_formula requires at least one mediator"
        )

    x_atom = intervention.atom

    # Build fresh bind names for each mediator in topo order and one
    # for x' (inner sum). Collect incrementally so each later atom sees
    # all prior names in its ``taken`` set.
    taken: frozenset[str] = frozenset()
    z_binds: list = []
    z_vas: list[ValuedAtom] = []
    for z_atom in mediators:
        b = fresh_bind_name(z_atom, taken)
        z_binds.append(b)
        z_vas.append(ValuedAtom(atom=z_atom, value=VarRef(name=b.name)))
        taken = taken | {b.name}
    x_bind = fresh_bind_name(x_atom, taken)
    x_prime_va = ValuedAtom(atom=x_atom, value=VarRef(name=x_bind.name))

    # Inner sum: ∑_{x'} P(Y | X=x', Z1=z1, ..., Zk=zk, observed) · P(X=x' | observed)
    inner_conditional = _conditional(
        target, (x_prime_va, *z_vas) + observed
    )
    x_prior = _conditional(x_prime_va, observed)
    inner_body = ProductExpr(terms=(inner_conditional, x_prior))
    inner_sum = SumExpr(bind=x_bind, over=x_atom, body=inner_body)

    # Chain-rule factors for the joint mediator conditional:
    # P(Z1|X) · P(Z2|Z1,X) · ... · P(Zk|Z_{<k}, X)
    chain_factors: list = []
    for i, z_va in enumerate(z_vas):
        prior_mediators = tuple(z_vas[:i])
        chain_factors.append(
            _conditional(z_va, (intervention,) + prior_mediators + observed)
        )

    # Combine factors with the inner sum; wrap in nested outer sums
    # over z1, z2, ..., zk (outer-to-inner matches topological order).
    body = ProductExpr(terms=tuple(chain_factors) + (inner_sum,))
    for z_atom, z_bind in reversed(list(zip(mediators, z_binds))):
        body = SumExpr(bind=z_bind, over=z_atom, body=body)
    return body


def mediation_potential_outcome_formula(
    target: ValuedAtom,
    intervention_outer: ValuedAtom,
    intervention_inner: ValuedAtom,
    mediators: tuple[Atom, ...],
    adjustment_set: tuple[Atom, ...] = (),
    observed: tuple[ValuedAtom, ...] = (),
) -> FormulaExpr:
    """Build the g-formula for a (possibly cross-world) potential
    outcome with mediator marginalization.

    Computes, over the mediator BLOCK M = (M1, ..., Mk)::

        E[Y(X=x_outer, M = M(X=x_inner)) | observed]
          = Σ_w  Σ_m1..mk
                P(Y=y | X=x_outer, M1=m1, .., Mk=mk, W=w, observed)
              · ∏_j P(Mj=mj | M_{<j}, X=x_inner, W=w, observed)
              · ∏_i P(Wi=wi | W_{<i}, observed)

    The cross-world case (``intervention_outer.value != intervention_inner.value``)
    is the natural-direct/indirect-effect primitive: NDE = E[Y(1, M(0))]
    − E[Y(0)], NIE = E[Y(1)] − E[Y(1, M(0))]. When the two interventions
    agree, this collapses to the standard potential outcome E[Y(X=x)]
    expressed via mediator-marginalised g-formula.

    The joint mediator law P(M1..Mk | X=x_inner, W=w) is expanded by the
    CHAIN RULE, exactly as P(W1..Wk) already is. That is an identity, not
    a modelling assumption: it needs no independence among the mediators
    and no separate declaration of a joint mediator distribution. When the
    mediators are in fact conditionally independent given (X, W), the
    numeric layer's graph-guarded reduction resolves each factor against
    the marginal CPT the user actually declared, so a parallel mediator
    block evaluates from ordinary per-mediator theta.

    ``adjustment_set`` must align with the NDE/NIE identification's W
    per ``structural_solver.mediation_sets(...).nde_nie.adjustment``
    — typically empty in textbook three-node mediation graphs.

    Caller passes ``adjustment_set`` AND ``mediators`` in topological
    order so the chain-rule factors of P(W1, ..., Wk) and of the mediator
    block align with structural parent relationships (same convention as
    ``backdoor_formula``). A single-element ``mediators`` reproduces the
    classical Pearl 2001 single-mediator formula exactly.
    """
    taken: set[str] = set()
    w_binds: list[tuple[Atom, BindDecl, ValuedAtom]] = []
    for w_atom in adjustment_set:
        bind = fresh_bind_name(w_atom, frozenset(taken))
        taken.add(bind.name)
        w_va = ValuedAtom(atom=w_atom, value=VarRef(name=bind.name))
        w_binds.append((w_atom, bind, w_va))
    w_valueds = tuple(vv for (_, _, vv) in w_binds)

    m_binds: list[tuple[Atom, BindDecl, ValuedAtom]] = []
    for m_atom in mediators:
        bind = fresh_bind_name(m_atom, frozenset(taken))
        taken.add(bind.name)
        m_va = ValuedAtom(atom=m_atom, value=VarRef(name=bind.name))
        m_binds.append((m_atom, bind, m_va))
    m_valueds = tuple(vv for (_, _, vv) in m_binds)

    y_conditional = _conditional(
        target,
        (intervention_outer,) + m_valueds + w_valueds + observed,
    )
    # Chain rule for the joint mediator law: ∏_j P(Mj | M_{<j}, x_inner, w).
    m_factors: list[ProbabilityRefExpr] = []
    for j, (_, _, m_va) in enumerate(m_binds):
        prior = m_valueds[:j]
        m_factors.append(
            _conditional(
                m_va,
                (intervention_inner,) + prior + w_valueds + observed,
            )
        )
    w_factors: list[ProbabilityRefExpr] = []
    for i, (_, _, w_va) in enumerate(w_binds):
        prior = w_valueds[:i]
        w_factors.append(_conditional(w_va, prior + observed))

    body: FormulaExpr = ProductExpr(
        terms=(y_conditional, *m_factors, *w_factors)
    )

    for m_atom, bind, _ in reversed(m_binds):
        body = SumExpr(bind=bind, over=m_atom, body=body)
    for w_atom, bind, _ in reversed(w_binds):
        body = SumExpr(bind=bind, over=w_atom, body=body)

    return body


def mediation_controlled_outcome_formula(
    target: ValuedAtom,
    intervention: ValuedAtom,
    mediators: tuple[ValuedAtom, ...],
    adjustment_set: tuple[Atom, ...] = (),
    observed: tuple[ValuedAtom, ...] = (),
) -> FormulaExpr:
    """Build the g-formula for a controlled potential outcome.

    Computes, with the whole mediator block held fixed at m* ::

        E[Y | do(X=x, M1=m1*, .., Mk=mk*), observed]
          = Σ_w  P(Y=y | X=x, M1=m1*, .., Mk=mk*, W=w, observed)
                · ∏_i P(Wi=wi | W_{<i}, observed)

    Used by mediation CDE: CDE(m*) = E[Y|do(X=1, M=m*)] − E[Y|do(X=0, M=m*)].
    Both X and M are intervened on (do-calculus rule 2 along the
    X → M → Y paths is licensed by the structural CDE identification).
    Unlike ``mediation_potential_outcome_formula`` there is no inner
    mediator sum because every mediator is fixed by the do — which is
    why the block form needs no chain rule here.

    ``adjustment_set`` must align with the CDE identification's W per
    ``structural_solver.mediation_sets(...).cde.adjustment``.

    When ``adjustment_set`` is empty the formula reduces to a single
    conditional ``P(Y=y | X=x, M=m*, observed)``.
    """
    if len(adjustment_set) == 0:
        return _conditional(target, (intervention,) + mediators + observed)

    taken: set[str] = set()
    w_binds: list[tuple[Atom, BindDecl, ValuedAtom]] = []
    for w_atom in adjustment_set:
        bind = fresh_bind_name(w_atom, frozenset(taken))
        taken.add(bind.name)
        w_va = ValuedAtom(atom=w_atom, value=VarRef(name=bind.name))
        w_binds.append((w_atom, bind, w_va))
    w_valueds = tuple(vv for (_, _, vv) in w_binds)

    y_conditional = _conditional(
        target,
        (intervention,) + mediators + w_valueds + observed,
    )
    w_factors: list[ProbabilityRefExpr] = []
    for i, (_, _, w_va) in enumerate(w_binds):
        prior = w_valueds[:i]
        w_factors.append(_conditional(w_va, prior + observed))

    body: FormulaExpr = ProductExpr(terms=(y_conditional, *w_factors))

    for w_atom, bind, _ in reversed(w_binds):
        body = SumExpr(bind=bind, over=w_atom, body=body)

    return body


def transport_formula(
    target: ValuedAtom,
    intervention: ValuedAtom,
    adjustment_set: tuple[Atom, ...],
    *,
    source_population: str = "source",
    target_population: str = "target",
    observed: tuple[ValuedAtom, ...] = (),
) -> FormulaExpr:
    """Build Bareinboim-Pearl single-source transport g-formula
    (Fix 3+4, charter FIX_3_4_CHARTER_llm_mediated_transport.md).

    Computes::

        P*(Y=y | do(X=x)) = Σ_z P(Y=y | X=x, Z=z, source)
                                · ∏_i P*(Zi=zi | Z_{<i}, target)

    where:

    - ``adjustment_set`` Z satisfies Bareinboim Theorem 1
      S-admissibility AND the source-population back-door criterion
      (the standard joint condition where the inner factor reduces
      from ``P(Y | do(X), Z)`` to ``P(Y | X, Z)`` without further
      adjustment). Caller (``scheduler._dispatch_transport``)
      enforces this via ``transport.identify_via_transport``.
    - Source factor ``P(Y | X, Z, source)`` is tagged
      ``population=source_population`` so the evaluator routes it to
      source theta entries (declared by user / supplied by literature).
    - Target factors ``P*(Zi=zi | ..., target)`` are tagged
      ``population=target_population`` so they route to target theta
      entries — typically LLM-proposed priors under Fix 3 in real
      deployment.
    - Empty ``adjustment_set`` reduces to ``P(Y | X, source)`` flat —
      the trivial-transportability case where source and target
      effects coincide.

    Empty observed currently; the q.given clause on EffectQuery doesn't
    conventionally appear in transport's textbook form. If a real case
    surfaces needing observed, extend symmetrically to
    ``backdoor_formula``.
    """
    if len(adjustment_set) == 0:
        # Trivial: transport reduces to direct source observational
        # conditional (no Z to marginalise over, no target-marginal
        # needed). Bareinboim Theorem 1 still requires the diagram
        # check that S doesn't open a back-door from X to Y, but that
        # check is structural-layer (transport.identify_via_transport).
        return ProbabilityRefExpr(
            target=target,
            given=(intervention,) + observed,
            population=source_population,
        )

    taken: set[str] = set()
    z_binds: list[tuple[Atom, BindDecl, ValuedAtom]] = []
    for z_atom in adjustment_set:
        bind = fresh_bind_name(z_atom, frozenset(taken))
        taken.add(bind.name)
        z_va = ValuedAtom(atom=z_atom, value=VarRef(name=bind.name))
        z_binds.append((z_atom, bind, z_va))
    z_valueds = tuple(vv for (_, _, vv) in z_binds)

    # Source factor: P(Y | X, Z, observed) — single conditional in source.
    source_factor = ProbabilityRefExpr(
        target=target,
        given=(intervention,) + z_valueds + observed,
        population=source_population,
    )

    # Target factors: chain-rule decomposition of P*(Z1, ..., Zk),
    # mirroring backdoor_formula's joint-W treatment but with each
    # term tagged population=target.
    target_factors: list[ProbabilityRefExpr] = []
    for i, (_, _, z_va) in enumerate(z_binds):
        prior = z_valueds[:i]
        target_factors.append(
            ProbabilityRefExpr(
                target=z_va,
                given=prior + observed,
                population=target_population,
            )
        )

    body: FormulaExpr = ProductExpr(terms=(source_factor, *target_factors))
    for z_atom, bind, _ in reversed(z_binds):
        body = SumExpr(bind=bind, over=z_atom, body=body)
    return body


def bind_target_value(
    formula: FormulaExpr,
    target_atom: Atom,
    target_value,
) -> FormulaExpr:
    """Walk a formula tree and bind ``target_atom``'s currently-``None``
    target values to ``target_value``.

    Used by the Tian-in-effect path (Fix 5, v0.1.5): Shpitser-Pearl ID
    returns a FormulaExpr where the outermost Y target has
    ``value=None`` so the IdentifyQuery caller (which has no value)
    can use it. For EffectQuery the target has a concrete value
    (``q.target.value``) that the evaluator needs bound before it can
    look up ``P(Y=y | ...)`` in theta.

    Only binds ProbRefs where ``target.atom == target_atom`` AND
    ``target.value is None``. ProbRefs with VarRef values (bound by
    enclosing SumExpr) are left alone — those are inner sum-bound
    variables, not the outer query target. ProbRefs with literal
    values are also left alone.

    Returns a new tree; the input is not mutated (FormulaExpr is
    frozen).
    """
    if isinstance(formula, ConstantExpr):
        return formula
    if isinstance(formula, ProbabilityRefExpr):
        if (
            formula.target.atom == target_atom
            and formula.target.value is None
        ):
            new_target = ValuedAtom(
                atom=formula.target.atom, value=target_value,
            )
            return ProbabilityRefExpr(
                target=new_target,
                given=formula.given,
                population=formula.population,
            )
        return formula
    if isinstance(formula, ProductExpr):
        return ProductExpr(
            terms=tuple(
                bind_target_value(t, target_atom, target_value)
                for t in formula.terms
            )
        )
    if isinstance(formula, SumExpr):
        return SumExpr(
            bind=formula.bind,
            over=formula.over,
            body=bind_target_value(formula.body, target_atom, target_value),
        )
    if isinstance(formula, FractionExpr):
        return FractionExpr(
            numerator=bind_target_value(
                formula.numerator, target_atom, target_value,
            ),
            denominator=bind_target_value(
                formula.denominator, target_atom, target_value,
            ),
        )
    raise TypeError(
        f"unknown FormulaExpr node: {type(formula).__name__}"
    )


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
