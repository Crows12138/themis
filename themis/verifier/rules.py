"""Rules R1..R5 for slice V0 identify derivations.

Each rule is implemented independently of ``themis.runtime.*``. The
verifier deliberately re-derives structural facts rather than calling
``structural_solver`` or ``formula_builder`` — if the verifier and the
elaborator agree the derivation is accepted; if they disagree the
derivation is rejected. The verifier carries the theorem statements;
the elaborator merely claims to satisfy them.

Named rules in this file:

- R1 ``graph_is_dag``
- R2 ``d_separation_check``
- R3 ``backdoor_criterion``
- R4 ``backdoor_adjustment_formula``
- R5 ``identify_via_backdoor``
"""
from __future__ import annotations

from itertools import product
from typing import Any, Callable

import networkx as nx

from ..runtime.numeric_estimator import ProbabilityKey, Theta
from ..types import (
    Atom,
    BindDecl,
    ConstantExpr,
    CounterfactualQuery,
    FormulaExpr,
    IdentifyQuery,
    NumericInterval,
    NumericResult,
    ProbabilityRefExpr,
    ProductExpr,
    StepRef,
    StructuralResult,
    SumExpr,
    ValuedAtom,
    VarRef,
)
from .context import VerificationContext
from .errors import (
    RuleCheckFailed,
    UnknownRuleInputError,
)

# Numeric tolerance for R7/R8 equality checks. Formula evaluation in
# floating point can drift slightly even when the algebra is identical
# (associativity of addition, etc.). 1e-9 is generous for boolean
# probability problems while still catching real mismatches.
_NUMERIC_TOL = 1e-9


# ========================================================== R1

