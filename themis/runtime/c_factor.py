"""Tian / Shpitser ID + IDC algorithms for ADMG identification.

Phase 2.latent ext §S3.b.2 — kicks in when ADMG-aware backdoor /
front-door / IV all fail. Implements Shpitser & Pearl 2006's complete
ID algorithm (which subsumes Tian 2002) plus IDC (the conditional
extension, "Identification of Conditional Interventional
Distributions").

``identify_via_tian`` covers the unconditional shape ``P(Y | do(X))``
— single intervention, single target, empty given — across all seven
lines of the recursion (ancestral shrink, descendant exclusion,
c-component split, hedge witness, Q[S] product, and the Line-7 S ⊊ S'
re-marginalization). Return shapes:

- ``identifiable=True`` with a ``formula`` — c-factor product witness.
- ``identifiable=False`` with a ``hedge`` — Shpitser Line-5 witness of
  provable unidentifiability.
- ``identifiable=False`` with no hedge — a Line-7 sub-case the verdict
  recursion could not settle without asserting a definitive hedge;
  scheduler routes to ``needs_investigation``.

``identify_via_idc`` covers the conditional shape
``P(Y | do(X), Z)`` (non-empty ``given``). It runs the do-calculus
Rule-2 exchange loop — moving each conditioned ``Z`` into the do-set
when ``Y ⊥ Z | X, (rest)`` holds in the mutilated graph
``G_{X̄, Z_}`` — then returns the normalized ratio
``ID(Y ∪ Z_rem, X') / ID(Z_rem, X')`` as a ``FractionExpr`` (or the
bare numerator when every Z exchanges away and no conditioning
remains). The two sub-problems reuse the same ID recursion; only the
value decoration differs (see ``_apply_idc_values``).

Output formula uses the c-factor product form for Q[S] (S a c-component
of the full ADMG): each variable in S contributes
``P(v_i | v_{<i})`` where ``v_{<i}`` are the variables earlier in the
ADMG topological order. This is the canonical witness for Tian
identifiability and matches what verifier replay re-checks.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import networkx as nx

from ..types import (
    Atom,
    BindDecl,
    FormulaExpr,
    FractionExpr,
    ProbabilityRefExpr,
    ProductExpr,
    SumExpr,
    ValuedAtom,
    VarRef,
)
from .formula_simplify import simplify_formula
from .structural_solver import BidirectedEdgeSet, c_components, is_m_connected


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


# Upper bound on graph size for the full nested-Identify Line-7 retry.
# Nested-ID queries are small in practice; beyond this the full path (and
# its numeric probe self-check) is not attempted and the query degrades.
_FULL_LINE7_MAX_NODES = 8


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

    # The compact Line-7 shortcut may fail to express a genuine nested-ID
    # estimand: either it PUNTS (returns None, with no definitive hedge —
    # its inner verdict recursion mis-reads S' as a hedge) or it emits a
    # MALFORMED formula (a free, unbound sum variable from a variable that
    # leaked out of S'). The canonical example is Pearl's napkin graph
    # (W→Z→X→Y, W↔X, W↔Y). In either case, retry with Tian's full nested
    # Identify, which expresses the estimand as the required ratio.
    shortcut_ok = formula is not None and _formula_is_well_formed(formula)
    if (
        not shortcut_ok
        and state.hedge is None
        and graph.number_of_nodes() <= _FULL_LINE7_MAX_NODES
    ):
        # The full nested Identify + its numeric probe self-check are
        # exponential in the graph; bound the attempt to small graphs
        # (nested-ID queries are small in practice). Larger graphs that the
        # shortcut can't express PUNT — the scheduler degrades to the IV
        # escalation / needs_investigation rather than risk an expensive
        # blow-up.
        full_state = replace(state, use_full_line7=True, trail=[], hedge=None)
        full_formula = _id(full_state)
        if full_formula is not None:
            # Bind the genuinely-free parameters ONCE at the top level —
            # variables Line 3 folded out of every S' that no enclosing sum
            # claimed (e.g. Z in the napkin). Doing it here, not inside the
            # Line-7 recursion, avoids double-binding a mediator an outer
            # Line-4 sum already owns.
            full_formula = _bind_free_params(full_state, full_formula, keep=y_set)
        if (
            full_formula is not None
            and _formula_is_well_formed(full_formula)
            and _full_line7_numerically_sound(
                graph, bidirected, x_atom, y_atom, x_value, full_formula
            )
        ):
            return TianResult(
                identifiable=True,
                formula=full_formula,
                witness_trail=tuple(full_state.trail),
            )

    if formula is None:
        return TianResult(
            identifiable=False,
            formula=None,
            witness_trail=tuple(state.trail),
            hedge=state.hedge,
        )
    if not _formula_is_well_formed(formula):
        # Even the full path could not produce a well-formed estimand —
        # PUNT so the scheduler degrades to the IV escalation /
        # needs_investigation instead of crashing the public API.
        return TianResult(
            identifiable=False,
            formula=None,
            witness_trail=tuple(state.trail),
            hedge=None,
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
    # Line 7 mode: False = the compact Q[S'] shortcut (correct for
    # front-door-style cases); True = Tian's full nested Identify (handles
    # napkin-style nested ID). identify_via_tian runs the shortcut first
    # and only re-runs with this True when the shortcut is malformed.
    use_full_line7: bool = False


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


def _formula_is_well_formed(formula: FormulaExpr) -> bool:
    """True iff ``formula`` passes the kernel formula grammar — in
    particular, every ``VarRef`` is bound by an enclosing ``SumExpr``.
    Used as a self-check so the ID/IDC engines never emit a malformed
    estimand (a free, unbound sum variable from an unhandled nested-ID
    case); they punt to needs_investigation instead. Imported locally to
    avoid a runtime↔input import cycle."""
    from ..input.semantic_validator import validate_formula, SemanticError

    try:
        validate_formula(formula)
        return True
    except SemanticError:
        return False


def _full_line7_numerically_sound(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    x_atom: Atom,
    y_atom: Atom,
    x_value,
    formula: FormulaExpr,
) -> bool:
    """Numeric self-check for the FULL nested-Identify Line-7 path — the
    hardest, least-battle-tested code in the engine. Probe the produced
    formula against random SCMs consistent with the graph and reject it
    only if the probe DISPROVES it (status ``mismatch``); ``match`` and
    ``inconclusive`` (cannot probe) both pass. This guarantees the full
    Line-7 path never EMITS a numerically-wrong estimand — a nested-ID
    case the construction gets wrong PUNTS (the scheduler then degrades to
    the IV escalation) instead of returning a confident wrong answer. The
    same probe backs the verifier; running it here closes the loop at the
    source. Imported locally to avoid an import cycle."""
    from ..verifier.semantic_probe import probe_identify_formula

    result = probe_identify_formula(
        graph, bidirected, x=x_atom, x_value=x_value, y=y_atom,
        given=(), formula=formula, k=3,
    )
    return result.status != "mismatch"


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
            use_full_line7=state.use_full_line7,
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
            use_full_line7=state.use_full_line7,
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
                use_full_line7=state.use_full_line7,
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

    # Line 7 of the Shpitser-Pearl algorithm: the single c-component S of
    # G\X is a STRICT subset of a c-component S' of the full G. The
    # algorithm recurses ID(y, x∩S', Q[S'], G[S']). For the kernel's
    # single-intervention / single-target scope the recursion always
    # re-marginalizes the intervention atoms that fall inside S' — an
    # intervention that stayed a parent of Y inside G[S'] would put X and
    # Y in one c-component (a bow-arc hedge), already caught at Line 5.
    # So the result is Q[S'] (the c-factor product over S' in topo order)
    # marginalized to keep Y, with those interventions turned from do(...)
    # literals into BOUND SUM variables — i.e. dropped from do_atoms so
    # ``_atom_to_target_va`` issues a VarRef rather than the literal
    # x_value. That re-marginalization Σ_{x'} P(x')·P(y | x', ...) is
    # exactly the front-door inner sum.
    #
    # Iter 141 tried this same Q[S'] shortcut but left the intervention in
    # do_atoms, so x collapsed to the literal do-value (the iter-143
    # retraction). Dropping it from do_atoms is the missing piece that
    # retraction asked for: decide do-vs-sum per call site, do not read a
    # fixed do_atoms blind.
    # Settle identifiability by recursing on G[S'] (throwaway trail): a
    # LOCAL bow-arc (X→Y direct inside S' together with X↔Y) is a hedge the
    # global Line-5 check missed — e.g. the IV graph Z→X→Y, X↔Y reaches
    # here and G[{X,Y}] is a bow arc. The sub-recursion's formula is built
    # from full-P (not the Q[S'] re-factorization), so we use only its
    # identifiability VERDICT.
    for s_prime in cc_full:
        if S < s_prime:
            if state.use_full_line7:
                # FULL: Tian's nested Identify(S, S', Q[S']). Return
                # Σ_{S\y} of the recursively-computed c-factor. Variables
                # that fell outside S' (e.g. Z in the napkin) are left as
                # value=None here — an ENCLOSING context may still bind
                # them (a Line-4 Σ over a mediator), so the genuinely-free
                # ones are bound once, at the top level, by identify_via_tian
                # (_bind_free_params). Binding them here would double-count
                # a variable an outer sum already owns (the extended-napkin
                # bug).
                # Identify is do-AGNOSTIC (Tian Lemma 4 / Shpitser
                # c-identify): build Q[S'] and run the c-factor recursion
                # with NO do-awareness — the intervention is an ordinary
                # distribution variable, summed/conditioned by the c-factor
                # algebra. Threading the do-value into the inner sums (the
                # old `- do_atoms`) degenerated the X-head ratio Q[H^(i)]/
                # Q[H^(i-1)] to 1 — coincidentally right for the napkin (X
                # terminal in S') but wrong when X is interior to S' (the
                # extended napkin: it dropped the c-factor ratio entirely).
                dist_state = replace(state, do_atoms=frozenset())
                q_sprime = _build_dist_cfactor(dist_state, s_prime)
                q_s = _identify_cfactor(
                    S, s_prime, q_sprime, graph, bidirected, state.topo,
                    frozenset(),
                )
                if q_s is None:
                    return None  # genuine hedge / unhandled
                # Apply do(X=x_value) HERE, after the c-factor ratios have
                # formed and been cancelled, then marginalize the remaining
                # S-variables to keep Y. X ∉ S, so it appears only in
                # conditionings; _bind_do_value sets its free occurrences to
                # the do-value (a still-summed X is left for the probe gate).
                q_s = _bind_do_value(q_s, state.do_atoms, state.x_value)
                return _dist_marginalize(q_s, S - y, state.topo)

            # SHORTCUT: settle identifiability by recursing on G[S'] (throw-
            # away trail). A LOCAL bow-arc (X→Y direct inside S' together
            # with X↔Y) is a hedge the global Line-5 check missed — e.g. the
            # IV graph Z→X→Y, X↔Y reaches here and G[{X,Y}] is a bow arc. The
            # sub-recursion's formula is built from full-P (not the Q[S']
            # re-factorization), so we use only its identifiability VERDICT.
            s_prime_nodes = s_prime & frozenset(graph.nodes())
            verdict_state = _IdState(
                V=s_prime,
                x=x & s_prime,
                y=y,
                graph=graph.subgraph(s_prime_nodes),
                bidirected=_restrict_bidirected(bidirected, s_prime),
                topo=state.topo,
                x_value=state.x_value,
                do_atoms=state.do_atoms,
                trail=[],
            )
            if _id(verdict_state) is None:
                return None
            # Identifiable: emit the Q[S'] re-marginalization formula. This
            # is well-formed UNLESS a variable outside S' leaks into S''s
            # c-factor conditioning (nested ID / napkin) — identify_via_tian
            # detects that malformedness and re-runs with use_full_line7.
            formula_state = replace(state, do_atoms=state.do_atoms - s_prime)
            return _build_q_factor(
                formula_state, s=s_prime, keep=y, summed_x=frozenset(),
            )
    return None


# ============================================ formula constructors


def _atomset_key(s: frozenset[Atom]) -> tuple:
    return tuple(sorted(
        (a.predicate, tuple(t.name for t in a.args)) for a in s
    ))


def _atom_predecessors(state: _IdState, v: Atom) -> tuple[Atom, ...]:
    """Predecessors of `v` for its c-factor term: atoms strictly before
    `v` in the ADMG-wide topological order AND inside the current scope
    ``state.V``.

    The full-graph topo (``state.topo``) is kept only for a CONSISTENT
    ordering across recursive calls; the conditioning set ``v^{(i-1)}`` of
    a c-factor ``P(v | v^{(i-1)})`` is over the CURRENT problem's vertex
    set ``V``, not the whole original graph. Without the ``in state.V``
    filter, an ancestral shrink (Line 2) that drops irrelevant nodes still
    leaks them into the conditioning as free, unbound VarRefs — e.g.
    P(health | do(exercise)) in a graph that also contains an unrelated
    stress→smokes→cancer triangle conditioned health on stress/smokes/
    cancer, producing ``free VarRef`` that validate_formula rejects.
    """
    out: list[Atom] = []
    for u in state.topo:
        if u == v:
            break
        if u in state.V:
            out.append(u)
    return tuple(out)


def _relevant_conditioning(
    state: _IdState,
    v: Atom,
    prior_atoms: tuple[Atom, ...],
) -> tuple[Atom, ...]:
    """Reduce a c-factor's conditioning ``P(v | prior_atoms)`` to v's
    Markov pillow: drop every predecessor ``p`` that ``v`` is m-separated
    from given the rest. By the ADMG ordered local Markov property this
    leaves the value unchanged (``P(v | rest, p) = P(v | rest)`` whenever
    ``v ⊥ p | rest``), and m-separation is ADMG-aware so a predecessor in
    ``v``'s bidirected district is never dropped.

    Why this is load-bearing, not cosmetic: Line 3 folds variables that
    are non-ancestors of Y in G_{X̄} into the intervention set ``x`` — they
    carry NO do-value, so if they survive into a c-factor's conditioning
    (as topo-predecessors) they become unbound free VarRefs that
    validate_formula rejects. The classic trigger is an irrelevant
    upstream variable, e.g. Z→X in a W-confounded P(Y|do(X)): Z is an
    ancestor of Y only through the now-severed X, so Y ⊥ Z | parents and
    Z is correctly dropped here.
    """
    if not prior_atoms:
        return prior_atoms
    prior_set = frozenset(prior_atoms)
    kept: list[Atom] = []
    for p in prior_atoms:
        rest = tuple(prior_set - {p})
        if is_m_connected(state.graph, state.bidirected, v, p, rest):
            kept.append(p)
    return tuple(kept)


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
        prior_atoms = _relevant_conditioning(
            state, v, _atom_predecessors(state, v))
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
        prior_atoms = _relevant_conditioning(
            state, v, _atom_predecessors(state, v))
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
    if isinstance(formula, FractionExpr):
        return FractionExpr(
            numerator=_bind_none_to_varref(formula.numerator, atoms),
            denominator=_bind_none_to_varref(formula.denominator, atoms),
        )
    return formula


def _bind_do_value(
    formula: FormulaExpr,
    do_atoms: frozenset[Atom],
    x_value,
) -> FormulaExpr:
    """Apply ``do(X = x_value)`` at the Identify boundary: set every
    value=None occurrence of a do-atom to its literal do-value.

    Tian's Identify / Shpitser's c-identify compute a PURE c-factor — the
    subroutine is do-AGNOSTIC, treating the intervention as an ordinary
    distribution variable (Tian-Pearl R-290-L Lemma 4; causaleffect
    ``compute.c.factor`` takes no do/x argument). The intervention enters
    only HERE, after the c-factor ratios have formed and been cancelled by
    ``simplify_formula``. A do-atom still bound by an inner sum
    (value=VarRef, not None) is left untouched: if simplification could not
    cancel that sum the estimand is malformed and the probe gate punts it,
    so a slip can never emit a wrong number."""
    from ..types import ConstantExpr

    def rw(va: ValuedAtom) -> ValuedAtom:
        if va.atom in do_atoms and va.value is None:
            return ValuedAtom(atom=va.atom, value=x_value)
        return va

    if isinstance(formula, ConstantExpr):
        return formula
    if isinstance(formula, ProbabilityRefExpr):
        return ProbabilityRefExpr(
            target=rw(formula.target),
            given=tuple(rw(g) for g in formula.given),
        )
    if isinstance(formula, ProductExpr):
        return ProductExpr(terms=tuple(
            _bind_do_value(t, do_atoms, x_value) for t in formula.terms
        ))
    if isinstance(formula, SumExpr):
        return SumExpr(
            bind=formula.bind, over=formula.over,
            body=_bind_do_value(formula.body, do_atoms, x_value),
        )
    if isinstance(formula, FractionExpr):
        return FractionExpr(
            numerator=_bind_do_value(formula.numerator, do_atoms, x_value),
            denominator=_bind_do_value(formula.denominator, do_atoms, x_value),
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


# ===================================== Line 7 — full nested identification
#
# The Q[S'] SHORTCUT (in _id Line 7) handles the cases where marginalising
# Q[S'] directly gives the answer (front-door and friends). It FAILS — a
# free, unbound sum variable — when a variable OUTSIDE S' (its own
# c-component) leaks into S''s c-factor conditioning, the canonical example
# being Pearl's napkin (W→Z→X→Y, W↔X, W↔Y: Z leaks into Q[{W,X,Y}]).
#
# The complete algorithm is Tian's recursive Identify(C, T, Q[T]): compute
# the c-factor Q[C] from a SYMBOLIC distribution Q over T, by alternating
# marginalisation and conditioning (the conditioning introduces the RATIOS
# that make the napkin identifiable). The functions below operate on a
# distribution represented as ``(FormulaExpr, vars)`` — the formula is a
# c-factor whose distribution variables carry value=None (marginalisation
# binds them); real interventions carry their do-value.


def _dist_value(state: _IdState, atom: Atom):
    """Value of an atom inside a symbolic distribution: the do-value for a
    real intervention, else None (a distribution variable / free parameter
    that a later marginalisation or the free-param bind will resolve)."""
    return state.x_value if atom in state.do_atoms else None


def _build_dist_cfactor(state: _IdState, s: frozenset[Atom]) -> FormulaExpr:
    """Q[S] as a SYMBOLIC distribution over ``s``: the c-factor product
    ``∏_{v∈S, topo} P(v | Markov-pillow(v))`` with distribution variables
    left at value=None (unbound), real interventions at their do-value.
    Unlike ``_build_q_factor`` this does NOT marginalise — the Identify
    recursion drives all summation."""
    factors: list[ProbabilityRefExpr] = []
    for v in state.topo:
        if v not in s:
            continue
        preds = _relevant_conditioning(state, v, _atom_predecessors(state, v))
        factors.append(ProbabilityRefExpr(
            target=ValuedAtom(atom=v, value=_dist_value(state, v)),
            given=tuple(
                ValuedAtom(atom=p, value=_dist_value(state, p)) for p in preds
            ),
        ))
    if not factors:
        from ..types import ConstantExpr
        return ConstantExpr(value=1.0)
    return factors[0] if len(factors) == 1 else ProductExpr(terms=tuple(factors))


def _dist_marginalize(
    formula: FormulaExpr,
    sum_atoms: frozenset[Atom],
    topo: tuple[Atom, ...],
) -> FormulaExpr:
    """``Σ_{sum_atoms} formula`` — bind each summed atom's value=None
    occurrences to its canonical VarRef, then wrap in nested SumExpr
    (topo order, outermost earliest)."""
    sum_atoms = frozenset(sum_atoms)
    if not sum_atoms:
        return formula
    body = _bind_none_to_varref(formula, sum_atoms)
    out: FormulaExpr = body
    for atom in reversed([a for a in topo if a in sum_atoms]):
        out = SumExpr(
            bind=BindDecl(name=_canonical_bind_name(atom)), over=atom, body=out,
        )
    # Simplify EAGERLY, between construction steps (Phase 16). The
    # do-agnostic Identify forms c-factor ratios (Lemma 4) whose summed
    # variables telescope by the sum-to-one identity; cancelling them as
    # they are built keeps every intermediate estimand bounded through the
    # nested recursion. Proven value-preserving; the full Line-7 path is
    # probe-gated regardless.
    return simplify_formula(out)


def _dist_conditional(
    formula: FormulaExpr,
    dist_vars: frozenset[Atom],
    v: Atom,
    given: frozenset[Atom],
    topo: tuple[Atom, ...],
    do_atoms: frozenset[Atom],
) -> FormulaExpr:
    """``Q(v | given) = [Σ_{dist\\(given∪v∪do)} Q] / [Σ_{dist\\(given∪do)} Q]``
    — a conditional of the symbolic distribution. Do-atoms are the query
    intervention: they are NEVER summed (they sit at their do-value), so
    they are excluded from both marginalisations. The ratio is exact and
    is what makes nested-ID estimands fractions."""
    num = _dist_marginalize(formula, dist_vars - given - {v} - do_atoms, topo)
    den = _dist_marginalize(formula, dist_vars - given - do_atoms, topo)
    # Cancel the shared factors of the c-factor ratio Q[H^(i)]/Q[H^(i-1)]
    # (Lemma 4): numerator and denominator are marginalizations of the same
    # Q differing only by whether v is summed, so they share a long common
    # factor. Eager simplify keeps the ratio from compounding through the
    # recursion. do_atoms is empty on the do-agnostic Identify path.
    return simplify_formula(FractionExpr(numerator=num, denominator=den))


def _dist_cfactor_from(
    formula: FormulaExpr,
    dist_vars: frozenset[Atom],
    s: frozenset[Atom],
    topo: tuple[Atom, ...],
    do_atoms: frozenset[Atom],
) -> FormulaExpr:
    """c-factor ``Q[S]`` computed FROM the symbolic distribution
    ``formula`` over ``dist_vars``: ``∏_{v∈S, topo} Q(v | dist-preds(v))``,
    where dist-preds(v) are the variables of the distribution strictly
    before v in topo order."""
    factors: list[FormulaExpr] = []
    seen: list[Atom] = []
    for v in topo:
        if v not in dist_vars:
            continue
        if v in s:
            given = frozenset(seen)
            factors.append(
                _dist_conditional(formula, dist_vars, v, given, topo, do_atoms))
        seen.append(v)
    if not factors:
        from ..types import ConstantExpr
        return ConstantExpr(value=1.0)
    return factors[0] if len(factors) == 1 else ProductExpr(terms=tuple(factors))


def _identify_cfactor(
    c: frozenset[Atom],
    t: frozenset[Atom],
    q_formula: FormulaExpr,
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    topo: tuple[Atom, ...],
    do_atoms: frozenset[Atom],
) -> FormulaExpr | None:
    """Tian's Identify: compute the c-factor ``Q[C]`` from a symbolic
    distribution ``q_formula`` = ``Q[T]`` over ``t`` (``C ⊆ T``), or None
    if ``C`` is not identifiable from ``Q[T]`` (a hedge).

    Recurrence: ``A = An_{G[T]}(C)``.
    - ``A == C``  → Q[C] = Σ_{(T\\C)\\do} Q[T].
    - ``A == T``  → FAIL (hedge).
    - ``C ⊆ A ⊂ T`` → marginalise Q[T] to A, take the c-factor of the
      c-component of G[A] that contains C, and recurse on it.

    ``do_atoms`` (the query intervention) are kept at their do-value and
    never summed — excluding them from the marginalisations is the fix for
    the extended-napkin degenerate sum (X is a member of S' AND the
    intervention)."""
    if c == t:
        return q_formula
    sub = graph.subgraph(t & frozenset(graph.nodes()))
    a = _ancestors_in_scope(sub, t, c)
    if a == c:
        return _dist_marginalize(q_formula, t - c - do_atoms, topo)
    if a == t:
        return None  # hedge — C not identifiable from Q[T]
    # C ⊆ A ⊂ T
    q_a = _dist_marginalize(q_formula, t - a - do_atoms, topo)
    sub_a = graph.subgraph(a & frozenset(graph.nodes()))
    bi_a = _restrict_bidirected(bidirected, a)
    comps = c_components(sub_a, bi_a)
    t_c = next((comp for comp in comps if c <= comp), None)
    if t_c is None:
        return None
    q_tc = _dist_cfactor_from(q_a, a, t_c, topo, do_atoms)
    return _identify_cfactor(c, t_c, q_tc, graph, bidirected, topo, do_atoms)


def _collect_none_atoms(formula: FormulaExpr) -> frozenset[Atom]:
    """Atoms appearing with value=None anywhere in ``formula`` — i.e. the
    still-unbound (query-target or free-parameter) slots."""
    from ..types import ConstantExpr

    out: set[Atom] = set()

    def walk(node: FormulaExpr) -> None:
        if isinstance(node, ConstantExpr):
            return
        if isinstance(node, ProbabilityRefExpr):
            for va in (node.target, *node.given):
                if va.value is None:
                    out.add(va.atom)
            return
        if isinstance(node, ProductExpr):
            for term in node.terms:
                walk(term)
            return
        if isinstance(node, SumExpr):
            walk(node.body)
            return
        if isinstance(node, FractionExpr):
            walk(node.numerator)
            walk(node.denominator)

    walk(formula)
    return frozenset(out)


def _bind_free_params(
    state: _IdState,
    formula: FormulaExpr,
    keep: frozenset[Atom],
) -> FormulaExpr:
    """Bind every free parameter of ``formula`` — a value=None atom that is
    NOT in ``keep`` (the query target). These are Line-3-folded variables
    that the nested identification left outside S' (e.g. Z in the napkin).
    The estimand is INVARIANT to them, so wrapping ``Σ_f P(f) · (...)`` with
    f's marginal both binds them and preserves the value. (Invariance is
    independently re-checked by the semantic probe.)"""
    free = _collect_none_atoms(formula) - keep
    if not free:
        return formula
    out = formula
    for f in [a for a in state.topo if a in free]:
        bound = _bind_none_to_varref(out, frozenset({f}))
        weight = ProbabilityRefExpr(
            target=ValuedAtom(atom=f, value=VarRef(name=_canonical_bind_name(f))),
            given=(),
        )
        out = SumExpr(
            bind=BindDecl(name=_canonical_bind_name(f)),
            over=f,
            body=ProductExpr(terms=(weight, bound)),
        )
    return out


# ============================================ IDC (conditional ID)


# Sentinel do-value used while the set-valued ID recursion builds the
# IDC sub-formulas. The real per-atom values (X's do-value, and the
# value=None query-bound holes for Y and Z) are stamped afterwards by
# ``_apply_idc_values`` — the structural recursion is value-blind, so
# any placeholder works.
_IDC_VALUE_SENTINEL = object()


@dataclass(frozen=True)
class IdcResult:
    """Result of conditional identification P(Y | do(X), Z) via IDC.

    ``exchanged`` are the Z atoms that the Rule-2 loop moved into the
    do-set; ``remaining_z`` are the Z atoms that stayed conditioned. When
    ``remaining_z`` is empty the formula is the bare interventional
    numerator (no division needed — every conditioned Z became
    irrelevant after the intervention); otherwise it is a
    ``FractionExpr``. Both sets are recorded so the verifier can replay
    the exchange independently.
    """
    identifiable: bool
    formula: FormulaExpr | None
    exchanged: frozenset[Atom] = frozenset()
    remaining_z: frozenset[Atom] = frozenset()
    is_fraction: bool = False
    hedge: frozenset[Atom] | None = None


def identify_via_idc(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    x_atom: Atom,
    y_atom: Atom,
    z_atoms,
    x_value,
) -> IdcResult:
    """Shpitser-Pearl IDC: identify the conditional interventional
    distribution ``P(Y | do(X), Z)``.

    Two phases:

    1. **Rule-2 exchange.** For each conditioned ``Z`` test whether
       ``Y ⊥ Z | X', (Z_set \\ {Z})`` holds in the mutilated ADMG
       ``G_{X'̄, Z_}`` (directed edges into the current do-set X' and
       bidirected edges at X' removed; directed edges out of Z removed).
       If so, conditioning on Z is equivalent to intervening on it (do-
       calculus Rule 2), so Z moves from the conditioning set into the
       do-set. Loop to a fixed point.
    2. **Normalize.** With X' the grown do-set and Z_rem the survivors,
       ``P(Y | do(X), Z) = ID(Y ∪ Z_rem, X') / ID(Z_rem, X')`` — the
       ratio of two ordinary (unconditional) interventional
       distributions, each handed to the ID recursion. When Z_rem is
       empty the denominator is 1 and the result is the bare numerator
       ``ID(Y, X')``.

    The intervention value is threaded onto X only; Y and Z are
    structural query-bound holes (value=None), matching the kernel's
    identify-query convention (target / given carry no values).
    """
    V = frozenset(graph.nodes()) | {a for pair in bidirected for a in pair}
    z_set = frozenset(z_atoms)
    y_set = frozenset({y_atom})

    if x_atom not in V or y_atom not in V:
        return IdcResult(identifiable=False, formula=None)
    if x_atom == y_atom or x_atom in z_set or y_atom in z_set:
        return IdcResult(identifiable=False, formula=None)
    if not (z_set <= V):
        return IdcResult(identifiable=False, formula=None)

    full_topo = tuple(_admg_topo_order(graph, V))

    do_set, z_rem = _rule2_exchange(graph, bidirected, x_atom, y_set, z_set)
    exchanged = do_set - {x_atom}
    # Free (value=None) targets: Y plus every conditioned Z (whether it
    # ended up exchanged into the do-set or stayed in Z_rem — in both
    # roles its value is the query-bound z, never X's do-value).
    free_targets = y_set | z_set

    # Numerator: ID(Y ∪ Z_rem, X').
    num_formula, _trail, num_hedge = _id_set_structural(
        graph, bidirected, full_topo, V, x_set=do_set, y_set=y_set | z_rem,
    )
    if num_formula is None:
        return IdcResult(identifiable=False, formula=None, hedge=num_hedge)
    num_formula = _apply_idc_values(
        num_formula, x_atom=x_atom, x_value=x_value, free_targets=free_targets,
    )

    if not z_rem:
        # Every conditioned Z exchanged away — the conditional collapses
        # to the plain interventional P(Y | do(X')). No fraction.
        if not _formula_is_well_formed(num_formula):
            return IdcResult(identifiable=False, formula=None, hedge=None)
        return IdcResult(
            identifiable=True,
            formula=num_formula,
            exchanged=exchanged,
            remaining_z=frozenset(),
            is_fraction=False,
        )

    # Denominator: ID(Z_rem, X') = Σ_Y of the numerator, recomputed as
    # its own ID problem (Y is marginalized — it is neither a target nor
    # in the do-set, so the recursion sums it out).
    den_formula, _dtrail, den_hedge = _id_set_structural(
        graph, bidirected, full_topo, V, x_set=do_set, y_set=z_rem,
    )
    if den_formula is None:
        return IdcResult(identifiable=False, formula=None, hedge=den_hedge)
    den_formula = _apply_idc_values(
        den_formula, x_atom=x_atom, x_value=x_value, free_targets=free_targets,
    )

    formula = FractionExpr(numerator=num_formula, denominator=den_formula)
    if not _formula_is_well_formed(formula):
        return IdcResult(identifiable=False, formula=None, hedge=None)
    return IdcResult(
        identifiable=True,
        formula=formula,
        exchanged=exchanged,
        remaining_z=z_rem,
        is_fraction=True,
    )


def _atom_sort_key(a: Atom) -> tuple:
    return (a.predicate, tuple(t.name for t in a.args))


def _mutilate_for_rule2(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    do_set: frozenset[Atom],
    underline: Atom,
) -> tuple[nx.DiGraph, BidirectedEdgeSet]:
    """Build the do-calculus Rule-2 mutilated ADMG ``G_{do_set̄, underline_}``.

    - ``G_{X̄}`` (intervention on every node in ``do_set``): remove
      directed edges *into* those nodes AND bidirected edges incident to
      them. Cutting the bidirected edge is the ADMG-correct reading of
      intervention: a bidirected X↔W stands for a latent L→X, L→W, and
      ``do(X)`` severs L→X, dissolving the edge.
    - ``G_{Z_}`` (the underlined observed node): remove directed edges
      *out of* ``underline``. Its bidirected edges represent arrows
      *into* it (from a latent), so they are NOT removed.
    """
    g = graph.copy()
    for node in do_set:
        if node in g:
            g.remove_edges_from(list(g.in_edges(node)))
    if underline in g:
        g.remove_edges_from(list(g.out_edges(underline)))
    bi = frozenset(p for p in bidirected if p.isdisjoint(do_set))
    return g, bi


def _rule2_exchange(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    x_atom: Atom,
    y_set: frozenset[Atom],
    z_set: frozenset[Atom],
) -> tuple[frozenset[Atom], frozenset[Atom]]:
    """Run the IDC Rule-2 loop. Returns ``(do_set, z_remaining)``.

    Starts with ``do_set = {X}`` and the full conditioning set. Each
    round, the first ``Z`` (deterministic order) for which the whole
    target set ``Y`` is m-separated from ``Z`` given ``do_set ∪ (Z_set
    \\ {Z})`` in ``G_{do_set̄, Z_}`` is moved into the do-set. Repeats
    until no further exchange is possible.
    """
    do_set = frozenset({x_atom})
    cond_z = frozenset(z_set)

    changed = True
    while changed and cond_z:
        changed = False
        for zi in sorted(cond_z, key=_atom_sort_key):
            rest = cond_z - {zi}
            mg, mbi = _mutilate_for_rule2(graph, bidirected, do_set, zi)
            conditioning = tuple(do_set | rest)
            separated = all(
                not is_m_connected(mg, mbi, yj, zi, conditioning)
                for yj in y_set
            )
            if separated:
                do_set = do_set | {zi}
                cond_z = rest
                changed = True
                break

    return do_set, cond_z


def _id_set_structural(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    full_topo: tuple[Atom, ...],
    V: frozenset[Atom],
    *,
    x_set: frozenset[Atom],
    y_set: frozenset[Atom],
) -> tuple[FormulaExpr | None, tuple, frozenset[Atom] | None]:
    """Run the ID recursion for an arbitrary (set-valued) intervention
    ``x_set`` and target ``y_set``, returning ``(formula, trail, hedge)``.

    The recursion is value-blind, so do-atoms get the sentinel value;
    the caller stamps real values via ``_apply_idc_values``. This is the
    same ``_id`` the single-target ``identify_via_tian`` drives — the
    recursion already operates on frozensets, so no algorithmic change
    is needed for IDC's set-valued sub-problems.
    """
    state = _IdState(
        V=V,
        x=x_set,
        y=y_set,
        graph=graph,
        bidirected=bidirected,
        topo=full_topo,
        x_value=_IDC_VALUE_SENTINEL,
        do_atoms=x_set,
        trail=[],
    )
    formula = _id(state)
    return formula, tuple(state.trail), state.hedge


def _apply_idc_values(
    formula: FormulaExpr,
    *,
    x_atom: Atom,
    x_value,
    free_targets: frozenset[Atom],
) -> FormulaExpr:
    """Stamp IDC value semantics onto a structurally-built formula.

    Resolution is driven by the MARKER the ID recursion left on each
    ``ValuedAtom``, not by atom identity — this is the load-bearing
    distinction. The recursion can reintroduce the intervention variable
    as a SUMMED re-marginalization variable inside a c-factor (the inner
    ``Σ_x'`` of a front-door-style witness), tagging it ``VarRef``;
    that occurrence must stay bound by its sum, NOT be overwritten with
    the literal do-value. Reading atom identity alone (X → do-value
    everywhere) collapses that inner sum — the iter-143 degenerate-sum
    bug, in the set-valued IDC path.

    - sentinel  → a genuine do-atom literal slot: the real intervention
      ``x_atom`` gets the concrete do-value; an exchanged Z (also in the
      do-set) becomes a query-bound hole (None).
    - free target (Y or any conditioned Z) → None, regardless of whether
      the recursion left it None or VarRef-marked it (a sub-recursion may
      tag a kept target with an unbound VarRef; it is query-bound here).
    - anything else → left untouched: a genuinely summed ``VarRef`` (the
      inner ``x'``, a mediator ``m``) bound by its enclosing ``SumExpr``.
    """
    def fix(va: ValuedAtom) -> ValuedAtom:
        if va.value is _IDC_VALUE_SENTINEL:
            new_value = x_value if va.atom == x_atom else None
            return ValuedAtom(atom=va.atom, value=new_value)
        if va.atom in free_targets:
            return va if va.value is None else ValuedAtom(atom=va.atom, value=None)
        return va

    return _map_valued_atoms(formula, fix)


def _map_valued_atoms(formula: FormulaExpr, fn) -> FormulaExpr:
    """Structure-preserving map over every ``ValuedAtom`` in a formula."""
    from ..types import ConstantExpr

    if isinstance(formula, ConstantExpr):
        return formula
    if isinstance(formula, ProbabilityRefExpr):
        return ProbabilityRefExpr(
            target=fn(formula.target),
            given=tuple(fn(g) for g in formula.given),
        )
    if isinstance(formula, ProductExpr):
        return ProductExpr(terms=tuple(_map_valued_atoms(t, fn) for t in formula.terms))
    if isinstance(formula, SumExpr):
        return SumExpr(
            bind=formula.bind,
            over=formula.over,
            body=_map_valued_atoms(formula.body, fn),
        )
    if isinstance(formula, FractionExpr):
        return FractionExpr(
            numerator=_map_valued_atoms(formula.numerator, fn),
            denominator=_map_valued_atoms(formula.denominator, fn),
        )
    return formula
