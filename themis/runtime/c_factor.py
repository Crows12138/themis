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

from collections.abc import Mapping
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
    ValueExpr,
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
# Nested-ID queries are small in practice; beyond this the full path is not
# attempted and the query degrades to the IV escalation.
#
# The bound is gated by the exponential 2^|V| sites that used to trip a flaky
# native fault, not by identification (`_id` is cheap and fast — |V|=18 in
# ~150ms). Those sites are now ALL evaluated by VARIABLE ELIMINATION
# (~2^treewidth, no giant enumeration):
#   - the probe's ground-truth do-quantity + observational conditionals
#     (semantic_probe._true_do / _theta_from_scm),
#   - the probe's referenced-key collection (runtime.referenced_keys — the old
#     enumerate_keys materialised 2^#sums keys, millions past |V|≈18),
#   - the formula evaluation itself (runtime.ve_estimate_formula), shared by
#     the probe self-check AND the general-ID plug-in numeric end (bootstrap
#     re-evaluates it hundreds of times).
# Measured after VE: the probe self-check is crash-free over 64 runs across
# |V|=11-20 (was ~33% at |V|=15-16 with the recursive walk) and clean to
# |V|=24; a 200x production bootstrap is crash-free at |V|=12-16. The cap rises
# from the old pre-VE safe value (10) to 14 — comfortable margin over realistic
# nested-ID, well inside the validated crash-free zone. A denser (high-
# treewidth) estimand within the cap declines gracefully (probe → inconclusive;
# numeric end → EstimatorFailure), never a crash.
_FULL_LINE7_MAX_NODES = 14


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
    return _run_tian_id(graph, bidirected, {x_atom: x_value}, y_atom)


def identify_via_tian_joint(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    x_assignment: Mapping[Atom, object],
    y_atom: Atom,
) -> TianResult:
    """Run Shpitser-Pearl ID for a JOINT intervention on a SET of
    treatments, single target. The recursion is already set-based (``x``,
    ``do_atoms`` are sets); this exposes it for |X| ≥ 1.

    ``x_assignment`` IS the intervention: a value per treatment. Its keys
    are the do-set, so a corner of the treatment box is one argument
    rather than a set plus a level that every member has to share —
    ``{A: 1, B: 0}`` says do(A=1, B=0) the same way ``{A: 1, B: 1}`` says
    do(A=1, B=1). The joint contrast is two calls (the all-hi and all-lo
    corners) and the K-way interaction is a finite difference over all
    2^K of them; neither is a special case of the other.

    A joint estimand the compact Line-7 shortcut cannot express goes to the
    full nested Identify exactly as a single intervention's does, and its
    numeric self-check probes the formula under the whole assignment.
    """
    return _run_tian_id(graph, bidirected, dict(x_assignment), y_atom)


def _run_tian_id(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    x_values: Mapping[Atom, object],
    y_atom: Atom,
) -> TianResult:
    """Shared core for :func:`identify_via_tian` (single X) and
    :func:`identify_via_tian_joint` (set X). ``x_values`` is the
    intervention — an assignment whose keys are the do-set and whose values
    are the literals stamped into the outer occurrence of each."""
    x_set = frozenset(x_values)
    V = frozenset(graph.nodes()) | {a for pair in bidirected for a in pair}
    y_set = frozenset({y_atom})

    if not x_set or not (x_set <= V) or y_atom not in V:
        return TianResult(identifiable=False, formula=None)
    if y_atom in x_set:
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
        x_values=dict(x_values),
        trail=[],
    )
    formula, trail, hedge = _identify(state, caller_resolves=frozenset())
    if formula is None:
        return TianResult(
            identifiable=False, formula=None, witness_trail=trail, hedge=hedge,
        )
    return TianResult(identifiable=True, formula=formula, witness_trail=trail)