def _rule_graph_is_dag(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """R1: graph is acyclic.

    inputs:
        graph — the DAG being reasoned about (must equal ctx.graph).
    output:
        True iff the graph is acyclic.
    """
    graph = _require(inputs, "graph", step_index, "graph_is_dag")
    _assert_same_graph(graph, ctx.graph, step_index, "graph_is_dag")

    recomputed = nx.is_directed_acyclic_graph(graph)
    if recomputed != claimed_output:
        raise RuleCheckFailed(
            f"graph_is_dag claimed {claimed_output!r}, recomputed {recomputed!r}",
            step_index=step_index, rule="graph_is_dag",
        )


# ========================================================== R2

def _is_collider(graph: nx.DiGraph, a: Atom, b: Atom, c: Atom) -> bool:
    return graph.has_edge(a, b) and graph.has_edge(c, b)


def _path_is_open(
    graph: nx.DiGraph,
    path: tuple[Atom, ...],
    conditioning: frozenset[Atom],
) -> bool:
    """Pearl d-separation: a path is open iff every intermediate node
    does NOT block it. Non-collider blocked iff in conditioning;
    collider blocked iff neither it nor any descendant is in
    conditioning."""
    for i in range(1, len(path) - 1):
        prev, mid, nxt = path[i - 1], path[i], path[i + 1]
        if _is_collider(graph, prev, mid, nxt):
            activated = {mid} | nx.descendants(graph, mid)
            blocked = activated.isdisjoint(conditioning)
        else:
            blocked = mid in conditioning
        if blocked:
            return False
    return True


def _undirected_paths(graph: nx.DiGraph, src: Atom, dst: Atom):
    return nx.all_simple_paths(graph.to_undirected(as_view=True), src, dst)


def _check_d_separation(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    z: frozenset[Atom],
) -> bool:
    """True iff X and Y are d-separated given Z — i.e. every simple
    undirected path between them is blocked."""
    if x == y:
        return False
    if x not in graph or y not in graph:
        return False
    for raw in _undirected_paths(graph, x, y):
        if _path_is_open(graph, tuple(raw), z):
            return False
    return True


def _rule_d_separation_check(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """R2: ``d_separation_check(graph, x, y, z) -> bool``.

    True iff every undirected path between x and y is blocked by z
    under Pearl's rules.
    """
    graph = _require(inputs, "graph", step_index, "d_separation_check")
    _assert_same_graph(graph, ctx.graph, step_index, "d_separation_check")
    x = _require_atom(inputs, "x", step_index, "d_separation_check")
    y = _require_atom(inputs, "y", step_index, "d_separation_check")
    z = _require_atom_set(inputs, "z", step_index, "d_separation_check")

    recomputed = _check_d_separation(graph, x, y, z)
    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"d_separation_check claimed {claimed_output!r}, "
            f"recomputed {recomputed!r} for x={x.predicate}, "
            f"y={y.predicate}, |z|={len(z)}",
            step_index=step_index, rule="d_separation_check",
        )


# ========================================================== R3

def _graph_minus_x_outgoing(graph: nx.DiGraph, x: Atom) -> nx.DiGraph:
    """Return G_X̄ — G with all outgoing edges of X removed.

    Used in the second leg of the backdoor criterion: Z must d-separate
    X and Y in the graph whose only remaining X-edges are incoming, i.e.
    after cutting off X's influence on descendants.
    """
    mutated = graph.copy()
    out_edges = list(mutated.out_edges(x))
    mutated.remove_edges_from(out_edges)
    return mutated


def _rule_backdoor_criterion(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """R3: Z satisfies the backdoor criterion for (X, Y) relative to
    the conditioning set ``given`` (W) iff:

    (i) (Z ∪ W) ∩ (descendants(X) ∪ {X, Y}) = ∅
    (ii) in G with X's outgoing edges removed, (Z ∪ W) d-separates X from Y
    """
    graph = _require(inputs, "graph", step_index, "backdoor_criterion")
    _assert_same_graph(graph, ctx.graph, step_index, "backdoor_criterion")
    x = _require_atom(inputs, "x", step_index, "backdoor_criterion")
    y = _require_atom(inputs, "y", step_index, "backdoor_criterion")
    z = _require_atom_set(inputs, "z", step_index, "backdoor_criterion")
    given = _require_atom_set(
        inputs, "given", step_index, "backdoor_criterion", allow_missing=True,
    )
    conditioning = z | given

    if x not in graph or y not in graph:
        raise RuleCheckFailed(
            f"backdoor_criterion: x or y not in graph",
            step_index=step_index, rule="backdoor_criterion",
        )

    forbidden = nx.descendants(graph, x) | {x, y}
    leg_i = conditioning.isdisjoint(forbidden)

    bidir = getattr(ctx, "bidirected", frozenset()) or frozenset()
    if leg_i:
        if bidir:
            # Phase 2.latent S4: on ADMG contexts the leg-ii check is
            # "no m-back-door from X to Y is open under conditioning".
            # Independent verifier implementation — does not call
            # structural_solver.
            connected = _verifier_is_admg_backdoor_connected(
                graph, bidir, x, y, conditioning,
            )
            recomputed = not connected
        else:
            leg_ii = _check_d_separation(
                _graph_minus_x_outgoing(graph, x), x, y, conditioning
            )
            recomputed = leg_ii
    else:
        recomputed = False

    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"backdoor_criterion claimed {claimed_output!r}, recomputed "
            f"{recomputed!r} (leg_i={leg_i}, admg={bool(bidir)})",
            step_index=step_index, rule="backdoor_criterion",
        )


# ========================================================== R4

def _build_expected_backdoor_formula(
    target: ValuedAtom,
    intervention: ValuedAtom,
    adjustment_set: tuple[Atom, ...],
    observed: tuple[ValuedAtom, ...],
) -> FormulaExpr:
    """Independent reimplementation of the backdoor adjustment formula
    as specified by Pearl. This is the verifier's own statement of the
    theorem — it does NOT call ``formula_builder``.

    Shape:

        Z = () → P(Y=y | X=x, observed)
        Z = (Z1,...,Zk) →
            Σ_{z1} ... Σ_{zk}
              P(Y=y | X=x, Z1=z1,...,Zk=zk, observed)
              · Π_i P(Zi=zi | Z1=z1,...,Z_{i-1}=z_{i-1}, observed)
    """
    if len(adjustment_set) == 0:
        return ProbabilityRefExpr(target=target, given=(intervention,) + observed)

    # Bind names — use a deterministic scheme so the same (predicate,
    # args) yields the same bind name each time the verifier runs.
    def _bind_for(atom: Atom, taken: set) -> BindDecl:
        args = "_".join(a.name for a in atom.args)
        base = f"z_{atom.predicate}_{args}" if args else f"z_{atom.predicate}"
        if base not in taken:
            return BindDecl(name=base)
        i = 2
        while f"{base}_{i}" in taken:
            i += 1
        return BindDecl(name=f"{base}_{i}")

    taken: set[str] = set()
    binds: list[tuple[Atom, BindDecl, ValuedAtom]] = []
    for z in adjustment_set:
        b = _bind_for(z, taken)
        taken.add(b.name)
        binds.append((z, b, ValuedAtom(atom=z, value=VarRef(name=b.name))))

    z_valueds = tuple(vv for (_, _, vv) in binds)

    conditional = ProbabilityRefExpr(
        target=target,
        given=(intervention,) + z_valueds + observed,
    )
    factors: list[ProbabilityRefExpr] = []
    for i, (_, _, z_va) in enumerate(binds):
        prior = z_valueds[:i]
        factors.append(ProbabilityRefExpr(target=z_va, given=prior + observed))

    body: FormulaExpr = ProductExpr(terms=(conditional, *factors))
    for z_atom, bind, _ in reversed(binds):
        body = SumExpr(bind=bind, over=z_atom, body=body)
    return body


def _rule_backdoor_adjustment_formula(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """R4: given a target, an intervention, an adjustment set Z, and the
    observed conditioning W, the identifying formula is the Pearl backdoor
    adjustment.

    inputs:
        target — ValuedAtom (value may be None in identify context)
        intervention — ValuedAtom (value is the do(...) value)
        z — ordered tuple of adjustment atoms (topological order
            recommended so chain-rule factors align with parents)
        given — tuple of observed ValuedAtoms (may be empty)
    output:
        FormulaExpr matching the Pearl adjustment template.
    """
    target = _require(inputs, "target", step_index, "backdoor_adjustment_formula")
    intervention = _require(
        inputs, "intervention", step_index, "backdoor_adjustment_formula",
    )
    z_tuple = _require(inputs, "z", step_index, "backdoor_adjustment_formula")
    if not isinstance(z_tuple, tuple) or not all(isinstance(a, Atom) for a in z_tuple):
        raise UnknownRuleInputError(
            "backdoor_adjustment_formula.z must be a tuple of Atom",
            step_index=step_index, rule="backdoor_adjustment_formula",
        )
    observed = inputs.get("given", ())
    if not isinstance(observed, tuple):
        raise UnknownRuleInputError(
            "backdoor_adjustment_formula.given must be a tuple",
            step_index=step_index, rule="backdoor_adjustment_formula",
        )

    expected = _build_expected_backdoor_formula(target, intervention, z_tuple, observed)
    if expected != claimed_output:
        raise RuleCheckFailed(
            f"backdoor_adjustment_formula output does not match the "
            f"expected backdoor template (|z|={len(z_tuple)})",
            step_index=step_index, rule="backdoor_adjustment_formula",
        )


# ========================================================== R5

def _rule_identify_via_backdoor(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """R5: combine R3 (backdoor_criterion True) and R4 (the corresponding
    formula) into the claimed StructuralResult(value=True).

    inputs:
        criterion — StepRef pointing at the R3 step (output must be True)
        formula — StepRef pointing at the R4 step (output is the formula)
    output:
        StructuralResult(value=True, ...)
    """
    criterion_ref = _require(inputs, "criterion", step_index, "identify_via_backdoor")
    formula_ref = _require(inputs, "formula", step_index, "identify_via_backdoor")
    if not isinstance(criterion_ref, StepRef) or not isinstance(formula_ref, StepRef):
        raise UnknownRuleInputError(
            "identify_via_backdoor inputs must be StepRef",
            step_index=step_index, rule="identify_via_backdoor",
        )

    criterion_out = step_output_by_id.get(criterion_ref.step_id)
    formula_out = step_output_by_id.get(formula_ref.step_id)
    criterion_step = step_by_id.get(criterion_ref.step_id)
    formula_step = step_by_id.get(formula_ref.step_id)
    if criterion_out is None or formula_out is None:
        raise RuleCheckFailed(
            f"identify_via_backdoor: referenced step output missing "
            f"(criterion={criterion_ref.step_id}, formula={formula_ref.step_id})",
            step_index=step_index, rule="identify_via_backdoor",
        )
    if criterion_step is None or formula_step is None:
        raise RuleCheckFailed(
            f"identify_via_backdoor: referenced step metadata missing "
            f"(criterion={criterion_ref.step_id}, formula={formula_ref.step_id})",
            step_index=step_index, rule="identify_via_backdoor",
        )
    if criterion_step.rule != "backdoor_criterion":
        raise RuleCheckFailed(
            "identify_via_backdoor: criterion must reference a backdoor_criterion step",
            step_index=step_index, rule="identify_via_backdoor",
        )
    if formula_step.rule != "backdoor_adjustment_formula":
        raise RuleCheckFailed(
            "identify_via_backdoor: formula must reference a backdoor_adjustment_formula step",
            step_index=step_index, rule="identify_via_backdoor",
        )
    if criterion_out is not True:
        raise RuleCheckFailed(
            f"identify_via_backdoor: criterion step did not prove True "
            f"(got {criterion_out!r})",
            step_index=step_index, rule="identify_via_backdoor",
        )
    if not isinstance(formula_out, (ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr)):
        raise RuleCheckFailed(
            "identify_via_backdoor: formula step did not produce a FormulaExpr",
            step_index=step_index, rule="identify_via_backdoor",
        )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            f"identify_via_backdoor output must be a StructuralResult",
            step_index=step_index, rule="identify_via_backdoor",
        )
    if claimed_output.value is not True:
        raise RuleCheckFailed(
            f"identify_via_backdoor output must have value=True, "
            f"got {claimed_output.value!r}",
            step_index=step_index, rule="identify_via_backdoor",
        )


# ========================================================== A6 front-door

def _path_is_open_for_front_door(
    graph: nx.DiGraph,
    path: tuple[Atom, ...],
    conditioning: frozenset,
) -> bool:
    """Duplicate of the structural-solver d-separation check. The
    verifier keeps its own copy so the two layers cannot drift without
    a visible diff.
    """
    for i in range(1, len(path) - 1):
        u, v, w = path[i - 1], path[i], path[i + 1]
        if graph.has_edge(u, v) and graph.has_edge(w, v):  # collider
            activated = {v} | nx.descendants(graph, v)
            blocked = activated.isdisjoint(conditioning)
        else:
            blocked = v in conditioning
        if blocked:
            return False
    return True


def _backdoor_paths_for_front_door(
    graph: nx.DiGraph, a: Atom, b: Atom,
) -> tuple[tuple[Atom, ...], ...]:
    """Undirected simple paths from a to b whose first edge points
    INTO a. Independent reimplementation of structural_solver's
    ``backdoor_paths`` so the verifier does not silently depend on the
    runtime's helper drifting."""
    if a not in graph or b not in graph or a == b:
        return ()
    result: list[tuple[Atom, ...]] = []
    for p in nx.all_simple_paths(graph.to_undirected(as_view=True), a, b):
        path = tuple(p)
        if len(path) >= 2 and graph.has_edge(path[1], a):
            result.append(path)
    return tuple(result)


def _rule_front_door_criterion(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify that the mediator set Z satisfies Pearl's front-door
    criterion for (X, Y):

    (FD1) every directed path from X to Y passes through some z ∈ Z
    (FD2) no back-door path from X to any z ∈ Z is open under empty
          conditioning
    (FD3) every back-door path from z ∈ Z to Y is blocked by {X}

    inputs: graph, x, y, z (frozenset of atoms)
    output: bool
    """
    graph = _require(inputs, "graph", step_index, "front_door_criterion")
    _assert_same_graph(graph, ctx.graph, step_index, "front_door_criterion")
    x = _require_atom(inputs, "x", step_index, "front_door_criterion")
    y = _require_atom(inputs, "y", step_index, "front_door_criterion")
    z = _require_atom_set(inputs, "z", step_index, "front_door_criterion")

    if x not in graph or y not in graph or x == y:
        raise RuleCheckFailed(
            "front_door_criterion: x or y missing / identical",
            step_index=step_index, rule="front_door_criterion",
        )
    if not z:
        raise RuleCheckFailed(
            "front_door_criterion: mediator set must be non-empty",
            step_index=step_index, rule="front_door_criterion",
        )
    if (z & {x, y}):
        raise RuleCheckFailed(
            "front_door_criterion: mediator set must not contain x or y",
            step_index=step_index, rule="front_door_criterion",
        )

    # FD1
    fd1 = True
    for path in nx.all_simple_paths(graph, x, y):
        if not (set(path[1:-1]) & z):
            fd1 = False
            break

    bidir = getattr(ctx, "bidirected", frozenset()) or frozenset()

    # FD2
    fd2 = True
    if fd1:
        if bidir:
            # ADMG-aware: no open back-door m-path from X to any zi
            # under empty conditioning. Independent implementation.
            for zi in z:
                if _verifier_is_admg_backdoor_connected(
                    graph, bidir, x, zi, frozenset(),
                ):
                    fd2 = False
                    break
        else:
            for zi in z:
                for path in _backdoor_paths_for_front_door(graph, x, zi):
                    if _path_is_open_for_front_door(graph, path, frozenset()):
                        fd2 = False
                        break
                if not fd2:
                    break

    # FD3
    fd3 = True
    if fd1 and fd2:
        x_cond = frozenset({x})
        if bidir:
            # ADMG-aware: every back-door m-path from zi to Y must be
            # m-blocked by {x}.
            for zi in z:
                if _verifier_is_admg_backdoor_connected(
                    graph, bidir, zi, y, x_cond,
                ):
                    fd3 = False
                    break
        else:
            for zi in z:
                for path in _backdoor_paths_for_front_door(graph, zi, y):
                    if _path_is_open_for_front_door(graph, path, x_cond):
                        fd3 = False
                        break
                if not fd3:
                    break

    recomputed = fd1 and fd2 and fd3
    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"front_door_criterion claimed {claimed_output!r}, "
            f"recomputed {recomputed!r} (FD1={fd1}, FD2={fd2}, FD3={fd3}, "
            f"admg={bool(bidir)})",
            step_index=step_index, rule="front_door_criterion",
        )


def _build_expected_front_door_formula(
    target: ValuedAtom,
    intervention: ValuedAtom,
    mediators: tuple[Atom, ...],
) -> FormulaExpr:
    """Independent restatement of the front-door formula (Pearl Eq. 3.29
    for the single-mediator case; chain-rule generalisation for
    multi-mediator per Phase 6.front-door-multi).

    Deliberately does not import from formula_builder — the verifier is
    meant to catch regressions in the builder. The expected formula is
    built here from scratch mirroring the builder's topological
    chain-rule expansion; if the two disagree the verifier rejects.
    """
    if len(mediators) == 0:
        raise RuleCheckFailed(
            "front_door_adjustment_formula requires at least one mediator",
            step_index=0, rule="front_door_adjustment_formula",
        )
    x_atom = intervention.atom

    def _bind_for(atom: Atom, taken: set) -> BindDecl:
        args = "_".join(a.name for a in atom.args)
        base = f"z_{atom.predicate}_{args}" if args else f"z_{atom.predicate}"
        if base not in taken:
            return BindDecl(name=base)
        i = 2
        while f"{base}_{i}" in taken:
            i += 1
        return BindDecl(name=f"{base}_{i}")

    # Generate bind names for each mediator in topological order, then
    # one for x'. Each later name sees all prior names in ``taken``.
    taken: set[str] = set()
    z_binds: list = []
    z_vas: list[ValuedAtom] = []
    for z_atom in mediators:
        b = _bind_for(z_atom, taken)
        taken.add(b.name)
        z_binds.append(b)
        z_vas.append(ValuedAtom(atom=z_atom, value=VarRef(name=b.name)))
    x_bind = _bind_for(x_atom, taken)
    x_prime_va = ValuedAtom(atom=x_atom, value=VarRef(name=x_bind.name))

    # Inner sum: ∑_{x'} P(Y | X=x', Z1=z1, ..., Zk=zk) · P(X=x')
    inner_conditional = ProbabilityRefExpr(
        target=target, given=(x_prime_va, *z_vas),
    )
    x_prior = ProbabilityRefExpr(target=x_prime_va, given=())
    inner_body = ProductExpr(terms=(inner_conditional, x_prior))
    inner_sum = SumExpr(bind=x_bind, over=x_atom, body=inner_body)

    # Chain rule: P(Z1|X) · P(Z2|Z1,X) · ... · P(Zk|Z_{<k}, X)
    chain_factors: list = []
    for i, z_va in enumerate(z_vas):
        prior_mediators = tuple(z_vas[:i])
        chain_factors.append(
            ProbabilityRefExpr(
                target=z_va, given=(intervention,) + prior_mediators,
            )
        )

    body = ProductExpr(terms=tuple(chain_factors) + (inner_sum,))
    for z_atom, z_bind in reversed(list(zip(mediators, z_binds))):
        body = SumExpr(bind=z_bind, over=z_atom, body=body)
    return body


def _rule_front_door_adjustment_formula(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify that the claimed formula matches the canonical front-door
    template for the given target / intervention / mediator set.

    inputs: target (ValuedAtom), intervention (ValuedAtom), z (tuple of Atom)
    output: FormulaExpr
    """
    target = _require(inputs, "target", step_index, "front_door_adjustment_formula")
    intervention = _require(
        inputs, "intervention", step_index, "front_door_adjustment_formula",
    )
    z_tuple = _require(inputs, "z", step_index, "front_door_adjustment_formula")
    if not isinstance(z_tuple, tuple) or not all(isinstance(a, Atom) for a in z_tuple):
        raise UnknownRuleInputError(
            "front_door_adjustment_formula.z must be a tuple of Atom",
            step_index=step_index, rule="front_door_adjustment_formula",
        )
    if len(z_tuple) == 0:
        raise RuleCheckFailed(
            "front_door_adjustment_formula: mediator tuple must be non-empty",
            step_index=step_index, rule="front_door_adjustment_formula",
        )

    expected = _build_expected_front_door_formula(target, intervention, z_tuple)
    if expected != claimed_output:
        raise RuleCheckFailed(
            "front_door_adjustment_formula output does not match the "
            "canonical front-door template",
            step_index=step_index, rule="front_door_adjustment_formula",
        )


def _rule_identify_via_front_door(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Combine ``front_door_criterion`` (True) with
    ``front_door_adjustment_formula`` (the matching formula) into a
    StructuralResult(value=True). Same shape as identify_via_backdoor.
    """
    criterion_ref = _require(inputs, "criterion", step_index, "identify_via_front_door")
    formula_ref = _require(inputs, "formula", step_index, "identify_via_front_door")
    if not isinstance(criterion_ref, StepRef) or not isinstance(formula_ref, StepRef):
        raise UnknownRuleInputError(
            "identify_via_front_door inputs must be StepRef",
            step_index=step_index, rule="identify_via_front_door",
        )

    criterion_out = step_output_by_id.get(criterion_ref.step_id)
    formula_out = step_output_by_id.get(formula_ref.step_id)
    criterion_step = step_by_id.get(criterion_ref.step_id)
    formula_step = step_by_id.get(formula_ref.step_id)
    if criterion_out is None or formula_out is None:
        raise RuleCheckFailed(
            f"identify_via_front_door: referenced step output missing "
            f"(criterion={criterion_ref.step_id}, formula={formula_ref.step_id})",
            step_index=step_index, rule="identify_via_front_door",
        )
    if criterion_step is None or formula_step is None:
        raise RuleCheckFailed(
            f"identify_via_front_door: referenced step metadata missing",
            step_index=step_index, rule="identify_via_front_door",
        )
    if criterion_step.rule != "front_door_criterion":
        raise RuleCheckFailed(
            "identify_via_front_door: criterion must reference a "
            "front_door_criterion step",
            step_index=step_index, rule="identify_via_front_door",
        )
    if formula_step.rule != "front_door_adjustment_formula":
        raise RuleCheckFailed(
            "identify_via_front_door: formula must reference a "
            "front_door_adjustment_formula step",
            step_index=step_index, rule="identify_via_front_door",
        )
    if criterion_out is not True:
        raise RuleCheckFailed(
            f"identify_via_front_door: criterion step did not prove True "
            f"(got {criterion_out!r})",
            step_index=step_index, rule="identify_via_front_door",
        )
    if not isinstance(formula_out, (ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr)):
        raise RuleCheckFailed(
            "identify_via_front_door: formula step did not produce a FormulaExpr",
            step_index=step_index, rule="identify_via_front_door",
        )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            "identify_via_front_door output must be a StructuralResult",
            step_index=step_index, rule="identify_via_front_door",
        )
    if claimed_output.value is not True:
        raise RuleCheckFailed(
            f"identify_via_front_door output must have value=True, "
            f"got {claimed_output.value!r}",
            step_index=step_index, rule="identify_via_front_door",
        )


# ========================================================== Phase 6.iv S.IV.3

def _rule_iv_criterion_check(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify that (instrument Z, conditioning W) satisfies Pearl's IV
    criterion for (X, Y):

    (IV1 relevance)     Z is m-connected to X given W in G
    (IV2 exclusion +
     IV3 independence)  Z is m-separated from Y given W in
                        G[\\bar{X}] (G with X's outgoing edges removed)

    See PHASE_6_IV_CHARTER.md §3 for the formal reduction of Pearl's
    three IV conditions to a single m-separation check in the
    mutilated graph.

    inputs: graph, x, y, instrument, conditioning (frozenset of atoms)
    output: bool
    """
    graph = _require(inputs, "graph", step_index, "iv_criterion_check")
    _assert_same_graph(graph, ctx.graph, step_index, "iv_criterion_check")
    x = _require_atom(inputs, "x", step_index, "iv_criterion_check")
    y = _require_atom(inputs, "y", step_index, "iv_criterion_check")
    z = _require_atom(inputs, "instrument", step_index, "iv_criterion_check")
    w = _require_atom_set(inputs, "conditioning", step_index, "iv_criterion_check")

    if x not in graph or y not in graph or z not in graph:
        raise RuleCheckFailed(
            "iv_criterion_check: x, y, or instrument missing from graph",
            step_index=step_index, rule="iv_criterion_check",
        )
    if x == y or z == x or z == y:
        raise RuleCheckFailed(
            "iv_criterion_check: x, y, and instrument must be distinct",
            step_index=step_index, rule="iv_criterion_check",
        )
    if w & {x, y, z}:
        raise RuleCheckFailed(
            "iv_criterion_check: conditioning set must not contain x, y, or z",
            step_index=step_index, rule="iv_criterion_check",
        )

    bidir = getattr(ctx, "bidirected", frozenset()) or frozenset()
    w_tuple = tuple(w)

    # IV1 (relevance): Z and X m-connected given W in original G.
    iv1 = _verifier_is_m_connected(graph, bidir, z, x, w_tuple)

    # IV2 + IV3 (exogeneity + exclusion): in G with X's outgoing edges
    # removed, Z is m-separated from Y given W. Build mutilated graph
    # independently here — no delegation to structural_solver.
    mutilated = graph.copy()
    mutilated.remove_edges_from(list(mutilated.out_edges(x)))
    iv23 = not _verifier_is_m_connected(mutilated, bidir, z, y, w_tuple)

    recomputed = iv1 and iv23
    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"iv_criterion_check claimed {claimed_output!r}, "
            f"recomputed {recomputed!r} (IV1={iv1}, IV2+IV3={iv23}, "
            f"admg={bool(bidir)})",
            step_index=step_index, rule="iv_criterion_check",
        )


def _rule_identify_via_iv(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Consume an ``iv_criterion_check`` step (output True) and conclude
    that the query is structurally identifiable via IV.

    Unlike ``identify_via_front_door`` / ``identify_via_backdoor`` which
    also require a formula step, IV identification at the structural
    layer does NOT emit a closed-form formula — the Wald / 2SLS / LATE
    formula requires an additional assumption (monotonicity or
    linearity) chosen at the estimation layer (Phase 7). So the
    criterion step alone is the full witness.
    """
    criterion_ref = _require(inputs, "criterion", step_index, "identify_via_iv")
    if not isinstance(criterion_ref, StepRef):
        raise UnknownRuleInputError(
            "identify_via_iv.criterion must be a StepRef",
            step_index=step_index, rule="identify_via_iv",
        )

    criterion_out = step_output_by_id.get(criterion_ref.step_id)
    criterion_step = step_by_id.get(criterion_ref.step_id)
    if criterion_out is None or criterion_step is None:
        raise RuleCheckFailed(
            f"identify_via_iv: referenced step {criterion_ref.step_id!r} missing",
            step_index=step_index, rule="identify_via_iv",
        )
    if criterion_step.rule != "iv_criterion_check":
        raise RuleCheckFailed(
            "identify_via_iv: criterion must reference an iv_criterion_check step",
            step_index=step_index, rule="identify_via_iv",
        )
    if criterion_out is not True:
        raise RuleCheckFailed(
            f"identify_via_iv: criterion step did not prove True "
            f"(got {criterion_out!r})",
            step_index=step_index, rule="identify_via_iv",
        )
    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            "identify_via_iv output must be a StructuralResult",
            step_index=step_index, rule="identify_via_iv",
        )
    if claimed_output.value is not True:
        raise RuleCheckFailed(
            f"identify_via_iv output must have value=True, "
            f"got {claimed_output.value!r}",
            step_index=step_index, rule="identify_via_iv",
        )


# ===================================================== Phase 6.mediation S.M.3

def _rule_mediation_nde_nie_check(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify Pearl 2001 four-condition check for NDE/NIE identification.

    Given candidate adjustment set W:

    M1: Y m-separated from X given W in G\\bar{X}
    M2: M m-separated from X given W in G\\bar{X}
    M3: Y m-separated from M given {X} ∪ W in G\\bar{M}
    M4: W contains no descendants of X in G

    The check outputs True iff W satisfies all four conditions. A False
    output means W (possibly empty) does not identify NDE/NIE; callers
    typically pass adjustment=∅ as the witness for unidentifiability.

    Independent reimplementation — does not call structural_solver.
    """
    graph = _require(inputs, "graph", step_index, "mediation_nde_nie_check")
    _assert_same_graph(graph, ctx.graph, step_index, "mediation_nde_nie_check")
    x = _require_atom(inputs, "x", step_index, "mediation_nde_nie_check")
    y = _require_atom(inputs, "y", step_index, "mediation_nde_nie_check")
    m = _require_atom(inputs, "mediator", step_index, "mediation_nde_nie_check")
    w = _require_atom_set(
        inputs, "adjustment", step_index, "mediation_nde_nie_check"
    )

    if x not in graph or y not in graph or m not in graph:
        raise RuleCheckFailed(
            "mediation_nde_nie_check: x, y, or mediator missing from graph",
            step_index=step_index, rule="mediation_nde_nie_check",
        )
    if x == y or x == m or y == m:
        raise RuleCheckFailed(
            "mediation_nde_nie_check: x, y, and mediator must be distinct",
            step_index=step_index, rule="mediation_nde_nie_check",
        )
    if w & {x, y, m}:
        raise RuleCheckFailed(
            "mediation_nde_nie_check: adjustment must not contain x, y, or mediator",
            step_index=step_index, rule="mediation_nde_nie_check",
        )

    bidir = getattr(ctx, "bidirected", frozenset()) or frozenset()

    # M4: W has no X-descendants. Compute descendants from the directed
    # edges of G directly (BFS), without importing networkx.descendants.
    x_desc = _verifier_directed_descendants(graph, x)
    if w & x_desc:
        m4 = False
    else:
        m4 = True

    w_tuple = tuple(w)

    # Build G\bar{X} (X's outgoing edges removed)
    g_bar_x = graph.copy()
    g_bar_x.remove_edges_from(list(g_bar_x.out_edges(x)))

    # M1: Y ⊥ X | W in G\bar{X}
    m1 = not _verifier_is_m_connected(g_bar_x, bidir, x, y, w_tuple)

    # M2: M ⊥ X | W in G\bar{X}
    m2 = not _verifier_is_m_connected(g_bar_x, bidir, x, m, w_tuple)

    # Build G\bar{M} (M's outgoing edges removed)
    g_bar_m = graph.copy()
    g_bar_m.remove_edges_from(list(g_bar_m.out_edges(m)))

    # M3: Y ⊥ M | X, W in G\bar{M}
    xw_tuple = tuple(w | {x})
    m3 = not _verifier_is_m_connected(g_bar_m, bidir, m, y, xw_tuple)

    recomputed = m1 and m2 and m3 and m4
    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"mediation_nde_nie_check claimed {claimed_output!r}, "
            f"recomputed {recomputed!r} (M1={m1}, M2={m2}, M3={m3}, M4={m4})",
            step_index=step_index, rule="mediation_nde_nie_check",
        )


def _rule_mediation_cde_check(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify backdoor-based CDE(m) identification.

    C1: Y m-separated from X given W AND Y m-separated from M given W,
        both in G\\bar{XM} (outgoing edges from both X and M removed)
    C2: W contains no descendants of X or M in G

    Independent reimplementation — does not call structural_solver.
    """
    graph = _require(inputs, "graph", step_index, "mediation_cde_check")
    _assert_same_graph(graph, ctx.graph, step_index, "mediation_cde_check")
    x = _require_atom(inputs, "x", step_index, "mediation_cde_check")
    y = _require_atom(inputs, "y", step_index, "mediation_cde_check")
    m = _require_atom(inputs, "mediator", step_index, "mediation_cde_check")
    w = _require_atom_set(
        inputs, "adjustment", step_index, "mediation_cde_check"
    )

    if x not in graph or y not in graph or m not in graph:
        raise RuleCheckFailed(
            "mediation_cde_check: x, y, or mediator missing from graph",
            step_index=step_index, rule="mediation_cde_check",
        )
    if x == y or x == m or y == m:
        raise RuleCheckFailed(
            "mediation_cde_check: x, y, and mediator must be distinct",
            step_index=step_index, rule="mediation_cde_check",
        )
    if w & {x, y, m}:
        raise RuleCheckFailed(
            "mediation_cde_check: adjustment must not contain x, y, or mediator",
            step_index=step_index, rule="mediation_cde_check",
        )

    bidir = getattr(ctx, "bidirected", frozenset()) or frozenset()

    # C2: W has no descendants of X or M
    x_desc = _verifier_directed_descendants(graph, x)
    m_desc = _verifier_directed_descendants(graph, m)
    if w & (x_desc | m_desc):
        c2 = False
    else:
        c2 = True

    w_tuple = tuple(w)

    # Build G\bar{XM}: remove X's and M's outgoing edges
    g_bar_xm = graph.copy()
    g_bar_xm.remove_edges_from(list(g_bar_xm.out_edges(x)))
    g_bar_xm.remove_edges_from(list(g_bar_xm.out_edges(m)))

    # C1: both Y ⊥ X and Y ⊥ M given W in G\bar{XM}
    c1_x = not _verifier_is_m_connected(g_bar_xm, bidir, x, y, w_tuple)
    c1_m = not _verifier_is_m_connected(g_bar_xm, bidir, m, y, w_tuple)
    c1 = c1_x and c1_m

    recomputed = c1 and c2
    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"mediation_cde_check claimed {claimed_output!r}, "
            f"recomputed {recomputed!r} (C1={c1}, C2={c2})",
            step_index=step_index, rule="mediation_cde_check",
        )


def _rule_identify_via_mediation(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Consume a mediation_nde_nie_check and a mediation_cde_check and
    conclude structural identifiability of at least one decomposition.

    ``claimed_output.value`` must be True iff either referenced step
    output True. When both checks return False, the query is not
    identifiable by standard backdoor methods and claimed_output.value
    must be False.
    """
    nde_ref = _require(inputs, "nde_nie", step_index, "identify_via_mediation")
    cde_ref = _require(inputs, "cde", step_index, "identify_via_mediation")
    if not isinstance(nde_ref, StepRef) or not isinstance(cde_ref, StepRef):
        raise UnknownRuleInputError(
            "identify_via_mediation inputs must be StepRef",
            step_index=step_index, rule="identify_via_mediation",
        )

    nde_step = step_by_id.get(nde_ref.step_id)
    cde_step = step_by_id.get(cde_ref.step_id)
    nde_out = step_output_by_id.get(nde_ref.step_id)
    cde_out = step_output_by_id.get(cde_ref.step_id)

    if nde_step is None or cde_step is None:
        raise RuleCheckFailed(
            "identify_via_mediation: referenced step missing",
            step_index=step_index, rule="identify_via_mediation",
        )
    if nde_step.rule != "mediation_nde_nie_check":
        raise RuleCheckFailed(
            "identify_via_mediation: nde_nie must reference mediation_nde_nie_check",
            step_index=step_index, rule="identify_via_mediation",
        )
    if cde_step.rule != "mediation_cde_check":
        raise RuleCheckFailed(
            "identify_via_mediation: cde must reference mediation_cde_check",
            step_index=step_index, rule="identify_via_mediation",
        )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            "identify_via_mediation output must be a StructuralResult",
            step_index=step_index, rule="identify_via_mediation",
        )

    any_identifiable = bool(nde_out) or bool(cde_out)
    if claimed_output.value is not any_identifiable:
        raise RuleCheckFailed(
            f"identify_via_mediation output.value must be {any_identifiable!r} "
            f"(nde_nie={nde_out!r}, cde={cde_out!r}), got {claimed_output.value!r}",
            step_index=step_index, rule="identify_via_mediation",
        )


# ----- Phase 6.mediation Fix 1 (v0.1.4) — numeric evaluation rule -----

def _verifier_mediation_bind_for(atom: "Atom", taken: set) -> "BindDecl":
    """Verifier-side fresh bind-name generator. Uses a ``v_`` prefix to
    stay distinct from runtime's ``z_`` scheme — bind names don't have
    to byte-match between the two implementations (they only need to be
    unique within one formula tree)."""
    args = "_".join(t.name for t in atom.args)
    base = f"v_{atom.predicate}_{args}" if args else f"v_{atom.predicate}"
    if base not in taken:
        return BindDecl(name=base)
    i = 2
    while f"{base}_{i}" in taken:
        i += 1
    return BindDecl(name=f"{base}_{i}")


def _verifier_build_mediation_potential_outcome_formula(
    target: ValuedAtom,
    intervention_outer: ValuedAtom,
    intervention_inner: ValuedAtom,
    mediator: Atom,
    adjustment_set: tuple[Atom, ...],
    observed: tuple[ValuedAtom, ...],
) -> FormulaExpr:
    """Verifier-side independent reconstruction of the mediation
    potential-outcome g-formula. Does NOT call ``formula_builder``.

    Shape (Pearl 2001 + g-formula expansion)::

        E[Y(X=x_outer, M = M(X=x_inner))]
          = Σ_w  Σ_m  P(Y | X=x_outer, M=m, W=w)
                    · P(M=m | X=x_inner, W=w)
                    · ∏_i P(Wi=wi | W_{<i})

    The chain-rule factoring of P(W) and the cross-world M conditional
    are the two pieces a buggy runtime might get wrong; this
    independent rebuild lets the verifier detect either failure mode.
    """
    taken: set = set()
    w_binds: list[tuple[Atom, BindDecl, ValuedAtom]] = []
    for w_atom in adjustment_set:
        b = _verifier_mediation_bind_for(w_atom, taken)
        taken.add(b.name)
        w_va = ValuedAtom(atom=w_atom, value=VarRef(name=b.name))
        w_binds.append((w_atom, b, w_va))
    w_valueds = tuple(vv for (_, _, vv) in w_binds)

    m_bind = _verifier_mediation_bind_for(mediator, taken)
    m_va = ValuedAtom(atom=mediator, value=VarRef(name=m_bind.name))

    y_cond = ProbabilityRefExpr(
        target=target,
        given=(intervention_outer, m_va) + w_valueds + observed,
    )
    m_cond = ProbabilityRefExpr(
        target=m_va,
        given=(intervention_inner,) + w_valueds + observed,
    )
    w_factors: list[ProbabilityRefExpr] = []
    for i, (_, _, w_va) in enumerate(w_binds):
        prior = w_valueds[:i]
        w_factors.append(ProbabilityRefExpr(target=w_va, given=prior + observed))

    body: FormulaExpr = ProductExpr(terms=(y_cond, m_cond, *w_factors))
    body = SumExpr(bind=m_bind, over=mediator, body=body)
    for w_atom, b, _ in reversed(w_binds):
        body = SumExpr(bind=b, over=w_atom, body=body)
    return body


def _verifier_build_mediation_controlled_outcome_formula(
    target: ValuedAtom,
    intervention: ValuedAtom,
    mediator: ValuedAtom,
    adjustment_set: tuple[Atom, ...],
    observed: tuple[ValuedAtom, ...],
) -> FormulaExpr:
    """Verifier-side independent reconstruction of the CDE g-formula.
    Does NOT call ``formula_builder``.

    Shape::

        E[Y | do(X=x, M=m)]
          = Σ_w  P(Y | X=x, M=m, W=w) · ∏_i P(Wi=wi | W_{<i})

    When ``adjustment_set`` is empty, reduces to a single
    ``P(Y | X=x, M=m, observed)`` conditional.
    """
    if not adjustment_set:
        return ProbabilityRefExpr(
            target=target,
            given=(intervention, mediator) + observed,
        )

    taken: set = set()
    w_binds: list[tuple[Atom, BindDecl, ValuedAtom]] = []
    for w_atom in adjustment_set:
        b = _verifier_mediation_bind_for(w_atom, taken)
        taken.add(b.name)
        w_va = ValuedAtom(atom=w_atom, value=VarRef(name=b.name))
        w_binds.append((w_atom, b, w_va))
    w_valueds = tuple(vv for (_, _, vv) in w_binds)

    y_cond = ProbabilityRefExpr(
        target=target,
        given=(intervention, mediator) + w_valueds + observed,
    )
    w_factors: list[ProbabilityRefExpr] = []
    for i, (_, _, w_va) in enumerate(w_binds):
        prior = w_valueds[:i]
        w_factors.append(ProbabilityRefExpr(target=w_va, given=prior + observed))

    body: FormulaExpr = ProductExpr(terms=(y_cond, *w_factors))
    for w_atom, b, _ in reversed(w_binds):
        body = SumExpr(bind=b, over=w_atom, body=body)
    return body


def _rule_mediation_numeric_evaluate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify the bundled v0.1.4 mediation numeric evaluation step.

    Independently rebuilds the potential-outcome and/or CDE g-formulas
    from inputs + Pearl 2001 / g-formula specification, evaluates each
    against ``ctx.theta`` using the verifier's own
    ``_evaluate_formula``, recomputes the derived TE / NDE-at-control /
    NIE-at-treated / CDE-per-mediator-value quantities, and compares
    each component of ``claimed_output`` within ``_NUMERIC_TOL``.

    ``nde_nie_adjustment`` and ``cde_adjustment`` are optional inputs —
    their presence signals which branch the runtime ran. A
    ``nde_nie_status`` / ``cde_status`` entry in ``claimed_output``
    signals the runtime aborted that branch with InsufficientTheta; the
    verifier accepts the abort without recomputing (the abort itself is
    a valid outcome; the message is metadata for downstream consumers).
    """
    target = _require(inputs, "target", step_index, "mediation_numeric_evaluate")
    if not isinstance(target, ValuedAtom):
        raise RuleCheckFailed(
            "mediation_numeric_evaluate: target must be a ValuedAtom",
            step_index=step_index, rule="mediation_numeric_evaluate",
        )
    treated_va = _require(
        inputs, "intervention_treated", step_index, "mediation_numeric_evaluate"
    )
    control_va = _require(
        inputs, "intervention_control", step_index, "mediation_numeric_evaluate"
    )
    mediator = _require_atom(
        inputs, "mediator", step_index, "mediation_numeric_evaluate"
    )
    observed_raw = inputs.get("observed", ())
    observed: tuple[ValuedAtom, ...] = tuple(observed_raw) if observed_raw else ()

    nde_nie_adj = inputs.get("nde_nie_adjustment")
    cde_adj = inputs.get("cde_adjustment")

    if not isinstance(claimed_output, dict):
        raise RuleCheckFailed(
            "mediation_numeric_evaluate output must be a dict",
            step_index=step_index, rule="mediation_numeric_evaluate",
        )

    theta = getattr(ctx, "theta", None)
    if theta is None:
        raise RuleCheckFailed(
            "mediation_numeric_evaluate requires theta in VerificationContext",
            step_index=step_index, rule="mediation_numeric_evaluate",
        )

    graph = getattr(ctx, "graph", None)
    bidirected = getattr(ctx, "bidirected", None)

    # ---- NDE/NIE branch ----
    if nde_nie_adj is not None and "nde_nie_status" not in claimed_output:
        nde_w = tuple(nde_nie_adj)
        f_treated = _verifier_build_mediation_potential_outcome_formula(
            target, treated_va, treated_va, mediator, nde_w, observed,
        )
        f_control = _verifier_build_mediation_potential_outcome_formula(
            target, control_va, control_va, mediator, nde_w, observed,
        )
        # Both cross-world potentials — one per Pearl decomposition.
        f_cross_to = _verifier_build_mediation_potential_outcome_formula(
            target, treated_va, control_va, mediator, nde_w, observed,
        )
        f_cross_co = _verifier_build_mediation_potential_outcome_formula(
            target, control_va, treated_va, mediator, nde_w, observed,
        )
        try:
            e_y_treated = _evaluate_formula(
                f_treated, theta, {}, graph=graph, bidirected=bidirected
            )
            e_y_control = _evaluate_formula(
                f_control, theta, {}, graph=graph, bidirected=bidirected
            )
            e_y_cross_to = _evaluate_formula(
                f_cross_to, theta, {}, graph=graph, bidirected=bidirected
            )
            e_y_cross_co = _evaluate_formula(
                f_cross_co, theta, {}, graph=graph, bidirected=bidirected
            )
        except _NonConcreteValue as e:
            raise RuleCheckFailed(
                f"mediation_numeric_evaluate: NDE/NIE re-evaluation failed: {e}",
                step_index=step_index, rule="mediation_numeric_evaluate",
            )

        recomputed = {
            "e_y_treated":             e_y_treated,
            "e_y_control":             e_y_control,
            "e_y_cross_world":         e_y_cross_to,   # back-compat alias
            "e_y_cross_treated_outer": e_y_cross_to,
            "e_y_cross_control_outer": e_y_cross_co,
            "te":                      e_y_treated - e_y_control,
            "nde_at_control":          e_y_cross_to - e_y_control,
            "nie_at_treated":          e_y_treated - e_y_cross_to,
            "nde_at_treated":          e_y_treated - e_y_cross_co,
            "nie_at_control":          e_y_cross_co - e_y_control,
        }
        for key, expected in recomputed.items():
            if key not in claimed_output:
                raise RuleCheckFailed(
                    f"mediation_numeric_evaluate: claimed_output missing {key!r}",
                    step_index=step_index, rule="mediation_numeric_evaluate",
                )
            claimed = claimed_output[key]
            if not isinstance(claimed, (int, float)):
                raise RuleCheckFailed(
                    f"mediation_numeric_evaluate: {key} must be numeric, "
                    f"got {type(claimed).__name__}",
                    step_index=step_index, rule="mediation_numeric_evaluate",
                )
            if abs(float(claimed) - expected) > _NUMERIC_TOL:
                raise RuleCheckFailed(
                    f"mediation_numeric_evaluate: {key} mismatch — claimed "
                    f"{claimed!r}, recomputed {expected!r}",
                    step_index=step_index, rule="mediation_numeric_evaluate",
                )

    # ---- CDE branch ----
    if cde_adj is not None and "cde_status" not in claimed_output:
        if "cde" not in claimed_output:
            raise RuleCheckFailed(
                "mediation_numeric_evaluate: cde_adjustment supplied but no "
                "'cde' block in output",
                step_index=step_index, rule="mediation_numeric_evaluate",
            )
        claimed_cde = claimed_output["cde"]
        if not isinstance(claimed_cde, dict):
            raise RuleCheckFailed(
                "mediation_numeric_evaluate: 'cde' must be a dict",
                step_index=step_index, rule="mediation_numeric_evaluate",
            )
        cde_w = tuple(cde_adj)
        for m_val in theta.domain_of(mediator):
            m_va = ValuedAtom(atom=mediator, value=m_val)
            f_t = _verifier_build_mediation_controlled_outcome_formula(
                target, treated_va, m_va, cde_w, observed,
            )
            f_c = _verifier_build_mediation_controlled_outcome_formula(
                target, control_va, m_va, cde_w, observed,
            )
            try:
                v_t = _evaluate_formula(
                    f_t, theta, {}, graph=graph, bidirected=bidirected
                )
                v_c = _evaluate_formula(
                    f_c, theta, {}, graph=graph, bidirected=bidirected
                )
            except _NonConcreteValue as e:
                raise RuleCheckFailed(
                    f"mediation_numeric_evaluate: CDE re-evaluation failed "
                    f"for mediator={m_val!r}: {e}",
                    step_index=step_index, rule="mediation_numeric_evaluate",
                )
            recomputed_cde = v_t - v_c
            m_key = str(m_val)
            if m_key not in claimed_cde:
                raise RuleCheckFailed(
                    f"mediation_numeric_evaluate: cde missing mediator value "
                    f"{m_key!r}",
                    step_index=step_index, rule="mediation_numeric_evaluate",
                )
            claimed_v = claimed_cde[m_key]
            if not isinstance(claimed_v, (int, float)):
                raise RuleCheckFailed(
                    f"mediation_numeric_evaluate: cde[{m_key!r}] must be "
                    f"numeric, got {type(claimed_v).__name__}",
                    step_index=step_index, rule="mediation_numeric_evaluate",
                )
            if abs(float(claimed_v) - recomputed_cde) > _NUMERIC_TOL:
                raise RuleCheckFailed(
                    f"mediation_numeric_evaluate: cde[{m_key!r}] mismatch — "
                    f"claimed {claimed_v!r}, recomputed {recomputed_cde!r}",
                    step_index=step_index, rule="mediation_numeric_evaluate",
                )


def _verifier_directed_descendants(graph, node) -> frozenset:
    """BFS forward along directed edges to collect descendants.

    Inlined here instead of calling ``nx.descendants`` to keep the
    verifier's byte-code footprint auditable — the rule functions above
    scan their own ``co_names`` to prove independence from the runtime
    solver.
    """
    if node not in graph:
        return frozenset()
    seen: set = set()
    frontier = [node]
    while frontier:
        nxt = []
        for n in frontier:
            for _, succ in graph.out_edges(n):
                if succ not in seen and succ != node:
                    seen.add(succ)
                    nxt.append(succ)
        frontier = nxt
    return frozenset(seen)


# ===================================================== Phase 7.1 S.N.4

_NUMERIC_BACKDOOR_METHODS = frozenset({
    "backdoor_linear",
    "backdoor_logistic",
    # Phase 14: dose-response estimators are still backdoor-identified
    # (the criterion step is unchanged); they fit a curve over T given
    # the same Z, so verify can re-use the backdoor rule with an
    # extended method whitelist instead of duplicating the whole rule.
    "dose_response_linear_dml",
    "dose_response_causal_forest_dml",
    "dose_response_linear_drlearner",
})

_NUMERIC_FRONTDOOR_METHODS = frozenset({
    "frontdoor_linear",
    "frontdoor_logistic",
})

_NUMERIC_IV_METHODS = frozenset({"iv_wald", "iv_2sls"})

_SHA256_HEX_LEN = 64
_MIN_NUMERIC_SAMPLE_SIZE = 10


def _rule_numeric_backdoor_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Relaxed metadata audit for a data-based backdoor ATE estimate.

    The verifier does NOT re-train — full numerical reproduction would
    require shipping the data and accepting the runtime cost, and sklearn
    / bootstrap introduce determinism requirements that make bit-exact
    re-check brittle. Instead this rule audits the **metadata self-
    consistency** of a numeric_estimate block:

    - ``method`` is in the allowed enum
    - ``point`` lies inside ``[ci_lower, ci_upper]`` when the CI is present
    - ``ci_level`` is a probability in (0, 1)
    - ``data_hash`` is a well-formed SHA-256 hex digest
    - ``sample_size`` is at least the DataContract minimum (10)
    - ``adjustment`` is disjoint from {treatment, outcome}
    - referenced ``criterion`` step is a ``backdoor_criterion`` whose
      claimed z-set matches ``adjustment``

    This is narrower than the identification-layer rules (which do
    full structural re-checks) but catches the realistic tampering
    / bug cases: wrong method name, point outside CI, corrupted hash,
    adjustment that overlaps the treatment, mismatched adjustment
    between structural and numeric steps.
    """
    criterion_ref = _require(inputs, "criterion", step_index, "numeric_backdoor_estimate")
    if not isinstance(criterion_ref, StepRef):
        raise UnknownRuleInputError(
            "numeric_backdoor_estimate.criterion must be a StepRef",
            step_index=step_index, rule="numeric_backdoor_estimate",
        )
    treatment = _require_atom(inputs, "treatment", step_index, "numeric_backdoor_estimate")
    outcome = _require_atom(inputs, "outcome", step_index, "numeric_backdoor_estimate")
    adjustment = _require_atom_set(
        inputs, "adjustment", step_index, "numeric_backdoor_estimate",
    )
    method = inputs.get("method")
    data_hash = inputs.get("data_hash")
    sample_size = inputs.get("sample_size")
    point = inputs.get("point")
    ci_lower = inputs.get("ci_lower")
    ci_upper = inputs.get("ci_upper")
    ci_level = inputs.get("ci_level")

    if method not in _NUMERIC_BACKDOOR_METHODS:
        raise RuleCheckFailed(
            f"numeric_backdoor_estimate.method must be one of "
            f"{sorted(_NUMERIC_BACKDOOR_METHODS)}; got {method!r}",
            step_index=step_index, rule="numeric_backdoor_estimate",
        )

    if not isinstance(data_hash, str) or len(data_hash) != _SHA256_HEX_LEN:
        raise RuleCheckFailed(
            f"numeric_backdoor_estimate.data_hash must be a "
            f"{_SHA256_HEX_LEN}-char SHA-256 hex string",
            step_index=step_index, rule="numeric_backdoor_estimate",
        )
    if not all(c in "0123456789abcdef" for c in data_hash):
        raise RuleCheckFailed(
            "numeric_backdoor_estimate.data_hash must be lowercase hex",
            step_index=step_index, rule="numeric_backdoor_estimate",
        )

    if (
        not isinstance(sample_size, int)
        or isinstance(sample_size, bool)
        or sample_size < _MIN_NUMERIC_SAMPLE_SIZE
    ):
        raise RuleCheckFailed(
            f"numeric_backdoor_estimate.sample_size must be an int "
            f">= {_MIN_NUMERIC_SAMPLE_SIZE}; got {sample_size!r}",
            step_index=step_index, rule="numeric_backdoor_estimate",
        )

    if not isinstance(point, (int, float)) or isinstance(point, bool):
        raise RuleCheckFailed(
            f"numeric_backdoor_estimate.point must be a number; got "
            f"{point!r}",
            step_index=step_index, rule="numeric_backdoor_estimate",
        )

    ci_present = ci_lower is not None or ci_upper is not None
    if ci_present:
        if ci_lower is None or ci_upper is None:
            raise RuleCheckFailed(
                "numeric_backdoor_estimate: ci_lower and ci_upper must "
                "both be present or both absent",
                step_index=step_index, rule="numeric_backdoor_estimate",
            )
        if not (ci_lower <= point <= ci_upper):
            raise RuleCheckFailed(
                f"numeric_backdoor_estimate: point {point} is outside "
                f"[{ci_lower}, {ci_upper}]",
                step_index=step_index, rule="numeric_backdoor_estimate",
            )
        if not isinstance(ci_level, (int, float)) or not (0 < ci_level < 1):
            raise RuleCheckFailed(
                f"numeric_backdoor_estimate.ci_level must be in (0, 1); "
                f"got {ci_level!r}",
                step_index=step_index, rule="numeric_backdoor_estimate",
            )

    if adjustment & {treatment, outcome}:
        raise RuleCheckFailed(
            "numeric_backdoor_estimate.adjustment must be disjoint from "
            "{treatment, outcome}",
            step_index=step_index, rule="numeric_backdoor_estimate",
        )

    criterion_step = step_by_id.get(criterion_ref.step_id)
    if criterion_step is None:
        raise RuleCheckFailed(
            f"numeric_backdoor_estimate: referenced criterion step "
            f"{criterion_ref.step_id!r} missing",
            step_index=step_index, rule="numeric_backdoor_estimate",
        )
    if criterion_step.rule != "backdoor_criterion":
        raise RuleCheckFailed(
            "numeric_backdoor_estimate.criterion must reference a "
            "backdoor_criterion step",
            step_index=step_index, rule="numeric_backdoor_estimate",
        )
    criterion_z = criterion_step.inputs.get("z")
    if not isinstance(criterion_z, (frozenset, set)):
        raise RuleCheckFailed(
            "referenced backdoor_criterion.z must be an atom set",
            step_index=step_index, rule="numeric_backdoor_estimate",
        )
    if frozenset(criterion_z) != frozenset(adjustment):
        raise RuleCheckFailed(
            "numeric_backdoor_estimate.adjustment must equal the z-set "
            "claimed by the referenced backdoor_criterion step",
            step_index=step_index, rule="numeric_backdoor_estimate",
        )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            "numeric_backdoor_estimate output must be a StructuralResult",
            step_index=step_index, rule="numeric_backdoor_estimate",
        )
    if claimed_output.value is not True:
        raise RuleCheckFailed(
            "numeric_backdoor_estimate output.value must be True",
            step_index=step_index, rule="numeric_backdoor_estimate",
        )


def _rule_numeric_frontdoor_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Phase 7.2 — relaxed audit for a data-based front-door ATE estimate.

    Mirrors ``numeric_backdoor_estimate`` but for the front-door path:

    - ``method`` is in ``_NUMERIC_FRONTDOOR_METHODS``
    - ``point`` is inside ``[ci_lower, ci_upper]`` when the CI is present
    - ``ci_level`` in (0, 1)
    - ``data_hash`` is a well-formed SHA-256 hex digest
    - ``sample_size`` >= 10
    - ``mediators`` is non-empty and disjoint from {treatment, outcome}
    - referenced ``criterion`` step is a ``front_door_criterion`` whose
      z-set equals ``mediators``
    """
    criterion_ref = _require(inputs, "criterion", step_index, "numeric_frontdoor_estimate")
    if not isinstance(criterion_ref, StepRef):
        raise UnknownRuleInputError(
            "numeric_frontdoor_estimate.criterion must be a StepRef",
            step_index=step_index, rule="numeric_frontdoor_estimate",
        )
    treatment = _require_atom(inputs, "treatment", step_index, "numeric_frontdoor_estimate")
    outcome = _require_atom(inputs, "outcome", step_index, "numeric_frontdoor_estimate")
    mediators = _require_atom_set(
        inputs, "mediators", step_index, "numeric_frontdoor_estimate",
    )
    method = inputs.get("method")
    data_hash = inputs.get("data_hash")
    sample_size = inputs.get("sample_size")
    point = inputs.get("point")
    ci_lower = inputs.get("ci_lower")
    ci_upper = inputs.get("ci_upper")
    ci_level = inputs.get("ci_level")

    if method not in _NUMERIC_FRONTDOOR_METHODS:
        raise RuleCheckFailed(
            f"numeric_frontdoor_estimate.method must be one of "
            f"{sorted(_NUMERIC_FRONTDOOR_METHODS)}; got {method!r}",
            step_index=step_index, rule="numeric_frontdoor_estimate",
        )
    if not isinstance(data_hash, str) or len(data_hash) != _SHA256_HEX_LEN:
        raise RuleCheckFailed(
            f"numeric_frontdoor_estimate.data_hash must be a "
            f"{_SHA256_HEX_LEN}-char SHA-256 hex string",
            step_index=step_index, rule="numeric_frontdoor_estimate",
        )
    if not all(c in "0123456789abcdef" for c in data_hash):
        raise RuleCheckFailed(
            "numeric_frontdoor_estimate.data_hash must be lowercase hex",
            step_index=step_index, rule="numeric_frontdoor_estimate",
        )

    if (
        not isinstance(sample_size, int)
        or isinstance(sample_size, bool)
        or sample_size < _MIN_NUMERIC_SAMPLE_SIZE
    ):
        raise RuleCheckFailed(
            f"numeric_frontdoor_estimate.sample_size must be an int "
            f">= {_MIN_NUMERIC_SAMPLE_SIZE}; got {sample_size!r}",
            step_index=step_index, rule="numeric_frontdoor_estimate",
        )
    if not isinstance(point, (int, float)) or isinstance(point, bool):
        raise RuleCheckFailed(
            f"numeric_frontdoor_estimate.point must be a number; got "
            f"{point!r}",
            step_index=step_index, rule="numeric_frontdoor_estimate",
        )

    ci_present = ci_lower is not None or ci_upper is not None
    if ci_present:
        if ci_lower is None or ci_upper is None:
            raise RuleCheckFailed(
                "numeric_frontdoor_estimate: ci_lower and ci_upper must "
                "both be present or both absent",
                step_index=step_index, rule="numeric_frontdoor_estimate",
            )
        if not (ci_lower <= point <= ci_upper):
            raise RuleCheckFailed(
                f"numeric_frontdoor_estimate: point {point} outside "
                f"[{ci_lower}, {ci_upper}]",
                step_index=step_index, rule="numeric_frontdoor_estimate",
            )
        if not isinstance(ci_level, (int, float)) or not (0 < ci_level < 1):
            raise RuleCheckFailed(
                f"numeric_frontdoor_estimate.ci_level must be in (0, 1); "
                f"got {ci_level!r}",
                step_index=step_index, rule="numeric_frontdoor_estimate",
            )

    if not mediators:
        raise RuleCheckFailed(
            "numeric_frontdoor_estimate.mediators must be non-empty",
            step_index=step_index, rule="numeric_frontdoor_estimate",
        )
    if mediators & {treatment, outcome}:
        raise RuleCheckFailed(
            "numeric_frontdoor_estimate.mediators must be disjoint from "
            "{treatment, outcome}",
            step_index=step_index, rule="numeric_frontdoor_estimate",
        )

    criterion_step = step_by_id.get(criterion_ref.step_id)
    if criterion_step is None:
        raise RuleCheckFailed(
            f"numeric_frontdoor_estimate: referenced criterion step "
            f"{criterion_ref.step_id!r} missing",
            step_index=step_index, rule="numeric_frontdoor_estimate",
        )
    if criterion_step.rule != "front_door_criterion":
        raise RuleCheckFailed(
            "numeric_frontdoor_estimate.criterion must reference a "
            "front_door_criterion step",
            step_index=step_index, rule="numeric_frontdoor_estimate",
        )
    criterion_z = criterion_step.inputs.get("z")
    if not isinstance(criterion_z, (frozenset, set)):
        raise RuleCheckFailed(
            "referenced front_door_criterion.z must be an atom set",
            step_index=step_index, rule="numeric_frontdoor_estimate",
        )
    if frozenset(criterion_z) != frozenset(mediators):
        raise RuleCheckFailed(
            "numeric_frontdoor_estimate.mediators must equal the z-set "
            "claimed by the referenced front_door_criterion step",
            step_index=step_index, rule="numeric_frontdoor_estimate",
        )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            "numeric_frontdoor_estimate output must be a StructuralResult",
            step_index=step_index, rule="numeric_frontdoor_estimate",
        )
    if claimed_output.value is not True:
        raise RuleCheckFailed(
            "numeric_frontdoor_estimate output.value must be True",
            step_index=step_index, rule="numeric_frontdoor_estimate",
        )


def _rule_numeric_iv_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Phase 7.3 — relaxed audit for a data-based IV ATE estimate.

    Method enum + CI bounds + data_hash + sample_size + instrument
    validity checks. Same shape as numeric_backdoor_estimate /
    numeric_frontdoor_estimate; the referenced criterion step must be
    an ``iv_criterion_check`` and its (instrument, conditioning) must
    equal the numeric step's claims.
    """
    criterion_ref = _require(inputs, "criterion", step_index, "numeric_iv_estimate")
    if not isinstance(criterion_ref, StepRef):
        raise UnknownRuleInputError(
            "numeric_iv_estimate.criterion must be a StepRef",
            step_index=step_index, rule="numeric_iv_estimate",
        )
    treatment = _require_atom(inputs, "treatment", step_index, "numeric_iv_estimate")
    outcome = _require_atom(inputs, "outcome", step_index, "numeric_iv_estimate")
    instrument = _require_atom(inputs, "instrument", step_index, "numeric_iv_estimate")
    conditioning = _require_atom_set(
        inputs, "conditioning", step_index, "numeric_iv_estimate",
    )
    method = inputs.get("method")
    data_hash = inputs.get("data_hash")
    sample_size = inputs.get("sample_size")
    point = inputs.get("point")
    ci_lower = inputs.get("ci_lower")
    ci_upper = inputs.get("ci_upper")
    ci_level = inputs.get("ci_level")

    if method not in _NUMERIC_IV_METHODS:
        raise RuleCheckFailed(
            f"numeric_iv_estimate.method must be one of "
            f"{sorted(_NUMERIC_IV_METHODS)}; got {method!r}",
            step_index=step_index, rule="numeric_iv_estimate",
        )
    if not isinstance(data_hash, str) or len(data_hash) != _SHA256_HEX_LEN:
        raise RuleCheckFailed(
            f"numeric_iv_estimate.data_hash must be a "
            f"{_SHA256_HEX_LEN}-char SHA-256 hex string",
            step_index=step_index, rule="numeric_iv_estimate",
        )
    if not all(c in "0123456789abcdef" for c in data_hash):
        raise RuleCheckFailed(
            "numeric_iv_estimate.data_hash must be lowercase hex",
            step_index=step_index, rule="numeric_iv_estimate",
        )
    if (
        not isinstance(sample_size, int)
        or isinstance(sample_size, bool)
        or sample_size < _MIN_NUMERIC_SAMPLE_SIZE
    ):
        raise RuleCheckFailed(
            f"numeric_iv_estimate.sample_size must be an int "
            f">= {_MIN_NUMERIC_SAMPLE_SIZE}; got {sample_size!r}",
            step_index=step_index, rule="numeric_iv_estimate",
        )
    if not isinstance(point, (int, float)) or isinstance(point, bool):
        raise RuleCheckFailed(
            f"numeric_iv_estimate.point must be a number; got {point!r}",
            step_index=step_index, rule="numeric_iv_estimate",
        )
    ci_present = ci_lower is not None or ci_upper is not None
    if ci_present:
        if ci_lower is None or ci_upper is None:
            raise RuleCheckFailed(
                "numeric_iv_estimate: ci_lower and ci_upper must both be "
                "present or both absent",
                step_index=step_index, rule="numeric_iv_estimate",
            )
        if not (ci_lower <= point <= ci_upper):
            raise RuleCheckFailed(
                f"numeric_iv_estimate: point {point} outside "
                f"[{ci_lower}, {ci_upper}]",
                step_index=step_index, rule="numeric_iv_estimate",
            )
        if not isinstance(ci_level, (int, float)) or not (0 < ci_level < 1):
            raise RuleCheckFailed(
                f"numeric_iv_estimate.ci_level must be in (0, 1); "
                f"got {ci_level!r}",
                step_index=step_index, rule="numeric_iv_estimate",
            )

    if instrument in {treatment, outcome}:
        raise RuleCheckFailed(
            "numeric_iv_estimate.instrument must be distinct from "
            "{treatment, outcome}",
            step_index=step_index, rule="numeric_iv_estimate",
        )
    if conditioning & {treatment, outcome, instrument}:
        raise RuleCheckFailed(
            "numeric_iv_estimate.conditioning must be disjoint from "
            "{treatment, outcome, instrument}",
            step_index=step_index, rule="numeric_iv_estimate",
        )

    criterion_step = step_by_id.get(criterion_ref.step_id)
    if criterion_step is None:
        raise RuleCheckFailed(
            f"numeric_iv_estimate: referenced criterion step "
            f"{criterion_ref.step_id!r} missing",
            step_index=step_index, rule="numeric_iv_estimate",
        )
    if criterion_step.rule != "iv_criterion_check":
        raise RuleCheckFailed(
            "numeric_iv_estimate.criterion must reference an iv_criterion_check step",
            step_index=step_index, rule="numeric_iv_estimate",
        )
    if criterion_step.inputs.get("instrument") != instrument:
        raise RuleCheckFailed(
            "numeric_iv_estimate.instrument must equal the instrument "
            "claimed by the referenced iv_criterion_check step",
            step_index=step_index, rule="numeric_iv_estimate",
        )
    criterion_cond = criterion_step.inputs.get("conditioning", frozenset())
    if frozenset(criterion_cond) != frozenset(conditioning):
        raise RuleCheckFailed(
            "numeric_iv_estimate.conditioning must equal the conditioning "
            "set claimed by the referenced iv_criterion_check step",
            step_index=step_index, rule="numeric_iv_estimate",
        )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            "numeric_iv_estimate output must be a StructuralResult",
            step_index=step_index, rule="numeric_iv_estimate",
        )
    if claimed_output.value is not True:
        raise RuleCheckFailed(
            "numeric_iv_estimate output.value must be True",
            step_index=step_index, rule="numeric_iv_estimate",
        )


# ========================================================== R6

def _rule_probability_ref_lookup(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """R6: ``probability_ref_lookup(theta, target, given) -> float``.

    inputs:
        target — ValuedAtom with a concrete literal value (no VarRef)
        given — tuple of ValuedAtoms with concrete literal values
    output:
        the float stored in ``ctx.theta`` under the corresponding
        ``ProbabilityKey``.

    Rejects if: theta is absent, any value is a VarRef / None, the
    key is not in theta, or the recovered value disagrees with the
    claimed output.
    """
    if ctx.theta is None:
        raise RuleCheckFailed(
            "probability_ref_lookup: verification context has no theta",
            step_index=step_index, rule="probability_ref_lookup",
        )
    target = _require(inputs, "target", step_index, "probability_ref_lookup")
    given = _require(inputs, "given", step_index, "probability_ref_lookup")
    if not isinstance(target, ValuedAtom):
        raise UnknownRuleInputError(
            "probability_ref_lookup.target must be a ValuedAtom",
            step_index=step_index, rule="probability_ref_lookup",
        )
    if not isinstance(given, tuple):
        raise UnknownRuleInputError(
            "probability_ref_lookup.given must be a tuple of ValuedAtom",
            step_index=step_index, rule="probability_ref_lookup",
        )

    try:
        key = _concrete_probability_key(target, given)
    except _NonConcreteValue as e:
        raise RuleCheckFailed(
            f"probability_ref_lookup: non-concrete value in lookup ({e})",
            step_index=step_index, rule="probability_ref_lookup",
        )

    recovered = ctx.theta.entries.get(key)
    if recovered is None:
        raise RuleCheckFailed(
            f"probability_ref_lookup: theta has no entry for the requested key",
            step_index=step_index, rule="probability_ref_lookup",
        )
    if not isinstance(claimed_output, (int, float)):
        raise RuleCheckFailed(
            f"probability_ref_lookup: claimed output must be a number",
            step_index=step_index, rule="probability_ref_lookup",
        )
    if abs(float(recovered) - float(claimed_output)) > _NUMERIC_TOL:
        raise RuleCheckFailed(
            f"probability_ref_lookup: claimed {claimed_output}, "
            f"theta holds {recovered}",
            step_index=step_index, rule="probability_ref_lookup",
        )


class _NonConcreteValue(Exception):
    """Internal: raised by the key-builder when a ValuedAtom still
    carries a VarRef / None. Callers translate to RuleCheckFailed."""


def _concrete_value(v):
    if isinstance(v, VarRef):
        raise _NonConcreteValue(f"VarRef({v.name!r})")
    if v is None:
        raise _NonConcreteValue("None")
    return v


def _concrete_probability_key(
    target: ValuedAtom,
    given: tuple[ValuedAtom, ...],
) -> ProbabilityKey:
    tv = _concrete_value(target.value)
    pairs = frozenset((g.atom, _concrete_value(g.value)) for g in given)
    return ProbabilityKey(target_atom=target.atom, target_value=tv, given=pairs)


# ========================================================== R7

def _evaluate_formula(
    expr: FormulaExpr,
    theta: Theta,
    subs: dict,
    *,
    graph=None,
    bidirected=None,
) -> float:
    """Verifier's independent recursive evaluator for FormulaExpr.

    Does NOT call ``themis.runtime.numeric_estimator.estimate_formula``.
    The two evaluators must agree on every concrete value — that
    agreement is what makes R7 meaningful.

    ``graph`` / ``bidirected`` are threaded through to the marginal-
    independence fallback so the iter 199 d-separation safety guard
    fires on the verifier side too. Without them the guard would be
    dead code on this path and the verifier would silently agree with
    runtime's wrong answer for chain-DAG + marginal-only theta (iter
    195 risk). Callers from ``_rule_formula_evaluation`` pass
    ``ctx.graph`` / ``ctx.bidirected``.
    """
    if isinstance(expr, ConstantExpr):
        return float(expr.value)
    if isinstance(expr, ProbabilityRefExpr):
        target_value = _resolve(expr.target.value, subs)
        given_pairs = frozenset(
            (g.atom, _resolve(g.value, subs)) for g in expr.given
        )
        key = ProbabilityKey(
            target_atom=expr.target.atom,
            target_value=target_value,
            given=given_pairs,
        )
        value = theta.entries.get(key)
        if value is None:
            # Iter 173: mirror the runtime numeric_estimator's
            # auto-marginalization fallback. Verifier independence
            # is preserved because we only consume theta entries +
            # canonical math (no shared state with runtime).
            derived = _verifier_derive_via_marginalization(
                key, theta, graph=graph, bidirected=bidirected,
            )
            if derived is None:
                # Iter 193: mirror marginal-independence fallback.
                # Iter 200: thread graph + bidirected so the iter 199
                # d-sep guard fires on this path.
                derived = _verifier_marginal_independence_lookup(
                    key, theta, graph=graph, bidirected=bidirected,
                )
            if derived is not None:
                return float(derived)
            # Iter 202: enrich the refusal message with d-sep guard
            # diagnostic when the marginal-independence fallback found
            # a candidate but graph rejected it. Mirrors runtime so R7
            # surfaces the same actionable hint to downstream consumers
            # of verifier diagnostics.
            base_msg = (
                f"theta has no entry for P({expr.target.atom.predicate}="
                f"{target_value})"
            )
            refusal = _verifier_diagnose_marginal_independence_refusal(
                key, theta, graph=graph, bidirected=bidirected,
            )
            if refusal is not None:
                base_msg = f"{base_msg}; {refusal}"
            raise _NonConcreteValue(base_msg)
        return float(value)
    if isinstance(expr, ProductExpr):
        result = 1.0
        for t in expr.terms:
            result *= _evaluate_formula(
                t, theta, subs,
                graph=graph, bidirected=bidirected,
            )
        return result
    if isinstance(expr, SumExpr):
        total = 0.0
        for v in theta.domain_of(expr.over):
            new_subs = dict(subs)
            new_subs[expr.bind.name] = v
            total += _evaluate_formula(
                expr.body, theta, new_subs,
                graph=graph, bidirected=bidirected,
            )
        return total
    raise _NonConcreteValue(f"unknown formula node: {type(expr).__name__}")


def _resolve(value, subs: dict):
    if value is None:
        raise _NonConcreteValue("query-bound None reached R7 evaluator")
    if isinstance(value, VarRef):
        if value.name not in subs:
            raise _NonConcreteValue(f"unbound VarRef {value.name!r}")
        return subs[value.name]
    return value


def _verifier_derive_via_marginalization(
    missing_key: ProbabilityKey,
    theta,
    *,
    _depth: int = 0,
    graph=None,
    bidirected=None,
) -> float | None:
    """Iter 173 — verifier-side mirror of runtime numeric_estimator's
    auto-marginalization fallback. Pure function over theta; no shared
    state with runtime, preserving V0-V5 independence.

    Recursively derives P(target|given) = Σ_z P(target|given,Z=z) ·
    P(Z=z|given) using theta entries (or recursive sub-derivations,
    bounded depth ≤ 3). When evaluator hits a missing CPT, this
    fallback tries derivation before raising _NonConcreteValue.

    Mirrors themis.runtime.numeric_estimator._try_derive_via_
    marginalization byte-for-byte semantics; the two implementations
    must agree on every concrete value, which is what makes R7
    meaningful.
    """
    if _depth > 3:
        return None
    target_atom = missing_key.target_atom
    target_value = missing_key.target_value
    base_given = missing_key.given

    candidates = []
    seen: set = set()
    for key in theta.entries:
        for ga, _gv in key.given:
            if ga != target_atom and ga not in seen:
                candidates.append(ga)
                seen.add(ga)
        if (
            key.target_atom != target_atom
            and key.target_atom not in seen
        ):
            candidates.append(key.target_atom)
            seen.add(key.target_atom)

    given_atoms = {ga for ga, _ in base_given}
    for z in candidates:
        if z == target_atom or z in given_atoms:
            continue
        domain = theta.domain_of(z)
        if not domain:
            continue
        outer_values: dict = {}
        ok = True
        for v in domain:
            extended_given = frozenset(base_given | {(z, v)})
            outer_key = ProbabilityKey(
                target_atom=target_atom,
                target_value=target_value,
                given=extended_given,
            )
            v_outer = theta.entries.get(outer_key)
            if v_outer is None:
                v_outer = _verifier_derive_via_marginalization(
                    outer_key, theta, _depth=_depth + 1,
                    graph=graph, bidirected=bidirected,
                )
                if v_outer is None:
                    ok = False
                    break
            outer_values[v] = v_outer
        if not ok:
            continue
        inner_values: dict = {}
        ok = True
        for v in domain:
            inner_key = ProbabilityKey(
                target_atom=z, target_value=v, given=base_given,
            )
            v_inner = theta.entries.get(inner_key)
            if v_inner is None:
                v_inner = _verifier_derive_via_marginalization(
                    inner_key, theta, _depth=_depth + 1,
                    graph=graph, bidirected=bidirected,
                )
                if v_inner is None:
                    # Iter 188: mirror runtime's Bayes inversion
                    # fallback for the inner factor.
                    v_inner = _verifier_derive_via_bayes_inversion(
                        inner_key, theta, _depth=_depth + 1,
                        graph=graph, bidirected=bidirected,
                    )
                if v_inner is None:
                    # Iter 193: mirror marginal-independence lookup.
                    # Iter 200: thread graph + bidirected so the
                    # iter 199 d-sep guard fires here too.
                    v_inner = _verifier_marginal_independence_lookup(
                        inner_key, theta,
                        graph=graph, bidirected=bidirected,
                    )
                if v_inner is None:
                    ok = False
                    break
            inner_values[v] = v_inner
        if not ok:
            continue
        return sum(
            outer_values[v] * inner_values[v] for v in domain
        )
    return None


def _verifier_marginal_independence_lookup(
    missing_key: ProbabilityKey,
    theta,
    *,
    graph=None,
    bidirected=None,
) -> float | None:
    """Iter 193 — verifier mirror of runtime's marginal-independence
    lookup. Pure theta lookup; preserves V0-V5 independence.

    Iter 199: graph-aware d-separation guard mirroring runtime. When
    graph + bidirected supplied, only return value if target ⊥ extras
    | reduced_given holds structurally."""
    target_atom = missing_key.target_atom
    target_value = missing_key.target_value
    base_given = missing_key.given
    if not base_given:
        return None
    from itertools import combinations
    for n_remove in range(1, len(base_given) + 1):
        sorted_given = sorted(
            base_given, key=lambda p: (p[0].predicate, str(p[1])),
        )
        for to_remove in combinations(sorted_given, n_remove):
            reduced = frozenset(
                p for p in base_given if p not in to_remove
            )
            reduced_key = ProbabilityKey(
                target_atom=target_atom, target_value=target_value,
                given=reduced,
            )
            v = theta.entries.get(reduced_key)
            if v is None:
                continue
            if graph is not None and bidirected is not None:
                from ..runtime.structural_solver import m_separated
                conditioning = tuple(a for a, _ in reduced)
                extras_atoms = [a for a, _ in to_remove]
                all_separated = all(
                    m_separated(
                        graph, bidirected,
                        target_atom, extra, conditioning,
                    )
                    for extra in extras_atoms
                )
                if not all_separated:
                    continue
            return v
    return None


def _verifier_diagnose_marginal_independence_refusal(
    missing_key: ProbabilityKey,
    theta,
    *,
    graph,
    bidirected,
) -> str | None:
    """Iter 202 — verifier mirror of runtime's
    ``_diagnose_marginal_independence_refusal``. Returns a structured
    explanation when the d-sep guard refused an existing-but-graph-
    incompatible marginal candidate; None otherwise. Preserves V0-V5
    independence (this is its own re-derivation, not a runtime call).
    """
    if graph is None or bidirected is None:
        return None
    target_atom = missing_key.target_atom
    target_value = missing_key.target_value
    base_given = missing_key.given
    if not base_given:
        return None
    from itertools import combinations
    from ..runtime.structural_solver import m_separated

    for n_remove in range(1, len(base_given) + 1):
        sorted_given = sorted(
            base_given, key=lambda p: (p[0].predicate, str(p[1])),
        )
        for to_remove in combinations(sorted_given, n_remove):
            reduced = frozenset(
                p for p in base_given if p not in to_remove
            )
            reduced_key = ProbabilityKey(
                target_atom=target_atom, target_value=target_value,
                given=reduced,
            )
            if theta.entries.get(reduced_key) is None:
                continue
            conditioning = tuple(a for a, _ in reduced)
            extras_atoms = tuple(a for a, _ in to_remove)
            all_separated = all(
                m_separated(
                    graph, bidirected,
                    target_atom, extra, conditioning,
                )
                for extra in extras_atoms
            )
            if not all_separated:
                extras_repr = ",".join(a.predicate for a in extras_atoms)
                conditioning_repr = (
                    ",".join(a.predicate for a, _ in reduced) or "∅"
                )
                target_pred = target_atom.predicate
                return (
                    f"verifier: theta has marginal "
                    f"P({target_pred}={target_value}|"
                    f"{conditioning_repr}) but declared graph implies "
                    f"{target_pred} ⊥ {{{extras_repr}}} | "
                    f"{{{conditioning_repr}}} does NOT hold "
                    f"(d-separation refused); marginal cannot stand in "
                    f"for the demanded conditional"
                )
    return None


def _verifier_derive_via_bayes_inversion(
    missing_key: ProbabilityKey,
    theta,
    *,
    _depth: int = 0,
    graph=None,
    bidirected=None,
) -> float | None:
    """Iter 188 — verifier mirror of runtime's Bayes inversion helper.
    Pure function; preserves V0-V5 independence. Mirror change to
    runtime's _try_derive_via_bayes_inversion when modifying.

    Iter 200: ``graph`` / ``bidirected`` accepted and passed through
    to recursive marginalization calls so the d-sep guard at the
    leaf marginal-independence lookup fires correctly during deep
    recursion, not just at the top level.
    """
    if _depth > 2:
        return None
    target_atom = missing_key.target_atom
    target_value = missing_key.target_value
    base_given = missing_key.given
    if not base_given:
        return None
    for a_atom, a_value in base_given:
        if a_atom == target_atom:
            continue
        reduced_given = frozenset(p for p in base_given if p[0] != a_atom)
        flip_given = reduced_given | {(target_atom, target_value)}
        flip_key = ProbabilityKey(
            target_atom=a_atom, target_value=a_value,
            given=frozenset(flip_given),
        )
        flip_val = theta.entries.get(flip_key)
        if flip_val is None:
            flip_val = _verifier_derive_via_marginalization(
                flip_key, theta, _depth=_depth + 1,
                graph=graph, bidirected=bidirected,
            )
        if flip_val is None:
            continue
        target_key = ProbabilityKey(
            target_atom=target_atom, target_value=target_value,
            given=reduced_given,
        )
        target_marginal = theta.entries.get(target_key)
        if target_marginal is None:
            target_marginal = _verifier_derive_via_marginalization(
                target_key, theta, _depth=_depth + 1,
                graph=graph, bidirected=bidirected,
            )
        if target_marginal is None:
            continue
        denom_key = ProbabilityKey(
            target_atom=a_atom, target_value=a_value,
            given=reduced_given,
        )
        denom = theta.entries.get(denom_key)
        if denom is None:
            denom = _verifier_derive_via_marginalization(
                denom_key, theta, _depth=_depth + 1,
                graph=graph, bidirected=bidirected,
            )
        if denom is None or denom == 0:
            continue
        return flip_val * target_marginal / denom
    return None


def _rule_formula_evaluation(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """R7: ``formula_evaluation(formula, theta) -> float``.

    Recursively evaluates ``formula`` under ``ctx.theta`` and compares
    with ``claimed_output`` in floating-point tolerance. The formula
    may be any FormulaExpr (constant / probability_ref / product / sum).
    """
    if ctx.theta is None:
        raise RuleCheckFailed(
            "formula_evaluation: verification context has no theta",
            step_index=step_index, rule="formula_evaluation",
        )
    formula = _require(inputs, "formula", step_index, "formula_evaluation")
    if not isinstance(formula, (ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr)):
        raise UnknownRuleInputError(
            f"formula_evaluation.formula must be a FormulaExpr, "
            f"got {type(formula).__name__}",
            step_index=step_index, rule="formula_evaluation",
        )

    try:
        recomputed = _evaluate_formula(
            formula, ctx.theta, {},
            graph=ctx.graph, bidirected=ctx.bidirected,
        )
    except _NonConcreteValue as e:
        raise RuleCheckFailed(
            f"formula_evaluation: cannot evaluate ({e})",
            step_index=step_index, rule="formula_evaluation",
        )

    if not isinstance(claimed_output, (int, float)):
        raise RuleCheckFailed(
            "formula_evaluation: claimed output must be a number",
            step_index=step_index, rule="formula_evaluation",
        )
    if abs(recomputed - float(claimed_output)) > _NUMERIC_TOL:
        raise RuleCheckFailed(
            f"formula_evaluation: claimed {claimed_output}, "
            f"recomputed {recomputed}",
            step_index=step_index, rule="formula_evaluation",
        )


# ========================================================== R8

def _rule_numeric_result(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """R8: close a numeric derivation by tying a prior evaluation step
    to a ``NumericResult``.

    inputs:
        evaluation — StepRef pointing at an R6 or R7 step whose output
                     is a float.
    output:
        ``NumericResult(value=<that float>)``.
    """
    evaluation_ref = _require(inputs, "evaluation", step_index, "numeric_result")
    if not isinstance(evaluation_ref, StepRef):
        raise UnknownRuleInputError(
            "numeric_result.evaluation must be a StepRef",
            step_index=step_index, rule="numeric_result",
        )
    eval_step = step_by_id.get(evaluation_ref.step_id)
    eval_out = step_output_by_id.get(evaluation_ref.step_id)
    if eval_step is None or eval_out is None:
        raise RuleCheckFailed(
            f"numeric_result: referenced step {evaluation_ref.step_id!r} missing",
            step_index=step_index, rule="numeric_result",
        )
    if eval_step.rule not in (
        "formula_evaluation",
        "probability_ref_lookup",
        "mediation_numeric_evaluate",
    ):
        raise RuleCheckFailed(
            f"numeric_result: evaluation must reference a formula_evaluation, "
            f"probability_ref_lookup, or mediation_numeric_evaluate step, "
            f"got {eval_step.rule!r}",
            step_index=step_index, rule="numeric_result",
        )
    # v0.1.4 Fix 1: when the evaluation source is the bundled mediation
    # rule, extract `te` from its dict output as the canonical numeric
    # answer for the EffectQuery's total-effect closure.
    if eval_step.rule == "mediation_numeric_evaluate":
        if not isinstance(eval_out, dict) or "te" not in eval_out:
            raise RuleCheckFailed(
                "numeric_result: mediation_numeric_evaluate output must be a "
                "dict containing 'te' (total effect) for numeric closure",
                step_index=step_index, rule="numeric_result",
            )
        eval_out = eval_out["te"]
    if not isinstance(eval_out, (int, float)):
        raise RuleCheckFailed(
            "numeric_result: referenced evaluation output must be a number",
            step_index=step_index, rule="numeric_result",
        )

    if not isinstance(claimed_output, NumericResult):
        raise RuleCheckFailed(
            "numeric_result: claimed output must be a NumericResult",
            step_index=step_index, rule="numeric_result",
        )
    if claimed_output.value is None:
        raise RuleCheckFailed(
            "numeric_result: claimed NumericResult.value must not be None",
            step_index=step_index, rule="numeric_result",
        )
    if abs(float(eval_out) - float(claimed_output.value)) > _NUMERIC_TOL:
        raise RuleCheckFailed(
            f"numeric_result: claimed value {claimed_output.value}, "
            f"evaluation produced {eval_out}",
            step_index=step_index, rule="numeric_result",
        )


# ========================================================== V3: negative structural rules

def _rule_unidentifiable_via_backdoor(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """V3: prove ``StructuralResult(value=False)`` for an identify
    query by exhausting the candidate adjustment sets.

    inputs:
        graph — the DAG
        x — intervention atom
        y — target atom
        given — frozenset of pre-conditioned atoms W (may be empty)
    output:
        ``StructuralResult(value=False)``

    The verifier independently enumerates every Z ⊆ V \\ (descendants(X)
    ∪ {X, Y} ∪ W) and confirms no Z satisfies the backdoor criterion
    (given ∪ Z blocks all back-door paths after removing X's outgoing
    edges). This is the symmetric counterpart of R5 — same theorem,
    negative branch.
    """
    graph = _require(inputs, "graph", step_index, "unidentifiable_via_backdoor")
    _assert_same_graph(graph, ctx.graph, step_index, "unidentifiable_via_backdoor")
    x = _require_atom(inputs, "x", step_index, "unidentifiable_via_backdoor")
    y = _require_atom(inputs, "y", step_index, "unidentifiable_via_backdoor")
    given = _require_atom_set(
        inputs, "given", step_index, "unidentifiable_via_backdoor",
        allow_missing=True,
    )

    if x not in graph or y not in graph:
        raise RuleCheckFailed(
            "unidentifiable_via_backdoor: x or y not in graph",
            step_index=step_index, rule="unidentifiable_via_backdoor",
        )

    # given must itself respect the backdoor pre-conditions; if it
    # already violates them, the claim "unidentifiable" is trivially
    # true but under a degenerate premise. Pin to non-degenerate case.
    forbidden = nx.descendants(graph, x) | {x, y}
    if not given.isdisjoint(forbidden):
        raise RuleCheckFailed(
            "unidentifiable_via_backdoor: given violates backdoor pre-conditions",
            step_index=step_index, rule="unidentifiable_via_backdoor",
        )

    mutated = _graph_minus_x_outgoing(graph, x)
    candidates = [
        n for n in graph.nodes
        if n not in forbidden and n not in given
    ]

    # Exhaustion: for every subset Z, check that (Z ∪ given) fails to
    # d-separate x from y in mutated. As soon as one Z succeeds, the
    # claim is false.
    from itertools import combinations
    for size in range(len(candidates) + 1):
        for combo in combinations(candidates, size):
            z_total = frozenset(combo) | given
            if _check_d_separation(mutated, x, y, z_total):
                raise RuleCheckFailed(
                    f"unidentifiable_via_backdoor: found a valid "
                    f"adjustment set of size {size} — claim is false",
                    step_index=step_index, rule="unidentifiable_via_backdoor",
                )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            "unidentifiable_via_backdoor: output must be a StructuralResult",
            step_index=step_index, rule="unidentifiable_via_backdoor",
        )
    if claimed_output.value is not False:
        raise RuleCheckFailed(
            "unidentifiable_via_backdoor: output.value must be False",
            step_index=step_index, rule="unidentifiable_via_backdoor",
        )


def _rule_d_separated(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """V3: prove ``StructuralResult(value=False)`` for an assoc query
    by confirming X and Y are d-separated under the conditioning set.

    inputs:
        graph, x, y, conditioning (frozenset of Atom)
    output:
        ``StructuralResult(value=False)`` — assoc is False when there
        is NO open path, i.e. when x and y are d-separated.
    """
    graph = _require(inputs, "graph", step_index, "d_separated")
    _assert_same_graph(graph, ctx.graph, step_index, "d_separated")
    x = _require_atom(inputs, "x", step_index, "d_separated")
    y = _require_atom(inputs, "y", step_index, "d_separated")
    conditioning = _require_atom_set(
        inputs, "conditioning", step_index, "d_separated",
        allow_missing=True,
    )

    if x == y:
        raise RuleCheckFailed(
            "d_separated: x and y are the same node",
            step_index=step_index, rule="d_separated",
        )
    if x not in graph or y not in graph:
        raise RuleCheckFailed(
            "d_separated: x or y not in graph",
            step_index=step_index, rule="d_separated",
        )

    separated = _check_d_separation(graph, x, y, conditioning)
    if not separated:
        raise RuleCheckFailed(
            "d_separated: there exists an open path between x and y",
            step_index=step_index, rule="d_separated",
        )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            "d_separated: output must be a StructuralResult",
            step_index=step_index, rule="d_separated",
        )
    if claimed_output.value is not False:
        raise RuleCheckFailed(
            "d_separated: output.value must be False",
            step_index=step_index, rule="d_separated",
        )


def _rule_no_directed_path(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """V3: prove ``StructuralResult(value=False)`` for a cause query by
    confirming no directed path exists from src to dst.

    inputs:
        graph, src, dst
    output:
        ``StructuralResult(value=False)``
    """
    graph = _require(inputs, "graph", step_index, "no_directed_path")
    _assert_same_graph(graph, ctx.graph, step_index, "no_directed_path")
    src = _require_atom(inputs, "src", step_index, "no_directed_path")
    dst = _require_atom(inputs, "dst", step_index, "no_directed_path")

    if src not in graph or dst not in graph:
        raise RuleCheckFailed(
            "no_directed_path: src or dst not in graph",
            step_index=step_index, rule="no_directed_path",
        )
    if src == dst or nx.has_path(graph, src, dst):
        raise RuleCheckFailed(
            "no_directed_path: a directed path exists from src to dst",
            step_index=step_index, rule="no_directed_path",
        )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            "no_directed_path: output must be a StructuralResult",
            step_index=step_index, rule="no_directed_path",
        )
    if claimed_output.value is not False:
        raise RuleCheckFailed(
            "no_directed_path: output.value must be False",
            step_index=step_index, rule="no_directed_path",
        )


# ========================================================== V4: positive structural witnesses

def _atom_label_verifier(atom: Atom) -> str:
    """Independent copy of the scheduler's ``_atom_to_str``. Keeping the
    string format aligned means the verifier can rebuild the supporting_paths
    tuple from Atom-form witnesses and compare to the elaborator's output."""
    args = ",".join(a.name for a in atom.args)
    base = f"{atom.predicate}({args})"
    if atom.time_index is None:
        return base
    t = atom.time_index.value
    return f"{base}@t" if t == 0 else f"{base}@t{t:+d}"


def _validate_path_as_tuple_of_atoms(
    path,
    step_index: int,
    rule: str,
    what: str,
) -> tuple[Atom, ...]:
    if not isinstance(path, tuple):
        raise UnknownRuleInputError(
            f"{rule}.{what} must be a tuple of Atom",
            step_index=step_index, rule=rule,
        )
    for a in path:
        if not isinstance(a, Atom):
            raise UnknownRuleInputError(
                f"{rule}.{what} must contain only Atom",
                step_index=step_index, rule=rule,
            )
    return path


def _require_atom_paths(
    inputs: dict,
    key: str,
    step_index: int,
    rule: str,
) -> tuple[tuple[Atom, ...], ...]:
    v = _require(inputs, key, step_index, rule)
    if not isinstance(v, tuple):
        raise UnknownRuleInputError(
            f"{rule}.{key} must be a tuple of paths",
            step_index=step_index, rule=rule,
        )
    return tuple(
        _validate_path_as_tuple_of_atoms(p, step_index, rule, f"{key}[i]")
        for p in v
    )


def _rule_cause_via_directed_path(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """V4: prove ``StructuralResult(value=True)`` for a cause query by
    exhibiting at least one concrete directed path from src to dst.

    inputs:
        graph — the DAG (must equal ctx.graph)
        src — source atom
        dst — destination atom
        paths — non-empty tuple of paths; each path is a tuple of atoms
                starting at src and ending at dst, with a directed edge
                between every consecutive pair
    output:
        ``StructuralResult(value=True, supporting_paths=<string form>)``

    Rejects if any path does not start at src, does not end at dst, has
    a missing directed edge, if the witness set is not the full directed
    path set, or if the claimed supporting_paths do not match that full set.
    """
    graph = _require(inputs, "graph", step_index, "cause_via_directed_path")
    _assert_same_graph(graph, ctx.graph, step_index, "cause_via_directed_path")
    src = _require_atom(inputs, "src", step_index, "cause_via_directed_path")
    dst = _require_atom(inputs, "dst", step_index, "cause_via_directed_path")
    paths = _require_atom_paths(inputs, "paths", step_index, "cause_via_directed_path")

    if not paths:
        raise RuleCheckFailed(
            "cause_via_directed_path: at least one witness path is required",
            step_index=step_index, rule="cause_via_directed_path",
        )
    if src == dst:
        raise RuleCheckFailed(
            "cause_via_directed_path: src and dst must differ",
            step_index=step_index, rule="cause_via_directed_path",
        )

    for idx, path in enumerate(paths):
        if len(path) < 2:
            raise RuleCheckFailed(
                f"cause_via_directed_path.paths[{idx}] has length < 2",
                step_index=step_index, rule="cause_via_directed_path",
            )
        if path[0] != src or path[-1] != dst:
            raise RuleCheckFailed(
                f"cause_via_directed_path.paths[{idx}] must start at src and end at dst",
                step_index=step_index, rule="cause_via_directed_path",
            )
        for i in range(len(path) - 1):
            if not graph.has_edge(path[i], path[i + 1]):
                raise RuleCheckFailed(
                    f"cause_via_directed_path.paths[{idx}] is missing a "
                    f"directed edge between positions {i} and {i + 1}",
                    step_index=step_index, rule="cause_via_directed_path",
                )
        if len(set(path)) != len(path):
            raise RuleCheckFailed(
                f"cause_via_directed_path.paths[{idx}] repeats a node (must be simple)",
                step_index=step_index, rule="cause_via_directed_path",
            )

    expected_paths = tuple(
        tuple(path) for path in nx.all_simple_paths(graph, src, dst)
    )
    if tuple(paths) != expected_paths:
        raise RuleCheckFailed(
            "cause_via_directed_path.paths does not equal the full directed-path set",
            step_index=step_index, rule="cause_via_directed_path",
        )

    expected_supporting = tuple(
        tuple(_atom_label_verifier(a) for a in path) for path in expected_paths
    )
    expected = StructuralResult(
        value=True, supporting_paths=expected_supporting,
    )
    if claimed_output != expected:
        raise RuleCheckFailed(
            "cause_via_directed_path: claimed output does not match the "
            "StructuralResult implied by the witness paths",
            step_index=step_index, rule="cause_via_directed_path",
        )


def _path_is_open_for_verifier(
    graph: nx.DiGraph,
    path: tuple[Atom, ...],
    conditioning: frozenset,
) -> bool:
    """Whether an undirected simple path is *open* under conditioning.

    Non-colliders blocked iff the intermediate node is in conditioning.
    Colliders blocked iff neither the collider nor any descendant is in
    conditioning. A path is open iff no intermediate node blocks it.
    """
    for i in range(1, len(path) - 1):
        prev, mid, nxt = path[i - 1], path[i], path[i + 1]
        if _is_collider(graph, prev, mid, nxt):
            activated = {mid} | nx.descendants(graph, mid)
            if activated.isdisjoint(conditioning):
                return False
        else:
            if mid in conditioning:
                return False
    return True


def _all_open_paths_for_verifier(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    conditioning: frozenset,
) -> tuple[tuple[Atom, ...], ...]:
    """Enumerate the full open-path set for (x, y | conditioning).

    V4's positive assoc derivation is meant to justify the exact
    ``supporting_paths`` emitted by the runtime, not merely the
    existence of some open witness. The verifier therefore re-enumerates
    all simple undirected paths between x and y and keeps only those
    that remain open under the conditioning set.
    """
    if x not in graph or y not in graph or x == y:
        return ()
    return tuple(
        tuple(path)
        for path in nx.all_simple_paths(graph.to_undirected(as_view=True), x, y)
        if _path_is_open_for_verifier(graph, tuple(path), conditioning)
    )


def _rule_d_connected_via_open_path(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """V4: prove ``StructuralResult(value=True)`` for an assoc query by
    exhibiting one or more open undirected simple paths between x and y.

    inputs:
        graph, x, y, conditioning, paths
    output:
        ``StructuralResult(value=True, supporting_paths=<string form>)``

    Rejects if any witness path fails to be a simple undirected path
    between x and y in the graph, if it is blocked under conditioning,
    if the witness set is not the full open-path set, or if the claimed
    supporting_paths disagree with that full set.
    """
    graph = _require(inputs, "graph", step_index, "d_connected_via_open_path")
    _assert_same_graph(graph, ctx.graph, step_index, "d_connected_via_open_path")
    x = _require_atom(inputs, "x", step_index, "d_connected_via_open_path")
    y = _require_atom(inputs, "y", step_index, "d_connected_via_open_path")
    conditioning = _require_atom_set(
        inputs, "conditioning", step_index, "d_connected_via_open_path",
        allow_missing=True,
    )
    paths = _require_atom_paths(
        inputs, "paths", step_index, "d_connected_via_open_path",
    )

    if not paths:
        raise RuleCheckFailed(
            "d_connected_via_open_path: at least one witness path is required",
            step_index=step_index, rule="d_connected_via_open_path",
        )
    if x == y:
        raise RuleCheckFailed(
            "d_connected_via_open_path: x and y must differ",
            step_index=step_index, rule="d_connected_via_open_path",
        )

    for idx, path in enumerate(paths):
        if len(path) < 2:
            raise RuleCheckFailed(
                f"d_connected_via_open_path.paths[{idx}] has length < 2",
                step_index=step_index, rule="d_connected_via_open_path",
            )
        if path[0] != x or path[-1] != y:
            raise RuleCheckFailed(
                f"d_connected_via_open_path.paths[{idx}] must start at x and end at y",
                step_index=step_index, rule="d_connected_via_open_path",
            )
        if len(set(path)) != len(path):
            raise RuleCheckFailed(
                f"d_connected_via_open_path.paths[{idx}] repeats a node (must be simple)",
                step_index=step_index, rule="d_connected_via_open_path",
            )
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            if not (graph.has_edge(u, v) or graph.has_edge(v, u)):
                raise RuleCheckFailed(
                    f"d_connected_via_open_path.paths[{idx}] is missing an "
                    f"edge (either direction) between positions {i} and {i + 1}",
                    step_index=step_index, rule="d_connected_via_open_path",
                )
        if not _path_is_open_for_verifier(graph, path, conditioning):
            raise RuleCheckFailed(
                f"d_connected_via_open_path.paths[{idx}] is blocked under conditioning",
                step_index=step_index, rule="d_connected_via_open_path",
            )

    expected_paths = _all_open_paths_for_verifier(graph, x, y, conditioning)
    if tuple(paths) != expected_paths:
        raise RuleCheckFailed(
            "d_connected_via_open_path.paths does not equal the full open-path set",
            step_index=step_index, rule="d_connected_via_open_path",
        )

    expected_supporting = tuple(
        tuple(_atom_label_verifier(a) for a in path) for path in expected_paths
    )
    expected = StructuralResult(
        value=True, supporting_paths=expected_supporting,
    )
    if claimed_output != expected:
        raise RuleCheckFailed(
            "d_connected_via_open_path: claimed output does not match the "
            "StructuralResult implied by the witness paths",
            step_index=step_index, rule="d_connected_via_open_path",
        )


# ========================================================== Phase 2.latent S4
# Independent m-separation reimplementation for verifier. Does NOT call
# structural_solver.is_m_connected / _is_admg_backdoor_connected — the
# point of these rules is that a shared bug in the runtime m-sep cannot
# slip past the verifier.


def _verifier_build_admg_multigraph(
    directed: nx.DiGraph,
    bidirected: frozenset[frozenset[Atom]],
) -> nx.MultiGraph:
    """Independent copy of the runtime's _build_admg_path_graph."""
    mg = nx.MultiGraph()
    mg.add_nodes_from(directed.nodes())
    for pair in bidirected:
        mg.add_nodes_from(pair)
    for src, dst in directed.edges():
        mg.add_edge(src, dst, kind="directed", src=src, dst=dst)
    for pair in bidirected:
        a, b = tuple(pair)
        mg.add_edge(a, b, kind="bidirected")
    return mg


def _verifier_has_arrowhead_at(
    mg: nx.MultiGraph, edge_key: tuple, v: Atom
) -> bool:
    u, w, k = edge_key
    data = mg.edges[u, w, k]
    if data["kind"] == "bidirected":
        return True
    return data["dst"] == v


def _verifier_is_m_connected(
    graph: nx.DiGraph,
    bidirected: frozenset[frozenset[Atom]],
    left: Atom,
    right: Atom,
    conditioning: frozenset[Atom],
) -> bool:
    """True iff an open m-path connects left and right in the ADMG.

    Independently reimplemented — mirror of structural_solver.is_m_connected
    but verifier-local (never imports from runtime).
    """
    if left == right:
        return False
    mg = _verifier_build_admg_multigraph(graph, bidirected)
    if left not in mg or right not in mg:
        return False
    for edge_path in nx.all_simple_edge_paths(mg, left, right):
        nodes: list[Atom] = [left]
        for u, w, _k in edge_path:
            nodes.append(w if nodes[-1] == u else u)
        open_path = True
        for i in range(1, len(nodes) - 1):
            v = nodes[i]
            ahead_prev = _verifier_has_arrowhead_at(mg, edge_path[i - 1], v)
            ahead_next = _verifier_has_arrowhead_at(mg, edge_path[i], v)
            is_collider = ahead_prev and ahead_next
            if is_collider:
                activated = {v} | nx.descendants(graph, v) if v in graph else {v}
                if activated.isdisjoint(conditioning):
                    open_path = False
                    break
            else:
                if v in conditioning:
                    open_path = False
                    break
        if open_path:
            return True
    return False


def _verifier_is_admg_backdoor_connected(
    graph: nx.DiGraph,
    bidirected: frozenset[frozenset[Atom]],
    src: Atom,
    dst: Atom,
    conditioning: frozenset[Atom],
) -> bool:
    """True iff an open m-path goes from src to dst with arrowhead at src."""
    if src == dst:
        return False
    mg = _verifier_build_admg_multigraph(graph, bidirected)
    if src not in mg or dst not in mg:
        return False
    for edge_path in nx.all_simple_edge_paths(mg, src, dst):
        first = edge_path[0]
        fu, fw, fk = first
        data = mg.edges[fu, fw, fk]
        if data["kind"] == "bidirected":
            first_arrowhead_at_src = True
        else:
            first_arrowhead_at_src = (data["dst"] == src)
        if not first_arrowhead_at_src:
            continue
        nodes: list[Atom] = [src]
        for u, w, _k in edge_path:
            nodes.append(w if nodes[-1] == u else u)
        open_path = True
        for i in range(1, len(nodes) - 1):
            v = nodes[i]
            ahead_prev = _verifier_has_arrowhead_at(mg, edge_path[i - 1], v)
            ahead_next = _verifier_has_arrowhead_at(mg, edge_path[i], v)
            is_collider = ahead_prev and ahead_next
            if is_collider:
                activated = {v} | nx.descendants(graph, v) if v in graph else {v}
                if activated.isdisjoint(conditioning):
                    open_path = False
                    break
            else:
                if v in conditioning:
                    open_path = False
                    break
        if open_path:
            return True
    return False


def _rule_m_separation_witness(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Phase 2.latent S4 structural positive witness.

    inputs:
        graph        — directed part of the ADMG (must equal ctx.graph)
        bidirected   — optional bidirected edge set; when omitted the
                       verifier uses ctx.bidirected
        x, y, z      — atoms / atom set claimed to satisfy X ⊥_m Y | Z
    output:
        True iff X and Y are m-separated by Z in the ADMG.

    The rule independently recomputes m-separation. If the claim
    disagrees with the independent recomputation, reject.
    """
    graph = _require(inputs, "graph", step_index, "m_separation_witness")
    _assert_same_graph(graph, ctx.graph, step_index, "m_separation_witness")
    bidir = inputs.get("bidirected", ctx.bidirected)
    if bidir != ctx.bidirected:
        raise RuleCheckFailed(
            "m_separation_witness: bidirected input does not match context",
            step_index=step_index, rule="m_separation_witness",
        )
    x = _require_atom(inputs, "x", step_index, "m_separation_witness")
    y = _require_atom(inputs, "y", step_index, "m_separation_witness")
    z = _require_atom_set(inputs, "z", step_index, "m_separation_witness")

    connected = _verifier_is_m_connected(graph, bidir, x, y, z)
    recomputed = not connected
    if isinstance(claimed_output, StructuralResult):
        claimed_bool = claimed_output.value
    else:
        claimed_bool = bool(claimed_output)
    if recomputed != claimed_bool:
        raise RuleCheckFailed(
            f"m_separation_witness claimed {claimed_output!r}, recomputed "
            f"{recomputed!r} for x={x.predicate}, y={y.predicate}, "
            f"|z|={len(z)}, |bidir|={len(bidir)}",
            step_index=step_index, rule="m_separation_witness",
        )


def _rule_m_connection_witness(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Phase 2.latent S4 structural positive witness for m-connection.

    inputs:
        graph, bidirected, x, y, z  — as in m_separation_witness
    output:
        True iff an open m-path connects X and Y under Z in the ADMG.
    """
    graph = _require(inputs, "graph", step_index, "m_connection_witness")
    _assert_same_graph(graph, ctx.graph, step_index, "m_connection_witness")
    bidir = inputs.get("bidirected", ctx.bidirected)
    if bidir != ctx.bidirected:
        raise RuleCheckFailed(
            "m_connection_witness: bidirected input does not match context",
            step_index=step_index, rule="m_connection_witness",
        )
    x = _require_atom(inputs, "x", step_index, "m_connection_witness")
    y = _require_atom(inputs, "y", step_index, "m_connection_witness")
    z = _require_atom_set(inputs, "z", step_index, "m_connection_witness")

    recomputed = _verifier_is_m_connected(graph, bidir, x, y, z)
    if isinstance(claimed_output, StructuralResult):
        claimed_bool = claimed_output.value
    else:
        claimed_bool = bool(claimed_output)
    if recomputed != claimed_bool:
        raise RuleCheckFailed(
            f"m_connection_witness claimed {claimed_output!r}, recomputed "
            f"{recomputed!r} for x={x.predicate}, y={y.predicate}, "
            f"|z|={len(z)}",
            step_index=step_index, rule="m_connection_witness",
        )


# ========================================================== registry


# ========================================================== Phase 5 §T / S.T.2

def _relative_time_value(
    atom: Atom,
    *,
    step_index: int,
    rule: str,
    what: str,
) -> int:
    ti = atom.time_index
    if ti is None:
        raise RuleCheckFailed(
            f"{rule}: {what} must carry a relative time_index",
            step_index=step_index, rule=rule,
        )
    return ti.value


def _rule_t1_time_monotonicity(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Phase 5 §T / T1: source time must not be later than destination."""
    graph = _require(inputs, "graph", step_index, "T1_time_monotonicity")
    _assert_same_graph(graph, ctx.graph, step_index, "T1_time_monotonicity")
    src = _require_atom(inputs, "src", step_index, "T1_time_monotonicity")
    dst = _require_atom(inputs, "dst", step_index, "T1_time_monotonicity")
    src_t = _relative_time_value(
        src, step_index=step_index, rule="T1_time_monotonicity", what="src",
    )
    dst_t = _relative_time_value(
        dst, step_index=step_index, rule="T1_time_monotonicity", what="dst",
    )
    recomputed = src_t <= dst_t
    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"T1_time_monotonicity claimed {claimed_output!r}, recomputed "
            f"{recomputed!r} for src_t={src_t}, dst_t={dst_t}",
            step_index=step_index, rule="T1_time_monotonicity",
        )


def _rule_t2_lag_bound(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Phase 5 §T / T2: lag is non-negative.

    The original Phase 5 charter capped lag at 1 (``|t2 - t1| <= 1``)
    as conservative scaffolding for first-order Markov. Real-case
    causes have long latency — '1 week of sugar → cavity', '1 month
    of marathon training → marathon time' — so the upper bound was
    relaxed to admit any non-negative lag. Lag negativity is still
    rejected (cf. T1_time_monotonicity).

    The rule is effectively a redundancy check on top of T1: if T1
    accepts (src.t <= dst.t), T2 also accepts. Kept in the registry
    so existing derivations citing T2 keep validating; future
    runtimes that emit T2 steps get the wider lag range.
    """
    graph = _require(inputs, "graph", step_index, "T2_lag_bound")
    _assert_same_graph(graph, ctx.graph, step_index, "T2_lag_bound")
    src = _require_atom(inputs, "src", step_index, "T2_lag_bound")
    dst = _require_atom(inputs, "dst", step_index, "T2_lag_bound")
    src_t = _relative_time_value(
        src, step_index=step_index, rule="T2_lag_bound", what="src",
    )
    dst_t = _relative_time_value(
        dst, step_index=step_index, rule="T2_lag_bound", what="dst",
    )
    recomputed = (dst_t - src_t) >= 0
    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"T2_lag_bound claimed {claimed_output!r}, recomputed "
            f"{recomputed!r} for src_t={src_t}, dst_t={dst_t}",
            step_index=step_index, rule="T2_lag_bound",
        )


def _rule_t3_unroll_acyclic(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Phase 5 §T / T3: the supplied time-unrolled graph is acyclic."""
    graph = _require(inputs, "graph", step_index, "T3_unroll_acyclic")
    _assert_same_graph(graph, ctx.graph, step_index, "T3_unroll_acyclic")
    recomputed = nx.is_directed_acyclic_graph(graph)
    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"T3_unroll_acyclic claimed {claimed_output!r}, recomputed "
            f"{recomputed!r}",
            step_index=step_index, rule="T3_unroll_acyclic",
        )


# ========================================================== Phase 5 §C / S.C.verifier

def _counterfactual_theta_lookup(
    theta: Theta,
    *,
    target_atom: Atom,
    target_value: bool,
    given: frozenset[tuple[Atom, bool]],
    step_index: int,
    rule: str,
) -> float:
    key = ProbabilityKey(
        target_atom=target_atom,
        target_value=target_value,
        given=given,
    )
    value = theta.get(key)
    if value is None:
        raise RuleCheckFailed(
            f"{rule}: theta is missing required entry {key!r}",
            step_index=step_index, rule=rule,
        )
    return float(value)


def _counterfactual_joint_xy_for_verifier(
    graph: nx.DiGraph,
    theta: Theta,
    query: CounterfactualQuery,
    *,
    bidirected: frozenset[frozenset[Atom]] = frozenset(),
    step_index: int,
    rule: str,
) -> dict[tuple[bool, bool], float]:
    x_atom = query.observed.atom
    y_atom = query.counterfactual_target.atom

    if not set(theta.domain_of(x_atom)) or not set(theta.domain_of(x_atom)) <= {False, True}:
        raise RuleCheckFailed(
            f"{rule}: observed atom must have boolean domain",
            step_index=step_index, rule=rule,
        )
    if not set(theta.domain_of(y_atom)) or not set(theta.domain_of(y_atom)) <= {False, True}:
        raise RuleCheckFailed(
            f"{rule}: target atom must have boolean domain",
            step_index=step_index, rule=rule,
        )

    factorized = _counterfactual_joint_xy_via_ancestral_factorization_for_verifier(
        graph,
        theta,
        x_atom=x_atom,
        y_atom=y_atom,
        bidirected=bidirected,
        step_index=step_index,
        rule=rule,
    )
    if factorized is not None:
        return factorized

    joint: dict[tuple[bool, bool], float] = {}
    for x_val in (False, True):
        for y_val in (False, True):
            joint[(x_val, y_val)] = _counterfactual_joint_cell_for_verifier(
                theta,
                x_atom=x_atom,
                x_val=x_val,
                y_atom=y_atom,
                y_val=y_val,
                step_index=step_index,
                rule=rule,
            )
    return joint


def _counterfactual_joint_xy_via_ancestral_factorization_for_verifier(
    graph: nx.DiGraph,
    theta: Theta,
    *,
    x_atom: Atom,
    y_atom: Atom,
    bidirected: frozenset[frozenset[Atom]],
    step_index: int,
    rule: str,
) -> dict[tuple[bool, bool], float] | None:
    """Verifier-local twin of the scheduler's ancestral BN recovery.

    Keep the same conservative scope: only use directed ancestral
    factorization when no bidirected edge touches the ancestral
    subgraph of {X, Y}; otherwise fall back to the older local
    chain-rule recovery.
    """
    ancestral_nodes = (
        nx.ancestors(graph, x_atom)
        | nx.ancestors(graph, y_atom)
        | {x_atom, y_atom}
    )
    if not ancestral_nodes:
        return None
    if any(pair & ancestral_nodes for pair in bidirected):
        return None

    subgraph = graph.subgraph(ancestral_nodes).copy()
    topo = tuple(nx.topological_sort(subgraph))
    required_keys = _required_probability_keys_for_ancestral_joint_for_verifier(
        subgraph,
        topo=topo,
        theta=theta,
    )
    for key in required_keys:
        if _recover_boolean_theta_value_for_verifier(theta, key) is None:
            return None

    joint: dict[tuple[bool, bool], float] = {
        (False, False): 0.0,
        (False, True): 0.0,
        (True, False): 0.0,
        (True, True): 0.0,
    }
    for assignment in _ancestral_assignments_for_verifier(topo, theta):
        prob = 1.0
        for atom in topo:
            key = _assignment_probability_key_for_verifier(subgraph, atom, assignment)
            value = _recover_boolean_theta_value_for_verifier(theta, key)
            if value is None:
                raise RuleCheckFailed(
                    f"{rule}: missing key survived ancestral precheck",
                    step_index=step_index, rule=rule,
                )
            prob *= value
        joint[(assignment[x_atom], assignment[y_atom])] += prob
    return joint


def _required_probability_keys_for_ancestral_joint_for_verifier(
    graph: nx.DiGraph,
    *,
    topo: tuple[Atom, ...],
    theta: Theta,
) -> tuple[ProbabilityKey, ...]:
    keys: set[ProbabilityKey] = set()
    for assignment in _ancestral_assignments_for_verifier(topo, theta):
        for atom in topo:
            keys.add(_assignment_probability_key_for_verifier(graph, atom, assignment))
    return tuple(sorted(keys, key=_probability_key_sort_key_for_verifier))


def _ancestral_assignments_for_verifier(
    topo: tuple[Atom, ...],
    theta: Theta,
):
    domains = [
        _counterfactual_factorization_domain_for_verifier(theta, atom)
        for atom in topo
    ]
    for values in product(*domains):
        yield dict(zip(topo, values))


def _assignment_probability_key_for_verifier(
    graph: nx.DiGraph,
    atom: Atom,
    assignment: dict[Atom, object],
) -> ProbabilityKey:
    return ProbabilityKey(
        target_atom=atom,
        target_value=assignment[atom],
        given=frozenset(
            (parent, assignment[parent])
            for parent in graph.predecessors(atom)
        ),
    )


def _probability_key_sort_key_for_verifier(key: ProbabilityKey) -> tuple:
    given = tuple(
        sorted(
            (
                (atom.predicate, tuple(arg.name for arg in atom.args), repr(value))
                for atom, value in key.given
            )
        )
    )
    return (
        key.target_atom.predicate,
        tuple(arg.name for arg in key.target_atom.args),
        repr(key.target_value),
        given,
    )


def _counterfactual_factorization_domain_for_verifier(
    theta: Theta,
    atom: Atom,
) -> tuple:
    domain = tuple(theta.domain_of(atom))
    if domain and set(domain) <= {False, True}:
        return (False, True)
    return domain


def _counterfactual_joint_cell_for_verifier(
    theta: Theta,
    *,
    x_atom: Atom,
    x_val: bool,
    y_atom: Atom,
    y_val: bool,
    step_index: int,
    rule: str,
) -> float:
    """Verifier-local counterpart of scheduler's narrow joint recovery.

    Local fallback only. Prefer the ancestor-subgraph factorization
    above; if it is not applicable, still accept either chain-rule orientation:
    - P(X=x) * P(Y=y | X=x)
    - or, if unavailable, P(Y=y) * P(X=x | Y=y)
    """
    x_key = ProbabilityKey(
        target_atom=x_atom,
        target_value=x_val,
        given=frozenset(),
    )
    y_given_x_key = ProbabilityKey(
        target_atom=y_atom,
        target_value=y_val,
        given=frozenset({(x_atom, x_val)}),
    )
    p_x = _recover_boolean_theta_value_for_verifier(theta, x_key)
    p_y_given_x = _recover_boolean_theta_value_for_verifier(theta, y_given_x_key)
    if p_x is not None and p_y_given_x is not None:
        return p_x * p_y_given_x

    y_key = ProbabilityKey(
        target_atom=y_atom,
        target_value=y_val,
        given=frozenset(),
    )
    x_given_y_key = ProbabilityKey(
        target_atom=x_atom,
        target_value=x_val,
        given=frozenset({(y_atom, y_val)}),
    )
    p_y = _recover_boolean_theta_value_for_verifier(theta, y_key)
    p_x_given_y = _recover_boolean_theta_value_for_verifier(theta, x_given_y_key)
    if p_y is not None and p_x_given_y is not None:
        return p_y * p_x_given_y

    raise RuleCheckFailed(
        f"{rule}: theta is missing a recoverable chain-rule factorization "
        f"for joint cell ({x_val!r}, {y_val!r})",
        step_index=step_index, rule=rule,
    )


def _recover_boolean_theta_value_for_verifier(
    theta: Theta,
    key: ProbabilityKey,
) -> float | None:
    value = theta.get(key)
    if value is not None:
        return float(value)
    domain = set(theta.domain_of(key.target_atom))
    if not domain or not domain <= {False, True} or not isinstance(key.target_value, bool):
        return None
    complement = theta.get(
        ProbabilityKey(
            target_atom=key.target_atom,
            target_value=not key.target_value,
            given=key.given,
        )
    )
    if complement is None:
        return None
    return 1.0 - float(complement)


def _cf_bounds_non_decreasing_for_verifier(
    *,
    x_obs: bool,
    p_y1_given_xobs: float,
    factual_y: bool | None,
) -> tuple[float, float]:
    if not x_obs:
        if factual_y is True:
            return 1.0, 1.0
        if factual_y is False:
            return 0.0, 1.0
        return p_y1_given_xobs, 1.0

    if factual_y is True:
        return 0.0, 1.0
    if factual_y is False:
        return 0.0, 0.0
    return 0.0, p_y1_given_xobs


def _cf_bounds_non_increasing_for_verifier(
    *,
    x_obs: bool,
    p_y1_given_xobs: float,
    factual_y: bool | None,
) -> tuple[float, float]:
    if not x_obs:
        if factual_y is True:
            return 0.0, 1.0
        if factual_y is False:
            return 0.0, 0.0
        return 0.0, p_y1_given_xobs

    if factual_y is True:
        return 1.0, 1.0
    if factual_y is False:
        return 0.0, 1.0
    return p_y1_given_xobs, 1.0


def _expected_counterfactual_numeric_result(
    graph: nx.DiGraph,
    query: CounterfactualQuery,
    theta: Theta,
    *,
    bidirected: frozenset[frozenset[Atom]] = frozenset(),
    step_index: int,
    rule: str,
) -> NumericResult:
    if query.assumptions is None or query.assumptions.monotonicity is None:
        raise RuleCheckFailed(
            f"{rule}: query must carry an explicit monotonicity assumption",
            step_index=step_index, rule=rule,
        )

    values = (
        query.observed.value,
        query.counterfactual_intervention.value,
        query.counterfactual_target.value,
        query.factual_target_known,
    )
    for value in values:
        if value is not None and not isinstance(value, bool):
            raise RuleCheckFailed(
                f"{rule}: current verifier scope is boolean-only",
                step_index=step_index, rule=rule,
            )

    joint = _counterfactual_joint_xy_for_verifier(
        graph,
        theta,
        query,
        bidirected=bidirected,
        step_index=step_index,
        rule=rule,
    )
    x_obs = query.observed.value
    x_cf = query.counterfactual_intervention.value
    y_star = query.counterfactual_target.value
    factual_y = query.factual_target_known
    p_x_obs = joint[(x_obs, False)] + joint[(x_obs, True)]
    if p_x_obs == 0:
        raise RuleCheckFailed(
            f"{rule}: zero factual mass for observed value",
            step_index=step_index, rule=rule,
        )
    p_y1_given_xobs = joint[(x_obs, True)] / p_x_obs

    if x_cf == x_obs:
        if factual_y is not None:
            point = 1.0 if factual_y == y_star else 0.0
        else:
            point = p_y1_given_xobs if y_star else 1.0 - p_y1_given_xobs
        return NumericResult(value=point)

    if query.assumptions.monotonicity.value == "non_decreasing":
        low_true, high_true = _cf_bounds_non_decreasing_for_verifier(
            x_obs=x_obs, p_y1_given_xobs=p_y1_given_xobs, factual_y=factual_y,
        )
    else:
        low_true, high_true = _cf_bounds_non_increasing_for_verifier(
            x_obs=x_obs, p_y1_given_xobs=p_y1_given_xobs, factual_y=factual_y,
        )

    if y_star:
        interval = NumericInterval(low=low_true, high=high_true)
    else:
        interval = NumericInterval(low=1.0 - high_true, high=1.0 - low_true)
    if abs(interval.low - interval.high) <= _NUMERIC_TOL:
        return NumericResult(value=interval.low)
    return NumericResult(value=None, interval=interval)


def _numeric_result_matches(
    claimed: NumericResult,
    expected: NumericResult,
) -> bool:
    if claimed.unit != expected.unit:
        return False
    if claimed.value is None or expected.value is None:
        if claimed.value is not None or expected.value is not None:
            return False
    elif abs(float(claimed.value) - float(expected.value)) > _NUMERIC_TOL:
        return False

    if claimed.interval is None or expected.interval is None:
        return claimed.interval is None and expected.interval is None
    return (
        abs(claimed.interval.low - expected.interval.low) <= _NUMERIC_TOL
        and abs(claimed.interval.high - expected.interval.high) <= _NUMERIC_TOL
    )


def _rule_counterfactual_bounds_binary_monotone(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Phase 5 §C verifier rule for the currently landed narrow fragment.

    Recomputes the binary monotone counterfactual point value / bounds
    directly from the verification context:
    - query must be CounterfactualQuery
    - theta must support either
      (a) ancestral BN recovery on the directed ancestral subgraph of
          {X, Y}, or
      (b) the older local chain-rule fallback
    - monotonicity must be explicit on the query
    """
    graph = _require(inputs, "graph", step_index, "counterfactual_bounds_binary_monotone")
    _assert_same_graph(graph, ctx.graph, step_index, "counterfactual_bounds_binary_monotone")
    if not isinstance(ctx.query, CounterfactualQuery):
        raise RuleCheckFailed(
            "counterfactual_bounds_binary_monotone requires CounterfactualQuery context",
            step_index=step_index, rule="counterfactual_bounds_binary_monotone",
        )
    if ctx.theta is None:
        raise RuleCheckFailed(
            "counterfactual_bounds_binary_monotone requires theta in context",
            step_index=step_index, rule="counterfactual_bounds_binary_monotone",
        )
    if not isinstance(claimed_output, NumericResult):
        raise RuleCheckFailed(
            "counterfactual_bounds_binary_monotone output must be NumericResult",
            step_index=step_index, rule="counterfactual_bounds_binary_monotone",
        )

    expected = _expected_counterfactual_numeric_result(
        ctx.graph,
        ctx.query,
        ctx.theta,
        bidirected=ctx.bidirected,
        step_index=step_index,
        rule="counterfactual_bounds_binary_monotone",
    )
    if not _numeric_result_matches(claimed_output, expected):
        raise RuleCheckFailed(
            "counterfactual_bounds_binary_monotone claimed output does not "
            "match the recomputed narrow monotone bounds",
            step_index=step_index, rule="counterfactual_bounds_binary_monotone",
        )


# ============================================ Phase 9 §T9.1.4: T9-1, T9-2

# Verifier-side selection diagram + S-admissibility re-derivation. NO
# import from themis.runtime.transport — independence pin keeps the
# audit honest. The diagram is constructed locally from ctx.graph and
# ctx.selection_nodes; d-separation reuses the verifier-internal
# ``_check_d_separation`` already used by R3 / R5.

_VERIFIER_S_PREFIX = "__S_v__"  # distinct from runtime's __S__ prefix


def _verifier_build_selection_diagram(
    graph: nx.DiGraph,
    selection_nodes: tuple,
) -> tuple[nx.DiGraph, tuple]:
    """Local re-implementation of selection diagram construction. The
    runtime version lives in themis.runtime.transport; this one is
    independent (different prefix, different code path) so the
    independence audit can show it isn't calling the implementation
    it's supposed to be auditing.
    """
    from ..types import Atom as _Atom, ConstTerm as _ConstTerm
    diagram = graph.copy()
    s_atoms: list = []
    for sn in selection_nodes:
        s_atom = _Atom(
            predicate=f"{_VERIFIER_S_PREFIX}{sn.id}",
            args=(_ConstTerm(name=sn.id),),
        )
        s_atoms.append(s_atom)
        diagram.add_node(s_atom, atom=s_atom, kind="selection_node")
        if sn.affects in diagram:
            diagram.add_edge(s_atom, sn.affects)
    return diagram, tuple(s_atoms)


def _verifier_mutilate_incoming(graph: nx.DiGraph, x: Atom) -> nx.DiGraph:
    g = graph.copy()
    g.remove_edges_from(list(g.in_edges(x)))
    return g


def _rule_s_admissibility_check(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """T9-1: Re-derive Bareinboim Theorem 1 S-admissibility.

    Z is S-admissible iff every S node is d-separated from Y given Z
    in G_{\\overline{X}} (the intervention graph). Independent
    reimplementation: builds the selection diagram locally from
    ctx.selection_nodes and runs verifier-internal d-separation."""
    treatment = _require_atom(inputs, "treatment", step_index, "s_admissibility_check")
    outcome = _require_atom(inputs, "outcome", step_index, "s_admissibility_check")
    z = _require_atom_set(inputs, "adjustment_set", step_index, "s_admissibility_check")

    selection_nodes = getattr(ctx, "selection_nodes", ())
    diagram, s_atoms = _verifier_build_selection_diagram(ctx.graph, selection_nodes)
    g_bar_x = _verifier_mutilate_incoming(diagram, treatment)

    # Re-run S-admissibility: for each S, check d-separation from outcome given Z
    recomputed = True
    for s in s_atoms:
        if s not in g_bar_x or outcome not in g_bar_x:
            continue
        if _check_d_separation(g_bar_x, s, outcome, z):
            continue  # d-separated — good, this S is admissible
        recomputed = False
        break

    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"s_admissibility_check claimed {claimed_output!r}, recomputed "
            f"{recomputed!r} (z={[a.predicate for a in z]}, "
            f"|S|={len(s_atoms)})",
            step_index=step_index, rule="s_admissibility_check",
        )


def _rule_transport_formula(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """T9-2: Verify the Bareinboim transport formula has correct shape.

    Checks:
    - claimed_output is a string starting with ``P*(...)``
    - if adjustment_set is non-empty, formula contains ``Σ_{`` summation
      over the adjustment-set variables
    - source_population and target_population are non-empty strings
      (semantic differentiation of P from P*)"""
    treatment = _require_atom(inputs, "treatment", step_index, "transport_formula")
    outcome = _require_atom(inputs, "outcome", step_index, "transport_formula")
    z = _require_atom_set(inputs, "adjustment_set", step_index, "transport_formula")
    source_pop = inputs.get("source_population")
    target_pop = inputs.get("target_population")

    if not isinstance(claimed_output, str):
        raise RuleCheckFailed(
            f"transport_formula output must be a string, got {type(claimed_output).__name__}",
            step_index=step_index, rule="transport_formula",
        )
    if not claimed_output.startswith("P*("):
        raise RuleCheckFailed(
            "transport_formula output must lead with target-population term P*(...)",
            step_index=step_index, rule="transport_formula",
        )
    if outcome.predicate not in claimed_output:
        raise RuleCheckFailed(
            f"transport_formula output missing outcome predicate {outcome.predicate!r}",
            step_index=step_index, rule="transport_formula",
        )
    if treatment.predicate not in claimed_output:
        raise RuleCheckFailed(
            f"transport_formula output missing treatment predicate {treatment.predicate!r}",
            step_index=step_index, rule="transport_formula",
        )
    if z and "Σ_{" not in claimed_output:
        raise RuleCheckFailed(
            "transport_formula has non-empty adjustment_set but formula "
            "lacks Σ summation",
            step_index=step_index, rule="transport_formula",
        )
    for a in z:
        if a.predicate not in claimed_output:
            raise RuleCheckFailed(
                f"transport_formula adjustment variable {a.predicate!r} not "
                "named in formula text",
                step_index=step_index, rule="transport_formula",
            )
    if not isinstance(source_pop, str) or not source_pop:
        if z:
            raise RuleCheckFailed(
                "transport_formula with non-empty Z requires source_population label",
                step_index=step_index, rule="transport_formula",
            )
    if not isinstance(target_pop, str) or not target_pop:
        raise RuleCheckFailed(
            "transport_formula requires target_population label",
            step_index=step_index, rule="transport_formula",
        )


def _rule_identify_via_transport(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict,
    step_output_by_id: dict,
) -> None:
    """T9-final: Confirm the prior s_admissibility_check + transport_formula
    steps were both successful, and the claimed output is a positive
    StructuralResult."""
    criterion_ref = inputs.get("criterion")
    formula_ref = inputs.get("formula")
    if criterion_ref is None or formula_ref is None:
        raise RuleCheckFailed(
            "identify_via_transport requires inputs.criterion and inputs.formula step refs",
            step_index=step_index, rule="identify_via_transport",
        )
    criterion_id = getattr(criterion_ref, "step_id", None) or criterion_ref.get("step_id")
    formula_id = getattr(formula_ref, "step_id", None) or formula_ref.get("step_id")

    criterion_step = step_by_id.get(criterion_id)
    formula_step = step_by_id.get(formula_id)
    if criterion_step is None or formula_step is None:
        raise RuleCheckFailed(
            "identify_via_transport references unknown step_id(s)",
            step_index=step_index, rule="identify_via_transport",
        )
    if criterion_step.rule != "s_admissibility_check":
        raise RuleCheckFailed(
            f"identify_via_transport.criterion must reference an "
            f"s_admissibility_check step, got {criterion_step.rule!r}",
            step_index=step_index, rule="identify_via_transport",
        )
    if formula_step.rule != "transport_formula":
        raise RuleCheckFailed(
            f"identify_via_transport.formula must reference a "
            f"transport_formula step, got {formula_step.rule!r}",
            step_index=step_index, rule="identify_via_transport",
        )

    criterion_output = step_output_by_id.get(criterion_id)
    if criterion_output is not True:
        raise RuleCheckFailed(
            "identify_via_transport: referenced s_admissibility_check did "
            f"not output True (got {criterion_output!r})",
            step_index=step_index, rule="identify_via_transport",
        )

    if not isinstance(claimed_output, StructuralResult) or claimed_output.value is not True:
        raise RuleCheckFailed(
            "identify_via_transport must claim StructuralResult(value=True) "
            "when both criterion and formula steps succeed",
            step_index=step_index, rule="identify_via_transport",
        )


# ========================================================== Phase 2.latent ext §S3.b.2
# Tian / Shpitser ID — verifier independently checks the c-component
# witness without calling identify_via_tian (would be circular). It
# replays c_components on ctx.graph + ctx.bidirected and confirms the
# claim's structural prerequisites.


def _rule_tian_c_decomposition(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Declarative step: 'we ran c-decomposition on ctx.graph'. The
    actual partition is recomputed in identify_via_tian / hedge rules.
    Here we only validate inputs are well-formed."""
    graph = _require(inputs, "graph", step_index, "tian_c_decomposition")
    _assert_same_graph(graph, ctx.graph, step_index, "tian_c_decomposition")
    x = _require_atom(inputs, "x", step_index, "tian_c_decomposition")
    y = _require_atom(inputs, "y", step_index, "tian_c_decomposition")
    if x == y:
        raise RuleCheckFailed(
            "tian_c_decomposition: x and y must differ",
            step_index=step_index, rule="tian_c_decomposition",
        )
    if claimed_output is not True:
        raise RuleCheckFailed(
            f"tian_c_decomposition output must be True, got {claimed_output!r}",
            step_index=step_index, rule="tian_c_decomposition",
        )


def _rule_identify_via_tian(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict,
    step_output_by_id: dict,
) -> None:
    """Verifier-side independent check: re-derive c-components on the
    ADMG and confirm Y can be expressed as a c-factor product where
    the c-component containing Y in G[V\\X] coincides with a
    c-component of G (Shpitser Line 6).

    Uses ``structural_solver.c_components`` as a primitive (a single
    union-find pass — distinct from running the full identify_via_tian
    recursion) so the check is non-circular. The claim 'identifiable'
    is accepted iff:

    - the formula validates against ctx.graph
    - the c-component of Y in G[V\\X] under bidirected restriction
      is a c-component of G under full bidirected (Line 6 sufficient
      condition)
    """
    from ..runtime.structural_solver import c_components
    from ..input.semantic_validator import validate_formula

    decomp_ref = _require(
        inputs, "decomposition", step_index, "identify_via_tian",
    )
    formula = _require(inputs, "formula", step_index, "identify_via_tian")

    if not isinstance(decomp_ref, StepRef):
        raise UnknownRuleInputError(
            "identify_via_tian.decomposition must be a StepRef",
            step_index=step_index, rule="identify_via_tian",
        )
    decomp_step = step_by_id.get(decomp_ref.step_id)
    if decomp_step is None or decomp_step.rule != "tian_c_decomposition":
        raise RuleCheckFailed(
            "identify_via_tian.decomposition must reference a "
            f"tian_c_decomposition step, got "
            f"{getattr(decomp_step, 'rule', None)!r}",
            step_index=step_index, rule="identify_via_tian",
        )

    q = ctx.query
    if not isinstance(q, IdentifyQuery):
        raise RuleCheckFailed(
            "identify_via_tian requires IdentifyQuery context",
            step_index=step_index, rule="identify_via_tian",
        )
    x = q.intervention.atom
    y = q.target

    try:
        validate_formula(formula)
    except Exception as exc:
        raise RuleCheckFailed(
            f"identify_via_tian formula does not validate: {exc}",
            step_index=step_index, rule="identify_via_tian",
        ) from exc

    cc_full = c_components(ctx.graph, ctx.bidirected)
    nodes_minus_x = frozenset(ctx.graph.nodes()) - {x}
    sub = ctx.graph.subgraph(nodes_minus_x)
    bi_minus_x = frozenset(p for p in ctx.bidirected if p <= nodes_minus_x)
    cc_minus_x = c_components(sub, bi_minus_x)

    # Y's c-component in G[V\X] must be a c-component of G.
    y_cc_minus_x = next((c for c in cc_minus_x if y in c), None)
    if y_cc_minus_x is None:
        raise RuleCheckFailed(
            "identify_via_tian: y not present in G[V\\X] c-components",
            step_index=step_index, rule="identify_via_tian",
        )
    if y_cc_minus_x not in cc_full:
        # Either Line 4 split or Line 7 escalation. Verifier accepts
        # only when the formula's structure is consistent with these
        # branches — we check the looser condition that Y's c-component
        # in G[V\\X] is contained in a c-component of G (Line 7
        # sufficient), or equals one (Line 6). Line 4 splits are
        # covered when at least one of the cc_minus_x is in cc_full.
        any_match = any(c in cc_full for c in cc_minus_x)
        if not any_match:
            raise RuleCheckFailed(
                "identify_via_tian: no c-component of G[V\\X] coincides "
                "with a c-component of G — runtime should have punted",
                step_index=step_index, rule="identify_via_tian",
            )

    if not isinstance(claimed_output, StructuralResult) or claimed_output.value is not True:
        raise RuleCheckFailed(
            "identify_via_tian must claim StructuralResult(value=True)",
            step_index=step_index, rule="identify_via_tian",
        )


def _rule_tian_hedge_witness(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict,
    step_output_by_id: dict,
) -> None:
    """Verifier-side hedge check (Shpitser Line 5): re-run c_components
    on the ADMG. A hedge exists when the c-component containing both
    x and y covers everything reachable to y (i.e., x and y in the
    same c-component of G[An_G(Y)])."""
    from ..runtime.structural_solver import c_components

    decomp_ref = _require(
        inputs, "decomposition", step_index, "tian_hedge_witness",
    )
    if not isinstance(decomp_ref, StepRef):
        raise UnknownRuleInputError(
            "tian_hedge_witness.decomposition must be a StepRef",
            step_index=step_index, rule="tian_hedge_witness",
        )
    decomp_step = step_by_id.get(decomp_ref.step_id)
    if decomp_step is None or decomp_step.rule != "tian_c_decomposition":
        raise RuleCheckFailed(
            "tian_hedge_witness.decomposition must reference a "
            "tian_c_decomposition step",
            step_index=step_index, rule="tian_hedge_witness",
        )

    q = ctx.query
    if not isinstance(q, IdentifyQuery):
        raise RuleCheckFailed(
            "tian_hedge_witness requires IdentifyQuery context",
            step_index=step_index, rule="tian_hedge_witness",
        )
    x = q.intervention.atom
    y = q.target

    # Restrict to ancestors of y plus y itself; bidirected restricted
    # accordingly. Hedge condition: x and y in the same c-component of
    # G[An(Y)].
    if y not in ctx.graph.nodes():
        raise RuleCheckFailed(
            "tian_hedge_witness: y not in graph",
            step_index=step_index, rule="tian_hedge_witness",
        )
    ancestors = set(nx.ancestors(ctx.graph, y)) | {y}
    sub = ctx.graph.subgraph(ancestors)
    bi_ancestors = frozenset(p for p in ctx.bidirected if p <= frozenset(ancestors))
    cc = c_components(sub, bi_ancestors)
    x_cc = next((c for c in cc if x in c), None)
    y_cc = next((c for c in cc if y in c), None)
    if x_cc is None or y_cc is None or x_cc != y_cc:
        raise RuleCheckFailed(
            "tian_hedge_witness: x and y are not in the same c-component "
            "of G[An(Y)] — runtime claim of unidentifiability is unsound",
            step_index=step_index, rule="tian_hedge_witness",
        )

    if not isinstance(claimed_output, StructuralResult) or claimed_output.value is not False:
        raise RuleCheckFailed(
            "tian_hedge_witness must claim StructuralResult(value=False)",
            step_index=step_index, rule="tian_hedge_witness",
        )


# rule name -> handler. Each handler has the signature
#   (ctx, inputs, claimed_output, step_index, **maybe step_output_by_id) -> None
# Handlers raise VerificationError subclasses to reject.
#
# R5 and R8 are special because they need the step maps.
_SIMPLE_RULES: dict[str, Callable[..., None]] = {
    "graph_is_dag": _rule_graph_is_dag,
    "d_separation_check": _rule_d_separation_check,
    "backdoor_criterion": _rule_backdoor_criterion,
    "backdoor_adjustment_formula": _rule_backdoor_adjustment_formula,
    "front_door_criterion": _rule_front_door_criterion,
    "front_door_adjustment_formula": _rule_front_door_adjustment_formula,
    "probability_ref_lookup": _rule_probability_ref_lookup,
    "formula_evaluation": _rule_formula_evaluation,
    "unidentifiable_via_backdoor": _rule_unidentifiable_via_backdoor,
    "d_separated": _rule_d_separated,
    "no_directed_path": _rule_no_directed_path,
    "cause_via_directed_path": _rule_cause_via_directed_path,
    "d_connected_via_open_path": _rule_d_connected_via_open_path,
    # Phase 2.latent S4
    "m_separation_witness": _rule_m_separation_witness,
    "m_connection_witness": _rule_m_connection_witness,
    # Phase 5 §T / S.T.2
    "T1_time_monotonicity": _rule_t1_time_monotonicity,
    "T2_lag_bound": _rule_t2_lag_bound,
    "T3_unroll_acyclic": _rule_t3_unroll_acyclic,
    # Phase 5 §C
    "counterfactual_bounds_binary_monotone": _rule_counterfactual_bounds_binary_monotone,
    # Phase 6.iv S.IV.3
    "iv_criterion_check": _rule_iv_criterion_check,
    # Phase 6.mediation S.M.3
    "mediation_nde_nie_check": _rule_mediation_nde_nie_check,
    "mediation_cde_check": _rule_mediation_cde_check,
    # Phase 6.mediation Fix 1 (v0.1.4) — numeric evaluation
    "mediation_numeric_evaluate": _rule_mediation_numeric_evaluate,
    # Phase 9 §T9.1.4 — independent transport audit
    "s_admissibility_check": _rule_s_admissibility_check,
    "transport_formula": _rule_transport_formula,
    # Phase 2.latent ext §S3.b.2 — Tian / Shpitser ID
    "tian_c_decomposition": _rule_tian_c_decomposition,
}
_STEP_REF_RULES = {
    "identify_via_backdoor",
    "identify_via_front_door",
    "identify_via_iv",
    "identify_via_mediation",
    "numeric_result",
    # Phase 7.1 S.N.4
    "numeric_backdoor_estimate",
    # Phase 7.2 S.FDN.3
    "numeric_frontdoor_estimate",
    # Phase 7.3 S.IVN.3
    "numeric_iv_estimate",
    # Phase 9 §T9.1.4 — transport identification
    "identify_via_transport",
    # Phase 2.latent ext §S3.b.2 — Tian / Shpitser ID
    "identify_via_tian",
    "tian_hedge_witness",
}


def known_rule(name: str) -> bool:
    return name in _SIMPLE_RULES or name in _STEP_REF_RULES


def dispatch_rule(
    rule_name: str,
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    if rule_name == "identify_via_backdoor":
        _rule_identify_via_backdoor(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "identify_via_front_door":
        _rule_identify_via_front_door(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "identify_via_iv":
        _rule_identify_via_iv(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "identify_via_mediation":
        _rule_identify_via_mediation(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "numeric_backdoor_estimate":
        _rule_numeric_backdoor_estimate(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "numeric_frontdoor_estimate":
        _rule_numeric_frontdoor_estimate(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "numeric_iv_estimate":
        _rule_numeric_iv_estimate(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "numeric_result":
        _rule_numeric_result(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "identify_via_transport":
        _rule_identify_via_transport(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "identify_via_tian":
        _rule_identify_via_tian(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "tian_hedge_witness":
        _rule_tian_hedge_witness(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    handler = _SIMPLE_RULES[rule_name]  # known_rule guards this
    handler(ctx, inputs, claimed_output, step_index)


# ========================================================== input helpers

def _require(inputs: dict, key: str, step_index: int, rule: str):
    if key not in inputs:
        raise UnknownRuleInputError(
            f"{rule}.{key} is required",
            step_index=step_index, rule=rule,
        )
    return inputs[key]


def _require_atom(inputs: dict, key: str, step_index: int, rule: str) -> Atom:
    v = _require(inputs, key, step_index, rule)
    if not isinstance(v, Atom):
        raise UnknownRuleInputError(
            f"{rule}.{key} must be an Atom, got {type(v).__name__}",
            step_index=step_index, rule=rule,
        )
    return v


def _require_atom_set(
    inputs: dict,
    key: str,
    step_index: int,
    rule: str,
    *,
    allow_missing: bool = False,
) -> frozenset[Atom]:
    if allow_missing and key not in inputs:
        return frozenset()
    v = _require(inputs, key, step_index, rule)
    if isinstance(v, (set, frozenset)):
        items = v
    elif isinstance(v, tuple):
        items = v
    else:
        raise UnknownRuleInputError(
            f"{rule}.{key} must be a set/frozenset/tuple of Atom",
            step_index=step_index, rule=rule,
        )
    for a in items:
        if not isinstance(a, Atom):
            raise UnknownRuleInputError(
                f"{rule}.{key} must contain only Atom, got {type(a).__name__}",
                step_index=step_index, rule=rule,
            )
    return frozenset(items)


def _assert_same_graph(
    provided: nx.DiGraph,
    context: nx.DiGraph,
    step_index: int,
    rule: str,
) -> None:
    """The derivation must reason about the context's graph — not a
    modified copy. If the step's graph disagrees with the context on
    nodes or edges, reject.

    Enforcing identity by ``is`` would be too strict (copies of the
    same graph compare equal on content but not identity). Instead
    compare node and edge sets.
    """
    if set(provided.nodes) != set(context.nodes) or set(provided.edges) != set(context.edges):
        raise RuleCheckFailed(
            f"{rule}: derivation graph differs from context graph",
            step_index=step_index, rule=rule,
        )
