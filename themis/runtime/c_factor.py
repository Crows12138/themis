"""Tian / Shpitser ID algorithm for ADMG identification.

Phase 2.latent ext §S3.b.2 — kicks in when ADMG-aware backdoor /
front-door / IV all fail. Implements Shpitser & Pearl 2006's complete
ID algorithm (which subsumes Tian 2002), restricted to the kernel's
identify-query shape: single intervention, single target, empty given.

Three return shapes:

- `(FormulaExpr, ...)` — query identifiable; witness is a c-factor
  product. Lines 1-6 of the recursion (ancestral shrink, descendant
  exclusion, c-component split, hedge witness, Q[S] product form).
- `(None, "hedge")` — query is provably unidentifiable; witness is the
  hedge graph (Lines 1-5).
- `None` (no second value) — **Line 7 deferred**: the recursion needs
  symbolic substitution under a Q[S'] re-factorization (S ⊊ S' for
  some c-component S' of G), which this slice does not implement.
  Scheduler treats this as `needs_investigation` rather than falsely
  claiming unidentifiable. Identifiable-via-Line-7 ADMGs (the "ID-Y
  descent" case) are a documented capability gap; no real eval case
  has triggered Line 7 yet, so the deferral has not blocked any
  observed user query.

Output formula uses the c-factor product form for Q[S] (S a c-component
of the full ADMG): each variable in S contributes
``P(v_i | v_{<i})`` where ``v_{<i}`` are the variables earlier in the
ADMG topological order. This is the canonical witness for Tian
identifiability and matches what verifier replay re-checks.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

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
from .structural_solver import BidirectedEdgeSet, c_components


@dataclass(frozen=True)
class TianResult:
    """Result of running the Shpitser ID recursion on an ADMG.

    ``identifiable=False`` carries a hedge witness — the c-component
    that contains the intervention nodes at the FAIL line (Line 5),
    used by the diagnostic surface and by the verifier replay.
    """
    identifiable: bool
    formula: FormulaExpr | None
    # Witness: the c-component decomposition trail across recursion
    # depths. Each entry is a tuple of frozensets (the c-components
    # of the current subgraph). Stored for verifier replay; the
    # verifier re-runs c_components on the same scope and checks the
    # partition matches.
    witness_trail: tuple[tuple[frozenset[Atom], ...], ...] = field(default_factory=tuple)
    # When unidentifiable, the hedge: the single c-component of the
    # final ADMG that swallowed both X and (the closure of) Y.
    hedge: frozenset[Atom] | None = None


def identify_via_tian(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    x_atom: Atom,
    y_atom: Atom,
    x_value,
) -> TianResult:
    """Run Shpitser-Pearl ID for the single-intervention, single-target
    case. Returns a TianResult.

    The intervention value is threaded into the formula's outer X
    occurrence (so the rendered probabilistic expression carries the
    concrete do(X=x_value) assignment, just like backdoor/front-door
    formulas do). All other atoms in the formula are bound by sums
    or by the implicit query target (target = y_atom, value passed in
    by the query).
    """
    V = frozenset(graph.nodes()) | {a for pair in bidirected for a in pair}
    x_set = frozenset({x_atom})
    y_set = frozenset({y_atom})

    if x_atom not in V or y_atom not in V:
        return TianResult(identifiable=False, formula=None)
    if x_atom == y_atom:
        return TianResult(identifiable=False, formula=None)

    # Pick a stable ADMG-wide topological order once. The c-factor
    # product form needs every Q[S] to factor along the same v^(<i)
    # predecessor sequence — using sub-graph orders breaks consistency
    # across recursive calls.
    full_topo = tuple(_admg_topo_order(graph, V))

    state = _IdState(
        V=V,
        x=x_set,
        y=y_set,
        graph=graph,
        bidirected=bidirected,
        topo=full_topo,
        x_value=x_value,
        trail=[],
        do_atoms=x_set,
    )
    formula = _id(state)
    if formula is None:
        return TianResult(
            identifiable=False,
            formula=None,
            witness_trail=tuple(state.trail),
            hedge=state.hedge,
        )
    return TianResult(
        identifiable=True,
        formula=formula,
        witness_trail=tuple(state.trail),
    )


# ============================================ internals


@dataclass
class _IdState:
    """Mutable state threaded through the recursion. Carries the full
    ADMG topo order so c-factor terms always reference the canonical
    predecessor sequence regardless of which subgraph ID is currently
    operating on.

    ``x`` is the algorithmic X for the current recursion level — it
    grows in Line 3 (W join) and changes in Line 4 sub-recursion
    (``x = V \\ s_i``). ``do_atoms`` is the ORIGINAL outer query's
    intervention set, fixed across all recursion. Use ``do_atoms``
    (not ``x``) for "should this atom be substituted with the do-value
    literal in the formula?" — that question is about the user's
    semantic intervention, not the algorithmic recursion variable.
    Threading these separately is the iter 145 fix for the
    degenerate-sum bug iter 144 exposed.
    """
    V: frozenset[Atom]
    x: frozenset[Atom]
    y: frozenset[Atom]
    graph: nx.DiGraph
    bidirected: BidirectedEdgeSet
    topo: tuple[Atom, ...]
    x_value: object
    trail: list[tuple[frozenset[Atom], ...]]
    do_atoms: frozenset[Atom] = frozenset()
    hedge: frozenset[Atom] | None = None
    # Counter for fresh-bind names.
    _bind_seq: int = 0


def _admg_topo_order(graph: nx.DiGraph, scope: frozenset[Atom]) -> list[Atom]:
    """Topological order of `scope` using directed edges only.

    Bidirected edges do not impose a ordering — they represent latent
    common causes, not directed influence. Atoms in `scope` not
    represented in `graph.nodes()` (i.e. only present via bidirected
    pairs) are appended after the directed-graph topo order in a
    deterministic way (sorted by predicate name) so the order is
    stable across runs.
    """
    in_graph = [n for n in scope if n in graph.nodes()]
    sub = graph.subgraph(in_graph)
    topo = list(nx.topological_sort(sub))
    extras = sorted(
        (n for n in scope if n not in graph.nodes()),
        key=lambda a: (a.predicate, tuple(t.name for t in a.args)),
    )
    return topo + extras


def _ancestors_in_scope(
    graph: nx.DiGraph,
    scope: frozenset[Atom],
    targets: frozenset[Atom],
) -> frozenset[Atom]:
    """Closed ancestral set (including targets) inside `scope`."""
    in_scope = scope & frozenset(graph.nodes())
    sub = graph.subgraph(in_scope)
    result = set(targets & in_scope)
    for t in targets:
        if t in sub:
            result.update(nx.ancestors(sub, t))
    return frozenset(result & scope)


def _restrict_bidirected(
    bidirected: BidirectedEdgeSet,
    scope: frozenset[Atom],
) -> BidirectedEdgeSet:
    return frozenset(p for p in bidirected if p <= scope)


def _id(state: _IdState) -> FormulaExpr | None:
    """Recursive Shpitser ID. Mutates `state.trail` and `state.hedge`."""
    V = state.V
    x = state.x
    y = state.y
    graph = state.graph
    bidirected = state.bidirected

    # Line 1: x = empty → return Σ_{V\Y} ∏ P(v_i | v_{<i})
    if not x:
        return _build_marginal(state, keep=y, scope=V)

    # Line 2: V \ An_G(Y) ≠ empty → recurse on G[An_G(Y)]
    A = _ancestors_in_scope(graph, V, y)
    if A != V:
        sub = graph.subgraph(A & frozenset(graph.nodes()))
        sub_bi = _restrict_bidirected(bidirected, A)
        new_state = _IdState(
            V=A,
            x=x & A,
            y=y,
            graph=sub,
            bidirected=sub_bi,
            topo=state.topo,
            x_value=state.x_value,
            do_atoms=state.do_atoms,
            trail=state.trail,
        )
        result = _id(new_state)
        state.hedge = new_state.hedge
        return result

    # Line 3: W = (V \ X) \ An_{G[V\X]}(Y) ≠ empty → recurse with x ∪ W
    G_minus_x_nodes = (V - x) & frozenset(graph.nodes())
    G_minus_x = graph.subgraph(G_minus_x_nodes)
    A_minus_x = _ancestors_in_scope(G_minus_x, V - x, y)
    W = (V - x) - A_minus_x
    if W:
        new_state = _IdState(
            V=V,
            x=x | W,
            y=y,
            graph=graph,
            bidirected=bidirected,
            topo=state.topo,
            x_value=state.x_value,
            do_atoms=state.do_atoms,
            trail=state.trail,
        )
        result = _id(new_state)
        state.hedge = new_state.hedge
        return result

    # Line 4: c-components of G[V\X]
    bidirected_minus_x = _restrict_bidirected(bidirected, V - x)
    cc_minus_x = c_components(G_minus_x, bidirected_minus_x)
    cc_minus_x = tuple(sorted(cc_minus_x, key=_atomset_key))
    state.trail.append(cc_minus_x)

    if len(cc_minus_x) > 1:
        # Σ_{V\(Y∪X)} ∏_{S in cc_minus_x} ID(S, V\S, ...)
        sub_formulas: list[FormulaExpr] = []
        for s_i in cc_minus_x:
            sub_state = _IdState(
                V=V,
                x=V - s_i,
                y=s_i,
                graph=graph,
                bidirected=bidirected,
                topo=state.topo,
                x_value=state.x_value,
            do_atoms=state.do_atoms,
                trail=state.trail,
            )
            sub = _id(sub_state)
            if sub is None:
                state.hedge = sub_state.hedge
                return None
            sub_formulas.append(sub)

        body: FormulaExpr
        if len(sub_formulas) == 1:
            body = sub_formulas[0]
        else:
            body = ProductExpr(terms=tuple(sub_formulas))

        # Sum over V \ (Y ∪ X) — wrap each in a SumExpr binding a
        # fresh name; use the bind names to rewrite the formula's
        # references to those atoms.
        sum_set = V - (y | x)
        # Iter 147 second-half fix: each sub_formula was built with
        # its OWN sub-state.y (e.g. {M} for the s_i={M} branch),
        # which sets that atom's value=None in target slots — that
        # convention works in isolation (caller binds the value
        # externally). But here the outer Σ_M wrap binds the
        # canonical bind name for M, so the sub-formula's
        # value=None for M atoms must be rewritten to
        # VarRef(canonical_bind_name(M)) for the bind to actually
        # propagate. Without this rewrite, the evaluator hits
        # value=None in the inner P(m|x=True) and raises
        # InsufficientTheta — even though structurally the sum
        # binder is referenced elsewhere in the body.
        body = _bind_none_to_varref(body, sum_set)
        return _wrap_sum(state, body, sum_set)

    # Line 5: G has only one c-component → hedge → unidentifiable
    cc_full = c_components(graph, bidirected)
    cc_full = tuple(sorted(cc_full, key=_atomset_key))
    state.trail.append(cc_full)

    # Compare against c-components restricted to V (i.e. of G[V]).
    # If V == nodes(graph) (the typical case after ancestral shrink),
    # cc_full is exactly the partition of V.
    if len(cc_full) == 1 and cc_full[0] == V:
        state.hedge = V
        return None

    # Line 6: S equals a c-component of G
    S = cc_minus_x[0]
    if S in cc_full:
        return _build_q_factor(state, s=S, keep=y, summed_x=x)

    # Line 7 of the Shpitser algorithm: S ⊊ S' for some c-component S'
    # of G. ID(y, x ∩ S', Q[S'], G[S']) recursion needs symbolic
    # substitution of "current P" with Q[S'].
    #
    # Iter 141 attempted a "_build_q_factor(s=S', keep=y, summed_x=∅)
    # shortcut" claim that this directly yields the front-door inner
    # sum. Iter 143 traced the actual formula and found this is WRONG:
    # `_atom_to_target_va(atom)` always returns `value=state.x_value`
    # (literal True/False) when `atom ∈ state.x`, regardless of the
    # `summed_x` parameter. So for the front-door variant the inner
    # Σ_x body has `P(x=True) · P(y|x=True, m=True)` — both x and m
    # hardcoded to literal True instead of the bind variables. The
    # sum collapses degenerately:
    #     formula = P(x=True) · P(y|x=True)   (NOT front-door)
    # For real Line 7 implementation, _atom_to_target_va needs to
    # learn about which atoms are bind-summed vs do-substituted in
    # the current call site (parameterize, don't read state.x blind).
    # Reverting iter 141 until that machinery exists. See wall.md
    # iter 143 retraction note for full math trace.
    #
    # No real eval / L3 case has hit Line 7 to date — front-door
    # variants identify via the upstream ADMG-aware front-door path.
    # Punt: return None WITHOUT setting hedge so scheduler treats it
    # as needs_investigation rather than falsely claiming
    # unidentifiability. Setting state.hedge here would lie because
    # Line 7 cases are identifiable in principle, just not handled.
    return None


# ============================================ formula constructors


def _atomset_key(s: frozenset[Atom]) -> tuple:
    return tuple(sorted(
        (a.predicate, tuple(t.name for t in a.args)) for a in s
    ))


def _atom_predecessors(state: _IdState, v: Atom) -> tuple[Atom, ...]:
    """Atoms strictly before `v` in the ADMG-wide topological order."""
    out: list[Atom] = []
    for u in state.topo:
        if u == v:
            break
        out.append(u)
    return tuple(out)


def _build_q_factor(
    state: _IdState,
    *,
    s: frozenset[Atom],
    keep: frozenset[Atom],
    summed_x: frozenset[Atom],
) -> FormulaExpr:
    """Q[S] product form (Line 6).

    Q[S] = ∏_{v_i ∈ S, in topo order} P(v_i | v_{<i})

    The marginal we ultimately want is Σ_{S \\ keep} Q[S] (the
    intervention atoms in `summed_x` are NOT actually summed —
    they're substituted with their concrete do(...) values via the
    formula's free X slot).
    """
    factors: list[ProbabilityRefExpr] = []
    for v in state.topo:
        if v not in s:
            continue
        v_va = _atom_to_target_va(state, v)
        prior_atoms = _atom_predecessors(state, v)
        prior_vas = tuple(_atom_to_given_va(state, p) for p in prior_atoms)
        factors.append(ProbabilityRefExpr(target=v_va, given=prior_vas))

    body: FormulaExpr
    if len(factors) == 1:
        body = factors[0]
    else:
        body = ProductExpr(terms=tuple(factors))

    sum_atoms = s - keep - summed_x
    return _wrap_sum(state, body, sum_atoms)


def _build_marginal(
    state: _IdState,
    *,
    keep: frozenset[Atom],
    scope: frozenset[Atom],
) -> FormulaExpr:
    """Σ_{scope \\ keep} ∏_{v ∈ scope} P(v | v_{<v}) — Line 1 base case."""
    factors: list[ProbabilityRefExpr] = []
    for v in state.topo:
        if v not in scope:
            continue
        v_va = _atom_to_target_va(state, v)
        prior_atoms = _atom_predecessors(state, v)
        prior_vas = tuple(_atom_to_given_va(state, p) for p in prior_atoms)
        factors.append(ProbabilityRefExpr(target=v_va, given=prior_vas))

    if not factors:
        # Empty scope: degenerate; return a constant 1.
        from ..types import ConstantExpr
        return ConstantExpr(value=1.0)
    body: FormulaExpr = factors[0] if len(factors) == 1 else ProductExpr(terms=tuple(factors))

    sum_atoms = scope - keep
    return _wrap_sum(state, body, sum_atoms)


def _atom_to_target_va(state: _IdState, atom: Atom) -> ValuedAtom:
    """ValuedAtom for a probability_ref `target`. Free target atoms
    (i.e. y_atom in the outermost call) carry value=None — bound by
    the query. The user's TRUE intervention atoms (``state.do_atoms``,
    fixed across recursion) carry the concrete do() value. All other
    atoms — including ``state.x`` atoms that grew via Line 3 join or
    Line 4 c-component split — get a VarRef whose name matches the
    sum bind that will wrap them. The do_atoms / x split is the iter
    145 fix; pre-iter-145 used ``state.x`` directly here, which made
    Line 4 sub-recursion's enriched x atoms get hardcoded literal
    values instead of bind references (degenerate-sum bug)."""
    if atom in state.y:
        return ValuedAtom(atom=atom, value=None)
    if atom in state.do_atoms:
        return ValuedAtom(atom=atom, value=state.x_value)
    # Will be wrapped in a sum — issue the canonical VarRef name
    # `t_<predicate>` (deterministic; the wrap step uses the same key).
    return ValuedAtom(atom=atom, value=VarRef(name=_canonical_bind_name(atom)))


def _atom_to_given_va(state: _IdState, atom: Atom) -> ValuedAtom:
    """ValuedAtom for the `given` side of a probability_ref. Same value
    rules as the target side — the asymmetry (target vs given) is
    structural, not value-bearing."""
    return _atom_to_target_va(state, atom)


def _canonical_bind_name(atom: Atom) -> str:
    args = "_".join(a.name for a in atom.args)
    return f"t_{atom.predicate}_{args}" if args else f"t_{atom.predicate}"


def _bind_none_to_varref(
    formula: FormulaExpr,
    atoms: frozenset[Atom],
) -> FormulaExpr:
    """Rewrite every ``ValuedAtom`` whose ``atom`` is in ``atoms`` and
    whose ``value`` is None to use ``VarRef(_canonical_bind_name(atom))``.

    Used by Line 4's outer wrap to fix up sub-recursion formulas: when
    a sub_state was constructed with y={M}, its formula has M atoms
    carrying value=None ("locally bound externally"). When the outer
    Line 4 wraps with Σ_M binding the canonical name for M, those
    None values must become VarRef references for the bind to
    propagate through the evaluator's _resolve. Iter 147 fix: this
    rewrite was missing pre-iter-147; iter 145 only fixed the do-atom
    half of the substitution semantics.
    """
    from ..types import ConstantExpr

    def _maybe_rewrite_va(va: ValuedAtom) -> ValuedAtom:
        if va.atom in atoms and va.value is None:
            return ValuedAtom(
                atom=va.atom,
                value=VarRef(name=_canonical_bind_name(va.atom)),
            )
        return va

    if isinstance(formula, ConstantExpr):
        return formula
    if isinstance(formula, ProbabilityRefExpr):
        return ProbabilityRefExpr(
            target=_maybe_rewrite_va(formula.target),
            given=tuple(_maybe_rewrite_va(g) for g in formula.given),
        )
    if isinstance(formula, ProductExpr):
        return ProductExpr(terms=tuple(
            _bind_none_to_varref(t, atoms) for t in formula.terms
        ))
    if isinstance(formula, SumExpr):
        return SumExpr(
            bind=formula.bind,
            over=formula.over,
            body=_bind_none_to_varref(formula.body, atoms),
        )
    return formula


def _wrap_sum(
    state: _IdState,
    body: FormulaExpr,
    over: frozenset[Atom],
) -> FormulaExpr:
    """Wrap `body` in nested SumExpr nodes binding each atom in `over`.

    Nesting order is the ADMG topological order (outermost = earliest
    in topo) so the witness reads "deterministically inside-out".
    """
    if not over:
        return body
    ordered = [a for a in state.topo if a in over]
    out: FormulaExpr = body
    for atom in reversed(ordered):
        out = SumExpr(
            bind=BindDecl(name=_canonical_bind_name(atom)),
            over=atom,
            body=out,
        )
    return out