def _identify(
    state: _IdState,
    *,
    caller_resolves: frozenset[Atom],
) -> tuple[FormulaExpr | None, tuple, frozenset[Atom] | None]:
    """Run the ID recursion as every entry point runs it, returning
    ``(formula, trail, hedge)``: the single and joint effect through
    ``_run_tian_id``, IDC's numerator and denominator and ID*'s base case
    through ``_id_set_structural``. A retry held by one entry point is a
    nested-ID estimand the others punt on.

    The compact Line-7 shortcut may fail to express a genuine nested-ID
    estimand: either it PUNTS (returns None, with no definitive hedge —
    its inner verdict recursion mis-reads S' as a hedge, or an
    intervention inside S' is still an ancestor of Y there, which the
    shortcut cannot sum) or it emits a MALFORMED formula (a free, unbound
    sum variable from a variable that leaked out of S'). The canonical
    example is Pearl's napkin graph (W→Z→X→Y, W↔X, W↔Y). In either case,
    retry with Tian's full nested Identify, which expresses the estimand
    as the required ratio, and keep it only where the numeric self-check
    does not disprove it.

    Malformed is asked of the formula the caller will hold.
    ``caller_resolves`` names the atoms a caller reads as query-bound when
    the recursion leaves them tagged by a variable nothing binds (IDC's
    ``_apply_idc_values`` does, for Y and every Z): a free occurrence of
    one of those is not a leak, and every other free variable is.
    """
    formula = _id(state)
    if _caller_can_finish(formula, caller_resolves):
        return formula, tuple(state.trail), None
    if (
        state.hedge is None
        and state.graph.number_of_nodes() <= _FULL_LINE7_MAX_NODES
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
            full_formula = _bind_free_params(full_state, full_formula, keep=state.y)
        if (
            full_formula is not None
            and _caller_can_finish(full_formula, caller_resolves)
            and _full_line7_numerically_sound(
                full_state, full_formula, caller_resolves,
            )
        ):
            return full_formula, tuple(full_state.trail), None
    # Even the full path could not produce an estimand the caller can
    # finish — PUNT so the scheduler degrades to the IV escalation /
    # needs_investigation instead of crashing the public API.
    return None, tuple(state.trail), state.hedge if formula is None else None


def _caller_can_finish(
    formula: FormulaExpr | None,
    caller_resolves: frozenset[Atom],
) -> bool:
    """Is ``formula`` an estimand once its caller has read what it resolves
    as the query-bound holes they are? See :func:`_identify`."""
    return formula is not None and _formula_is_well_formed(
        _free_as_holes(formula, caller_resolves))


def _free_as_holes(
    formula: FormulaExpr,
    atoms: frozenset[Atom],
) -> FormulaExpr:
    """``formula`` with each occurrence of one of ``atoms`` that is tagged by
    a variable no enclosing sum binds read as the query-bound hole (None)
    it is: the reading ``_apply_idc_values`` gives a free target."""
    if not atoms:
        return formula

    def hole(va: ValuedAtom, bound: frozenset[str]) -> ValuedAtom:
        if (va.atom in atoms and isinstance(va.value, VarRef)
                and va.value.name not in bound):
            return ValuedAtom(atom=va.atom, value=None)
        return va

    return _map_valued_atoms(formula, hole)


# ============================================ internals


@dataclass
class _IdState:
    """Mutable state threaded through the recursion. Carries the full
    ADMG topo order so c-factor terms always reference the canonical
    predecessor sequence regardless of which subgraph ID is currently
    operating on.

    ``x`` is the algorithmic X for the current recursion level — it
    grows in Line 3 (W join) and changes in Line 4 sub-recursion
    (``x = V \\ s_i``). ``x_values`` is the ORIGINAL outer query's
    intervention, fixed across all recursion. Use ``do_atoms``
    (not ``x``) for "should this atom be substituted with the do-value
    literal in the formula?" — that question is about the user's
    semantic intervention, not the algorithmic recursion variable.
    They are threaded separately because collapsing them turns a sum
    bind into a literal do-value — the degenerate-sum bug.

    An intervention is an ASSIGNMENT: which atoms, and what each takes.
    ``x_values`` is that assignment, so ``do_atoms`` is its key set and
    not a second field to keep in step with it — a set plus one shared
    level can only say a UNIFORM corner do(X=v for all X), and every
    mixed corner do(A=1, B=0) is then not unimplemented but unsayable.
    """
    V: frozenset[Atom]
    x: frozenset[Atom]
    y: frozenset[Atom]
    graph: nx.DiGraph
    bidirected: BidirectedEdgeSet
    topo: tuple[Atom, ...]
    x_values: Mapping[Atom, object]
    trail: list[tuple[frozenset[Atom], ...]]
    hedge: frozenset[Atom] | None = None
    # Counter for fresh-bind names.
    _bind_seq: int = 0
    # Line 7 mode: False = the compact Q[S'] shortcut (correct for
    # front-door-style cases); True = Tian's full nested Identify (handles
    # napkin-style nested ID). _identify runs the shortcut first and re-runs
    # with this True when the shortcut gives no estimand its caller can finish.
    use_full_line7: bool = False

    @property
    def do_atoms(self) -> frozenset[Atom]:
        """The user's semantic intervention set — the assignment's keys.

        Derived rather than stored: dropping an atom from the do-set and
        dropping its value are the same act (Line 7 does exactly that), and
        two fields would let one happen without the other.
        """
        return frozenset(self.x_values)


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
    state: _IdState,
    formula: FormulaExpr,
    caller_resolves: frozenset[Atom],
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
    source.

    The question is the sub-problem's own: the joint distribution of its
    targets under its intervention. An intervention still holding the
    value-blind placeholder (IDC and ID* stamp values afterwards) is asked
    at every value, so is every target, and a free occurrence the caller
    resolves is asked as the hole it becomes. Imported locally to avoid an
    import cycle."""
    from ..verifier.semantic_probe import probe_intervention_formula

    def opened(va: ValuedAtom, _bound: frozenset[str]) -> ValuedAtom:
        if va.value is _IDC_VALUE_SENTINEL:
            return ValuedAtom(atom=va.atom, value=None)
        return va

    result = probe_intervention_formula(
        state.graph, state.bidirected,
        intervention={
            atom: None if value is _IDC_VALUE_SENTINEL else value
            for atom, value in state.x_values.items()
        },
        outcome=tuple(
            ValuedAtom(atom=target, value=None)
            for target in sorted(state.y, key=_atom_sort_key)
        ),
        given=(),
        formula=_map_valued_atoms(_free_as_holes(formula, caller_resolves), opened),
        k=3,
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
            x_values=state.x_values,
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
            x_values=state.x_values,
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
                x_values=state.x_values,
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
        # Each sub_formula was built with its OWN sub-state.y (e.g. {M}
        # for the s_i={M} branch), so M's occurrences carry value=None —
        # "bound by whoever holds this formula". That is true in
        # isolation and stops being true here: this sum takes M over.
        # ``_bind_and_sum`` is one operation for that reason.
        sum_set = V - (y | x)
        return _bind_and_sum(body, sum_set, state.topo)

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
    # algorithm recurses ID(y, x∩S', Q[S'], G[S']). When no intervention
    # inside S' is still an ancestor of Y within G[S'], that recursion
    # re-marginalizes all of them (Line 2 drops them, Line 1 sums), so the
    # result is Q[S'] (the c-factor product over S' in topo order)
    # marginalized to keep Y, with those interventions turned from do(...)
    # literals into BOUND SUM variables — i.e. dropped from do_atoms so
    # ``_atom_to_target_va`` issues a VarRef rather than the literal
    # x_value. That re-marginalization Σ_{x'} P(x')·P(y | x', ...) is
    # exactly the front-door inner sum. The shortcut below emits it only
    # under that condition.
    #
    # This same Q[S'] shortcut with the intervention left in do_atoms
    # collapses x to the literal do-value — it has to be dropped from
    # do_atoms here. The rule is: decide do-vs-sum per call site, do not
    # read a fixed do_atoms blind.
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
                # ones are bound once, at the top level, by _identify
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
                dist_state = replace(state, x_values={})
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
                q_s = _bind_do_value(q_s, state.x_values)
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
                x_values=state.x_values,
                trail=[],
            )
            if _id(verdict_state) is None:
                return None
            # An intervention still an ancestor of Y inside G[S'] is held at
            # its value by ID, not summed: do(f, b) on a with b→a, f↔a, f↔b
            # keeps b a parent of a in S' = {f, b, a}. Summing it answers
            # another question, so the shortcut declines and the full nested
            # Identify is retried.
            if x & s_prime & _ancestors_in_scope(verdict_state.graph, s_prime, y):
                return None
            # Identifiable: emit the Q[S'] re-marginalization formula. This
            # is well-formed UNLESS a variable outside S' leaks into S''s
            # c-factor conditioning (nested ID / napkin) — _identify detects
            # that malformedness and re-runs with use_full_line7.
            formula_state = replace(state, x_values={
                a: v for a, v in state.x_values.items() if a not in s_prime
            })
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
    return _bind_and_sum(body, sum_atoms, state.topo)


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
    return _bind_and_sum(body, sum_atoms, state.topo)


def _atom_to_target_va(state: _IdState, atom: Atom) -> ValuedAtom:
    """ValuedAtom for a probability_ref `target`. Free target atoms
    (i.e. y_atom in the outermost call) carry value=None — bound by
    the query. The user's TRUE intervention atoms (``state.x_values``,
    fixed across recursion) carry the concrete do() value — each its
    own, so a mixed corner reads off the same lookup a uniform one
    does. All other atoms — including ``state.x`` atoms that grew via
    Line 3 join or Line 4 c-component split — get a VarRef whose name
    matches the sum bind that will wrap them. Reading ``state.x``
    directly here instead of the intervention / x split gives Line 4
    sub-recursion's enriched x atoms hardcoded literal values in place
    of bind references — the degenerate-sum bug."""
    if atom in state.y:
        return ValuedAtom(atom=atom, value=None)
    if atom in state.x_values:
        return ValuedAtom(atom=atom, value=state.x_values[atom])
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


def _bind_occurrences(
    formula: FormulaExpr,
    atoms: frozenset[Atom],
) -> FormulaExpr:
    """Point every free occurrence of ``atoms`` at its canonical bind name.

    The private half of :func:`_bind_and_sum`, and not callable alone on
    purpose — a rewrite without the sum that justifies it names a binder
    that does not exist, which is the mirror of the defect the primitive
    was built to remove.

    ``value=None`` on an occurrence means "bound by whoever holds this
    formula". A sum taking the atom over makes that holder the sum, so
    the occurrence becomes ``VarRef(_canonical_bind_name(atom))``. An
    occurrence already carrying a VarRef or a do-value is left alone: it
    is bound by something nearer.
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
            _bind_occurrences(t, atoms) for t in formula.terms
        ))
    if isinstance(formula, SumExpr):
        return SumExpr(
            bind=formula.bind,
            over=formula.over,
            body=_bind_occurrences(formula.body, atoms),
        )
    if isinstance(formula, FractionExpr):
        return FractionExpr(
            numerator=_bind_occurrences(formula.numerator, atoms),
            denominator=_bind_occurrences(formula.denominator, atoms),
        )
    return formula


def _bind_do_value(
    formula: FormulaExpr,
    x_values: Mapping[Atom, object],
) -> FormulaExpr:
    """Apply the intervention at the Identify boundary: set every
    value=None occurrence of a do-atom to its own literal do-value.

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
        if va.atom in x_values and va.value is None:
            return ValuedAtom(atom=va.atom, value=x_values[va.atom])
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
            _bind_do_value(t, x_values) for t in formula.terms
        ))
    if isinstance(formula, SumExpr):
        return SumExpr(
            bind=formula.bind, over=formula.over,
            body=_bind_do_value(formula.body, x_values),
        )
    if isinstance(formula, FractionExpr):
        return FractionExpr(
            numerator=_bind_do_value(formula.numerator, x_values),
            denominator=_bind_do_value(formula.denominator, x_values),
        )
    return formula


def _bind_and_sum(
    body: FormulaExpr,
    over: frozenset[Atom],
    topo: tuple[Atom, ...],
) -> FormulaExpr:
    """``Σ_over body`` — binding what it takes over.

    Binding is not a step beside wrapping, it is what wrapping means. An
    occurrence carrying ``value=None`` is bound by whoever holds the
    formula — the query, or an enclosing construct not yet applied. The
    moment a sum here takes that atom over, the occurrence is bound HERE,
    and pointing it at this sum's own name is the whole content of
    "takes over".

    The two halves used to be two calls at three sites, and the failure
    mode of writing one is silent where it happens: the formula is built,
    and the evaluator later meets a ``value=None`` inside ``P(m | x=True)``
    with the binder sitting directly above it in the tree, and reports
    ``InsufficientTheta`` — a message about missing data, for a formula
    that is malformed. Every new binder in this module is created here so
    that half of the operation cannot ship alone;
    ``tests/test_a_sum_binds_what_it_takes_over.py`` refuses one built
    anywhere else.

    Which occurrences are bound is decided per level, and that is not a
    property of the atom: Tian's conditioning ratio puts the query's own
    target in the numerator as a query-bound hole and in the denominator
    under its own ``Σ_y``, the normalising constant. So the caller's
    ``over`` is the authority here, never "is this the query's Y".

    Nesting order is the ADMG topological order (outermost = earliest in
    topo) so the witness reads deterministically inside-out.
    """
    if not over:
        return body
    out: FormulaExpr = _bind_occurrences(body, over)
    for atom in reversed([a for a in topo if a in over]):
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
# being Pearl's napkin (W→Z→X→Y, W↔X, W↔Y: Z leaks into Q[{W,X,Y}]). It
# also DECLINES when an intervention inside S' is still an ancestor of Y
# within G[S']: ID holds that intervention at its value, the shortcut
# would sum it.
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
    return state.x_values.get(atom)


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
    """``Σ_{sum_atoms} formula``, plus the eager cancellation below.

    The marginalisation itself is :func:`_bind_and_sum`: taking a
    distribution variable over is the same operation here as in the ID
    recursion, and spelling it twice is what let the two drift.
    """
    sum_atoms = frozenset(sum_atoms)
    if not sum_atoms:
        return formula
    out: FormulaExpr = _bind_and_sum(formula, sum_atoms, topo)
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
        weight = ProbabilityRefExpr(
            target=ValuedAtom(atom=f, value=VarRef(name=_canonical_bind_name(f))),
            given=(),
        )
        out = _bind_and_sum(
            ProductExpr(terms=(weight, out)), frozenset({f}), state.topo,
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
        caller_resolves=free_targets,
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
        caller_resolves=free_targets,
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
    caller_resolves: frozenset[Atom] = frozenset(),
) -> tuple[FormulaExpr | None, tuple, frozenset[Atom] | None]:
    """Run the ID recursion for an arbitrary (set-valued) intervention
    ``x_set`` and target ``y_set``, returning ``(formula, trail, hedge)``.

    The recursion is value-blind, so do-atoms get the sentinel value;
    the caller stamps real values (``_apply_idc_values``, ID*'s base
    case). It runs through :func:`_identify` exactly as
    ``identify_via_tian`` does, the full nested Identify and its
    self-check included; ``caller_resolves`` is passed on to it.
    """
    state = _IdState(
        V=V,
        x=x_set,
        y=y_set,
        graph=graph,
        bidirected=bidirected,
        topo=full_topo,
        x_values=dict.fromkeys(x_set, _IDC_VALUE_SENTINEL),
        trail=[],
    )
    return _identify(state, caller_resolves=caller_resolves)


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
    everywhere) collapses that inner sum — the degenerate-sum bug, in
    the set-valued IDC path.

    - sentinel  → a genuine do-atom literal slot: the real intervention
      ``x_atom`` gets the concrete do-value; an exchanged Z (also in the
      do-set) becomes a query-bound hole (None).
    - free target (Y or any conditioned Z), NOT held by an enclosing sum
      → None, whether the recursion left it None or VarRef-marked it (a
      sub-recursion may tag a kept target with an unbound VarRef; with
      nothing binding that name it is query-bound here).
    - anything else → left untouched: a genuinely summed ``VarRef`` (the
      inner ``x'``, a mediator ``m``) bound by its enclosing ``SumExpr``.

    The scope test is what makes the second case a case rather than the
    whole story. Being a target of the QUESTION does not make every
    occurrence of that atom free: the IDC denominator ``ID(Z_rem, X')``
    marginalizes Y, so the recursion writes a ``Σ_y`` and marks Y's
    occurrences with its variable. Overwriting those with the query's
    y-value leaves a sum whose body no longer mentions what it sums over —
    the denominator becomes |dom(Y)| copies of the numerator and the whole
    ratio collapses to 1/|dom(Y)|, a confident number about nothing. Which
    is the same degenerate-sum disease the sentinel branch above is written
    to avoid, arriving through the door marked ``target``.
    """
    def fix(va: ValuedAtom, bound: frozenset[str]) -> ValuedAtom:
        if va.value is _IDC_VALUE_SENTINEL:
            new_value = x_value if va.atom == x_atom else None
            return ValuedAtom(atom=va.atom, value=new_value)
        held = isinstance(va.value, VarRef) and va.value.name in bound
        if va.atom in free_targets and not held:
            return va if va.value is None else ValuedAtom(atom=va.atom, value=None)
        return va

    return _map_valued_atoms(formula, fix)


def bind_idc_values(
    formula: FormulaExpr,
    value_map: "dict[Atom, ValueExpr | None]",
) -> FormulaExpr:
    """Fill the query-bound holes (``value=None``) that ``identify_via_idc``
    left on the free targets Y and each conditioned Z with the concrete
    values an EffectQuery supplies.

    ``identify_via_idc`` binds the intervention X to its do-value but leaves
    Y and every conditioned Z as ``value=None`` holes — the IdentifyQuery
    caller carries no values. An EffectQuery ``P(Y=y | do(X=x), Z=z)`` DOES;
    binding them grounds every ProbRef so the evaluator can compute a number.

    A hole is filled iff it is ``value is None`` AND its atom is a key of
    ``value_map``. This reaches BOTH target and given positions on purpose:
    an exchanged Z sits on the do-context (given) side, and a surviving
    ``Z_rem`` can appear as a numerator target AND as a chain-rule
    conditioning atom. Genuinely-summed ``VarRef`` occurrences (value is a
    VarRef, not None) and already-bound literals (X's do-value) are left
    untouched — this is the same discipline ``_apply_idc_values`` used to
    stamp the holes in the first place, run in reverse. Mirrors the binder
    proved correct to 1e-9 in ``test_idc_fraction_matches_latent_scm_ground_truth``.
    """
    def fix(va: ValuedAtom, _bound: frozenset[str]) -> ValuedAtom:
        if va.value is None and va.atom in value_map:
            return ValuedAtom(atom=va.atom, value=value_map[va.atom])
        return va

    return _map_valued_atoms(formula, fix)


def _map_valued_atoms(
    formula: FormulaExpr, fn, bound: frozenset[str] = frozenset(),
) -> FormulaExpr:
    """Structure-preserving map over every ``ValuedAtom`` in a formula.

    ``fn`` is called as ``fn(valued_atom, bound)``, where ``bound`` is the
    set of ``VarRef`` names an enclosing ``SumExpr`` binds at that
    position. Whether an occurrence is free or held by a sum is a fact
    about WHERE it sits, not about which atom it is; a caller that fills
    free slots cannot read that off the atom, and one that tries collapses
    the sum it was standing inside.
    """
    from ..types import ConstantExpr

    if isinstance(formula, ConstantExpr):
        return formula
    if isinstance(formula, ProbabilityRefExpr):
        return ProbabilityRefExpr(
            target=fn(formula.target, bound),
            given=tuple(fn(g, bound) for g in formula.given),
        )
    if isinstance(formula, ProductExpr):
        return ProductExpr(
            terms=tuple(_map_valued_atoms(t, fn, bound) for t in formula.terms))
    if isinstance(formula, SumExpr):
        return SumExpr(
            bind=formula.bind,
            over=formula.over,
            body=_map_valued_atoms(
                formula.body, fn, bound | {formula.bind.name}),
        )
    if isinstance(formula, FractionExpr):
        return FractionExpr(
            numerator=_map_valued_atoms(formula.numerator, fn, bound),
            denominator=_map_valued_atoms(formula.denominator, fn, bound),
        )
    return formula
