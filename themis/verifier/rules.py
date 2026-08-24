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

import math
from itertools import product
from typing import Any, Callable, Iterator

import networkx as nx

from ..runtime.numeric_estimator import ProbabilityKey, Theta
from ..types import (
    Atom,
    AtomValue,
    BindDecl,
    CausationQuery,
    ConstantExpr,
    CounterfactualQuery,
    EffectQuery,
    SCMCounterfactualQuery,
    FormulaExpr,
    FractionExpr,
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

    bidir = ctx.bidirected
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
    *,
    include_intervention: bool = True,
) -> FormulaExpr:
    """Independent reimplementation of the backdoor adjustment formula
    as specified by Pearl. This is the verifier's own statement of the
    theorem — it does NOT call ``formula_builder``.

    ``include_intervention`` mirrors the producer-independent rule that X
    belongs in the main conditional only when it has a directed path to Y;
    with no such path, ``target ⊥ intervention`` given Z so the conditional
    drops X. The caller derives the flag from the graph itself.

    Shape:

        Z = () → P(Y=y | X=x, observed)        [include_intervention]
                 P(Y=y | observed)             [not include_intervention]
        Z = (Z1,...,Zk) →
            Σ_{z1} ... Σ_{zk}
              P(Y=y | X=x, Z1=z1,...,Zk=zk, observed)
              · Π_i P(Zi=zi | Z1=z1,...,Z_{i-1}=z_{i-1}, observed)
    """
    cond_prefix = (intervention,) if include_intervention else ()
    if len(adjustment_set) == 0:
        return ProbabilityRefExpr(target=target, given=cond_prefix + observed)

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
        given=cond_prefix + z_valueds + observed,
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

    # Independent soundness mirror (the verifier reasons from the graph itself,
    # not from the producer): the intervention belongs in the main conditional
    # only when X has a directed path to Y. With no such path, given Z the
    # target is independent of X so P(Y|X,Z)=P(Y|Z); a formula that still
    # conditions on a non-cause X would name an un-supplyable estimand.
    graph = ctx.graph
    x_atom, y_atom = intervention.atom, target.atom
    x_is_cause = (
        graph is not None
        and x_atom in graph
        and y_atom in graph
        and x_atom != y_atom
        and nx.has_path(graph, x_atom, y_atom)
    )
    expected = _build_expected_backdoor_formula(
        target, intervention, z_tuple, observed,
        include_intervention=x_is_cause,
    )
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


# ============================================== joint (treatment-set) back-door
#
# Independent re-derivation of the generalized adjustment criterion for a
# treatment SET (van der Zander/Liśkiewicz/Textor 2014; Perković et al.
# 2018). This duplicates the structural-solver logic on purpose — if the
# producer and the verifier disagree on whether Z is a valid joint
# adjustment set, the derivation is rejected.


def _verifier_proper_causal_paths(
    graph: nx.DiGraph, treatments: frozenset[Atom], y: Atom,
) -> tuple[set[Atom], set[tuple[Atom, Atom]]]:
    """Return (cn_nodes, first_edges) for proper causal paths from the
    treatment set to Y. A proper causal path touches the treatment set
    only at its start. Independent reimplementation."""
    cn_nodes: set[Atom] = set()
    first_edges: set[tuple[Atom, Atom]] = set()
    for x in treatments:
        if x not in graph or y not in graph or x == y:
            continue
        for raw in nx.all_simple_paths(graph, x, y):
            path = tuple(raw)
            if set(path[1:]) & treatments:
                continue
            cn_nodes.update(path[1:])
            first_edges.add((path[0], path[1]))
    return cn_nodes, first_edges


def _verifier_set_d_connected(
    graph: nx.DiGraph,
    sources: frozenset[Atom],
    dst: Atom,
    conditioning: frozenset[Atom],
) -> bool:
    """True iff some source has an open path to dst given conditioning."""
    for s in sources:
        if s not in graph or dst not in graph or s == dst:
            continue
        for raw in _undirected_paths(graph, s, dst):
            if _path_is_open(graph, tuple(raw), conditioning):
                return True
    return False


def _verifier_set_m_connected(
    graph: nx.DiGraph,
    bidirected: frozenset[frozenset[Atom]],
    sources: frozenset[Atom],
    dst: Atom,
    conditioning: frozenset[Atom],
) -> bool:
    """ADMG analogue of :func:`_verifier_set_d_connected`: True iff some
    source has an open m-path to dst given conditioning in the ADMG.
    Independently reimplemented on the verifier's own m-connection helper
    so the joint-criterion re-derivation never imports the runtime."""
    for s in sources:
        if s == dst:
            continue
        if _verifier_is_m_connected(graph, bidirected, s, dst, conditioning):
            return True
    return False


def _rule_joint_backdoor_criterion(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Z ∪ given is a valid JOINT adjustment set for the treatment SET
    relative to Y iff:

    (i)  (Z ∪ given) ∩ forbidden = ∅, where forbidden = treatments ∪
         (nodes on proper causal paths) ∪ (their descendants), and
    (ii) Z ∪ given separates the treatment set from Y in the proper
         back-door graph (G with the first edge of every proper causal
         path removed) — d-separation for a pure DAG, m-separation when a
         bidirected (latent) context is present.

    inputs:
        graph, treatments (atom set), y (atom), z (atom set),
        given (atom set, optional)
    output:
        True iff (i) ∧ (ii).

    ADMG scope: a non-empty bidirected context switches leg (ii) to
    m-separation in the proper back-door graph (the generalized adjustment
    criterion), independently reimplemented on the verifier's own
    m-connection helper. Leg (i) stays directed-only (proper causal paths
    and their descendants are directed). Empty bidirected → bit-identical
    to the DAG check.
    """
    graph = _require(inputs, "graph", step_index, "joint_backdoor_criterion")
    _assert_same_graph(graph, ctx.graph, step_index, "joint_backdoor_criterion")
    treatments = _require_atom_set(
        inputs, "treatments", step_index, "joint_backdoor_criterion",
    )
    y = _require_atom(inputs, "y", step_index, "joint_backdoor_criterion")
    z = _require_atom_set(inputs, "z", step_index, "joint_backdoor_criterion")
    given = _require_atom_set(
        inputs, "given", step_index, "joint_backdoor_criterion",
        allow_missing=True,
    )

    bidir = ctx.bidirected

    if not treatments or y in treatments or y not in graph:
        recomputed = False
    elif any(t not in graph for t in treatments):
        recomputed = False
    else:
        conditioning = z | given
        cn_nodes, first_edges = _verifier_proper_causal_paths(
            graph, treatments, y,
        )
        forbidden: set[Atom] = set(treatments) | set(cn_nodes)
        for node in cn_nodes:
            forbidden |= nx.descendants(graph, node)
        leg_i = conditioning.isdisjoint(forbidden)
        if leg_i:
            g_pbd = graph.copy()
            g_pbd.remove_edges_from(first_edges)
            if bidir:
                leg_ii = not _verifier_set_m_connected(
                    g_pbd, bidir, treatments, y, conditioning,
                )
            else:
                leg_ii = not _verifier_set_d_connected(
                    g_pbd, treatments, y, conditioning,
                )
            recomputed = leg_ii
        else:
            recomputed = False

    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"joint_backdoor_criterion claimed {claimed_output!r}, "
            f"recomputed {recomputed!r}",
            step_index=step_index, rule="joint_backdoor_criterion",
        )


def _rule_identify_via_joint_backdoor(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Combine a proven ``joint_backdoor_criterion`` step into the claimed
    StructuralResult(value=True). Mirrors ``identify_via_backdoor`` but the
    joint path's identifying formula is the joint g-formula, which the
    data-based estimator evaluates numerically — so the structural
    terminal only certifies the criterion, not a symbolic formula tree."""
    criterion_ref = _require(
        inputs, "criterion", step_index, "identify_via_joint_backdoor",
    )
    if not isinstance(criterion_ref, StepRef):
        raise UnknownRuleInputError(
            "identify_via_joint_backdoor.criterion must be a StepRef",
            step_index=step_index, rule="identify_via_joint_backdoor",
        )
    criterion_out = step_output_by_id.get(criterion_ref.step_id)
    criterion_step = step_by_id.get(criterion_ref.step_id)
    if criterion_out is None or criterion_step is None:
        raise RuleCheckFailed(
            "identify_via_joint_backdoor: referenced criterion step "
            f"{criterion_ref.step_id!r} missing",
            step_index=step_index, rule="identify_via_joint_backdoor",
        )
    if criterion_step.rule != "joint_backdoor_criterion":
        raise RuleCheckFailed(
            "identify_via_joint_backdoor.criterion must reference a "
            "joint_backdoor_criterion step",
            step_index=step_index, rule="identify_via_joint_backdoor",
        )
    if criterion_out is not True:
        raise RuleCheckFailed(
            "identify_via_joint_backdoor: criterion step did not prove True "
            f"(got {criterion_out!r})",
            step_index=step_index, rule="identify_via_joint_backdoor",
        )
    if not isinstance(claimed_output, StructuralResult) or claimed_output.value is not True:
        raise RuleCheckFailed(
            "identify_via_joint_backdoor must claim StructuralResult(value=True)",
            step_index=step_index, rule="identify_via_joint_backdoor",
        )


def _rule_identify_via_general_id(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Combine a proven ``general_id_criterion`` step into the claimed
    StructuralResult(value=True) — the structural terminal for a JOINT
    (or single) general-ID identification.

    Mirrors ``identify_via_joint_backdoor``: the referenced criterion step
    (``general_id_criterion``) carries the real, independently re-run
    identifiability check (the set-valued Shpitser-Pearl ID over the query's
    treatment set). This terminal only certifies that the criterion proved
    True and that the effect is therefore point-identified — the identifying
    formula is the c-factor estimand the data-based estimator evaluates
    numerically, so there is no symbolic formula tree to re-check here."""
    criterion_ref = _require(
        inputs, "criterion", step_index, "identify_via_general_id",
    )
    if not isinstance(criterion_ref, StepRef):
        raise UnknownRuleInputError(
            "identify_via_general_id.criterion must be a StepRef",
            step_index=step_index, rule="identify_via_general_id",
        )
    criterion_out = step_output_by_id.get(criterion_ref.step_id)
    criterion_step = step_by_id.get(criterion_ref.step_id)
    if criterion_out is None or criterion_step is None:
        raise RuleCheckFailed(
            "identify_via_general_id: referenced criterion step "
            f"{criterion_ref.step_id!r} missing",
            step_index=step_index, rule="identify_via_general_id",
        )
    if criterion_step.rule != "general_id_criterion":
        raise RuleCheckFailed(
            "identify_via_general_id.criterion must reference a "
            "general_id_criterion step",
            step_index=step_index, rule="identify_via_general_id",
        )
    if criterion_out is not True:
        raise RuleCheckFailed(
            "identify_via_general_id: criterion step did not prove True "
            f"(got {criterion_out!r})",
            step_index=step_index, rule="identify_via_general_id",
        )
    if not isinstance(claimed_output, StructuralResult) or claimed_output.value is not True:
        raise RuleCheckFailed(
            "identify_via_general_id must claim StructuralResult(value=True)",
            step_index=step_index, rule="identify_via_general_id",
        )


#: The verifier's own transcription of
#: ``themis.estimation.treatment_box.INTERACTION_UNAVAILABLE_KINDS``.
#: Copied rather than imported: a verifier that reads the producer's
#: vocabulary is auditing the producer's spelling against itself.
_INTERACTION_UNAVAILABLE_KINDS = frozenset({
    "corner_unsupported",
    "order_above_cap",
})


def _check_joint_answer(inputs: dict, step_index: int, rule: str) -> None:
    """The two numbers a joint terminal carries, and the rule that an
    absent interaction must say WHICH way it went missing.

    Shared by both joint terminals because the answer shape is shared: what
    differs between the back-door and the general-ID roads is the
    identification the numbers rest on, not what a reader is owed about
    them.

    The interaction is a second quantity resting on a stricter support
    requirement than the contrast — it needs every one of the 2^K corners,
    where the contrast needs two — so a derivation may legitimately carry
    the contrast without it. What it may NOT do is drop it silently:
    absent, the step has to name the species, or the audit cannot tell a
    declared withholding from a number that went missing between the
    estimator and here.
    """
    has_interaction = "interaction_point" in inputs
    if not has_interaction:
        kind = inputs.get("interaction_unavailable")
        if kind not in _INTERACTION_UNAVAILABLE_KINDS:
            raise RuleCheckFailed(
                f"{rule}: interaction_point is absent, so "
                f"interaction_unavailable must be one of "
                f"{sorted(_INTERACTION_UNAVAILABLE_KINDS)}; got {kind!r}",
                step_index=step_index, rule=rule,
            )

    labels = ("joint_point", "interaction_point") if has_interaction \
        else ("joint_point",)
    for label in labels:
        val = inputs.get(label)
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            raise RuleCheckFailed(
                f"{rule}.{label} must be a number; got {val!r}",
                step_index=step_index, rule=rule,
            )

    intervals = [("joint_point", "joint_ci_lower", "joint_ci_upper")]
    if has_interaction:
        intervals.append(
            ("interaction_point", "interaction_ci_lower",
             "interaction_ci_upper"),
        )
    for point_key, lo_key, hi_key in intervals:
        lo = inputs.get(lo_key)
        hi = inputs.get(hi_key)
        if lo is None and hi is None:
            continue
        if lo is None or hi is None:
            raise RuleCheckFailed(
                f"{rule}: {lo_key} and {hi_key} must both be present or "
                "both absent",
                step_index=step_index, rule=rule,
            )
        if not (lo <= inputs[point_key] <= hi):
            raise RuleCheckFailed(
                f"{rule}: {point_key} {inputs[point_key]} outside "
                f"[{lo}, {hi}]",
                step_index=step_index, rule=rule,
            )


def _rule_numeric_joint_backdoor_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Relaxed metadata audit for a data-based JOINT effect estimate
    (mirrors ``numeric_backdoor_estimate``). Audits self-consistency of
    the joint_effect + interaction block without re-training:

    - ``method`` in the joint enum
    - joint point is a number inside its CI when present; the interaction
      point likewise, or absent with ``interaction_unavailable`` naming
      the species that withheld it
    - ``data_hash`` is a SHA-256 hex digest; ``sample_size`` >= 10
    - ``adjustment`` disjoint from the treatment vector and outcome
    - referenced ``criterion`` is a ``joint_backdoor_criterion`` whose
      treatment set + z-set match this step's treatments + adjustment
    """
    criterion_ref = _require(
        inputs, "criterion", step_index, "numeric_joint_backdoor_estimate",
    )
    if not isinstance(criterion_ref, StepRef):
        raise UnknownRuleInputError(
            "numeric_joint_backdoor_estimate.criterion must be a StepRef",
            step_index=step_index, rule="numeric_joint_backdoor_estimate",
        )
    treatments = _require_atom_set(
        inputs, "treatments", step_index, "numeric_joint_backdoor_estimate",
    )
    outcome = _require_atom(
        inputs, "outcome", step_index, "numeric_joint_backdoor_estimate",
    )
    adjustment = _require_atom_set(
        inputs, "adjustment", step_index, "numeric_joint_backdoor_estimate",
    )
    method = inputs.get("method")
    data_hash = inputs.get("data_hash")
    sample_size = inputs.get("sample_size")

    if method not in _NUMERIC_JOINT_METHODS:
        raise RuleCheckFailed(
            f"numeric_joint_backdoor_estimate.method must be one of "
            f"{sorted(_NUMERIC_JOINT_METHODS)}; got {method!r}",
            step_index=step_index, rule="numeric_joint_backdoor_estimate",
        )
    if not isinstance(data_hash, str) or len(data_hash) != _SHA256_HEX_LEN \
            or not all(c in "0123456789abcdef" for c in data_hash):
        raise RuleCheckFailed(
            f"numeric_joint_backdoor_estimate.data_hash must be a "
            f"{_SHA256_HEX_LEN}-char lowercase SHA-256 hex string",
            step_index=step_index, rule="numeric_joint_backdoor_estimate",
        )
    if (
        not isinstance(sample_size, int)
        or isinstance(sample_size, bool)
        or sample_size < _MIN_NUMERIC_SAMPLE_SIZE
    ):
        raise RuleCheckFailed(
            f"numeric_joint_backdoor_estimate.sample_size must be an int "
            f">= {_MIN_NUMERIC_SAMPLE_SIZE}; got {sample_size!r}",
            step_index=step_index, rule="numeric_joint_backdoor_estimate",
        )

    _check_joint_answer(inputs, step_index, "numeric_joint_backdoor_estimate")

    if adjustment & (treatments | {outcome}):
        raise RuleCheckFailed(
            "numeric_joint_backdoor_estimate.adjustment must be disjoint "
            "from the treatment vector and outcome",
            step_index=step_index, rule="numeric_joint_backdoor_estimate",
        )

    criterion_step = step_by_id.get(criterion_ref.step_id)
    if criterion_step is None or criterion_step.rule != "joint_backdoor_criterion":
        raise RuleCheckFailed(
            "numeric_joint_backdoor_estimate.criterion must reference a "
            "joint_backdoor_criterion step",
            step_index=step_index, rule="numeric_joint_backdoor_estimate",
        )
    crit_treatments = criterion_step.inputs.get("treatments")
    crit_z = criterion_step.inputs.get("z")
    if frozenset(crit_treatments or frozenset()) != frozenset(treatments):
        raise RuleCheckFailed(
            "numeric_joint_backdoor_estimate.treatments must equal the "
            "referenced joint_backdoor_criterion treatment set",
            step_index=step_index, rule="numeric_joint_backdoor_estimate",
        )
    if frozenset(crit_z or frozenset()) != frozenset(adjustment):
        raise RuleCheckFailed(
            "numeric_joint_backdoor_estimate.adjustment must equal the "
            "referenced joint_backdoor_criterion z-set",
            step_index=step_index, rule="numeric_joint_backdoor_estimate",
        )

    if not isinstance(claimed_output, StructuralResult) or claimed_output.value is not True:
        raise RuleCheckFailed(
            "numeric_joint_backdoor_estimate output must be "
            "StructuralResult(value=True)",
            step_index=step_index, rule="numeric_joint_backdoor_estimate",
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

    bidir = ctx.bidirected

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

    body: FormulaExpr = ProductExpr(terms=tuple(chain_factors) + (inner_sum,))
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

    bidir = ctx.bidirected

    # IV1 (relevance): Z and X m-connected given W in original G.
    iv1 = _verifier_is_m_connected(graph, bidir, z, x, w)

    # IV2 + IV3 (exogeneity + exclusion): in G with X's outgoing edges
    # removed, Z is m-separated from Y given W. Build mutilated graph
    # independently here — no delegation to structural_solver.
    mutilated = graph.copy()
    mutilated.remove_edges_from(list(mutilated.out_edges(x)))
    iv23 = not _verifier_is_m_connected(mutilated, bidir, z, y, w)

    recomputed = iv1 and iv23
    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"iv_criterion_check claimed {claimed_output!r}, "
            f"recomputed {recomputed!r} (IV1={iv1}, IV2+IV3={iv23}, "
            f"admg={bool(bidir)})",
            step_index=step_index, rule="iv_criterion_check",
        )


def _rule_vector_iv_criterion_check(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify that (instrument Z, conditioning W) is valid for a treatment
    VECTOR X = {X_1 .. X_k} on Y:

        in G with the outgoing edges of EVERY treatment removed, Z is
        m-separated from Y given W.

    Read on the SET, and that is not the conjunction of the scalar criteria
    in either direction. An instrument that reaches Y only through ANOTHER
    treatment of the vector is rejected by ``iv_criterion_check`` for its own
    treatment — correctly, because there the other treatment is a confounder —
    and is valid here, because there that path is inside the intervention.

    Relevance is deliberately no part of the check. The Anderson-Rubin test's
    size is correct whatever the first stage does, so an irrelevant instrument
    makes the region larger and not wrong, and requiring relevance would
    refuse the designs the method exists for. What relevance predicts is
    whether the region comes back bounded, and the route block reports it per
    instrument.

    inputs: graph, y, treatments (frozenset of atoms), instrument,
    conditioning (frozenset of atoms)
    output: bool
    """
    RULE = "vector_iv_criterion_check"
    graph = _require(inputs, "graph", step_index, RULE)
    _assert_same_graph(graph, ctx.graph, step_index, RULE)
    y = _require_atom(inputs, "y", step_index, RULE)
    z = _require_atom(inputs, "instrument", step_index, RULE)
    treatments = _require_atom_set(inputs, "treatments", step_index, RULE)
    w = _require_atom_set(inputs, "conditioning", step_index, RULE)

    if len(treatments) < 2:
        raise RuleCheckFailed(
            f"{RULE}: a treatment VECTOR is two or more treatments; got "
            f"{len(treatments)}",
            step_index=step_index, rule=RULE,
        )
    if y in treatments or z in treatments or z == y:
        raise RuleCheckFailed(
            f"{RULE}: treatments, y and the instrument must be distinct",
            step_index=step_index, rule=RULE,
        )
    if y not in graph or z not in graph or any(t not in graph for t in treatments):
        raise RuleCheckFailed(
            f"{RULE}: a treatment, y, or the instrument is missing from graph",
            step_index=step_index, rule=RULE,
        )
    if w & (set(treatments) | {y, z}):
        raise RuleCheckFailed(
            f"{RULE}: conditioning set must not contain a treatment, y, or z",
            step_index=step_index, rule=RULE,
        )

    # The mutilated graph is built here rather than borrowed, so that a bug in
    # the producer's cut is visible from this side.
    mutilated = graph.copy()
    for t in treatments:
        mutilated.remove_edges_from(list(mutilated.out_edges(t)))
    recomputed = not _verifier_is_m_connected(mutilated, ctx.bidirected, z, y, w)

    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"{RULE} claimed {claimed_output!r}, recomputed {recomputed!r} "
            f"(instrument {z.predicate!r} vs the treatment set "
            f"{sorted(t.predicate for t in treatments)}, admg="
            f"{bool(ctx.bidirected)})",
            step_index=step_index, rule=RULE,
        )


def _rule_general_id_criterion(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify that the effect is point-identified by the general ID
    (Tian–Shpitser c-factor) algorithm on this ADMG — the structural
    licence for a general-ID plug-in numeric estimate.

    Routes on the query's conditioning, so it licenses BOTH data-path
    plug-ins:

    - Unconditional ``P(Y | do(X))`` — re-executes
      ``c_factor.identify_via_tian``.
    - Conditional ``P(Y | do(X), Z)`` — re-executes
      ``c_factor.identify_via_idc`` (Shpitser–Pearl IDC: the Rule-2
      exchange + ratio normalization). IDC is the load-bearing licence
      here: the unconditional Tian criterion can succeed where the
      conditional IDC one FAILS, so a conditional estimate must clear the
      stricter IDC check. The conditioning set is read from the QUERY
      (ctx.query.given), not from a producer input — a producer cannot
      under-report ``given`` to dodge the IDC licence.
    - Joint ``P(Y | do(A, B, …))`` — re-executes
      ``c_factor.identify_via_tian_joint`` on the treatment SET read from
      the QUERY (intervention ∪ extra_interventions). The set is taken from
      ctx.query, never a producer input, so a producer cannot drop a
      treatment to make a harder joint effect look identifiable. v1 joint
      general-ID is unconditional only: a conditioning set on a joint query
      recomputes False (no supported estimand).

    Confirms the routed engine reports ``identifiable`` with a well-formed
    formula. This is the safety-critical check: a number is produced ONLY
    for a genuinely identified effect, never for a hedge.

    It re-runs the ID engine rather than reimplementing it — the deep,
    fully-independent c-factor / IDC replay lives in ``_rule_identify_via_tian``
    / ``_rule_identify_via_idc`` on the identify-query path. Here the relaxed
    numeric audit confirms identifiability, matching the cost trade-off the
    other numeric rules make (verify_numeric_estimate: numerical reproduction
    is prohibitively expensive for a verifier pass).

    inputs: graph, x, y
    output: bool
    """
    from ..runtime import c_factor

    graph = _require(inputs, "graph", step_index, "general_id_criterion")
    _assert_same_graph(graph, ctx.graph, step_index, "general_id_criterion")
    x = _require_atom(inputs, "x", step_index, "general_id_criterion")
    y = _require_atom(inputs, "y", step_index, "general_id_criterion")

    if x not in graph or y not in graph or x == y:
        raise RuleCheckFailed(
            "general_id_criterion: x / y missing from graph or identical",
            step_index=step_index, rule="general_id_criterion",
        )

    bidir = ctx.bidirected
    # Identifiability is independent of the intervention value; use the
    # query's value when available, else a boolean placeholder.
    x_value = True
    given_atoms: tuple = ()
    # The joint treatment SET is read from the QUERY (never a producer input),
    # so a producer cannot drop a treatment to make a harder joint effect look
    # identifiable. ``extra_interventions`` is an EffectQuery field, and that
    # query always carries the primary ``intervention`` beside it, so the set
    # is complete exactly when the extras are.
    joint_treatments: frozenset = frozenset()
    intervention = getattr(ctx.query, "intervention", None)
    if intervention is not None:
        x_value = intervention.value
        extras = getattr(ctx.query, "extra_interventions", None)
        if extras:
            joint_treatments = frozenset(
                {intervention.atom, *(iv.atom for iv in extras)}
            )
    given = getattr(ctx.query, "given", None)
    if given:
        given_atoms = tuple(g.atom for g in given)

    if joint_treatments and given_atoms:
        # Conditional JOINT effect P(Y | do(A, B, …), Z): out of v1 scope —
        # there is no supported estimand, so no derivation can ever license a
        # number here. Recompute False so a tampered "identifiable" claim on
        # a conditional joint query is rejected.
        recomputed = False
    elif joint_treatments:
        # Joint intervention do(X, extras…) → set-valued Shpitser-Pearl ID.
        # The declared primary x must be one of the query's joint treatments.
        if x not in joint_treatments:
            raise RuleCheckFailed(
                "general_id_criterion: joint criterion's x must be one of the "
                "query's joint treatments",
                step_index=step_index, rule="general_id_criterion",
            )
        joint_res = c_factor.identify_via_tian_joint(
            graph, bidir, dict.fromkeys(joint_treatments, x_value), y)
        recomputed = bool(joint_res.identifiable and joint_res.formula is not None)
    elif given_atoms:
        # Conditional query → IDC licence (see docstring). Read the
        # conditioning from the query itself, so the check is against the
        # real P(Y | do(X), Z) — never a producer-narrowed one.
        idc_res = c_factor.identify_via_idc(
            graph, bidir, x, y, given_atoms, x_value)
        recomputed = bool(idc_res.identifiable and idc_res.formula is not None)
    else:
        tian_res = c_factor.identify_via_tian(graph, bidir, x, y, x_value)
        recomputed = bool(tian_res.identifiable and tian_res.formula is not None)
    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"general_id_criterion claimed {claimed_output!r}, but the ID "
            f"engine recomputed identifiable={recomputed!r}",
            step_index=step_index, rule="general_id_criterion",
        )


def _rule_ctf_conjunction_criterion(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify that a counterfactual conjunction P(γ) / P(γ|δ) is identified
    by ID* (δ empty) / IDC* (δ present) on this ADMG — the structural
    licence for a counterfactual-conjunction plug-in numeric estimate.

    Re-runs ``ctf_identify.id_star`` / ``idc_star`` on the context's
    (graph, bidirected) and the query's γ / δ, and confirms the outcome is
    an identified estimand (a FormulaExpr, or the inconsistent-``ZERO``
    constant). ``FAIL`` (non-identifiable) and ``UNDEFINED`` (``P(δ)=0``)
    must NEVER back a numeric estimate — a number is produced only for a
    genuinely identified counterfactual. Like ``general_id_criterion``, it
    re-runs the engine rather than reimplementing it; the deep,
    fully-independent semantic replay lives on the structural
    counterfactual-conjunction path (``verify_counterfactual_conjunction``).

    inputs: graph
    output: bool
    """
    from ..runtime.ctf_identify import (
        CtfEvent,
        FAIL,
        UNDEFINED,
        id_star,
        idc_star,
    )
    from ..types import CounterfactualConjunctionQuery

    graph = _require(inputs, "graph", step_index, "ctf_conjunction_criterion")
    _assert_same_graph(graph, ctx.graph, step_index, "ctf_conjunction_criterion")

    q = getattr(ctx, "query", None)
    if not isinstance(q, CounterfactualConjunctionQuery):
        raise RuleCheckFailed(
            "ctf_conjunction_criterion requires a "
            "CounterfactualConjunctionQuery in the verification context",
            step_index=step_index, rule="ctf_conjunction_criterion",
        )

    bidir = ctx.bidirected

    def _to_gamma(events):
        return tuple(
            CtfEvent(
                variable=e.variable,
                subscript=frozenset((s.atom, s.value) for s in e.subscript),
                value=e.value,
            )
            for e in events
        )

    gamma = _to_gamma(q.events)
    delta = _to_gamma(q.condition)
    outcome = idc_star(graph, bidir, gamma, delta) if delta \
        else id_star(graph, bidir, gamma)
    # ZERO (an inconsistent conjunction, P=0) IS an identified answer.
    identified = outcome is not FAIL and outcome is not UNDEFINED
    if identified != bool(claimed_output):
        raise RuleCheckFailed(
            f"ctf_conjunction_criterion claimed {claimed_output!r}, but the "
            f"ID*/IDC* engine recomputed identifiable={identified!r}",
            step_index=step_index, rule="ctf_conjunction_criterion",
        )


def _rule_id_star_identification(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Structural licence for a general counterfactual (ID*) estimand.

    Re-runs ``ctf_identify.id_star`` on the context's (graph, bidirected)
    and the query's conjunction γ, and confirms the outcome CLASS matches
    the claimed result: an identified estimand (a FormulaExpr, or
    ``P(γ)=0`` for an inconsistent γ). ``FAIL`` (non-identifiable) must
    never back a structurally_solved step. Like ``general_id_criterion``,
    this re-runs the engine rather than reimplementing it; the deep,
    fully-independent check that the formula computes the true ``P(γ)`` is
    the Monte-Carlo semantic probe in ``verify_counterfactual_conjunction``
    (mirroring how ``verify_identify`` layers the semantic probe on top of
    the per-method structural rules).

    inputs: graph, formula
    output: StructuralResult(value=True)
    """
    from ..runtime.ctf_identify import (
        CtfEvent,
        FAIL,
        UNDEFINED,
        ZERO,
        id_star,
        idc_star,
    )
    from ..types import (
        ConstantExpr,
        CounterfactualConjunctionQuery,
        StructuralResult,
    )

    graph = _require(inputs, "graph", step_index, "id_star_identification")
    _assert_same_graph(graph, ctx.graph, step_index, "id_star_identification")

    q = getattr(ctx, "query", None)
    if not isinstance(q, CounterfactualConjunctionQuery):
        raise RuleCheckFailed(
            "id_star_identification requires a CounterfactualConjunctionQuery "
            "in the verification context",
            step_index=step_index, rule="id_star_identification",
        )
    if not (isinstance(claimed_output, StructuralResult)
            and claimed_output.value is True):
        raise RuleCheckFailed(
            "id_star_identification output must be StructuralResult(value=True)",
            step_index=step_index, rule="id_star_identification",
        )

    bidir = ctx.bidirected

    def _to_gamma(events):
        return tuple(
            CtfEvent(
                variable=e.variable,
                subscript=frozenset((s.atom, s.value) for s in e.subscript),
                value=e.value,
            )
            for e in events
        )

    gamma = _to_gamma(q.events)
    delta = _to_gamma(q.condition)
    # Conditional (IDC*) when δ is present; unconditional (ID*) otherwise —
    # re-run the SAME engine dispatch the scheduler used.
    outcome = idc_star(graph, bidir, gamma, delta) if delta \
        else id_star(graph, bidir, gamma)
    if outcome is FAIL or outcome is UNDEFINED:
        raise RuleCheckFailed(
            "id_star_identification: the ID*/IDC* engine reports P(γ|δ) "
            "NON-identifiable or UNDEFINED, but the result claims a "
            "structural solution",
            step_index=step_index, rule="id_star_identification",
        )
    claimed_formula = inputs.get("formula")
    claimed_zero = (
        isinstance(claimed_formula, ConstantExpr)
        and claimed_formula.value == 0.0
    )
    engine_zero = outcome is ZERO
    if claimed_zero != engine_zero:
        raise RuleCheckFailed(
            f"id_star_identification: claimed P(γ)=0 is {claimed_zero}, but "
            f"the ID* engine reports inconsistent={engine_zero}",
            step_index=step_index, rule="id_star_identification",
        )


# ----- Fix 6 (v0.1.5, audit follow-up) — IV-in-effect Wald LATE rule -----

def _rule_iv_wald_numeric_evaluate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify the bundled IV Wald LATE numeric step (Fix 6), stratified
    over a conditional instrument's conditioning set.

    Inputs:
      - ``target``: ValuedAtom (Y=y)
      - ``intervention_treated``: ValuedAtom (X=x_treated)
      - ``instrument_treated``: ValuedAtom (Z=z_treated)
      - ``instrument_control``: ValuedAtom (Z=z_control)
      - ``instrument_conditioning``: ordered tuple of Atoms — W, empty
        for a marginal instrument. The order is what gives each
        stratum's positional ``values`` a meaning, and it fixes the
        chain-rule factorization of P(W=w).
      - ``monotonicity``: string label (just metadata; the semantic
        check lives at scheduler dispatch time, not here)

    Output dict: ``strata`` (one entry per W-stratum, carrying its
    weight and its four conditionals), ``outcome_shift``,
    ``treatment_shift``, ``late``.

    Three independent recomputations, none of which take the producer's
    word for anything:

    1. **(Z, W) is re-checked as an instrument** against ctx.graph here,
       rather than leaning on the sibling iv_criterion_check step. The
       arithmetic below is valid only at the W it was actually computed
       at, and what this catches is a producer that ran the MARGINAL
       Wald and recorded W = ∅ for a Z that is only conditionally valid.
    2. **The strata are re-enumerated** from ctx.theta's domains, so a
       producer that quietly dropped one — the stratum whose theta cell
       was missing, say — does not get to average over the rest and call
       it the population.
    3. **The aggregate is recomputed as a ratio of averages.** The
       average of the per-stratum ratios is the plausible wrong answer
       here, and it agrees with the right one exactly when the first
       stage is constant across strata — which is precisely the case a
       test would fail to notice.
    """
    RULE = "iv_wald_numeric_evaluate"
    target = _require(inputs, "target", step_index, RULE)
    treated = _require(inputs, "intervention_treated", step_index, RULE)
    z_treated = _require(inputs, "instrument_treated", step_index, RULE)
    z_control = _require(inputs, "instrument_control", step_index, RULE)
    conditioning = _require(inputs, "instrument_conditioning", step_index, RULE)

    for name, va in (
        ("target", target),
        ("intervention_treated", treated),
        ("instrument_treated", z_treated),
        ("instrument_control", z_control),
    ):
        if not isinstance(va, ValuedAtom):
            raise RuleCheckFailed(
                f"{RULE}: {name} must be a ValuedAtom",
                step_index=step_index, rule=RULE,
            )
    if not isinstance(conditioning, tuple) or any(
        not isinstance(a, Atom) for a in conditioning
    ):
        raise RuleCheckFailed(
            f"{RULE}: instrument_conditioning must be an ordered tuple of Atoms",
            step_index=step_index, rule=RULE,
        )

    if not isinstance(claimed_output, dict):
        raise RuleCheckFailed(
            f"{RULE} output must be a dict", step_index=step_index, rule=RULE,
        )

    theta = getattr(ctx, "theta", None)
    if theta is None:
        raise RuleCheckFailed(
            f"{RULE} requires theta in ctx", step_index=step_index, rule=RULE,
        )

    y_atom, y_val = target.atom, target.value
    x_atom, x_val = treated.atom, treated.value
    z_atom = z_treated.atom

    # (1) Re-establish the licence. A Wald ratio computed at the wrong
    # conditioning set is not a LATE at all, so the instrument check is
    # part of THIS step's obligation, not a neighbour's.
    graph = ctx.graph
    bidir = ctx.bidirected
    for name, atom in (("target", y_atom), ("treatment", x_atom),
                       ("instrument", z_atom)):
        if atom not in graph:
            raise RuleCheckFailed(
                f"{RULE}: {name} atom is not in the graph",
                step_index=step_index, rule=RULE,
            )
    if set(conditioning) & {x_atom, y_atom, z_atom}:
        raise RuleCheckFailed(
            f"{RULE}: the conditioning set must not contain the treatment, "
            f"outcome or instrument",
            step_index=step_index, rule=RULE,
        )
    w_set = frozenset(conditioning)
    if not _verifier_is_m_connected(graph, bidir, z_atom, x_atom, w_set):
        raise RuleCheckFailed(
            f"{RULE}: instrument is not m-connected to the treatment given "
            f"the recorded conditioning set — IV1 (relevance) fails, so the "
            f"first stage is not an instrument shift",
            step_index=step_index, rule=RULE,
        )
    mutilated = graph.copy()
    mutilated.remove_edges_from(list(mutilated.out_edges(x_atom)))
    if _verifier_is_m_connected(mutilated, bidir, z_atom, y_atom, w_set):
        raise RuleCheckFailed(
            f"{RULE}: instrument is m-connected to the outcome given the "
            f"recorded conditioning set in G[x-bar] — IV2/IV3 (exclusion + "
            f"exogeneity) fail, so this ratio is not a LATE at the "
            f"conditioning set it was computed at",
            step_index=step_index, rule=RULE,
        )

    def lookup(target_atom, target_val, given_pairs, label):
        key = ProbabilityKey(
            target_atom=target_atom,
            target_value=target_val,
            given=frozenset(given_pairs),
        )
        value = theta.entries.get(key)
        if value is None:
            raise RuleCheckFailed(
                f"{RULE}: verifier theta lookup failed for {label}",
                step_index=step_index, rule=RULE,
            )
        return value

    # (2) Re-enumerate the strata from the declared domains, in the
    # recorded order, and expand P(W=w) by the chain rule.
    expected_strata = []
    for values in product(*(theta.domain_of(w) for w in conditioning)):
        w_pairs = tuple(zip(conditioning, values))
        weight = 1.0
        for i, (w_atom, w_value) in enumerate(w_pairs):
            weight *= lookup(
                w_atom, w_value, w_pairs[:i], f"stratum weight factor {i}",
            )
        expected_strata.append(
            {
                "values": tuple(values),
                "weight": weight,
                "p_y_given_z_treated": lookup(
                    y_atom, y_val, ((z_atom, z_treated.value), *w_pairs),
                    "p_y_given_z_treated",
                ),
                "p_y_given_z_control": lookup(
                    y_atom, y_val, ((z_atom, z_control.value), *w_pairs),
                    "p_y_given_z_control",
                ),
                "p_x_given_z_treated": lookup(
                    x_atom, x_val, ((z_atom, z_treated.value), *w_pairs),
                    "p_x_given_z_treated",
                ),
                "p_x_given_z_control": lookup(
                    x_atom, x_val, ((z_atom, z_control.value), *w_pairs),
                    "p_x_given_z_control",
                ),
            }
        )

    claimed_strata = claimed_output.get("strata")
    if not isinstance(claimed_strata, (list, tuple)):
        raise RuleCheckFailed(
            f"{RULE}: claimed_output.strata must be a sequence",
            step_index=step_index, rule=RULE,
        )
    if len(claimed_strata) != len(expected_strata):
        raise RuleCheckFailed(
            f"{RULE}: claimed {len(claimed_strata)} strata for a conditioning "
            f"set whose declared domains give {len(expected_strata)} — the "
            f"weighted average does not run over the population it claims to",
            step_index=step_index, rule=RULE,
        )

    for index, (claimed_cell, cell) in enumerate(
        zip(claimed_strata, expected_strata)
    ):
        if not isinstance(claimed_cell, dict):
            raise RuleCheckFailed(
                f"{RULE}: strata[{index}] must be a dict",
                step_index=step_index, rule=RULE,
            )
        claimed_values = tuple(claimed_cell.get("values") or ())
        if claimed_values != cell["values"]:
            raise RuleCheckFailed(
                f"{RULE}: strata[{index}] is recorded at {claimed_values!r} "
                f"but the enumeration in the recorded conditioning order "
                f"reaches {cell['values']!r}",
                step_index=step_index, rule=RULE,
            )
        for key in (
            "weight",
            "p_y_given_z_treated", "p_y_given_z_control",
            "p_x_given_z_treated", "p_x_given_z_control",
        ):
            _pin_number(
                claimed_cell, key, cell[key],
                step_index=step_index, rule=RULE, where=f"strata[{index}]",
            )

    # (3) Ratio of averages — each stratum weighted by its own complier
    # share, which is what makes the result the effect among compliers.
    outcome_shift = sum(
        c["weight"] * (c["p_y_given_z_treated"] - c["p_y_given_z_control"])
        for c in expected_strata
    )
    treatment_shift = sum(
        c["weight"] * (c["p_x_given_z_treated"] - c["p_x_given_z_control"])
        for c in expected_strata
    )
    if abs(treatment_shift) < 1e-12:
        raise RuleCheckFailed(
            f"{RULE}: the weighted first stage (instrument shift on X) ≈ 0; "
            f"Wald undefined",
            step_index=step_index, rule=RULE,
        )
    for key, val in (
        ("outcome_shift", outcome_shift),
        ("treatment_shift", treatment_shift),
        ("late", outcome_shift / treatment_shift),
    ):
        _pin_number(
            claimed_output, key, val,
            step_index=step_index, rule=RULE, where="output",
        )


def _require_reported_probability(
    holder: dict,
    key: str,
    *,
    step_index: int,
    rule: str,
) -> float:
    """The probability ``holder[key]`` reports, checked and handed back.

    Returning the checked value is what lets the caller go on reasoning about
    a number: a check that only raises leaves the reader (and the reader's
    type checker) holding whatever the step happened to put there."""
    value = holder.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not (0.0 <= value <= 1.0)
    ):
        raise RuleCheckFailed(
            f"{rule}.{key} must be a probability in [0, 1]; got {value!r}",
            step_index=step_index, rule=rule,
        )
    return value


def _envelope_number(
    envelope: dict,
    key: str,
    *,
    step_index: int,
    rule: str,
    where: str,
) -> float:
    """The finite number the claimed envelope reports at ``key``.

    The envelope is the producer's claim, so an entry that is not a finite
    number is a malformed claim to reject, and it has to be rejected *here*
    because neither way of failing survives being passed on. A non-number
    leaves the verifier as whatever ``float`` raises on it rather than as a
    verdict — and asking merely whether ``float`` would accept the type is
    not enough, because ``float`` converts an ``int`` but *parses* a ``str``,
    so a string that is not a numeral gets through a type test and blows up
    on the next line. A NaN fails in the opposite direction: it is a genuine
    ``float``, every ``abs(claimed - expected) > tol`` comparison downstream
    is False against it, so an unguarded NaN bound is silently *certified*
    instead of raised on."""
    value = envelope.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise RuleCheckFailed(
            f"{rule}: {where} reports {key}={value!r}, "
            f"which is not a finite number",
            step_index=step_index, rule=rule,
        )
    return float(value)


def _require_number_column(
    value: object,
    name: str,
    *,
    step_index: int,
    rule: str,
) -> tuple[float, ...]:
    """One column of a per-stratum table, checked and handed back."""
    if not isinstance(value, tuple) or not value:
        raise RuleCheckFailed(
            f"{rule}.{name} must be a non-empty tuple; got {value!r}",
            step_index=step_index, rule=rule,
        )
    if any(
        not isinstance(v, (int, float)) or isinstance(v, bool)
        for v in value
    ):
        raise RuleCheckFailed(
            f"{rule}.{name} must hold numbers",
            step_index=step_index, rule=rule,
        )
    return value


def _pin_number(
    holder: dict,
    key: str,
    expected: float,
    *,
    step_index: int,
    rule: str,
    where: str,
) -> None:
    """Assert ``holder[key]`` is present, numeric, and equals the
    independently recomputed ``expected`` within the paired-implementation
    tolerance."""
    if key not in holder:
        raise RuleCheckFailed(
            f"{rule}: {where} missing {key!r}",
            step_index=step_index, rule=rule,
        )
    claimed = holder[key]
    if isinstance(claimed, bool) or not isinstance(claimed, (int, float)):
        raise RuleCheckFailed(
            f"{rule}: {where}.{key} must be numeric",
            step_index=step_index, rule=rule,
        )
    if abs(float(claimed) - expected) > _NUMERIC_TOL:
        raise RuleCheckFailed(
            f"{rule}: {where}.{key} mismatch — claimed {claimed!r}, "
            f"recomputed {expected!r}",
            step_index=step_index, rule=rule,
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

    bidir = ctx.bidirected

    # M4: W has no X-descendants. Compute descendants from the directed
    # edges of G directly (BFS), without importing networkx.descendants.
    x_desc = _verifier_directed_descendants(graph, x)
    if w & x_desc:
        m4 = False
    else:
        m4 = True

    # Build G\bar{X} (X's outgoing edges removed)
    g_bar_x = graph.copy()
    g_bar_x.remove_edges_from(list(g_bar_x.out_edges(x)))

    # M1: Y ⊥ X | W in G\bar{X}
    m1 = not _verifier_is_m_connected(g_bar_x, bidir, x, y, w)

    # M2: M ⊥ X | W in G\bar{X}
    m2 = not _verifier_is_m_connected(g_bar_x, bidir, x, m, w)

    # Build G\bar{M} (M's outgoing edges removed)
    g_bar_m = graph.copy()
    g_bar_m.remove_edges_from(list(g_bar_m.out_edges(m)))

    # M3: Y ⊥ M | X, W in G\bar{M}
    xw = w | {x}
    m3 = not _verifier_is_m_connected(g_bar_m, bidir, m, y, xw)

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

    bidir = ctx.bidirected

    # C2: W has no descendants of X or M
    x_desc = _verifier_directed_descendants(graph, x)
    m_desc = _verifier_directed_descendants(graph, m)
    if w & (x_desc | m_desc):
        c2 = False
    else:
        c2 = True

    # Build G\bar{XM}: remove X's and M's outgoing edges
    g_bar_xm = graph.copy()
    g_bar_xm.remove_edges_from(list(g_bar_xm.out_edges(x)))
    g_bar_xm.remove_edges_from(list(g_bar_xm.out_edges(m)))

    # C1: both Y ⊥ X and Y ⊥ M given W in G\bar{XM}
    c1_x = not _verifier_is_m_connected(g_bar_xm, bidir, x, y, w)
    c1_m = not _verifier_is_m_connected(g_bar_xm, bidir, m, y, w)
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


def _rule_mediation_nde_nie_joint_check(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify the JOINT NDE/NIE four-condition check for a mediator SET
    (VanderWeele-Vansteelandt 2014) — Pearl's conditions with M a vector:

    M1: Y m-separated from X given W            in G\\bar{X}
    M2: each M_j m-separated from X given W     in G\\bar{X}
    M3: each M_j m-separated from Y given {X}∪W in G\\bar{M_set}
        (outgoing edges of EVERY set member removed)
    M4: W contains no descendants of X in G

    Treating the set as a block is what tolerates a recanting witness
    inside the set: removing every member's outgoing edges cuts the
    intra-set confounding path, so M3 passes where a single-mediator M4
    would fail. Independent reimplementation — does not call
    structural_solver.
    """
    rule = "mediation_nde_nie_joint_check"
    graph = _require(inputs, "graph", step_index, rule)
    _assert_same_graph(graph, ctx.graph, step_index, rule)
    x = _require_atom(inputs, "x", step_index, rule)
    y = _require_atom(inputs, "y", step_index, rule)
    ms = _require_atom_set(inputs, "mediators", step_index, rule)
    w = _require_atom_set(inputs, "adjustment", step_index, rule)

    if not ms:
        raise RuleCheckFailed(
            f"{rule}: mediator set must be non-empty",
            step_index=step_index, rule=rule,
        )
    if x not in graph or y not in graph or not (ms <= set(graph.nodes)):
        raise RuleCheckFailed(
            f"{rule}: x, y, or a mediator missing from graph",
            step_index=step_index, rule=rule,
        )
    if x == y or x in ms or y in ms:
        raise RuleCheckFailed(
            f"{rule}: x, y, and every mediator must be distinct",
            step_index=step_index, rule=rule,
        )
    if w & ({x, y} | ms):
        raise RuleCheckFailed(
            f"{rule}: adjustment must not contain x, y, or any mediator",
            step_index=step_index, rule=rule,
        )

    bidir = ctx.bidirected

    # M4: W has no X-descendants.
    x_desc = _verifier_directed_descendants(graph, x)
    m4 = not (w & x_desc)

    # G\bar{X}
    g_bar_x = graph.copy()
    g_bar_x.remove_edges_from(list(g_bar_x.out_edges(x)))

    # M1: Y ⊥ X | W
    m1 = not _verifier_is_m_connected(g_bar_x, bidir, x, y, w)
    # M2: each M_j ⊥ X | W
    m2 = all(
        not _verifier_is_m_connected(g_bar_x, bidir, x, m, w)
        for m in ms
    )

    # G\bar{M_set}: remove outgoing edges of EVERY mediator.
    g_bar_ms = graph.copy()
    for m in ms:
        g_bar_ms.remove_edges_from(list(g_bar_ms.out_edges(m)))
    xw = w | {x}
    # M3: each M_j ⊥ Y | {X}∪W
    m3 = all(
        not _verifier_is_m_connected(g_bar_ms, bidir, m, y, xw)
        for m in ms
    )

    recomputed = m1 and m2 and m3 and m4
    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"{rule} claimed {claimed_output!r}, recomputed {recomputed!r} "
            f"(M1={m1}, M2={m2}, M3={m3}, M4={m4})",
            step_index=step_index, rule=rule,
        )


def _rule_mediation_cde_joint_check(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify backdoor-based CDE-for-a-set identification — the ordinary
    back-door criterion for the JOINT intervention do(X, M_set) that holds
    the whole mediator block fixed. The single-mediator CDE conditions
    (``mediation_cde_check``) with M a vector:

    C2: W contains no descendant of X or of any M_j.
    C1: in G\\bar{X,M_set} (outgoing edges of X AND every M_j removed),
        Y m-separated from X given W AND from each M_j given W.

    Weaker than the joint NDE/NIE conditions (no X-M_set no-confounding
    requirement) — identifies where the natural effects fail under a latent
    X<->M edge. Independent reimplementation; does not call structural_solver.
    """
    rule = "mediation_cde_joint_check"
    graph = _require(inputs, "graph", step_index, rule)
    _assert_same_graph(graph, ctx.graph, step_index, rule)
    x = _require_atom(inputs, "x", step_index, rule)
    y = _require_atom(inputs, "y", step_index, rule)
    ms = _require_atom_set(inputs, "mediators", step_index, rule)
    w = _require_atom_set(inputs, "adjustment", step_index, rule)

    if not ms:
        raise RuleCheckFailed(
            f"{rule}: mediator set must be non-empty",
            step_index=step_index, rule=rule,
        )
    if x not in graph or y not in graph or not (ms <= set(graph.nodes)):
        raise RuleCheckFailed(
            f"{rule}: x, y, or a mediator missing from graph",
            step_index=step_index, rule=rule,
        )
    if x == y or x in ms or y in ms:
        raise RuleCheckFailed(
            f"{rule}: x, y, and every mediator must be distinct",
            step_index=step_index, rule=rule,
        )
    if w & ({x, y} | ms):
        raise RuleCheckFailed(
            f"{rule}: adjustment must not contain x, y, or any mediator",
            step_index=step_index, rule=rule,
        )

    bidir = ctx.bidirected

    # C2: W has no descendants of X or of any set member.
    x_desc = _verifier_directed_descendants(graph, x)
    m_desc: set = set()
    for m in ms:
        m_desc |= _verifier_directed_descendants(graph, m)
    c2 = not (w & (x_desc | m_desc))

    # G\bar{X,M_set}: remove outgoing edges of X AND every mediator.
    g_bar = graph.copy()
    g_bar.remove_edges_from(list(g_bar.out_edges(x)))
    for m in ms:
        g_bar.remove_edges_from(list(g_bar.out_edges(m)))

    # C1: Y ⊥ X | W and each M_j ⊥ Y | W in G\bar{X,M_set}.
    c1_x = not _verifier_is_m_connected(g_bar, bidir, x, y, w)
    c1_m = all(
        not _verifier_is_m_connected(g_bar, bidir, m, y, w)
        for m in ms
    )
    c1 = c1_x and c1_m

    recomputed = c1 and c2
    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"{rule} claimed {claimed_output!r}, recomputed {recomputed!r} "
            f"(C1={c1}, C2={c2})",
            step_index=step_index, rule=rule,
        )


def _rule_identify_via_mediation_joint(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Consume a mediation_nde_nie_joint_check and a mediation_cde_joint_check
    and conclude structural identifiability of the joint decomposition.

    ``claimed_output.value`` must be True iff EITHER referenced step output is
    True — the joint natural effects (block strategy) or the CDE-for-a-set
    (back-door), mirroring the single-mediator ``identify_via_mediation``.
    """
    rule = "identify_via_mediation_joint"
    nde_ref = _require(inputs, "nde_nie", step_index, rule)
    cde_ref = _require(inputs, "cde", step_index, rule)
    if not isinstance(nde_ref, StepRef) or not isinstance(cde_ref, StepRef):
        raise UnknownRuleInputError(
            f"{rule} nde_nie and cde inputs must be StepRef",
            step_index=step_index, rule=rule,
        )
    nde_step = step_by_id.get(nde_ref.step_id)
    cde_step = step_by_id.get(cde_ref.step_id)
    nde_out = step_output_by_id.get(nde_ref.step_id)
    cde_out = step_output_by_id.get(cde_ref.step_id)
    if nde_step is None or cde_step is None:
        raise RuleCheckFailed(
            f"{rule}: referenced step missing",
            step_index=step_index, rule=rule,
        )
    if nde_step.rule != "mediation_nde_nie_joint_check":
        raise RuleCheckFailed(
            f"{rule}: nde_nie must reference mediation_nde_nie_joint_check",
            step_index=step_index, rule=rule,
        )
    if cde_step.rule != "mediation_cde_joint_check":
        raise RuleCheckFailed(
            f"{rule}: cde must reference mediation_cde_joint_check",
            step_index=step_index, rule=rule,
        )
    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            f"{rule} output must be a StructuralResult",
            step_index=step_index, rule=rule,
        )
    any_identifiable = bool(nde_out) or bool(cde_out)
    if claimed_output.value is not any_identifiable:
        raise RuleCheckFailed(
            f"{rule} output.value must be {any_identifiable!r} "
            f"(nde_nie={nde_out!r}, cde={cde_out!r}), got {claimed_output.value!r}",
            step_index=step_index, rule=rule,
        )


def _rule_longitudinal_sequential_exchangeability_check(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Independently re-check Pearl-Robins sequential exchangeability for a
    time-varying treatment strategy (g-formula / sequential back-door
    identification, Hernán & Robins ch.21).

    For each treatment A_k in temporal order, the measured history
    ``H_k = {L_0..L_k, A_0..A_{k-1}}`` must

    (i)  contain no descendant of A_k (can't adjust for A_k's own
         consequences), and
    (ii) block every back-door path from A_k to Y.

    Future covariates are intentionally NOT in H_k, so a causal path
    A_k → L_{k+1} → Y is never mistaken for a back-door. Output is True iff
    every time point passes. Verifier-local m-separation — never calls
    structural_solver, so it is an independent re-derivation of the
    producer's ``minimal_adjustment_sets`` check.
    """
    rule = "longitudinal_sequential_exchangeability_check"
    graph = _require(inputs, "graph", step_index, rule)
    _assert_same_graph(graph, ctx.graph, step_index, rule)
    y = _require_atom(inputs, "y", step_index, rule)
    treatments_raw = _require(inputs, "treatments", step_index, rule)
    conf_raw = _require(inputs, "confounders_by_time", step_index, rule)

    if not isinstance(treatments_raw, tuple) or not all(
        isinstance(a, Atom) for a in treatments_raw
    ):
        raise UnknownRuleInputError(
            f"{rule}.treatments must be a tuple of Atom",
            step_index=step_index, rule=rule,
        )
    if not isinstance(conf_raw, tuple) or not all(
        isinstance(blk, tuple) and all(isinstance(a, Atom) for a in blk)
        for blk in conf_raw
    ):
        raise UnknownRuleInputError(
            f"{rule}.confounders_by_time must be a tuple of tuples of Atom",
            step_index=step_index, rule=rule,
        )
    if len(conf_raw) != len(treatments_raw):
        raise RuleCheckFailed(
            f"{rule}: confounders_by_time length {len(conf_raw)} must equal "
            f"treatments length {len(treatments_raw)}",
            step_index=step_index, rule=rule,
        )
    if not treatments_raw:
        raise RuleCheckFailed(
            f"{rule}: treatments must be non-empty",
            step_index=step_index, rule=rule,
        )
    if y not in graph:
        raise RuleCheckFailed(
            f"{rule}: outcome {y!r} not in graph",
            step_index=step_index, rule=rule,
        )

    bidir = ctx.bidirected

    all_ok = True
    history: set[Atom] = set()
    for k, a_k in enumerate(treatments_raw):
        if a_k not in graph:
            raise RuleCheckFailed(
                f"{rule}: treatment {a_k!r} not in graph",
                step_index=step_index, rule=rule,
            )
        if a_k == y:
            raise RuleCheckFailed(
                f"{rule}: treatment {a_k!r} equals the outcome",
                step_index=step_index, rule=rule,
            )
        history |= set(conf_raw[k])  # L_k measured BEFORE A_k
        h_k = frozenset(history)
        # (i) H_k has no descendant of A_k
        no_descendant = h_k.isdisjoint(_verifier_directed_descendants(graph, a_k))
        # (ii) every back-door path from A_k to Y is blocked by H_k
        backdoor_blocked = not _verifier_is_admg_backdoor_connected(
            graph, bidir, a_k, y, h_k
        )
        if not (no_descendant and backdoor_blocked):
            all_ok = False
        history.add(a_k)  # A_k enters the history for later times

    if bool(claimed_output) is not all_ok:
        raise RuleCheckFailed(
            f"{rule} claimed {claimed_output!r}, recomputed {all_ok!r}",
            step_index=step_index, rule=rule,
        )


def _rule_identify_via_gformula(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Consume a ``longitudinal_sequential_exchangeability_check`` and
    conclude g-formula (sequential back-door) identifiability of the time-
    varying strategy contrast.

    Binds to the active effect query: the derivation's outcome must be the
    query target and the query's intervention must be one of the declared
    treatments — so a valid longitudinal proof for a DIFFERENT query is
    rejected. ``claimed_output.value`` must equal the referenced check's
    all-times-admissible verdict.
    """
    rule = "identify_via_gformula"
    check_ref = _require(inputs, "check", step_index, rule)
    y = _require_atom(inputs, "y", step_index, rule)
    treatments_raw = _require(inputs, "treatments", step_index, rule)
    if not isinstance(check_ref, StepRef):
        raise UnknownRuleInputError(
            f"{rule}.check must be a StepRef",
            step_index=step_index, rule=rule,
        )
    if not isinstance(treatments_raw, tuple) or not all(
        isinstance(a, Atom) for a in treatments_raw
    ):
        raise UnknownRuleInputError(
            f"{rule}.treatments must be a tuple of Atom",
            step_index=step_index, rule=rule,
        )

    check_step = step_by_id.get(check_ref.step_id)
    check_out = step_output_by_id.get(check_ref.step_id)
    if check_step is None:
        raise RuleCheckFailed(
            f"{rule}: referenced check step missing",
            step_index=step_index, rule=rule,
        )
    if check_step.rule != "longitudinal_sequential_exchangeability_check":
        raise RuleCheckFailed(
            f"{rule}: check must reference "
            f"longitudinal_sequential_exchangeability_check",
            step_index=step_index, rule=rule,
        )
    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            f"{rule} output must be a StructuralResult",
            step_index=step_index, rule=rule,
        )

    # Query binding: this must prove the ACTIVE query, not another.
    q = ctx.query
    if isinstance(q, EffectQuery):
        if y != q.target.atom:
            raise RuleCheckFailed(
                f"{rule}.y {y!r} does not match the query target "
                f"{q.target.atom!r}",
                step_index=step_index, rule=rule,
            )
        if q.intervention.atom not in set(treatments_raw):
            raise RuleCheckFailed(
                f"{rule}: query intervention {q.intervention.atom!r} is not "
                f"among the declared treatments",
                step_index=step_index, rule=rule,
            )

    if claimed_output.value is not bool(check_out):
        raise RuleCheckFailed(
            f"{rule} output.value must equal the sequential-exchangeability "
            f"check verdict ({check_out!r}), got {claimed_output.value!r}",
            step_index=step_index, rule=rule,
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
    mediators: tuple[Atom, ...],
    adjustment_set: tuple[Atom, ...],
    observed: tuple[ValuedAtom, ...],
) -> FormulaExpr:
    """Verifier-side independent reconstruction of the mediation
    potential-outcome g-formula. Does NOT call ``formula_builder``.

    Shape (Pearl 2001 + g-formula expansion), over the mediator BLOCK::

        E[Y(X=x_outer, M = M(X=x_inner))]
          = Σ_w Σ_m1..mk  P(Y | X=x_outer, M1=m1, .., Mk=mk, W=w)
                        · ∏_j P(Mj=mj | M_{<j}, X=x_inner, W=w)
                        · ∏_i P(Wi=wi | W_{<i})

    The chain-rule factoring of P(W), the chain-rule factoring of the
    joint mediator law, and the cross-world arm on the mediator factors
    are the pieces a buggy runtime might get wrong; this independent
    rebuild lets the verifier detect each failure mode. A single-element
    ``mediators`` reproduces the classical single-mediator formula.
    """
    taken: set = set()
    w_binds: list[tuple[Atom, BindDecl, ValuedAtom]] = []
    for w_atom in adjustment_set:
        b = _verifier_mediation_bind_for(w_atom, taken)
        taken.add(b.name)
        w_va = ValuedAtom(atom=w_atom, value=VarRef(name=b.name))
        w_binds.append((w_atom, b, w_va))
    w_valueds = tuple(vv for (_, _, vv) in w_binds)

    m_binds: list[tuple[Atom, BindDecl, ValuedAtom]] = []
    for m_atom in mediators:
        b = _verifier_mediation_bind_for(m_atom, taken)
        taken.add(b.name)
        m_va = ValuedAtom(atom=m_atom, value=VarRef(name=b.name))
        m_binds.append((m_atom, b, m_va))
    m_valueds = tuple(vv for (_, _, vv) in m_binds)

    y_cond = ProbabilityRefExpr(
        target=target,
        given=(intervention_outer,) + m_valueds + w_valueds + observed,
    )
    m_factors: list[ProbabilityRefExpr] = []
    for j, (_, _, m_va) in enumerate(m_binds):
        prior = m_valueds[:j]
        m_factors.append(
            ProbabilityRefExpr(
                target=m_va,
                given=(intervention_inner,) + prior + w_valueds + observed,
            )
        )
    w_factors: list[ProbabilityRefExpr] = []
    for i, (_, _, w_va) in enumerate(w_binds):
        prior = w_valueds[:i]
        w_factors.append(ProbabilityRefExpr(target=w_va, given=prior + observed))

    body: FormulaExpr = ProductExpr(terms=(y_cond, *m_factors, *w_factors))
    for m_atom, b, _ in reversed(m_binds):
        body = SumExpr(bind=b, over=m_atom, body=body)
    for w_atom, b, _ in reversed(w_binds):
        body = SumExpr(bind=b, over=w_atom, body=body)
    return body


def _verifier_build_mediation_controlled_outcome_formula(
    target: ValuedAtom,
    intervention: ValuedAtom,
    mediators: tuple[ValuedAtom, ...],
    adjustment_set: tuple[Atom, ...],
    observed: tuple[ValuedAtom, ...],
) -> FormulaExpr:
    """Verifier-side independent reconstruction of the CDE g-formula.
    Does NOT call ``formula_builder``.

    Shape, with the whole mediator block held fixed at m* ::

        E[Y | do(X=x, M1=m1*, .., Mk=mk*)]
          = Σ_w  P(Y | X=x, M1=m1*, .., Mk=mk*, W=w) · ∏_i P(Wi=wi | W_{<i})

    When ``adjustment_set`` is empty, reduces to a single
    ``P(Y | X=x, M=m*, observed)`` conditional.
    """
    if not adjustment_set:
        return ProbabilityRefExpr(
            target=target,
            given=(intervention,) + mediators + observed,
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
        given=(intervention,) + mediators + w_valueds + observed,
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
    mediators_raw = inputs.get("mediators")
    if not isinstance(mediators_raw, (tuple, list)) or not mediators_raw:
        raise RuleCheckFailed(
            "mediation_numeric_evaluate: 'mediators' must be a non-empty "
            "tuple of mediator atoms",
            step_index=step_index, rule="mediation_numeric_evaluate",
        )
    mediators = tuple(mediators_raw)
    if not all(isinstance(a, Atom) for a in mediators):
        raise RuleCheckFailed(
            "mediation_numeric_evaluate: every entry of 'mediators' must be "
            "an Atom",
            step_index=step_index, rule="mediation_numeric_evaluate",
        )
    if len(set(mediators)) != len(mediators):
        raise RuleCheckFailed(
            "mediation_numeric_evaluate: 'mediators' repeats an atom — the "
            "chain-rule factorisation would double-count it",
            step_index=step_index, rule="mediation_numeric_evaluate",
        )
    # The evaluated block must be exactly the mediator set the QUERY
    # declared. Dropping one changes which paths count as indirect, and the
    # resulting natural effects are internally consistent while answering a
    # DIFFERENT question — precisely the failure a numbers-only re-derivation
    # would confirm rather than catch.
    #
    # The block ORDER is deliberately not pinned: the chain rule
    # ∏_j P(Mj | M_{<j}, ...) is an exact factorisation of the joint law for
    # any ordering, so every order that evaluates yields the same value. The
    # order only decides which CPTs theta is asked for. Re-deriving with the
    # producer's recorded order therefore checks the arithmetic without
    # rejecting a correct answer that took a different route to it.
    declared_mediators = set(getattr(ctx.query, "mediators", ()) or ())
    if not declared_mediators:
        single = getattr(ctx.query, "mediator", None)
        if single is not None:
            declared_mediators = {single}
    if declared_mediators and set(mediators) != declared_mediators:
        raise RuleCheckFailed(
            "mediation_numeric_evaluate: evaluated mediator block "
            f"{sorted(str(a) for a in mediators)} != the mediator set the "
            f"query declares {sorted(str(a) for a in declared_mediators)} — "
            "the reported natural effects are not the ones asked for",
            step_index=step_index, rule="mediation_numeric_evaluate",
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
            target, treated_va, treated_va, mediators, nde_w, observed,
        )
        f_control = _verifier_build_mediation_potential_outcome_formula(
            target, control_va, control_va, mediators, nde_w, observed,
        )
        # Both cross-world potentials — one per Pearl decomposition.
        f_cross_to = _verifier_build_mediation_potential_outcome_formula(
            target, treated_va, control_va, mediators, nde_w, observed,
        )
        f_cross_co = _verifier_build_mediation_potential_outcome_formula(
            target, control_va, treated_va, mediators, nde_w, observed,
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
        # Independent transcription of the reference grid: the Cartesian
        # product of the block's theta domains, keyed by the values joined
        # with '|' in block order (a bare str(value) when k == 1).
        from itertools import product as _product
        for combo in _product(*(theta.domain_of(m) for m in mediators)):
            m_vas = tuple(
                ValuedAtom(atom=m_atom, value=m_val)
                for m_atom, m_val in zip(mediators, combo)
            )
            f_t = _verifier_build_mediation_controlled_outcome_formula(
                target, treated_va, m_vas, cde_w, observed,
            )
            f_c = _verifier_build_mediation_controlled_outcome_formula(
                target, control_va, m_vas, cde_w, observed,
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
                    f"for mediator reference={combo!r}: {e}",
                    step_index=step_index, rule="mediation_numeric_evaluate",
                )
            recomputed_cde = v_t - v_c
            m_key = "|".join(str(v) for v in combo)
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

_NUMERIC_IV_METHODS = frozenset({"iv_wald", "iv_stratified_wald", "iv_2sls"})

_NUMERIC_JOINT_METHODS = frozenset({
    "joint_backdoor_linear",
    "joint_backdoor_logistic",
})

# General-ID (c-factor) non-parametric plug-in — the crown-jewel
# identification made numeric on discrete data.
_NUMERIC_GENERAL_ID_METHODS = frozenset({
    "general_id_plugin",
    # Conditional effect P(Y | do(X), Z=z) identified via Shpitser–Pearl
    # IDC and evaluated by the same non-parametric plug-in within the Z=z
    # stratum. Same terminal / criterion; the criterion re-runs IDC when the
    # query carries a conditioning set.
    "general_id_idc_plugin",
    # Joint effect P(Y | do(A, B, …)) identified via the set-valued
    # Shpitser–Pearl ID (identify_via_tian_joint) and evaluated by the same
    # non-parametric plug-in on the uniform all-hi / all-lo contrast. Same
    # terminal / criterion; the criterion re-runs the set ID when the query
    # carries extra_interventions.
    "joint_general_id_plugin",
})

# Counterfactual-conjunction (ID*/IDC*) non-parametric plug-in — the
# counterfactual rung made numeric on discrete data.
_NUMERIC_CTF_CONJUNCTION_METHODS = frozenset({"ctf_conjunction_plugin"})

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


# =============================== doubly-robust (IPW / AIPW) numeric terminals

_NUMERIC_AIPW_METHODS = frozenset({"aipw"})
_NUMERIC_TMLE_METHODS = frozenset({"tmle"})
_NUMERIC_IPW_METHODS = frozenset({"ipw_stabilized", "ipw_ht"})
_AIPW_CI_METHODS = frozenset({"influence_function", "bootstrap"})


def _audit_dr_numeric_estimate(
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    *,
    rule: str,
    allowed_methods: frozenset,
    require_aipw_fields: bool,
) -> None:
    """Metadata self-consistency audit for an IPW / AIPW numeric estimate.

    Like ``numeric_backdoor_estimate``, this does NOT re-train — it
    audits the block's internal consistency (the identification witness
    is the same ``backdoor_criterion`` structural step, re-derived
    elsewhere). Beyond the backdoor checks it enforces the
    doubly-robust-specific invariants that make a propensity-weighted
    estimate trustworthy:

    - the propensity disclosure is coherent: raw min/max in [0,1] with
      min ≤ max; n_trimmed an int in [0, sample_size]; floor in (0, 0.5)
    - for AIPW: ``doubly_robust`` is True, ``ci_method`` is a known
      value, and any reported ``std_error`` is a non-negative number.

    Catches the realistic tamper / bug cases: wrong method name, point
    outside CI, corrupted hash, adjustment overlapping treatment, a
    propensity range escaping [0,1], a negative std_error, or a trimmed
    count exceeding the sample.
    """
    criterion_ref = _require(inputs, "criterion", step_index, rule)
    if not isinstance(criterion_ref, StepRef):
        raise UnknownRuleInputError(
            f"{rule}.criterion must be a StepRef",
            step_index=step_index, rule=rule,
        )
    treatment = _require_atom(inputs, "treatment", step_index, rule)
    outcome = _require_atom(inputs, "outcome", step_index, rule)
    adjustment = _require_atom_set(inputs, "adjustment", step_index, rule)
    method = inputs.get("method")
    data_hash = inputs.get("data_hash")
    sample_size = inputs.get("sample_size")
    point = inputs.get("point")
    ci_lower = inputs.get("ci_lower")
    ci_upper = inputs.get("ci_upper")
    ci_level = inputs.get("ci_level")

    if method not in allowed_methods:
        raise RuleCheckFailed(
            f"{rule}.method must be one of {sorted(allowed_methods)}; "
            f"got {method!r}",
            step_index=step_index, rule=rule,
        )
    if not isinstance(data_hash, str) or len(data_hash) != _SHA256_HEX_LEN:
        raise RuleCheckFailed(
            f"{rule}.data_hash must be a {_SHA256_HEX_LEN}-char SHA-256 hex "
            f"string",
            step_index=step_index, rule=rule,
        )
    if not all(c in "0123456789abcdef" for c in data_hash):
        raise RuleCheckFailed(
            f"{rule}.data_hash must be lowercase hex",
            step_index=step_index, rule=rule,
        )
    if (
        not isinstance(sample_size, int)
        or isinstance(sample_size, bool)
        or sample_size < _MIN_NUMERIC_SAMPLE_SIZE
    ):
        raise RuleCheckFailed(
            f"{rule}.sample_size must be an int >= {_MIN_NUMERIC_SAMPLE_SIZE}; "
            f"got {sample_size!r}",
            step_index=step_index, rule=rule,
        )
    if not isinstance(point, (int, float)) or isinstance(point, bool):
        raise RuleCheckFailed(
            f"{rule}.point must be a number; got {point!r}",
            step_index=step_index, rule=rule,
        )

    ci_present = ci_lower is not None or ci_upper is not None
    if ci_present:
        if ci_lower is None or ci_upper is None:
            raise RuleCheckFailed(
                f"{rule}: ci_lower and ci_upper must both be present or both "
                f"absent",
                step_index=step_index, rule=rule,
            )
        if not (ci_lower <= point <= ci_upper):
            raise RuleCheckFailed(
                f"{rule}: point {point} is outside [{ci_lower}, {ci_upper}]",
                step_index=step_index, rule=rule,
            )
        if not isinstance(ci_level, (int, float)) or not (0 < ci_level < 1):
            raise RuleCheckFailed(
                f"{rule}.ci_level must be in (0, 1); got {ci_level!r}",
                step_index=step_index, rule=rule,
            )

    if adjustment & {treatment, outcome}:
        raise RuleCheckFailed(
            f"{rule}.adjustment must be disjoint from {{treatment, outcome}}",
            step_index=step_index, rule=rule,
        )

    # --- propensity disclosure coherence ---
    n_trimmed = inputs.get("propensity_n_trimmed")
    floor = inputs.get("propensity_floor")
    raw_min = _require_reported_probability(
        inputs, "propensity_raw_min", step_index=step_index, rule=rule,
    )
    raw_max = _require_reported_probability(
        inputs, "propensity_raw_max", step_index=step_index, rule=rule,
    )
    if raw_min > raw_max:
        raise RuleCheckFailed(
            f"{rule}: propensity_raw_min {raw_min} exceeds propensity_raw_max "
            f"{raw_max}",
            step_index=step_index, rule=rule,
        )
    if (
        not isinstance(n_trimmed, int)
        or isinstance(n_trimmed, bool)
        or not (0 <= n_trimmed <= sample_size)
    ):
        raise RuleCheckFailed(
            f"{rule}.propensity_n_trimmed must be an int in [0, sample_size]; "
            f"got {n_trimmed!r}",
            step_index=step_index, rule=rule,
        )
    if not isinstance(floor, (int, float)) or isinstance(floor, bool) or not (0.0 < floor < 0.5):
        raise RuleCheckFailed(
            f"{rule}.propensity_floor must be in (0, 0.5); got {floor!r}",
            step_index=step_index, rule=rule,
        )

    # --- AIPW-only fields ---
    if require_aipw_fields:
        if inputs.get("doubly_robust") is not True:
            raise RuleCheckFailed(
                f"{rule}.doubly_robust must be True for an AIPW estimate",
                step_index=step_index, rule=rule,
            )
        ci_method = inputs.get("ci_method")
        if ci_method not in _AIPW_CI_METHODS:
            raise RuleCheckFailed(
                f"{rule}.ci_method must be one of {sorted(_AIPW_CI_METHODS)}; "
                f"got {ci_method!r}",
                step_index=step_index, rule=rule,
            )
        std_error = inputs.get("std_error")
        if std_error is not None:
            if not isinstance(std_error, (int, float)) or isinstance(std_error, bool) or std_error < 0:
                raise RuleCheckFailed(
                    f"{rule}.std_error must be a non-negative number or null; "
                    f"got {std_error!r}",
                    step_index=step_index, rule=rule,
                )

    # --- criterion linkage (same backdoor witness as the g-formula path) ---
    criterion_step = step_by_id.get(criterion_ref.step_id)
    if criterion_step is None:
        raise RuleCheckFailed(
            f"{rule}: referenced criterion step {criterion_ref.step_id!r} "
            f"missing",
            step_index=step_index, rule=rule,
        )
    if criterion_step.rule != "backdoor_criterion":
        raise RuleCheckFailed(
            f"{rule}.criterion must reference a backdoor_criterion step",
            step_index=step_index, rule=rule,
        )
    criterion_z = criterion_step.inputs.get("z")
    if not isinstance(criterion_z, (frozenset, set)):
        raise RuleCheckFailed(
            "referenced backdoor_criterion.z must be an atom set",
            step_index=step_index, rule=rule,
        )
    if frozenset(criterion_z) != frozenset(adjustment):
        raise RuleCheckFailed(
            f"{rule}.adjustment must equal the z-set claimed by the "
            f"referenced backdoor_criterion step",
            step_index=step_index, rule=rule,
        )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            f"{rule} output must be a StructuralResult",
            step_index=step_index, rule=rule,
        )
    if claimed_output.value is not True:
        raise RuleCheckFailed(
            f"{rule} output.value must be True",
            step_index=step_index, rule=rule,
        )


def _rule_numeric_aipw_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Audit an augmented-IPW (doubly-robust) numeric estimate."""
    _audit_dr_numeric_estimate(
        inputs, claimed_output, step_index, step_by_id,
        rule="numeric_aipw_estimate",
        allowed_methods=_NUMERIC_AIPW_METHODS,
        require_aipw_fields=True,
    )


def _rule_numeric_tmle_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Audit a targeted-maximum-likelihood (TMLE) numeric estimate.

    Shares the doubly-robust audit (doubly_robust / ci_method / std_error
    + propensity coherence), plus a check that the fluctuation parameter
    ``tmle_epsilon`` is a finite number — a corrupted / non-finite
    targeting step would silently invalidate the substitution estimate.
    """
    _audit_dr_numeric_estimate(
        inputs, claimed_output, step_index, step_by_id,
        rule="numeric_tmle_estimate",
        allowed_methods=_NUMERIC_TMLE_METHODS,
        require_aipw_fields=True,
    )
    epsilon = inputs.get("tmle_epsilon")
    if not isinstance(epsilon, (int, float)) or isinstance(epsilon, bool) \
            or not math.isfinite(epsilon):
        raise RuleCheckFailed(
            f"numeric_tmle_estimate.tmle_epsilon must be a finite number; "
            f"got {epsilon!r}",
            step_index=step_index, rule="numeric_tmle_estimate",
        )


def _rule_numeric_ipw_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Audit an inverse-probability-weighted numeric estimate."""
    _audit_dr_numeric_estimate(
        inputs, claimed_output, step_index, step_by_id,
        rule="numeric_ipw_estimate",
        allowed_methods=_NUMERIC_IPW_METHODS,
        require_aipw_fields=False,
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


def _ar_solve_set_verifier(a: float, b: float, c: float, *, atol: float):
    """Independent transcription (NOT the producer's ``_ar_solve_set``) of the
    Anderson-Rubin quadratic solve, so a bug on either side is caught by the
    other. Returns ``(kind, lower, upper)``."""
    import math

    if abs(a) <= atol:
        if abs(b) <= atol:
            return ("whole_line", None, None) if c <= 0 else ("empty", None, None)
        root = -c / b
        if b > 0:
            return ("unbounded_below", None, root)
        return ("unbounded_above", root, None)
    disc = b * b - 4.0 * a * c
    if a > 0:
        if disc <= 0:
            return ("empty", None, None)
        sq = math.sqrt(disc)
        r1, r2 = (-b - sq) / (2 * a), (-b + sq) / (2 * a)
        lo, hi = (r1, r2) if r1 <= r2 else (r2, r1)
        return ("bounded", lo, hi)
    if disc <= 0:
        return ("whole_line", None, None)
    sq = math.sqrt(disc)
    r1, r2 = (-b - sq) / (2 * a), (-b + sq) / (2 * a)
    lo, hi = (r1, r2) if r1 <= r2 else (r2, r1)
    return ("disconnected", lo, hi)


def _point_in_ar_set(kind, lower, upper, point, *, tol) -> bool:
    if kind == "bounded":
        return lower - tol <= point <= upper + tol
    if kind == "disconnected":
        return point <= lower + tol or point >= upper - tol
    if kind == "unbounded_below":
        return point <= upper + tol
    if kind == "unbounded_above":
        return point >= lower - tol
    if kind == "whole_line":
        return True
    return False  # empty


def _check_anderson_rubin(inputs: dict, point, step_index: int) -> None:
    """Re-solve the Anderson-Rubin confidence set from the reported
    residualised sufficient statistics and confirm the claimed set (kind +
    endpoints), the F critical value, and the IV point (Szy/Szx) all match —
    the verifier's OWN transcription, never the producer's solve. Gives the
    IV numeric audit real teeth: an isolated tamper of the AR set, the point,
    or kappa is rejected."""
    from scipy.stats import f as _f_dist

    try:
        s_yy = float(inputs["ar_s_yy"]); s_xy = float(inputs["ar_s_xy"])
        s_xx = float(inputs["ar_s_xx"]); s_zy = float(inputs["ar_s_zy"])
        s_zx = float(inputs["ar_s_zx"]); s_zz = float(inputs["ar_s_zz"])
        n_obs = int(inputs["ar_n_obs"]); n_exog = int(inputs["ar_n_exog"])
        ci_level = float(inputs["ar_ci_level"])
    except (KeyError, TypeError, ValueError):
        raise RuleCheckFailed(
            "numeric_iv_estimate: AR set present but its sufficient "
            "statistics are missing or ill-typed",
            step_index=step_index, rule="numeric_iv_estimate",
        )

    claimed_kind = inputs.get("ar_kind")
    claimed_lower = inputs.get("ar_lower")
    claimed_upper = inputs.get("ar_upper")

    m = n_obs - n_exog - 2
    if m < 1 or s_zz <= 0:
        raise RuleCheckFailed(
            "numeric_iv_estimate: AR sufficient statistics are degenerate "
            "(residual df < 1 or Szz <= 0)",
            step_index=step_index, rule="numeric_iv_estimate",
        )

    kappa = float(_f_dist.ppf(ci_level, 1, m))
    ar_kappa = inputs.get("ar_kappa")
    if ar_kappa is not None and abs(float(ar_kappa) - kappa) > 1e-6 * (1 + abs(kappa)):
        raise RuleCheckFailed(
            f"numeric_iv_estimate: reported AR kappa {ar_kappa} does not "
            f"match the F(1,{m}) critical value {kappa}",
            step_index=step_index, rule="numeric_iv_estimate",
        )

    g = (m + kappa) / s_zz
    a = g * s_zx * s_zx - kappa * s_xx
    b = 2.0 * (kappa * s_xy - g * s_zx * s_zy)
    c = g * s_zy * s_zy - kappa * s_yy
    a_scale = abs(g * s_zx * s_zx) + abs(kappa * s_xx) + 1.0
    kind, lower, upper = _ar_solve_set_verifier(a, b, c, atol=1e-9 * a_scale)

    if kind != claimed_kind:
        raise RuleCheckFailed(
            f"numeric_iv_estimate: AR set kind mismatch — re-solve {kind!r} "
            f"vs claimed {claimed_kind!r}",
            step_index=step_index, rule="numeric_iv_estimate",
        )
    for name, recomputed, claimed in (
        ("lower", lower, claimed_lower),
        ("upper", upper, claimed_upper),
    ):
        if recomputed is None or claimed is None:
            if recomputed is not None or claimed is not None:
                raise RuleCheckFailed(
                    f"numeric_iv_estimate: AR {name} presence mismatch — "
                    f"re-solve {recomputed} vs claimed {claimed}",
                    step_index=step_index, rule="numeric_iv_estimate",
                )
            continue
        if abs(recomputed - float(claimed)) > 1e-6 * (1 + abs(recomputed)):
            raise RuleCheckFailed(
                f"numeric_iv_estimate: AR {name} mismatch — re-solve "
                f"{recomputed} vs claimed {claimed}",
                step_index=step_index, rule="numeric_iv_estimate",
            )

    # Independent re-derivation of the IV point: for a single instrument the
    # just-identified estimate is exactly Szy/Szx (Wald and 2SLS both).
    if abs(s_zx) > 1e-12 and isinstance(point, (int, float)):
        pt = s_zy / s_zx
        if abs(pt - point) > 1e-5 * (1 + abs(pt)):
            raise RuleCheckFailed(
                f"numeric_iv_estimate: IV point {point} does not match "
                f"Szy/Szx = {pt} from the reported sufficient statistics",
                step_index=step_index, rule="numeric_iv_estimate",
            )
        if not _point_in_ar_set(
            kind, lower, upper, point, tol=1e-7 * (1 + abs(point))
        ):
            raise RuleCheckFailed(
                "numeric_iv_estimate: IV point estimate is not contained in "
                "its own Anderson-Rubin confidence set",
                step_index=step_index, rule="numeric_iv_estimate",
            )


def _rule_numeric_iv_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Phase 7.3 — audit for a data-based IV ATE estimate.

    Method enum + CI bounds + data_hash + sample_size + instrument
    validity checks. Same shape as numeric_backdoor_estimate /
    numeric_frontdoor_estimate; the referenced criterion step must be
    an ``iv_criterion_check`` and its (instrument, conditioning) must
    equal the numeric step's claims.

    When an Anderson-Rubin set is attached, it is independently
    RE-SOLVED from the reported residualised sufficient statistics — the
    verifier re-derives kappa, the quadratic, the set shape/endpoints, and
    the point Szy/Szx — so a tampered AR set, point, or kappa is rejected.
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

    # The stratified Wald has a closed-form sufficient statistic, so this
    # one IV path escapes the metadata-audit ceiling: re-aggregate it. Its
    # weak-robust set is a closed form over the same table, so it is
    # re-solved rather than audited too.
    #
    # Order matters: which set belongs to which method is a routing fact,
    # and it has to be settled before either set is audited on its own
    # terms. A linear AR set on a stratified point is wrong because of
    # what it is, not because its statistics fail to add up.
    _check_stratified_wald(inputs, point, method, step_index)
    _check_stratified_anderson_rubin(inputs, point, method, step_index)

    # Independently re-solve the Anderson-Rubin set when present.
    if inputs.get("ar_kind") is not None:
        _check_anderson_rubin(inputs, point, step_index)


def _check_stratified_wald(
    inputs: dict, point: float, method: str, step_index: int,
) -> None:
    """Recompute a stratified-Wald point from the recorded stratum table.

    The estimand is the RATIO OF AVERAGES — each stratum weighted by its
    own complier share, which is the denominator term (Abadie 2003). The
    plausible wrong answer is the average of the per-stratum ratios, and
    the two coincide whenever the first stage is equally strong in every
    stratum, so nothing but an explicit re-aggregation separates them.

    Also pins the table to the method: only the stratified path may carry
    strata, and the stratified path may not omit them.
    """
    RULE = "numeric_iv_estimate"
    present = any(
        inputs.get(name) is not None
        for name in (
            "stratum_weights",
            "stratum_outcome_shifts",
            "stratum_treatment_shifts",
        )
    )

    if method == "iv_stratified_wald":
        if not present:
            raise RuleCheckFailed(
                f"{RULE}: method 'iv_stratified_wald' must record the stratum "
                f"table it aggregated — without it the point is uncheckable",
                step_index=step_index, rule=RULE,
            )
    elif present:
        raise RuleCheckFailed(
            f"{RULE}: a stratum table is recorded but method is {method!r}; "
            f"only the stratified Wald aggregates over strata",
            step_index=step_index, rule=RULE,
        )
    else:
        return

    columns = {
        name: _require_number_column(
            inputs.get(name), name, step_index=step_index, rule=RULE,
        )
        for name in (
            "stratum_weights",
            "stratum_outcome_shifts",
            "stratum_treatment_shifts",
            "stratum_shift_var_yy",
            "stratum_shift_var_xy",
            "stratum_shift_var_xx",
        )
    }
    lengths = {name: len(column) for name, column in columns.items()}
    if len(set(lengths.values())) != 1:
        raise RuleCheckFailed(
            f"{RULE}: stratum table columns disagree on length {lengths!r}",
            step_index=step_index, rule=RULE,
        )
    weights = columns["stratum_weights"]
    d_y = columns["stratum_outcome_shifts"]
    d_x = columns["stratum_treatment_shifts"]

    if any(w <= 0.0 for w in weights):
        raise RuleCheckFailed(
            f"{RULE}: every stratum weight must be positive; a zero or "
            f"negative weight means the aggregate does not run over the "
            f"population it claims to",
            step_index=step_index, rule=RULE,
        )
    total = math.fsum(weights)
    if abs(total - 1.0) > _NUMERIC_TOL:
        raise RuleCheckFailed(
            f"{RULE}: stratum weights sum to {total!r}, not 1 — a stratum "
            f"was dropped or reweighted, so the average is over a different "
            f"population than the query asked about",
            step_index=step_index, rule=RULE,
        )

    num = math.fsum(w * v for w, v in zip(weights, d_y))
    den = math.fsum(w * v for w, v in zip(weights, d_x))
    _pin_number(
        inputs, "aggregate_outcome_shift", num,
        step_index=step_index, rule=RULE, where="the stratum table",
    )
    _pin_number(
        inputs, "aggregate_treatment_shift", den,
        step_index=step_index, rule=RULE, where="the stratum table",
    )
    if abs(den) < 1e-12:
        raise RuleCheckFailed(
            f"{RULE}: the aggregate first stage is ~0, so no point estimate "
            f"can rest on it",
            step_index=step_index, rule=RULE,
        )

    expected = num / den
    if abs(point - expected) > _NUMERIC_TOL:
        average_of_ratios = math.fsum(
            w * (a / b) for w, a, b in zip(weights, d_y, d_x) if b
        )
        hint = ""
        if abs(point - average_of_ratios) <= _NUMERIC_TOL:
            hint = (
                " — the reported value is the average of the per-stratum "
                "ratios, which weights each stratum by P(w) instead of by "
                "its complier share and is a different estimand"
            )
        raise RuleCheckFailed(
            f"{RULE}: point {point!r} is not the ratio of averages "
            f"{expected!r} implied by the recorded stratum table{hint}",
            step_index=step_index, rule=RULE,
        )


def _check_stratified_anderson_rubin(
    inputs: dict, point, method: str, step_index: int,
) -> None:
    """Re-solve the stratified Anderson-Rubin set from the stratum table.

    The set is a closed-form function of the same table the point rests
    on, so the verifier rebuilds the aggregate moment and its variance
    coefficients from the per-stratum columns — not from the aggregates
    the producer recorded — re-solves the quadratic, and pins the claimed
    shape and endpoints against its own solve.

    The load-bearing pin is that this set's point IS the headline point.
    A weak-instrument set that brackets a different estimator's estimate
    is worse than no set at all, and the arithmetic on either side stays
    self-consistent, so nothing but naming the two and comparing them
    catches the substitution. For the same reason the linear AR inputs
    are refused outright on this method: when the strata happen to share
    a first-stage strength the two points coincide, and a numerical check
    alone would wave the mismatch through.
    """
    from scipy.stats import f as _f_dist

    RULE = "numeric_iv_estimate"
    present = inputs.get("sar_kind") is not None
    stratified = method == "iv_stratified_wald"

    if present and not stratified:
        raise RuleCheckFailed(
            f"{RULE}: a stratified Anderson-Rubin set is recorded but method "
            f"is {method!r}; that set inverts the stratified Wald's moment "
            f"and stands for no other estimand",
            step_index=step_index, rule=RULE,
        )
    if stratified and inputs.get("ar_kind") is not None:
        raise RuleCheckFailed(
            f"{RULE}: method 'iv_stratified_wald' carries the LINEAR "
            f"Anderson-Rubin set, which residualises on [1, W] and inverts a "
            f"test for the 2SLS coefficient — a confidence set for one "
            f"estimand beside a point for another",
            step_index=step_index, rule=RULE,
        )
    if not present:
        return

    try:
        weights = inputs["stratum_weights"]
        d_y = inputs["stratum_outcome_shifts"]
        d_x = inputs["stratum_treatment_shifts"]
        v_yy = inputs["stratum_shift_var_yy"]
        v_xy = inputs["stratum_shift_var_xy"]
        v_xx = inputs["stratum_shift_var_xx"]
        n_obs = int(inputs["sar_n_obs"])
        n_strata = int(inputs["sar_n_strata"])
        dof = int(inputs["sar_dof"])
        ci_level = float(inputs["sar_ci_level"])
    except (KeyError, TypeError, ValueError):
        raise RuleCheckFailed(
            f"{RULE}: stratified AR set present but the statistics it was "
            f"solved from are missing or ill-typed",
            step_index=step_index, rule=RULE,
        )

    if n_strata != len(weights):
        raise RuleCheckFailed(
            f"{RULE}: stratified AR set reports {n_strata} strata but the "
            f"recorded table holds {len(weights)}",
            step_index=step_index, rule=RULE,
        )
    if dof != n_obs - 2 * n_strata:
        raise RuleCheckFailed(
            f"{RULE}: stratified AR degrees of freedom {dof} is not "
            f"n - 2*S = {n_obs - 2 * n_strata}",
            step_index=step_index, rule=RULE,
        )
    if dof < 1:
        raise RuleCheckFailed(
            f"{RULE}: stratified AR set reports {dof} residual degrees of "
            f"freedom, so the test it inverts is undefined",
            step_index=step_index, rule=RULE,
        )

    a_num = math.fsum(w * v for w, v in zip(weights, d_y))
    b_den = math.fsum(w * v for w, v in zip(weights, d_x))
    c_yy = math.fsum(w * w * v for w, v in zip(weights, v_yy))
    c_xy = math.fsum(w * w * v for w, v in zip(weights, v_xy))
    c_xx = math.fsum(w * w * v for w, v in zip(weights, v_xx))
    for key, value in (
        ("sar_outcome_shift", a_num), ("sar_treatment_shift", b_den),
        ("sar_var_yy", c_yy), ("sar_var_xy", c_xy), ("sar_var_xx", c_xx),
    ):
        _pin_number(
            inputs, key, value,
            step_index=step_index, rule=RULE, where="the stratum table",
        )

    kappa = float(_f_dist.ppf(ci_level, 1, dof))
    _pin_number(
        inputs, "sar_kappa", kappa,
        step_index=step_index, rule=RULE,
        where=f"the F(1,{dof}) critical value",
    )

    a = b_den * b_den - kappa * c_xx
    b = 2.0 * (kappa * c_xy - a_num * b_den)
    c = a_num * a_num - kappa * c_yy
    a_scale = abs(b_den * b_den) + abs(kappa * c_xx) + 1.0
    kind, lower, upper = _ar_solve_set_verifier(a, b, c, atol=1e-9 * a_scale)

    if kind != inputs.get("sar_kind"):
        raise RuleCheckFailed(
            f"{RULE}: stratified AR set kind mismatch — re-solve {kind!r} vs "
            f"claimed {inputs.get('sar_kind')!r}",
            step_index=step_index, rule=RULE,
        )
    for name, recomputed, claimed in (
        ("lower", lower, inputs.get("sar_lower")),
        ("upper", upper, inputs.get("sar_upper")),
    ):
        if recomputed is None or claimed is None:
            if recomputed is not None or claimed is not None:
                raise RuleCheckFailed(
                    f"{RULE}: stratified AR {name} presence mismatch — re-solve "
                    f"{recomputed} vs claimed {claimed}",
                    step_index=step_index, rule=RULE,
                )
            continue
        if abs(recomputed - float(claimed)) > 1e-6 * (1 + abs(recomputed)):
            raise RuleCheckFailed(
                f"{RULE}: stratified AR {name} mismatch — re-solve "
                f"{recomputed} vs claimed {claimed}",
                step_index=step_index, rule=RULE,
            )

    if abs(b_den) > 1e-12:
        expected = a_num / b_den
        _pin_number(
            inputs, "sar_point", expected,
            step_index=step_index, rule=RULE, where="the stratum table",
        )
        if isinstance(point, (int, float)) and not isinstance(point, bool):
            if abs(expected - point) > 1e-6 * (1 + abs(expected)):
                raise RuleCheckFailed(
                    f"{RULE}: the stratified AR set is centred on {expected!r} "
                    f"but the reported point is {point!r}; a confidence set "
                    f"and a point that disagree are two estimands in one "
                    f"result",
                    step_index=step_index, rule=RULE,
                )
            if not _point_in_ar_set(
                kind, lower, upper, point, tol=1e-7 * (1 + abs(point))
            ):
                raise RuleCheckFailed(
                    f"{RULE}: the stratified Wald point is not contained in "
                    f"its own Anderson-Rubin confidence set",
                    step_index=step_index, rule=RULE,
                )


def _rule_numeric_iv_overid_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Over-identified 2SLS terminal — metadata self-consistency + structural
    licensing.

    Each of the q ≥ 2 instruments must be witnessed by an ``iv_criterion_check``
    step (claimed output True, independently re-verified) with the SAME
    (x, y, conditioning), so the over-identified system rests only on
    structurally valid instruments. The numeric re-derivation — the 2SLS point,
    the Sargan J, and its p-value from the recorded residualised moment matrices
    — is ``verify_iv_overid_numeric`` (called from the kernel), because those
    matrices don't fit the derivation-input serialization.
    """
    RULE = "numeric_iv_overid_estimate"
    treatment = _require_atom(inputs, "treatment", step_index, RULE)
    outcome = _require_atom(inputs, "outcome", step_index, RULE)
    instruments = _require_atom_set(inputs, "instruments", step_index, RULE)
    conditioning = _require_atom_set(inputs, "conditioning", step_index, RULE)
    method = inputs.get("method")
    data_hash = inputs.get("data_hash")
    sample_size = inputs.get("sample_size")
    point = inputs.get("point")
    ci_lower = inputs.get("ci_lower")
    ci_upper = inputs.get("ci_upper")
    ci_level = inputs.get("ci_level")
    n_instruments = inputs.get("n_instruments")

    if method != "iv_2sls_overid":
        raise RuleCheckFailed(
            f"{RULE}.method must be 'iv_2sls_overid'; got {method!r}",
            step_index=step_index, rule=RULE,
        )
    if len(instruments) < 2:
        raise RuleCheckFailed(
            f"{RULE} requires >= 2 instruments; got {len(instruments)}",
            step_index=step_index, rule=RULE,
        )
    if n_instruments != len(instruments):
        raise RuleCheckFailed(
            f"{RULE}.n_instruments {n_instruments!r} != |instruments| "
            f"{len(instruments)}",
            step_index=step_index, rule=RULE,
        )
    if treatment == outcome or treatment in instruments or outcome in instruments:
        raise RuleCheckFailed(
            f"{RULE}: treatment/outcome/instruments must be distinct",
            step_index=step_index, rule=RULE,
        )
    if conditioning & ({treatment, outcome} | set(instruments)):
        raise RuleCheckFailed(
            f"{RULE}.conditioning must be disjoint from treatment/outcome/instruments",
            step_index=step_index, rule=RULE,
        )
    if not isinstance(data_hash, str) or len(data_hash) != _SHA256_HEX_LEN \
            or not all(c in "0123456789abcdef" for c in data_hash):
        raise RuleCheckFailed(
            f"{RULE}.data_hash must be a {_SHA256_HEX_LEN}-char lowercase "
            "SHA-256 hex string",
            step_index=step_index, rule=RULE,
        )
    if (
        not isinstance(sample_size, int) or isinstance(sample_size, bool)
        or sample_size < _MIN_NUMERIC_SAMPLE_SIZE
    ):
        raise RuleCheckFailed(
            f"{RULE}.sample_size must be an int >= {_MIN_NUMERIC_SAMPLE_SIZE}; "
            f"got {sample_size!r}",
            step_index=step_index, rule=RULE,
        )
    if not isinstance(point, (int, float)) or isinstance(point, bool):
        raise RuleCheckFailed(
            f"{RULE}.point must be a number; got {point!r}",
            step_index=step_index, rule=RULE,
        )
    if ci_lower is not None or ci_upper is not None:
        if ci_lower is None or ci_upper is None:
            raise RuleCheckFailed(
                f"{RULE}: ci_lower and ci_upper must both be present or absent",
                step_index=step_index, rule=RULE,
            )
        if not (ci_lower <= point <= ci_upper):
            raise RuleCheckFailed(
                f"{RULE}: point {point} outside [{ci_lower}, {ci_upper}]",
                step_index=step_index, rule=RULE,
            )
        if not isinstance(ci_level, (int, float)) or not (0 < ci_level < 1):
            raise RuleCheckFailed(
                f"{RULE}.ci_level must be in (0, 1); got {ci_level!r}",
                step_index=step_index, rule=RULE,
            )

    # Structural licensing: every instrument is witnessed by an
    # iv_criterion_check step (claimed True, independently re-verified in the
    # walk) with matching (x, y, conditioning).
    for z in instruments:
        matched = False
        for sid, step in step_by_id.items():
            if getattr(step, "rule", None) != "iv_criterion_check":
                continue
            si = getattr(step, "inputs", {})
            if (
                si.get("instrument") == z
                and si.get("x") == treatment
                and si.get("y") == outcome
                and frozenset(si.get("conditioning", frozenset()))
                == frozenset(conditioning)
            ):
                out = step_output_by_id.get(sid, getattr(step, "output", None))
                if out is True:
                    matched = True
                    break
        if not matched:
            raise RuleCheckFailed(
                f"{RULE}: instrument {z.predicate!r} has no iv_criterion_check "
                "witness (output True) with matching (x, y, conditioning)",
                step_index=step_index, rule=RULE,
            )

    if not isinstance(claimed_output, StructuralResult) or claimed_output.value is not True:
        raise RuleCheckFailed(
            f"{RULE} output must be a StructuralResult(value=True)",
            step_index=step_index, rule=RULE,
        )


#: What a region can say about the vector as a whole, transcribed here
#: rather than imported. The verifier owns its copy of every closed
#: vocabulary it checks — importing the producer's would make this step
#: audit its own spelling.
_AR_REGION_SHAPES = frozenset(
    {"bounded", "unbounded", "whole_space", "empty"})


def _rule_numeric_anderson_rubin_region(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Anderson-Rubin region terminal — metadata self-consistency + structural
    licensing.

    Every instrument must be witnessed by a ``vector_iv_criterion_check`` step
    (claimed True, independently re-verified in the walk) over the SAME
    treatment set, outcome and conditioning, so the region rests only on
    instruments valid for the vector as a whole. The region itself — the
    inverted quadratic, its shape, and every coordinate projection — is
    re-derived from the recorded second moments by
    ``themis.verifier.verify_vector_iv_region``, which the kernel calls: those are
    matrices, and matrices do not fit the derivation-input serialization.

    Deliberately no ``point``: the answer here is a region over k
    coefficients, and a terminal that demanded one number would be demanding
    the thing this route exists because the data may not supply.
    """
    RULE = "numeric_anderson_rubin_region"
    treatments = _require_atom_set(inputs, "treatments", step_index, RULE)
    outcome = _require_atom(inputs, "outcome", step_index, RULE)
    instruments = _require_atom_set(inputs, "instruments", step_index, RULE)
    conditioning = _require_atom_set(inputs, "conditioning", step_index, RULE)
    method = inputs.get("method")
    data_hash = inputs.get("data_hash")
    sample_size = inputs.get("sample_size")
    shape = inputs.get("shape")
    ci_level = inputs.get("ci_level")

    if method != "iv_anderson_rubin_region":
        raise RuleCheckFailed(
            f"{RULE}.method must be 'iv_anderson_rubin_region'; got {method!r}",
            step_index=step_index, rule=RULE,
        )
    if len(treatments) < 2:
        raise RuleCheckFailed(
            f"{RULE} is for a treatment VECTOR; got {len(treatments)} "
            f"treatment(s)",
            step_index=step_index, rule=RULE,
        )
    if not instruments:
        raise RuleCheckFailed(
            f"{RULE} requires at least one instrument",
            step_index=step_index, rule=RULE,
        )
    if outcome in treatments or instruments & (set(treatments) | {outcome}):
        raise RuleCheckFailed(
            f"{RULE}: treatments/outcome/instruments must be distinct",
            step_index=step_index, rule=RULE,
        )
    if conditioning & (set(treatments) | {outcome} | set(instruments)):
        raise RuleCheckFailed(
            f"{RULE}.conditioning must be disjoint from "
            f"treatments/outcome/instruments",
            step_index=step_index, rule=RULE,
        )
    if not isinstance(data_hash, str) or len(data_hash) != _SHA256_HEX_LEN \
            or not all(c in "0123456789abcdef" for c in data_hash):
        raise RuleCheckFailed(
            f"{RULE}.data_hash must be a {_SHA256_HEX_LEN}-char lowercase "
            "SHA-256 hex string",
            step_index=step_index, rule=RULE,
        )
    if (
        not isinstance(sample_size, int) or isinstance(sample_size, bool)
        or sample_size < _MIN_NUMERIC_SAMPLE_SIZE
    ):
        raise RuleCheckFailed(
            f"{RULE}.sample_size must be an int >= {_MIN_NUMERIC_SAMPLE_SIZE}; "
            f"got {sample_size!r}",
            step_index=step_index, rule=RULE,
        )
    if shape not in _AR_REGION_SHAPES:
        raise RuleCheckFailed(
            f"{RULE}.shape must be one of {sorted(_AR_REGION_SHAPES)}; got "
            f"{shape!r}",
            step_index=step_index, rule=RULE,
        )
    if not isinstance(ci_level, (int, float)) or isinstance(ci_level, bool) \
            or not (0 < ci_level < 1):
        raise RuleCheckFailed(
            f"{RULE}.ci_level must be in (0, 1); got {ci_level!r}",
            step_index=step_index, rule=RULE,
        )

    for z in instruments:
        matched = False
        for sid, step in step_by_id.items():
            if getattr(step, "rule", None) != "vector_iv_criterion_check":
                continue
            si = getattr(step, "inputs", {})
            if (
                si.get("instrument") == z
                and si.get("y") == outcome
                and frozenset(si.get("treatments", frozenset()))
                == frozenset(treatments)
                and frozenset(si.get("conditioning", frozenset()))
                == frozenset(conditioning)
            ):
                out = step_output_by_id.get(sid, getattr(step, "output", None))
                if out is True:
                    matched = True
                    break
        if not matched:
            raise RuleCheckFailed(
                f"{RULE}: instrument {z.predicate!r} has no "
                f"vector_iv_criterion_check witness (output True) over the "
                f"same treatment set, outcome and conditioning",
                step_index=step_index, rule=RULE,
            )

    if not isinstance(claimed_output, StructuralResult) or claimed_output.value is not True:
        raise RuleCheckFailed(
            f"{RULE} output must be a StructuralResult(value=True)",
            step_index=step_index, rule=RULE,
        )


def _rule_numeric_general_id_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Relaxed audit for a general-ID (c-factor plug-in) ATE estimate.

    Method enum + CI bounds + data_hash + sample_size checks; the
    referenced ``criterion`` step must be a ``general_id_criterion`` for
    the same (treatment, outcome). Same shape as numeric_iv_estimate —
    a metadata self-consistency audit, no re-fit. The identification the
    number rests on is re-derived by the referenced general_id_criterion
    step (which re-runs the ID engine).
    """
    criterion_ref = _require(
        inputs, "criterion", step_index, "numeric_general_id_estimate",
    )
    if not isinstance(criterion_ref, StepRef):
        raise UnknownRuleInputError(
            "numeric_general_id_estimate.criterion must be a StepRef",
            step_index=step_index, rule="numeric_general_id_estimate",
        )
    treatment = _require_atom(
        inputs, "treatment", step_index, "numeric_general_id_estimate",
    )
    outcome = _require_atom(
        inputs, "outcome", step_index, "numeric_general_id_estimate",
    )
    method = inputs.get("method")
    data_hash = inputs.get("data_hash")
    sample_size = inputs.get("sample_size")
    point = inputs.get("point")
    ci_lower = inputs.get("ci_lower")
    ci_upper = inputs.get("ci_upper")
    ci_level = inputs.get("ci_level")

    if method not in _NUMERIC_GENERAL_ID_METHODS:
        raise RuleCheckFailed(
            f"numeric_general_id_estimate.method must be one of "
            f"{sorted(_NUMERIC_GENERAL_ID_METHODS)}; got {method!r}",
            step_index=step_index, rule="numeric_general_id_estimate",
        )
    if not isinstance(data_hash, str) or len(data_hash) != _SHA256_HEX_LEN:
        raise RuleCheckFailed(
            f"numeric_general_id_estimate.data_hash must be a "
            f"{_SHA256_HEX_LEN}-char SHA-256 hex string",
            step_index=step_index, rule="numeric_general_id_estimate",
        )
    if not all(c in "0123456789abcdef" for c in data_hash):
        raise RuleCheckFailed(
            "numeric_general_id_estimate.data_hash must be lowercase hex",
            step_index=step_index, rule="numeric_general_id_estimate",
        )
    if (
        not isinstance(sample_size, int)
        or isinstance(sample_size, bool)
        or sample_size < _MIN_NUMERIC_SAMPLE_SIZE
    ):
        raise RuleCheckFailed(
            f"numeric_general_id_estimate.sample_size must be an int "
            f">= {_MIN_NUMERIC_SAMPLE_SIZE}; got {sample_size!r}",
            step_index=step_index, rule="numeric_general_id_estimate",
        )
    if not isinstance(point, (int, float)) or isinstance(point, bool):
        raise RuleCheckFailed(
            f"numeric_general_id_estimate.point must be a number; got {point!r}",
            step_index=step_index, rule="numeric_general_id_estimate",
        )
    ci_present = ci_lower is not None or ci_upper is not None
    if ci_present:
        if ci_lower is None or ci_upper is None:
            raise RuleCheckFailed(
                "numeric_general_id_estimate: ci_lower and ci_upper must both "
                "be present or both absent",
                step_index=step_index, rule="numeric_general_id_estimate",
            )
        if not (ci_lower <= point <= ci_upper):
            raise RuleCheckFailed(
                f"numeric_general_id_estimate: point {point} outside "
                f"[{ci_lower}, {ci_upper}]",
                step_index=step_index, rule="numeric_general_id_estimate",
            )
        if not isinstance(ci_level, (int, float)) or not (0 < ci_level < 1):
            raise RuleCheckFailed(
                f"numeric_general_id_estimate.ci_level must be in (0, 1); "
                f"got {ci_level!r}",
                step_index=step_index, rule="numeric_general_id_estimate",
            )

    if treatment == outcome:
        raise RuleCheckFailed(
            "numeric_general_id_estimate: treatment and outcome must differ",
            step_index=step_index, rule="numeric_general_id_estimate",
        )

    criterion_step = step_by_id.get(criterion_ref.step_id)
    if criterion_step is None:
        raise RuleCheckFailed(
            f"numeric_general_id_estimate: referenced criterion step "
            f"{criterion_ref.step_id!r} missing",
            step_index=step_index, rule="numeric_general_id_estimate",
        )
    if criterion_step.rule != "general_id_criterion":
        raise RuleCheckFailed(
            "numeric_general_id_estimate.criterion must reference a "
            "general_id_criterion step",
            step_index=step_index, rule="numeric_general_id_estimate",
        )
    if criterion_step.inputs.get("x") != treatment:
        raise RuleCheckFailed(
            "numeric_general_id_estimate.treatment must equal the x claimed "
            "by the referenced general_id_criterion step",
            step_index=step_index, rule="numeric_general_id_estimate",
        )
    if criterion_step.inputs.get("y") != outcome:
        raise RuleCheckFailed(
            "numeric_general_id_estimate.outcome must equal the y claimed "
            "by the referenced general_id_criterion step",
            step_index=step_index, rule="numeric_general_id_estimate",
        )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            "numeric_general_id_estimate output must be a StructuralResult",
            step_index=step_index, rule="numeric_general_id_estimate",
        )
    if claimed_output.value is not True:
        raise RuleCheckFailed(
            "numeric_general_id_estimate output.value must be True",
            step_index=step_index, rule="numeric_general_id_estimate",
        )


def _rule_numeric_joint_general_id_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Relaxed audit for a JOINT general-ID (c-factor plug-in) estimate.

    The joint analog of ``numeric_general_id_estimate``, and the same
    ANSWER-shape audit as ``numeric_joint_backdoor_estimate``: a contrast
    between two corners of the treatment box, plus a K-way interaction
    that is present as a number or absent with its species named.

    A separate terminal from the single-treatment one because the answer
    is a different shape, and the derivation's terminal is what every
    surface routes on. Sharing the name would make ``point`` and
    ``joint_point`` two spellings of one slot, which is how a router stops
    being able to tell the two answers apart.

    The declared primary treatment on the referenced ``general_id_criterion``
    step must be one of this step's treatments; the criterion re-runs the
    SET ID off ``ctx.query``, so the set it checks cannot be narrowed here.
    The two numbers themselves are re-derived from the recorded per-corner
    risks by ``themis.verifier.verify_joint_general_id_numeric`` — this
    terminal audits metadata and licensing only, matching the cost
    trade-off every other numeric rule makes.

    inputs: criterion, treatments, outcome, method, data_hash, sample_size,
        joint_point, joint_ci_lower, joint_ci_upper, ci_level, and either
        interaction_point (+ its CI) or interaction_unavailable
    output: StructuralResult(value=True)
    """
    rule = "numeric_joint_general_id_estimate"
    criterion_ref = _require(inputs, "criterion", step_index, rule)
    if not isinstance(criterion_ref, StepRef):
        raise UnknownRuleInputError(
            f"{rule}.criterion must be a StepRef",
            step_index=step_index, rule=rule,
        )
    treatments = _require_atom_set(inputs, "treatments", step_index, rule)
    outcome = _require_atom(inputs, "outcome", step_index, rule)
    method = inputs.get("method")
    data_hash = inputs.get("data_hash")
    sample_size = inputs.get("sample_size")

    if method not in _NUMERIC_GENERAL_ID_METHODS:
        raise RuleCheckFailed(
            f"{rule}.method must be one of "
            f"{sorted(_NUMERIC_GENERAL_ID_METHODS)}; got {method!r}",
            step_index=step_index, rule=rule,
        )
    if len(treatments) < 2:
        raise RuleCheckFailed(
            f"{rule}.treatments must name at least two treatments; a joint "
            f"answer over one is the single-treatment estimand",
            step_index=step_index, rule=rule,
        )
    if outcome in treatments:
        raise RuleCheckFailed(
            f"{rule}: the outcome must not be one of the treatments",
            step_index=step_index, rule=rule,
        )
    if not isinstance(data_hash, str) or len(data_hash) != _SHA256_HEX_LEN \
            or not all(c in "0123456789abcdef" for c in data_hash):
        raise RuleCheckFailed(
            f"{rule}.data_hash must be a {_SHA256_HEX_LEN}-char lowercase "
            "SHA-256 hex string",
            step_index=step_index, rule=rule,
        )
    if (
        not isinstance(sample_size, int)
        or isinstance(sample_size, bool)
        or sample_size < _MIN_NUMERIC_SAMPLE_SIZE
    ):
        raise RuleCheckFailed(
            f"{rule}.sample_size must be an int >= "
            f"{_MIN_NUMERIC_SAMPLE_SIZE}; got {sample_size!r}",
            step_index=step_index, rule=rule,
        )

    _check_joint_answer(inputs, step_index, rule)

    ci_level = inputs.get("ci_level")
    if inputs.get("joint_ci_lower") is not None and (
        not isinstance(ci_level, (int, float)) or not (0 < ci_level < 1)
    ):
        raise RuleCheckFailed(
            f"{rule}.ci_level must be in (0, 1); got {ci_level!r}",
            step_index=step_index, rule=rule,
        )

    criterion_step = step_by_id.get(criterion_ref.step_id)
    if criterion_step is None or criterion_step.rule != "general_id_criterion":
        raise RuleCheckFailed(
            f"{rule}.criterion must reference a general_id_criterion step",
            step_index=step_index, rule=rule,
        )
    if criterion_step.inputs.get("x") not in treatments:
        raise RuleCheckFailed(
            f"{rule}: the criterion's x must be one of this step's "
            "treatments",
            step_index=step_index, rule=rule,
        )
    if criterion_step.inputs.get("y") != outcome:
        raise RuleCheckFailed(
            f"{rule}.outcome must equal the y claimed by the referenced "
            "general_id_criterion step",
            step_index=step_index, rule=rule,
        )

    if not isinstance(claimed_output, StructuralResult) \
            or claimed_output.value is not True:
        raise RuleCheckFailed(
            f"{rule} output must be StructuralResult(value=True)",
            step_index=step_index, rule=rule,
        )


def _rule_numeric_scm_counterfactual_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Metadata audit for a data-fitted linear-SCM counterfactual estimate.

    Method enum + data_hash + sample_size + CI bracket checks, and binds the
    intervention / target to the QUERY (not a producer input, so a mislabelled
    terminal is caught). The STRONG re-derivation — re-solving each node's OLS
    from the recorded moment matrices and re-running abduction-action-
    prediction — is prohibitively shaped for derivation-input serialization
    (nested matrices), so it lives in ``verify_scm_counterfactual_numeric``
    (kernel.verify calls it on the numeric_estimate directly), mirroring the
    iv_2sls_overid / regression_calibration split."""
    rule = "numeric_scm_counterfactual_estimate"
    q = getattr(ctx, "query", None)
    if not isinstance(q, SCMCounterfactualQuery):
        raise RuleCheckFailed(
            f"{rule} requires a SCMCounterfactualQuery context",
            step_index=step_index, rule=rule,
        )
    target = _require_atom(inputs, "target", step_index, rule)
    intervention_var = _require_atom(inputs, "intervention_var", step_index, rule)
    # Bind to the QUERY, never trust the producer's claimed atoms.
    if target != q.target or intervention_var != q.intervention.atom:
        raise RuleCheckFailed(
            f"{rule}: target / intervention_var must match the query",
            step_index=step_index, rule=rule,
        )
    if target not in ctx.graph or intervention_var not in ctx.graph:
        raise RuleCheckFailed(
            f"{rule}: query atoms are not in the graph",
            step_index=step_index, rule=rule,
        )
    if target == intervention_var:
        raise RuleCheckFailed(
            f"{rule}: target and intervention must differ",
            step_index=step_index, rule=rule,
        )

    method = inputs.get("method")
    if method != "scm_counterfactual_linear_fit":
        raise RuleCheckFailed(
            f"{rule}.method must be 'scm_counterfactual_linear_fit'; got {method!r}",
            step_index=step_index, rule=rule,
        )
    data_hash = inputs.get("data_hash")
    if not isinstance(data_hash, str) or len(data_hash) != _SHA256_HEX_LEN \
            or not all(c in "0123456789abcdef" for c in data_hash):
        raise RuleCheckFailed(
            f"{rule}.data_hash must be a {_SHA256_HEX_LEN}-char lowercase SHA-256 hex",
            step_index=step_index, rule=rule,
        )
    sample_size = inputs.get("sample_size")
    if (
        not isinstance(sample_size, int)
        or isinstance(sample_size, bool)
        or sample_size < _MIN_NUMERIC_SAMPLE_SIZE
    ):
        raise RuleCheckFailed(
            f"{rule}.sample_size must be an int >= {_MIN_NUMERIC_SAMPLE_SIZE}; "
            f"got {sample_size!r}",
            step_index=step_index, rule=rule,
        )
    point = inputs.get("point")
    if not isinstance(point, (int, float)) or isinstance(point, bool):
        raise RuleCheckFailed(
            f"{rule}.point must be a number; got {point!r}",
            step_index=step_index, rule=rule,
        )
    ci_lower = inputs.get("ci_lower")
    ci_upper = inputs.get("ci_upper")
    if ci_lower is None or ci_upper is None:
        if ci_lower is not None or ci_upper is not None:
            raise RuleCheckFailed(
                f"{rule}: ci_lower and ci_upper must both be present or both absent",
                step_index=step_index, rule=rule,
            )
    else:
        if not (ci_lower <= point <= ci_upper):
            raise RuleCheckFailed(
                f"{rule}: point {point} outside [{ci_lower}, {ci_upper}]",
                step_index=step_index, rule=rule,
            )
        ci_level = inputs.get("ci_level")
        if not isinstance(ci_level, (int, float)) or not (0 < ci_level < 1):
            raise RuleCheckFailed(
                f"{rule}.ci_level must be in (0, 1); got {ci_level!r}",
                step_index=step_index, rule=rule,
            )
    if not isinstance(claimed_output, StructuralResult) or claimed_output.value is not True:
        raise RuleCheckFailed(
            f"{rule} output must be a StructuralResult(value=True)",
            step_index=step_index, rule=rule,
        )


def _rule_numeric_ctf_conjunction_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Relaxed audit for a counterfactual-conjunction (ID*/IDC* plug-in)
    estimate.

    Method enum + CI bounds + data_hash + sample_size + conditional-flag
    checks; the referenced ``criterion`` step must be a
    ``ctf_conjunction_criterion``. Same shape as
    ``numeric_general_id_estimate`` — a metadata self-consistency audit, no
    re-fit. The identifiability the number rests on is re-derived by the
    referenced ``ctf_conjunction_criterion`` step (which re-runs ID*/IDC*).
    There is no treatment / outcome pair (the estimand is a single
    conjunction probability, not an ATE contrast).
    """
    rule = "numeric_ctf_conjunction_estimate"
    criterion_ref = _require(inputs, "criterion", step_index, rule)
    if not isinstance(criterion_ref, StepRef):
        raise UnknownRuleInputError(
            "numeric_ctf_conjunction_estimate.criterion must be a StepRef",
            step_index=step_index, rule=rule,
        )
    method = inputs.get("method")
    data_hash = inputs.get("data_hash")
    sample_size = inputs.get("sample_size")
    point = inputs.get("point")
    ci_lower = inputs.get("ci_lower")
    ci_upper = inputs.get("ci_upper")
    ci_level = inputs.get("ci_level")
    conditional = inputs.get("conditional")

    if method not in _NUMERIC_CTF_CONJUNCTION_METHODS:
        raise RuleCheckFailed(
            f"numeric_ctf_conjunction_estimate.method must be one of "
            f"{sorted(_NUMERIC_CTF_CONJUNCTION_METHODS)}; got {method!r}",
            step_index=step_index, rule=rule,
        )
    if not isinstance(data_hash, str) or len(data_hash) != _SHA256_HEX_LEN:
        raise RuleCheckFailed(
            f"numeric_ctf_conjunction_estimate.data_hash must be a "
            f"{_SHA256_HEX_LEN}-char SHA-256 hex string",
            step_index=step_index, rule=rule,
        )
    if not all(c in "0123456789abcdef" for c in data_hash):
        raise RuleCheckFailed(
            "numeric_ctf_conjunction_estimate.data_hash must be lowercase hex",
            step_index=step_index, rule=rule,
        )
    if (
        not isinstance(sample_size, int)
        or isinstance(sample_size, bool)
        or sample_size < _MIN_NUMERIC_SAMPLE_SIZE
    ):
        raise RuleCheckFailed(
            f"numeric_ctf_conjunction_estimate.sample_size must be an int "
            f">= {_MIN_NUMERIC_SAMPLE_SIZE}; got {sample_size!r}",
            step_index=step_index, rule=rule,
        )
    if not isinstance(point, (int, float)) or isinstance(point, bool):
        raise RuleCheckFailed(
            f"numeric_ctf_conjunction_estimate.point must be a number; "
            f"got {point!r}",
            step_index=step_index, rule=rule,
        )
    if not isinstance(conditional, bool):
        raise RuleCheckFailed(
            f"numeric_ctf_conjunction_estimate.conditional must be a bool; "
            f"got {conditional!r}",
            step_index=step_index, rule=rule,
        )
    ci_present = ci_lower is not None or ci_upper is not None
    if ci_present:
        if ci_lower is None or ci_upper is None:
            raise RuleCheckFailed(
                "numeric_ctf_conjunction_estimate: ci_lower and ci_upper must "
                "both be present or both absent",
                step_index=step_index, rule=rule,
            )
        if not (ci_lower <= point <= ci_upper):
            raise RuleCheckFailed(
                f"numeric_ctf_conjunction_estimate: point {point} outside "
                f"[{ci_lower}, {ci_upper}]",
                step_index=step_index, rule=rule,
            )
        if not isinstance(ci_level, (int, float)) or not (0 < ci_level < 1):
            raise RuleCheckFailed(
                f"numeric_ctf_conjunction_estimate.ci_level must be in (0, 1); "
                f"got {ci_level!r}",
                step_index=step_index, rule=rule,
            )

    criterion_step = step_by_id.get(criterion_ref.step_id)
    if criterion_step is None:
        raise RuleCheckFailed(
            f"numeric_ctf_conjunction_estimate: referenced criterion step "
            f"{criterion_ref.step_id!r} missing",
            step_index=step_index, rule=rule,
        )
    if criterion_step.rule != "ctf_conjunction_criterion":
        raise RuleCheckFailed(
            "numeric_ctf_conjunction_estimate.criterion must reference a "
            "ctf_conjunction_criterion step",
            step_index=step_index, rule=rule,
        )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            "numeric_ctf_conjunction_estimate output must be a StructuralResult",
            step_index=step_index, rule=rule,
        )
    if claimed_output.value is not True:
        raise RuleCheckFailed(
            "numeric_ctf_conjunction_estimate output.value must be True",
            step_index=step_index, rule=rule,
        )


_NUMERIC_PROXIMAL_METHODS = frozenset({"proximal_matrix"})


def _rule_proximal_criterion(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify P(Y|do(X)) is proximal-identifiable (Miao model (f)) on this
    ADMG — the structural licence for a proximal matrix plug-in estimate and
    the primary answer of a structural proximal query.

    Re-runs ``proximal_identify.identify_proximal`` on the context's
    (graph, bidirected) and the query's roles (treatment/outcome/latent/
    proxies + k), and confirms the outcome is a ``ProximalEstimand``. A
    ``ProximalNotIdentified`` must NEVER back a numeric estimate. Like
    ``ctf_conjunction_criterion`` / ``general_id_criterion``, it re-runs the
    identification engine independently rather than trusting the result.

    inputs: graph
    output: bool
    """
    from ..runtime.proximal_identify import ProximalEstimand, identify_proximal
    from ..types import ProximalEffectQuery

    graph = _require(inputs, "graph", step_index, "proximal_criterion")
    _assert_same_graph(graph, ctx.graph, step_index, "proximal_criterion")

    q = getattr(ctx, "query", None)
    if not isinstance(q, ProximalEffectQuery):
        raise RuleCheckFailed(
            "proximal_criterion requires a ProximalEffectQuery in the "
            "verification context",
            step_index=step_index, rule="proximal_criterion",
        )

    bidir = ctx.bidirected
    outcome = identify_proximal(
        graph, bidir,
        treatment=q.treatment, outcome=q.outcome, latent=q.latent,
        treatment_proxy=q.treatment_proxy, outcome_proxy=q.outcome_proxy,
        latent_cardinality=q.latent_cardinality,
    )
    identified = isinstance(outcome, ProximalEstimand)
    if identified != bool(claimed_output):
        raise RuleCheckFailed(
            f"proximal_criterion claimed {claimed_output!r}, but "
            f"identify_proximal recomputed identifiable={identified!r}",
            step_index=step_index, rule="proximal_criterion",
        )


def _rule_numeric_proximal_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Relaxed audit for a proximal matrix plug-in ATE estimate.

    Method enum + CI bounds + data_hash + sample_size checks; the referenced
    ``criterion`` step must be a ``proximal_criterion``. Same shape as
    ``numeric_ctf_conjunction_estimate`` — a metadata self-consistency audit,
    no re-fit. The identifiability the number rests on is re-derived by the
    referenced ``proximal_criterion`` step (which re-runs identify_proximal).
    """
    rule = "numeric_proximal_estimate"
    criterion_ref = _require(inputs, "criterion", step_index, rule)
    if not isinstance(criterion_ref, StepRef):
        raise UnknownRuleInputError(
            "numeric_proximal_estimate.criterion must be a StepRef",
            step_index=step_index, rule=rule,
        )
    method = inputs.get("method")
    data_hash = inputs.get("data_hash")
    sample_size = inputs.get("sample_size")
    point = inputs.get("point")
    ci_lower = inputs.get("ci_lower")
    ci_upper = inputs.get("ci_upper")
    ci_level = inputs.get("ci_level")

    if method not in _NUMERIC_PROXIMAL_METHODS:
        raise RuleCheckFailed(
            f"numeric_proximal_estimate.method must be one of "
            f"{sorted(_NUMERIC_PROXIMAL_METHODS)}; got {method!r}",
            step_index=step_index, rule=rule,
        )
    if not isinstance(data_hash, str) or len(data_hash) != _SHA256_HEX_LEN:
        raise RuleCheckFailed(
            f"numeric_proximal_estimate.data_hash must be a "
            f"{_SHA256_HEX_LEN}-char SHA-256 hex string",
            step_index=step_index, rule=rule,
        )
    if not all(c in "0123456789abcdef" for c in data_hash):
        raise RuleCheckFailed(
            "numeric_proximal_estimate.data_hash must be lowercase hex",
            step_index=step_index, rule=rule,
        )
    if (
        not isinstance(sample_size, int)
        or isinstance(sample_size, bool)
        or sample_size < _MIN_NUMERIC_SAMPLE_SIZE
    ):
        raise RuleCheckFailed(
            f"numeric_proximal_estimate.sample_size must be an int "
            f">= {_MIN_NUMERIC_SAMPLE_SIZE}; got {sample_size!r}",
            step_index=step_index, rule=rule,
        )
    if not isinstance(point, (int, float)) or isinstance(point, bool):
        raise RuleCheckFailed(
            f"numeric_proximal_estimate.point must be a number; got {point!r}",
            step_index=step_index, rule=rule,
        )
    ci_present = ci_lower is not None or ci_upper is not None
    if ci_present:
        if ci_lower is None or ci_upper is None:
            raise RuleCheckFailed(
                "numeric_proximal_estimate: ci_lower and ci_upper must both be "
                "present or both absent",
                step_index=step_index, rule=rule,
            )
        if not (ci_lower <= point <= ci_upper):
            raise RuleCheckFailed(
                f"numeric_proximal_estimate: point {point} outside "
                f"[{ci_lower}, {ci_upper}]",
                step_index=step_index, rule=rule,
            )
        if not isinstance(ci_level, (int, float)) or not (0 < ci_level < 1):
            raise RuleCheckFailed(
                f"numeric_proximal_estimate.ci_level must be in (0, 1); "
                f"got {ci_level!r}",
                step_index=step_index, rule=rule,
            )

    criterion_step = step_by_id.get(criterion_ref.step_id)
    if criterion_step is None:
        raise RuleCheckFailed(
            f"numeric_proximal_estimate: referenced criterion step "
            f"{criterion_ref.step_id!r} missing",
            step_index=step_index, rule=rule,
        )
    if criterion_step.rule != "proximal_criterion":
        raise RuleCheckFailed(
            "numeric_proximal_estimate.criterion must reference a "
            "proximal_criterion step",
            step_index=step_index, rule=rule,
        )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            "numeric_proximal_estimate output must be a StructuralResult",
            step_index=step_index, rule=rule,
        )
    if claimed_output.value is not True:
        raise RuleCheckFailed(
            "numeric_proximal_estimate output.value must be True",
            step_index=step_index, rule=rule,
        )


_NUMERIC_MEASUREMENT_CORRECTION_METHODS = frozenset({
    "measurement_error_correction",
    "exposure_measurement_error_correction",
    # Both channels at once — same terminal; the two-sided inversion is
    # re-derived by verify_combined_measurement_correction_numeric.
    "combined_measurement_error_correction",
    # Continuous mismeasurement (regression calibration) shares this terminal —
    # metadata + back-door structural licensing; the moment-correction point is
    # re-derived from the recorded design covariance by
    # verify_regression_calibration_numeric (kernel-called).
    "regression_calibration",
})


def _rule_numeric_measurement_correction_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict[str, Any],
    step_output_by_id: dict[str, Any],
) -> None:
    """Relaxed audit for a confusion-matrix-corrected effect estimate.

    Method enum + CI bounds + data_hash + sample_size checks, plus structural
    licensing: the referenced ``criterion`` step must be a ``backdoor_criterion``
    (the correction standardises over a back-door adjustment set). The matrix
    inversion / point re-derivation from the recorded confusion matrix +
    per-stratum value-count vectors is ``verify_measurement_correction_numeric``,
    called from the kernel — those matrices don't fit derivation-input
    serialization, so they live in the numeric_estimate block, not here.
    """
    rule = "numeric_measurement_correction_estimate"
    criterion_ref = _require(inputs, "criterion", step_index, rule)
    if not isinstance(criterion_ref, StepRef):
        raise UnknownRuleInputError(
            "numeric_measurement_correction_estimate.criterion must be a StepRef",
            step_index=step_index, rule=rule,
        )
    method = inputs.get("method")
    data_hash = inputs.get("data_hash")
    sample_size = inputs.get("sample_size")
    point = inputs.get("point")
    ci_lower = inputs.get("ci_lower")
    ci_upper = inputs.get("ci_upper")
    ci_level = inputs.get("ci_level")

    if method not in _NUMERIC_MEASUREMENT_CORRECTION_METHODS:
        raise RuleCheckFailed(
            f"numeric_measurement_correction_estimate.method must be one of "
            f"{sorted(_NUMERIC_MEASUREMENT_CORRECTION_METHODS)}; got {method!r}",
            step_index=step_index, rule=rule,
        )
    if not isinstance(data_hash, str) or len(data_hash) != _SHA256_HEX_LEN:
        raise RuleCheckFailed(
            f"numeric_measurement_correction_estimate.data_hash must be a "
            f"{_SHA256_HEX_LEN}-char SHA-256 hex string",
            step_index=step_index, rule=rule,
        )
    if not all(c in "0123456789abcdef" for c in data_hash):
        raise RuleCheckFailed(
            "numeric_measurement_correction_estimate.data_hash must be "
            "lowercase hex",
            step_index=step_index, rule=rule,
        )
    if (
        not isinstance(sample_size, int)
        or isinstance(sample_size, bool)
        or sample_size < _MIN_NUMERIC_SAMPLE_SIZE
    ):
        raise RuleCheckFailed(
            f"numeric_measurement_correction_estimate.sample_size must be an int "
            f">= {_MIN_NUMERIC_SAMPLE_SIZE}; got {sample_size!r}",
            step_index=step_index, rule=rule,
        )
    if not isinstance(point, (int, float)) or isinstance(point, bool):
        raise RuleCheckFailed(
            f"numeric_measurement_correction_estimate.point must be a number; "
            f"got {point!r}",
            step_index=step_index, rule=rule,
        )
    ci_present = ci_lower is not None or ci_upper is not None
    if ci_present:
        if ci_lower is None or ci_upper is None:
            raise RuleCheckFailed(
                "numeric_measurement_correction_estimate: ci_lower and ci_upper "
                "must both be present or both absent",
                step_index=step_index, rule=rule,
            )
        if not (ci_lower <= point <= ci_upper):
            raise RuleCheckFailed(
                f"numeric_measurement_correction_estimate: point {point} outside "
                f"[{ci_lower}, {ci_upper}]",
                step_index=step_index, rule=rule,
            )
        if not isinstance(ci_level, (int, float)) or not (0 < ci_level < 1):
            raise RuleCheckFailed(
                f"numeric_measurement_correction_estimate.ci_level must be in "
                f"(0, 1); got {ci_level!r}",
                step_index=step_index, rule=rule,
            )

    criterion_step = step_by_id.get(criterion_ref.step_id)
    if criterion_step is None:
        raise RuleCheckFailed(
            f"numeric_measurement_correction_estimate: referenced criterion step "
            f"{criterion_ref.step_id!r} missing",
            step_index=step_index, rule=rule,
        )
    if criterion_step.rule != "backdoor_criterion":
        raise RuleCheckFailed(
            "numeric_measurement_correction_estimate.criterion must reference a "
            "backdoor_criterion step",
            step_index=step_index, rule=rule,
        )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            "numeric_measurement_correction_estimate output must be a "
            "StructuralResult",
            step_index=step_index, rule=rule,
        )
    if claimed_output.value is not True:
        raise RuleCheckFailed(
            "numeric_measurement_correction_estimate output.value must be True",
            step_index=step_index, rule=rule,
        )


_NUMERIC_CAUSATION_METHODS = frozenset({"causation_plugin"})

#: What a resampled pair of endpoints can be a statement about, spelled here
#: rather than imported. This verifier keeps its own copy of every word it
#: checks, for the reason the bounds verifier keeps its own estimand table:
#: a check that read the producer's vocabulary would agree with it by
#: construction, and what is being checked is a producer's claim (#419).
_WIDTH_SAMPLING = "sampling"
_WIDTH_OUTER_BAND = "outer_band"


def _check_ci_width(inputs, *, pinned: bool, step_index, rule: str) -> None:
    """Which of the two the ci pair is, against which one the run produced.

    Re-derived rather than read: a point came out or it did not, and that
    settles it. Absent is refused, because the surfaces that render this
    pair used to work the answer out for themselves and the field exists so
    that they stop — a row that omits it sends them back to guessing.
    """
    said = inputs.get("ci_width_is")
    expected = _WIDTH_SAMPLING if pinned else _WIDTH_OUTER_BAND
    if said != expected:
        raise RuleCheckFailed(
            f"{rule}: ci_width_is is {said!r} and this run produced "
            f"{expected!r} — the pair is "
            + ("a point’s bootstrap interval" if pinned
               else "a band on the identified interval")
            + ". The two narrow with different things, so the word decides "
              "what a reader is told to do next",
            step_index=step_index, rule=rule,
        )


def _rule_numeric_causation_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Independent audit of a data-based PN/PS/PNS (causation) estimate.

    The numeric counterpart of ``causation_probability_bounds``, but
    the observational joint + interventional risks are now EMPIRICAL, so the
    theta-recovery leg does not apply. Three independent re-checks:

    1. Theorem re-application — the reported PN/PS/PNS points must equal the
       verifier's OWN Tian-Pearl transcription (``_tian_pearl_poc_for_verifier``,
       never the producer's oracle) of the reported joint + do-risks; catches a
       formula / packaging bug in the data path.
    2. Identification structure — when the do-risks were back-door standardized
       (or exogenous), the claimed adjustment set is re-derived from
       ``ctx.graph`` via ``minimal_adjustment_sets`` and must be a genuinely
       admissible back-door set; catches standardizing over a WRONG set.
    3. Metadata self-consistency — method enum, data_hash hex, sample_size,
       probabilities in range, PN CI brackets the point.

    Like the other numeric verifiers this does not re-fit on the raw data (the
    verifier holds only the ``data_hash``); the arithmetic and the graph
    licence are what it re-derives.

    inputs: cause/effect atoms, the four empirical cells, the two do-risks,
        monotonic, provenance, adjustment, the reported pn/ps/pns points, CI.
    output: StructuralResult(value=True)
    """
    from ..runtime import structural_solver

    rule = "numeric_causation_estimate"
    if not isinstance(ctx.query, CausationQuery):
        raise RuleCheckFailed(
            f"{rule} requires a CausationQuery context",
            step_index=step_index, rule=rule,
        )

    method = inputs.get("method")
    if method not in _NUMERIC_CAUSATION_METHODS:
        raise RuleCheckFailed(
            f"{rule}.method must be one of {sorted(_NUMERIC_CAUSATION_METHODS)}; "
            f"got {method!r}",
            step_index=step_index, rule=rule,
        )
    data_hash = inputs.get("data_hash")
    if not isinstance(data_hash, str) or len(data_hash) != _SHA256_HEX_LEN:
        raise RuleCheckFailed(
            f"{rule}.data_hash must be a {_SHA256_HEX_LEN}-char SHA-256 hex string",
            step_index=step_index, rule=rule,
        )
    if not all(c in "0123456789abcdef" for c in data_hash):
        raise RuleCheckFailed(
            f"{rule}.data_hash must be lowercase hex",
            step_index=step_index, rule=rule,
        )
    sample_size = inputs.get("sample_size")
    if (
        not isinstance(sample_size, int)
        or isinstance(sample_size, bool)
        or sample_size < _MIN_NUMERIC_SAMPLE_SIZE
    ):
        raise RuleCheckFailed(
            f"{rule}.sample_size must be an int >= {_MIN_NUMERIC_SAMPLE_SIZE}; "
            f"got {sample_size!r}",
            step_index=step_index, rule=rule,
        )

    x_atom = _require_atom(inputs, "cause", step_index, rule)
    y_atom = _require_atom(inputs, "effect", step_index, rule)
    if x_atom != ctx.query.cause or y_atom != ctx.query.effect:
        raise RuleCheckFailed(
            f"{rule}: cause/effect inputs do not bind to the query atoms",
            step_index=step_index, rule=rule,
        )

    cells = {
        "p_x1_y1": float(_require(inputs, "p_x1_y1", step_index, rule)),
        "p_x1_y0": float(_require(inputs, "p_x1_y0", step_index, rule)),
        "p_x0_y1": float(_require(inputs, "p_x0_y1", step_index, rule)),
        "p_x0_y0": float(_require(inputs, "p_x0_y0", step_index, rule)),
    }
    if abs(sum(cells.values()) - 1.0) > 1e-6:
        raise RuleCheckFailed(
            f"{rule}: the four observational cells must sum to 1; "
            f"got {sum(cells.values()):.6g}",
            step_index=step_index, rule=rule,
        )
    raw_r1 = _require(inputs, "p_y_do_x1", step_index, rule)
    raw_r0 = _require(inputs, "p_y_do_x0", step_index, rule)
    p_y_do_x1 = None if raw_r1 is None else float(raw_r1)
    p_y_do_x0 = None if raw_r0 is None else float(raw_r0)
    for label, v in (("p_y_do_x1", p_y_do_x1), ("p_y_do_x0", p_y_do_x0)):
        if v is not None and not (0.0 <= v <= 1.0):
            raise RuleCheckFailed(
                f"{rule}: {label}={v} is not a probability in [0, 1]",
                step_index=step_index, rule=rule,
            )
    monotonic = bool(_require(inputs, "monotonic", step_index, rule))

    # 2 (first, because it decides which solver to re-run). Identification
    #    structure: the licence is re-derived rather than read, and it is what
    #    says whether the closed form had inputs at all.
    provenance = _check_risk_provenance(
        inputs, ctx, None, step_index=step_index, rule=rule,
    )
    risk_free = provenance in _RISK_FREE
    if risk_free != (p_y_do_x1 is None or p_y_do_x0 is None):
        raise RuleCheckFailed(
            f"{rule}: provenance {provenance!r} disagrees with the presence "
            f"of the interventional risks",
            step_index=step_index, rule=rule,
        )

    # 1. Independent re-derivation on the reported empirical inputs — by
    #    whichever solver the licence says ran. Tian-Pearl's closed form has no
    #    answer for the instrument route (it would demand the very risks that
    #    route exists because nobody has), so choosing here is not a shortcut:
    #    it is the same question asked of the same producer through the program
    #    it actually solved. The bounds are re-derived for every answer; a
    #    point is re-derived where the route can have one, and the loop below
    #    checks that an absent point is consistent either way.
    if provenance == "instrument_response_polytope":
        recomputed = _rederive_causation_over_response_polytope(
            ctx, inputs, cells, monotonic, step_index=step_index, rule=rule,
        )
    elif p_y_do_x1 is None or p_y_do_x0 is None:
        raise RuleCheckFailed(
            f"{rule}: provenance {provenance!r} claims both arms were "
            f"obtained, but one of them is absent",
            step_index=step_index, rule=rule,
        )
    else:
        recomputed = _tian_pearl_poc_for_verifier(
            p_x1_y1=cells["p_x1_y1"], p_x1_y0=cells["p_x1_y0"],
            p_x0_y1=cells["p_x0_y1"], p_x0_y0=cells["p_x0_y0"],
            p_y_do_x1=p_y_do_x1, p_y_do_x0=p_y_do_x0, monotonic=monotonic,
        )
    for q in ("pn", "ps", "pns"):
        exp_lower, exp_upper, exp_point = recomputed[q]
        # Bounds must match the independent re-derivation exactly.
        for label, reported_v, expected_v in (
            (f"{q}_lower", _require(inputs, f"{q}_lower", step_index, rule), exp_lower),
            (f"{q}_upper", _require(inputs, f"{q}_upper", step_index, rule), exp_upper),
        ):
            if abs(float(reported_v) - expected_v) > 1e-9:
                raise RuleCheckFailed(
                    f"{rule}: {label} {reported_v} does not match the "
                    f"independently re-derived Tian-Pearl value {expected_v}",
                    step_index=step_index, rule=rule,
                )
        reported = _require(inputs, f"{q}_point", step_index, rule)
        if exp_point is None:
            # A zero conditioning cell — the producer should not claim a point.
            if reported is not None:
                raise RuleCheckFailed(
                    f"{rule}: {q} point claimed {reported} but the conditioning "
                    "cell has zero mass — it is not point-identified",
                    step_index=step_index, rule=rule,
                )
            continue
        if reported is None or abs(float(reported) - exp_point) > 1e-9:
            raise RuleCheckFailed(
                f"{rule}: {q} point {reported} does not match the independently "
                f"re-derived Tian-Pearl value {exp_point}",
                step_index=step_index, rule=rule,
            )
        if not (0.0 <= float(reported) <= 1.0):
            raise RuleCheckFailed(
                f"{rule}: {q} point {reported} is not a probability in [0, 1]",
                step_index=step_index, rule=rule,
            )

    # 2 (continued). The adjustment set must be an admissible back-door set on
    #    ctx.graph, and the routes that standardize over nothing must claim
    #    nothing. ``adjustment`` is serialized as a comma-joined scalar string
    #    (the derivation serializer does not take a tuple of strings).
    adjustment_str = _require(inputs, "adjustment", step_index, rule)
    if provenance in ("backdoor_adjustment", "exogenous"):
        sets = structural_solver.minimal_adjustment_sets(
            ctx.graph, x_atom, y_atom,
            bidirected=(ctx.bidirected or None),
        )
        if not sets:
            raise RuleCheckFailed(
                f"{rule}: no admissible back-door adjustment set exists on the "
                "graph, yet the estimate claims a data-identified do-risk",
                step_index=step_index, rule=rule,
            )
        claimed = frozenset(p for p in str(adjustment_str).split(",") if p)
        admissible = {frozenset(a.predicate for a in s) for s in sets}
        if claimed not in admissible:
            raise RuleCheckFailed(
                f"{rule}: claimed adjustment set {sorted(claimed)} is not an "
                f"admissible minimal back-door set on the graph",
                step_index=step_index, rule=rule,
            )
    else:
        if str(adjustment_str):
            raise RuleCheckFailed(
                f"{rule}: provenance {provenance!r} standardizes over nothing, "
                f"yet an adjustment set {str(adjustment_str)!r} is claimed",
                step_index=step_index, rule=rule,
            )
        if provenance in ("general_id_plug_in", "instrument_response_polytope"):
            # Both licences open with the same claim — that NO covariate set
            # identifies the risks — and it is the claim that sent the answer
            # down a route with weaker guarantees, so it is re-derived here
            # rather than believed. What each licence adds on top of it is
            # checked in its own place: the estimands below, the table above.
            if structural_solver.minimal_adjustment_sets(
                ctx.graph, x_atom, y_atom, bidirected=(ctx.bidirected or None),
            ):
                raise RuleCheckFailed(
                    f"{rule}: provenance {provenance!r} claims no covariate "
                    f"set identifies the do-risks, but the graph admits a "
                    f"back-door adjustment set",
                    step_index=step_index, rule=rule,
                )
        if provenance == "general_id_plug_in":
            _check_causation_general_id_risks(
                ctx, inputs, x_atom, y_atom, step_index=step_index, rule=rule,
            )

    # 3. Headline PN CI (present only when a bootstrap ran). When the PN point
    #    is identified (monotone) the CI must bracket the point; for the
    #    bounds-only answer it is the OUTER band on the PN identified set, which
    #    is a bootstrap artifact (not independently re-derivable from a data_hash)
    #    so it is checked only for validity as a probability interval.
    ci_lower = inputs.get("ci_lower")
    ci_upper = inputs.get("ci_upper")
    if ci_lower is not None or ci_upper is not None:
        if ci_lower is None or ci_upper is None:
            raise RuleCheckFailed(
                f"{rule}: ci_lower and ci_upper must both be present or absent",
                step_index=step_index, rule=rule,
            )
        pn_point_in = inputs.get("pn_point")
        _check_ci_width(inputs, pinned=pn_point_in is not None,
                        step_index=step_index, rule=rule)
        if pn_point_in is not None:
            pn_point = float(pn_point_in)
            if not (ci_lower <= pn_point <= ci_upper):
                raise RuleCheckFailed(
                    f"{rule}: PN point {pn_point} outside CI [{ci_lower}, {ci_upper}]",
                    step_index=step_index, rule=rule,
                )
        elif not (0.0 <= ci_lower <= ci_upper <= 1.0):
            raise RuleCheckFailed(
                f"{rule}: PN outer band [{ci_lower}, {ci_upper}] is not a valid "
                "probability interval",
                step_index=step_index, rule=rule,
            )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            f"{rule} output must be a StructuralResult",
            step_index=step_index, rule=rule,
        )
    if claimed_output.value is not True:
        raise RuleCheckFailed(
            f"{rule} output.value must be True",
            step_index=step_index, rule=rule,
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
    independence fallback so the d-separation safety guard fires on the
    verifier side too. Without them the guard is dead code on this path
    and the verifier silently agrees with the runtime's wrong answer for
    chain-DAG + marginal-only theta — the one case where two independent
    evaluators agreeing proves nothing, because they would be making the
    same substitution. Callers from ``_rule_formula_evaluation`` pass
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
            # Fix 3+4: thread population from the ProbRef so transport
            # formulas (P(...source) vs P*(...target)) route to the
            # right theta partition. None default = pre-fix behaviour
            # for all single-population formulas.
            population=expr.population,
        )
        value = theta.entries.get(key)
        if value is None:
            # mirror the runtime numeric_estimator's
            # auto-marginalization fallback. Verifier independence
            # is preserved because we only consume theta entries +
            # canonical math (no shared state with runtime).
            derived = _verifier_derive_via_marginalization(
                key, theta, graph=graph, bidirected=bidirected,
            )
            if derived is None:
                # Mirror the marginal-independence fallback, with graph
                # + bidirected threaded so the d-sep guard fires here
                # too.
                derived = _verifier_marginal_independence_lookup(
                    key, theta, graph=graph, bidirected=bidirected,
                )
            if derived is not None:
                return float(derived)
            # enrich the refusal message with the d-sep guard's
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
    if isinstance(expr, FractionExpr):
        # Conditional interventional estimand P(Y|do(X),Z) =
        # ID(Y∪Z_rem, X') / ID(Z_rem, X') (IDC). Independent mirror of the
        # runtime numeric_estimator's FractionExpr branch, positivity guard
        # included: a zero denominator is a zero-probability conditioning
        # event, not a value.
        num = _evaluate_formula(
            expr.numerator, theta, subs,
            graph=graph, bidirected=bidirected,
        )
        den = _evaluate_formula(
            expr.denominator, theta, subs,
            graph=graph, bidirected=bidirected,
        )
        if den == 0.0:
            raise _NonConcreteValue(
                "fraction denominator evaluated to 0 — positivity violation "
                "(the conditioning event P_x(z) has zero probability)"
            )
        return num / den
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
    """Verifier-side mirror of runtime numeric_estimator's
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
    pop = missing_key.population  # Fix 3+4: same-population isolation

    candidates = []
    seen: set = set()
    for key in theta.entries:
        if key.population != pop:
            continue
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
                population=pop,
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
                population=pop,
            )
            v_inner = theta.entries.get(inner_key)
            if v_inner is None:
                v_inner = _verifier_derive_via_marginalization(
                    inner_key, theta, _depth=_depth + 1,
                    graph=graph, bidirected=bidirected,
                )
                if v_inner is None:
                    # mirror the runtime's Bayes inversion
                    # fallback for the inner factor.
                    v_inner = _verifier_derive_via_bayes_inversion(
                        inner_key, theta, _depth=_depth + 1,
                        graph=graph, bidirected=bidirected,
                    )
                if v_inner is None:
                    # mirror the marginal-independence lookup.
                    # graph + bidirected threaded so the d-sep guard
                    # fires here too.
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
    """Verifier mirror of the runtime's marginal-independence
    lookup. Pure theta lookup; preserves V0-V5 independence.

    The graph-aware d-separation guard mirrors the runtime's. When
    graph + bidirected supplied, only return value if target ⊥ extras
    | reduced_given holds structurally."""
    target_atom = missing_key.target_atom
    target_value = missing_key.target_value
    base_given = missing_key.given
    pop = missing_key.population  # Fix 3+4
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
                given=reduced, population=pop,
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
    """Verifier mirror of the runtime's
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
    pop = missing_key.population  # Fix 3+4
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
            # Sync with runtime _diagnose_marginal_independence_refusal:
            # a bare marginal (empty conditioning) is not an independence
            # claim, so its d-sep refusal is missing data, not a
            # graph-CPT mismatch. Skip so both diagnostics agree.
            if not reduced:
                continue
            reduced_key = ProbabilityKey(
                target_atom=target_atom, target_value=target_value,
                given=reduced, population=pop,
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
    """Verifier mirror of the runtime's Bayes inversion helper.
    Pure function; preserves V0-V5 independence. Mirror change to
    runtime's _try_derive_via_bayes_inversion when modifying.

    ``graph`` / ``bidirected`` are accepted and passed through
    to recursive marginalization calls so the d-sep guard at the
    leaf marginal-independence lookup fires correctly during deep
    recursion, not just at the top level.
    """
    if _depth > 2:
        return None
    target_atom = missing_key.target_atom
    target_value = missing_key.target_value
    base_given = missing_key.given
    pop = missing_key.population  # Fix 3+4
    if not base_given:
        return None
    for a_atom, a_value in base_given:
        if a_atom == target_atom:
            continue
        reduced_given = frozenset(p for p in base_given if p[0] != a_atom)
        flip_given = reduced_given | {(target_atom, target_value)}
        flip_key = ProbabilityKey(
            target_atom=a_atom, target_value=a_value,
            given=frozenset(flip_given), population=pop,
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
            given=reduced_given, population=pop,
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
            given=reduced_given, population=pop,
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
    if not isinstance(formula, (ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr, FractionExpr)):
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
        "iv_wald_numeric_evaluate",
    ):
        raise RuleCheckFailed(
            f"numeric_result: evaluation must reference a formula_evaluation, "
            f"probability_ref_lookup, mediation_numeric_evaluate, or "
            f"iv_wald_numeric_evaluate step, got {eval_step.rule!r}",
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
    # Fix 6 (audit follow-up): IV Wald path extracts `late` from the
    # bundled numeric step's output. Caller's NumericResult.value must
    # equal LATE; semantic caveat (LATE ≠ ATE) is in extensions.
    if eval_step.rule == "iv_wald_numeric_evaluate":
        if not isinstance(eval_out, dict) or "late" not in eval_out:
            raise RuleCheckFailed(
                "numeric_result: iv_wald_numeric_evaluate output must be a "
                "dict containing 'late'",
                step_index=step_index, rule="numeric_result",
            )
        eval_out = eval_out["late"]
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

    # The SET of directed paths is the semantic content; its order is not
    # meaningful, exactly as for the open-path twin below. The producer sorts
    # output.supporting_paths for a canonical render but stores inputs.paths
    # in raw traversal order, and nx.all_simple_paths enumerates in a third —
    # so compare as SETS. The order-sensitive equality this replaces rejected
    # every correct multi-path cause claim (a mediator alongside a direct
    # edge), while agreeing with the docstring's word for it, which was
    # "set" all along.
    expected_paths = tuple(nx.all_simple_paths(graph, src, dst))
    if set(paths) != {tuple(path) for path in expected_paths}:
        raise RuleCheckFailed(
            "cause_via_directed_path.paths does not equal the full directed-path set",
            step_index=step_index, rule="cause_via_directed_path",
        )

    if not isinstance(claimed_output, StructuralResult) or claimed_output.value is not True:
        raise RuleCheckFailed(
            "cause_via_directed_path must claim StructuralResult(value=True)",
            step_index=step_index, rule="cause_via_directed_path",
        )
    expected_supporting = {
        tuple(_atom_label_verifier(a) for a in path) for path in expected_paths
    }
    if set(claimed_output.supporting_paths or ()) != expected_supporting:
        raise RuleCheckFailed(
            "cause_via_directed_path: claimed supporting_paths do not match "
            "the directed-path set implied by the witnesses",
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

    # The SET of open paths is the semantic content; its order is not
    # meaningful. The producer sorts output.supporting_paths for a canonical
    # render but stores inputs.paths in raw traversal order, while
    # _all_open_paths_for_verifier returns its own traversal order — so compare
    # as SETS. (The earlier order-sensitive equality rejected every correct
    # multi-open-path d-connection, e.g. X->Y together with X->Z->Y, merely
    # because the two sides enumerated the same paths in a different order.)
    expected_paths = _all_open_paths_for_verifier(graph, x, y, conditioning)
    if set(paths) != set(expected_paths):
        raise RuleCheckFailed(
            "d_connected_via_open_path.paths does not equal the full open-path set",
            step_index=step_index, rule="d_connected_via_open_path",
        )

    if not isinstance(claimed_output, StructuralResult) or claimed_output.value is not True:
        raise RuleCheckFailed(
            "d_connected_via_open_path must claim StructuralResult(value=True)",
            step_index=step_index, rule="d_connected_via_open_path",
        )
    expected_supporting = {
        tuple(_atom_label_verifier(a) for a in path) for path in expected_paths
    }
    if set(claimed_output.supporting_paths or ()) != expected_supporting:
        raise RuleCheckFailed(
            "d_connected_via_open_path: claimed supporting_paths do not match "
            "the open-path set implied by the witnesses",
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
    if isinstance(claimed_output, StructuralResult):
        claimed_bool = claimed_output.value
    else:
        claimed_bool = bool(claimed_output)
    # The assoc StructuralResult.value is the ASSOCIATION truth (True =
    # m-connected) — the SAME convention m_connection_witness verifies. The
    # separation witness must therefore compare the recomputed connectivity
    # DIRECTLY against the claim, not its negation. The earlier `not connected`
    # flip compared separation-truth against association-truth and so rejected
    # every correct "not associated" verdict whose blocking node is a collider
    # formed by bidirected edges (textbook M-bias A<->L<->Y, What If Fig 7.4).
    if connected != claimed_bool:
        raise RuleCheckFailed(
            f"m_separation_witness claimed {claimed_output!r}, recomputed "
            f"m-connected={connected!r} for x={x.predicate}, y={y.predicate}, "
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

    The chain rule in topological order holds for any joint distribution;
    what a DAG whose common causes are all measured adds is permission to
    DROP each factor's non-parents. A bidirected edge takes that permission
    away and leaves the factorization intact with wider conditioning sets, so
    this reads the ancestral subgraph either way and only changes what each
    factor is conditioned on. Falling back to the local chain-rule recovery
    is for a theta that does not carry the factors, not for a graph that
    carries a bow.
    """
    recovered = _ancestral_joint_for_verifier(
        graph, theta, x_atom=x_atom, y_atom=y_atom, bidirected=bidirected,
        step_index=step_index, rule=rule,
    )
    if recovered is None:
        return None
    topo, joint = recovered
    xi, yi = topo.index(x_atom), topo.index(y_atom)
    cells: dict[tuple[bool, bool], float] = {
        (False, False): 0.0,
        (False, True): 0.0,
        (True, False): 0.0,
        (True, True): 0.0,
    }
    for row, prob in joint.items():
        cells[(row[xi], row[yi])] = cells.get((row[xi], row[yi]), 0.0) + prob
    return cells


def _ancestral_joint_for_verifier(
    graph: nx.DiGraph,
    theta: Theta,
    *,
    x_atom: Atom,
    y_atom: Atom,
    bidirected: frozenset[frozenset[Atom]],
    step_index: int,
    rule: str,
):
    """``(topo, joint)`` over the ancestral subgraph of {X, Y}, or ``None``.

    Kept whole so the two things audited off it — the four ``P(X, Y)`` cells
    and, on the instrument route, the ``P(X, Y | Z)`` table — come from one
    recovery here as they do on the producer's side. Reducing to the cells
    first would leave the table with nothing to be checked against except the
    producer's own copy of it.
    """
    ancestral_nodes = (
        nx.ancestors(graph, x_atom)
        | nx.ancestors(graph, y_atom)
        | {x_atom, y_atom}
    )
    if not ancestral_nodes:
        return None

    subgraph = graph.subgraph(ancestral_nodes).copy()
    topo = tuple(nx.topological_sort(subgraph))
    may_drop_non_parents = not any(
        pair & ancestral_nodes for pair in bidirected
    )
    conditioning = {
        atom: (
            tuple(subgraph.predecessors(atom)) if may_drop_non_parents
            else topo[:i]
        )
        for i, atom in enumerate(topo)
    }
    required_keys = _required_probability_keys_for_ancestral_joint_for_verifier(
        topo=topo,
        theta=theta,
        conditioning=conditioning,
    )
    for key in required_keys:
        if _recover_boolean_theta_value_for_verifier(theta, key) is None:
            return None

    joint: dict[tuple, float] = {}
    for assignment in _ancestral_assignments_for_verifier(topo, theta):
        prob = 1.0
        for atom in topo:
            key = _assignment_probability_key_for_verifier(
                atom, assignment, conditioning[atom],
            )
            value = _recover_boolean_theta_value_for_verifier(theta, key)
            if value is None:
                raise RuleCheckFailed(
                    f"{rule}: missing key survived ancestral precheck",
                    step_index=step_index, rule=rule,
                )
            prob *= value
        row = tuple(assignment[atom] for atom in topo)
        joint[row] = joint.get(row, 0.0) + prob
    return topo, joint


def _recorded_instrument_table_matches_theta(
    graph: nx.DiGraph,
    theta: Theta,
    inputs: dict,
    *,
    bidirected: frozenset[frozenset[Atom]],
    step_index: int,
    rule: str,
    x_atom: Atom,
    y_atom: Atom,
) -> None:
    """The recorded ``P(X, Y | Z)`` must be the one theta implies, stratum for
    stratum, at the levels the step says they are.

    Only this door can ask that: the data end's verifier has the producer's
    table and no second source for it, so the strongest it can do is check
    the table is internally a family of distributions and marginalises to the
    reported joint. Here theta is the second source. That is what makes the
    LEVELS auditable rather than decorative — permuting them leaves an
    internally tidy table that marginalises identically whenever P(Z) is
    symmetric, and the answer it produces is a different one.
    """
    import numpy as np

    instrument = inputs.get("instrument")
    if not isinstance(instrument, str):
        raise RuleCheckFailed(
            f"{rule}: the step claims the instrument route but names no "
            f"instrument",
            step_index=step_index, rule=rule,
        )
    z_atoms = [
        node for node in graph.nodes if node.predicate == instrument
    ]
    if len(z_atoms) != 1:
        raise RuleCheckFailed(
            f"{rule}: {instrument!r} is not one node of this graph",
            step_index=step_index, rule=rule,
        )
    z_atom = z_atoms[0]
    if graph.has_edge(z_atom, y_atom) or not graph.has_edge(z_atom, x_atom):
        raise RuleCheckFailed(
            f"{rule}: {instrument!r} is not an instrument on this graph — the "
            f"route's licence asserts an edge into the treatment and none "
            f"into the outcome",
            step_index=step_index, rule=rule,
        )

    recovered = _ancestral_joint_for_verifier(
        graph, theta, x_atom=x_atom, y_atom=y_atom,
        bidirected=bidirected, step_index=step_index, rule=rule,
    )
    if recovered is None:
        raise RuleCheckFailed(
            f"{rule}: theta does not carry the factors this route's table was "
            f"built from",
            step_index=step_index, rule=rule,
        )
    topo, joint = recovered
    if z_atom not in topo:
        raise RuleCheckFailed(
            f"{rule}: {instrument!r} is not an ancestor of the cell's "
            f"variables, so it cannot have conditioned the table",
            step_index=step_index, rule=rule,
        )
    zi, xi, yi = topo.index(z_atom), topo.index(x_atom), topo.index(y_atom)

    levels = list(inputs.get("instrument_levels") or ())
    P = np.asarray(inputs.get("p_xyz"), dtype=float)
    p_z = np.asarray(inputs.get("p_z"), dtype=float)
    for position, z_value in enumerate(levels):
        mass = sum(p for row, p in joint.items() if row[zi] == z_value)
        if abs(mass - float(p_z[position])) > 1e-6:
            raise RuleCheckFailed(
                f"{rule}: the step reports P(Z={z_value!r}) = "
                f"{float(p_z[position]):.6g}, but theta gives {mass:.6g}",
                step_index=step_index, rule=rule,
            )
        for x_index, x_value in ((0, False), (1, True)):
            for y_index, y_value in ((0, False), (1, True)):
                cell = sum(
                    p for row, p in joint.items()
                    if row[zi] == z_value and row[xi] == x_value
                    and row[yi] == y_value
                )
                expected = cell / mass if mass > 0 else 0.0
                if abs(expected - float(P[position, x_index, y_index])) > 1e-6:
                    raise RuleCheckFailed(
                        f"{rule}: the step reports "
                        f"P(X={x_value}, Y={y_value} | Z={z_value!r}) = "
                        f"{float(P[position, x_index, y_index]):.6g}, but "
                        f"theta gives {expected:.6g}",
                        step_index=step_index, rule=rule,
                    )


def _required_probability_keys_for_ancestral_joint_for_verifier(
    *,
    topo: tuple[Atom, ...],
    theta: Theta,
    conditioning: dict[Atom, tuple[Atom, ...]],
) -> tuple[ProbabilityKey, ...]:
    keys: set[ProbabilityKey] = set()
    for assignment in _ancestral_assignments_for_verifier(topo, theta):
        for atom in topo:
            keys.add(
                _assignment_probability_key_for_verifier(
                    atom, assignment, conditioning[atom],
                )
            )
    return tuple(sorted(keys, key=_probability_key_sort_key_for_verifier))


def _ancestral_assignments_for_verifier(
    topo: tuple[Atom, ...],
    theta: Theta,
) -> Iterator[dict[Atom, AtomValue]]:
    domains = [
        _counterfactual_factorization_domain_for_verifier(theta, atom)
        for atom in topo
    ]
    for values in product(*domains):
        yield dict(zip(topo, values))


def _assignment_probability_key_for_verifier(
    atom: Atom,
    assignment: dict[Atom, AtomValue],
    conditioning: tuple[Atom, ...],
) -> ProbabilityKey:
    return ProbabilityKey(
        target_atom=atom,
        target_value=assignment[atom],
        given=frozenset(
            (given_atom, assignment[given_atom]) for given_atom in conditioning
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
) -> tuple[AtomValue, ...]:
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


def _cf_monotonicity_pins_for_verifier(
    query: CounterfactualQuery,
) -> dict[bool, float]:
    """The verifier's own reading of which cell monotonicity determines.

    Deliberately re-derived here rather than imported from
    ``runtime.counterfactual``: consistency fixes the unit's outcome under
    its OWN treatment, and the monotone order then forces the other world.
    With ``x`` observed and ``y`` factual,

      non-decreasing (Y_0 <= Y_1): x=1 gives Y_1=y, so y=0 forces Y_0=0;
                                   x=0 gives Y_0=y, so y=1 forces Y_1=1.
      non-increasing (Y_1 <= Y_0): x=1 gives Y_1=y, so y=1 forces Y_0=1;
                                   x=0 gives Y_0=y, so y=0 forces Y_1=0.

    Keyed by the factual ``y``, valued by P(Y_{x'}=1 | X=x, Y=y).
    """
    if query.assumptions is None or query.assumptions.monotonicity is None:
        return {}
    x_obs = query.observed.value
    kind = query.assumptions.monotonicity.value
    if kind == "non_decreasing":
        return {False: 0.0} if x_obs else {True: 1.0}
    if kind == "non_increasing":
        return {True: 1.0} if x_obs else {False: 0.0}
    return {}


def _cf_cell_needs_risk_for_verifier(query: CounterfactualQuery) -> bool:
    """Does this cell's value depend on P(Y=1 | do(x')) at all?

    No when both worlds coincide (consistency answers it) or when
    monotonicity pins the requested cell outright. This is what makes a
    producer's ``interventional_risk_provenance = "not_required"`` claim
    auditable rather than self-certifying.
    """
    if query.counterfactual_intervention.value == query.observed.value:
        return False
    factual_y = query.factual_target_known
    if factual_y is None:
        return True
    return factual_y not in _cf_monotonicity_pins_for_verifier(query)


def _require_boolean_cell_coordinate(
    value: object, step_index: int, rule: str,
) -> bool:
    if not isinstance(value, bool):
        raise RuleCheckFailed(
            f"{rule}: current verifier scope is boolean-only",
            step_index=step_index, rule=rule,
        )
    return value


def _counterfactual_cell_coordinates_for_verifier(
    query: CounterfactualQuery, step_index: int, rule: str,
) -> tuple[bool, bool, bool, bool | None]:
    """The cell's coordinates ``(x_obs, x_cf, y_star, factual_y)``.

    The counterfactual cell is indexed by boolean coordinates — the joint
    P(X, Y) it is solved against has exactly four of them — so anything else
    is outside the verifier's scope for this family. The factual outcome is
    the one coordinate that may be absent: it is evidence the query need not
    carry, and the identity has a branch for its absence. Returning the
    checked coordinates is what stops the callers below from reading the
    query again and indexing the joint with whatever they find.
    """
    factual_y = query.factual_target_known
    return (
        _require_boolean_cell_coordinate(query.observed.value, step_index, rule),
        _require_boolean_cell_coordinate(
            query.counterfactual_intervention.value, step_index, rule,
        ),
        _require_boolean_cell_coordinate(
            query.counterfactual_target.value, step_index, rule,
        ),
        None if factual_y is None
        else _require_boolean_cell_coordinate(factual_y, step_index, rule),
    )


def _solve_counterfactual_cell_for_verifier(
    query: CounterfactualQuery,
    joint: dict[tuple[bool, bool], float],
    *,
    p_y_do_x_cf: float | None,
    step_index: int,
    rule: str,
) -> tuple[float, float]:
    """Recompute one binary counterfactual cell, independently of the producer.

    Same theorem, transcribed here from the identity rather than imported:
    with ``a = P(Y_{x'}=1 | X=x, Y=1)`` and ``b = P(Y_{x'}=1 | X=x, Y=0)``,

        a * P(x, Y=1) + b * P(x, Y=0) = P(Y=1 | do(x')) - P(x', Y=1)

    since the left side is P(Y_{x'}=1 | X=x) * P(x) and consistency gives
    P(Y_{x'}=1, X=x') = P(Y=1, X=x'). Solve for the requested cell inside the
    [0, 1] box, tightened by any monotonicity pin on the other one.

    ``joint`` is the four observational cells, whose ORIGIN is the caller's
    business: the theta path recovers them symbolically, the data path reports
    them as empirical frequencies. The identity is the same either way, so it
    is transcribed here once. Returns ``(low, high)``.
    """
    x_obs, x_cf, y_star, factual_y = _counterfactual_cell_coordinates_for_verifier(
        query, step_index, rule,
    )
    p_x_obs = joint[(x_obs, False)] + joint[(x_obs, True)]
    if p_x_obs == 0:
        raise RuleCheckFailed(
            f"{rule}: zero factual mass for observed value",
            step_index=step_index, rule=rule,
        )

    if x_cf == x_obs:
        if factual_y is not None:
            point = 1.0 if factual_y == y_star else 0.0
        else:
            p_y1 = joint[(x_obs, True)] / p_x_obs
            point = p_y1 if y_star else 1.0 - p_y1
        return point, point

    pins = _cf_monotonicity_pins_for_verifier(query)

    if p_y_do_x_cf is None:
        if factual_y is None or factual_y not in pins:
            raise RuleCheckFailed(
                f"{rule}: this cell is not determined without "
                f"P(Y=1|do(X={x_cf})), but the step declares none",
                step_index=step_index, rule=rule,
            )
        pinned = pins[factual_y]
        value = pinned if y_star else 1.0 - pinned
        return value, value

    k = p_y_do_x_cf - joint[(x_cf, True)]
    if not (-_NUMERIC_TOL <= k <= p_x_obs + _NUMERIC_TOL):
        raise RuleCheckFailed(
            f"{rule}: P(Y=1|do(X={x_cf}))={p_y_do_x_cf} contradicts the "
            f"theta-recovered observational joint via consistency",
            step_index=step_index, rule=rule,
        )

    if factual_y is None:
        point = min(1.0, max(0.0, k / p_x_obs))
        value = point if y_star else 1.0 - point
        return value, value

    w_target = joint[(x_obs, factual_y)]
    w_other = joint[(x_obs, not factual_y)]
    lo_other = pins.get(not factual_y, 0.0)
    hi_other = pins.get(not factual_y, 1.0)
    low = pins.get(factual_y, 0.0)
    high = pins.get(factual_y, 1.0)
    if w_target > 0.0:
        low = max(low, (k - hi_other * w_other) / w_target)
        high = min(high, (k - lo_other * w_other) / w_target)
    # Emptiness first, clamping second — the other order silently folds an
    # empty feasible set onto the boundary and certifies a confident 0 or 1.
    if low > high + _NUMERIC_TOL:
        raise RuleCheckFailed(
            f"{rule}: no distribution satisfies the observational joint, "
            f"P(Y=1|do(X={x_cf}))={p_y_do_x_cf} and the declared "
            f"monotonicity at once",
            step_index=step_index, rule=rule,
        )
    low = min(1.0, max(0.0, low))
    high = min(1.0, max(0.0, high))
    high = max(high, low)

    if y_star:
        return low, high
    return 1.0 - high, 1.0 - low


def _expected_counterfactual_numeric_result(
    graph: nx.DiGraph,
    query: CounterfactualQuery,
    theta: Theta,
    *,
    bidirected: frozenset[frozenset[Atom]] = frozenset(),
    p_y_do_x_cf: float | None,
    step_index: int,
    rule: str,
) -> NumericResult:
    """Theta entry point: recover the observational joint symbolically, then
    solve the cell with the verifier's own transcription of the identity."""
    _counterfactual_cell_coordinates_for_verifier(query, step_index, rule)
    joint = _counterfactual_joint_xy_for_verifier(
        graph,
        theta,
        query,
        bidirected=bidirected,
        step_index=step_index,
        rule=rule,
    )
    low, high = _solve_counterfactual_cell_for_verifier(
        query, joint, p_y_do_x_cf=p_y_do_x_cf, step_index=step_index, rule=rule,
    )
    if abs(low - high) <= _NUMERIC_TOL:
        return NumericResult(value=low)
    return NumericResult(value=None, interval=NumericInterval(low=low, high=high))


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


def _rule_counterfactual_cell_bounds(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Independent audit of one binary counterfactual cell.

    Three re-checks, each catching a distinct producer bug:

    1. The observational joint is recovered from ``ctx.theta`` again by the
       verifier (ancestral BN factorization, local chain-rule fallback) and
       the cell is re-solved from the consistency identity — catches a
       mis-wired joint or a mis-applied formula.
    2. The declared ``interventional_risk_provenance`` must agree with
       whether the cell actually depends on P(Y=1|do(x')). A step claiming
       ``not_required`` while carrying a risk, or carrying none while the
       cell needs one, is refused — otherwise "not required" would be a
       self-certifying claim.
    3. The declared risk must be a probability and must not contradict the
       theta-recovered joint (nor, with monotonicity declared, leave an
       empty feasible set).

    Scope boundary, mirroring the causation rule: when the risk came from
    ``derived_identification`` it was produced by the effect-identification
    subsystem, which has its own independent verifier. This rule audits the
    joint recovery, the identity, and internal consistency; it does not
    re-run that cascade.
    """
    rule = "counterfactual_cell_bounds"
    graph = _require(inputs, "graph", step_index, rule)
    _assert_same_graph(graph, ctx.graph, step_index, rule)
    if not isinstance(ctx.query, CounterfactualQuery):
        raise RuleCheckFailed(
            f"{rule} requires CounterfactualQuery context",
            step_index=step_index, rule=rule,
        )
    if ctx.theta is None:
        raise RuleCheckFailed(
            f"{rule} requires theta in context",
            step_index=step_index, rule=rule,
        )
    if not isinstance(claimed_output, NumericResult):
        raise RuleCheckFailed(
            f"{rule} output must be NumericResult",
            step_index=step_index, rule=rule,
        )

    provenance = _check_risk_provenance(
        inputs, ctx, ctx.query.counterfactual_intervention.value,
        step_index=step_index, rule=rule,
    )

    raw_risk = inputs.get("p_y_do_x_cf")
    risk = None if raw_risk is None else float(raw_risk)
    if risk is not None and not (0.0 <= risk <= 1.0):
        raise RuleCheckFailed(
            f"{rule}: p_y_do_x_cf={risk} is not a probability in [0, 1]",
            step_index=step_index, rule=rule,
        )
    if (provenance in _RISK_FREE) != (risk is None):
        raise RuleCheckFailed(
            f"{rule}: provenance {provenance!r} disagrees with the presence "
            f"of p_y_do_x_cf",
            step_index=step_index, rule=rule,
        )
    if provenance == "instrument_response_polytope":
        # A different program, so a different recomputation. The consistency
        # identity is not it: that route consumes a risk this one declares it
        # could not obtain, and running it here would audit the answer against
        # a theorem the producer did not use.
        joint = _counterfactual_joint_xy_for_verifier(
            ctx.graph, ctx.theta, ctx.query,
            bidirected=ctx.bidirected, step_index=step_index, rule=rule,
        )
        _recorded_instrument_table_matches_theta(
            ctx.graph, ctx.theta, inputs,
            bidirected=ctx.bidirected, step_index=step_index, rule=rule,
            x_atom=ctx.query.observed.atom,
            y_atom=ctx.query.counterfactual_target.atom,
        )
        low, high = _rederive_cell_over_response_polytope(
            ctx, inputs, ctx.query, joint,
            step_index=step_index, rule=rule,
        )
        expected = NumericResult(
            value=low if low == high else None,
            interval=(
                None if low == high else NumericInterval(low=low, high=high)
            ),
        )
    else:
        if risk is None and _cf_cell_needs_risk_for_verifier(ctx.query):
            raise RuleCheckFailed(
                f"{rule}: the step declares no interventional risk, but "
                f"neither consistency nor the declared monotonicity "
                f"determines this cell",
                step_index=step_index, rule=rule,
            )
        expected = _expected_counterfactual_numeric_result(
            ctx.graph,
            ctx.query,
            ctx.theta,
            bidirected=ctx.bidirected,
            p_y_do_x_cf=risk,
            step_index=step_index,
            rule=rule,
        )
    if not _numeric_result_matches(claimed_output, expected):
        raise RuleCheckFailed(
            f"{rule} claimed output does not match the recomputed cell",
            step_index=step_index, rule=rule,
        )


_NUMERIC_COUNTERFACTUAL_CELL_METHODS = frozenset({"counterfactual_cell_plugin"})

_RISK_PROVENANCES_BY_RULE: dict[str, frozenset[str]] = {
    "causation_probability_bounds": frozenset({
        "derived_identification", "instrument_response_polytope",
        "user_experimental",
    }),
    "numeric_causation_estimate": frozenset({
        "exogenous", "backdoor_adjustment", "general_id_plug_in",
        "instrument_response_polytope", "user_experimental",
    }),
    "counterfactual_cell_bounds": frozenset({
        "not_required", "instrument_response_polytope",
        "derived_identification", "user_experimental",
    }),
    "numeric_counterfactual_cell_estimate": frozenset({
        "not_required", "pinned_by_monotonicity",
        "instrument_response_polytope",
        "user_experimental", "exogenous", "backdoor_adjustment",
        "general_id_plug_in",
    }),
}
"""Which risk licences each rule here will accept, re-declared.

The producer's copy is not imported: re-deriving an answer from the
vocabulary the producer chose is not an independent check. A test pins the
two equal, which is how this package catches drift everywhere else it
deliberately re-implements something.

Keyed by rule, because the admissible set depends on the rule and on
nothing else — the rule fixes both how many arms the answer needs and
whether they came from theta or from data.
"""

_RISK_FREE = frozenset({
    "not_required", "pinned_by_monotonicity", "instrument_response_polytope",
})
"""The licences that claim no interventional risk was used at all.

Two of them say the cell never needed one. The third says one was needed and
could not be point-identified, and that the answer went around it — which is a
different claim and is checked differently below, but reaches this set by the
same road: nothing on the producer's side may report a risk beside it."""


def _check_risk_provenance(
    inputs: dict, ctx: VerificationContext, arm: AtomValue | None,
    *, step_index: int, rule: str,
) -> str:
    """The licence, re-derived rather than read.

    Membership first, because a rule that accepts a licence it can never
    produce has no branch that checks it. Then the one claim every rule
    shares: ``user_experimental`` says the CALLER supplied the arm, and
    the query is where that is recorded, so the verifier can settle it
    without the producer. It was checked nowhere, and it is the value that
    switches off the identification re-check in three of the four rules —
    so relabelling a back-door-standardized estimate as experimental made
    its adjustment set stop being audited.

    ``arm`` is the intervened value whose risk this answer used, or None
    when the rule uses both arms.
    """
    provenance = _require(inputs, "interventional_risk_provenance", step_index, rule)
    if provenance not in _RISK_PROVENANCES_BY_RULE[rule]:
        raise RuleCheckFailed(
            f"{rule}: unknown interventional_risk_provenance {provenance!r}; "
            f"this rule may carry "
            f"{sorted(_RISK_PROVENANCES_BY_RULE[rule])}",
            step_index=step_index, rule=rule,
        )

    query = ctx.query
    if arm is None:
        supplied = (
            getattr(query, "experimental_risk_treated", None) is not None
            and getattr(query, "experimental_risk_control", None) is not None
        )
    elif arm:
        supplied = getattr(query, "experimental_risk_treated", None) is not None
    else:
        supplied = getattr(query, "experimental_risk_control", None) is not None

    if provenance == "user_experimental":
        if not supplied:
            raise RuleCheckFailed(
                f"{rule}: provenance 'user_experimental' claims the caller "
                f"supplied the interventional risk, but the query carries "
                f"none",
                step_index=step_index, rule=rule,
            )
    elif provenance not in _RISK_FREE and supplied:
        # An answer that used an arm, while the caller had handed one over,
        # cannot have got it from the graph: every producer takes the
        # supplied arm first. Only the risk-free licences are exempt, and
        # they are exempt because they read no arm at all — a same-world
        # cell is answered by consistency whatever the caller also sent.
        raise RuleCheckFailed(
            f"{rule}: provenance {provenance!r} claims the risk was obtained "
            f"from the graph, but the query carries the experimental arm this "
            f"answer would have used",
            step_index=step_index, rule=rule,
        )
    return provenance


def _rule_numeric_counterfactual_cell_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Independent audit of a data-based binary counterfactual cell.

    The numeric counterpart of ``counterfactual_cell_bounds``: the identity is
    the same, but the observational joint and the interventional risk are now
    EMPIRICAL, so the theta-recovery leg does not apply and the reported inputs
    take its place. Four independent re-checks:

    1. Identity re-application — the reported ``lower``/``upper``/``point``
       must equal the verifier's own solution of the consistency identity on
       the reported joint + risk. The CELL COORDINATES are read off
       ``ctx.query``, never off the step inputs, so a producer cannot quietly
       answer an easier cell than the one that was asked.
    2. Risk provenance — every value of ``interventional_risk_provenance``
       makes a checkable claim, and the two that mean "no risk was used" make
       the strongest one. ``not_required`` asserts the two worlds coincide;
       ``pinned_by_monotonicity`` asserts the declared monotonicity determines
       this cell outright. Both are re-derived from ``ctx.query`` here, so
       neither can certify itself.
    3. Identification structure — when the risk was back-door standardized (or
       exogenous), the claimed adjustment set is re-derived from ``ctx.graph``
       and must be genuinely admissible; catches standardizing over a WRONG
       set. When it was identified by the general ID algorithm instead, the
       estimand itself is re-derived for the arm ``ctx.query`` asks about and
       must match the one recorded; catches evaluating the WRONG estimand.
    4. Metadata self-consistency — method enum, data_hash hex, sample_size,
       probabilities in range, and a CI that brackets the point (or is a valid
       probability interval when the answer is an interval).

    Like the other numeric verifiers this does not re-fit on the raw data (the
    verifier holds only the ``data_hash``); the arithmetic, the cell identity
    and the graph licence are what it re-derives.
    """
    from ..runtime import structural_solver

    rule = "numeric_counterfactual_cell_estimate"
    if not isinstance(ctx.query, CounterfactualQuery):
        raise RuleCheckFailed(
            f"{rule} requires a CounterfactualQuery context",
            step_index=step_index, rule=rule,
        )
    query = ctx.query
    x_obs, x_cf, _y_star, factual_y = _counterfactual_cell_coordinates_for_verifier(
        query, step_index, rule,
    )

    method = inputs.get("method")
    if method not in _NUMERIC_COUNTERFACTUAL_CELL_METHODS:
        raise RuleCheckFailed(
            f"{rule}.method must be one of "
            f"{sorted(_NUMERIC_COUNTERFACTUAL_CELL_METHODS)}; got {method!r}",
            step_index=step_index, rule=rule,
        )
    data_hash = inputs.get("data_hash")
    if not isinstance(data_hash, str) or len(data_hash) != _SHA256_HEX_LEN:
        raise RuleCheckFailed(
            f"{rule}.data_hash must be a {_SHA256_HEX_LEN}-char SHA-256 hex string",
            step_index=step_index, rule=rule,
        )
    if not all(c in "0123456789abcdef" for c in data_hash):
        raise RuleCheckFailed(
            f"{rule}.data_hash must be lowercase hex",
            step_index=step_index, rule=rule,
        )
    sample_size = inputs.get("sample_size")
    if (
        not isinstance(sample_size, int)
        or isinstance(sample_size, bool)
        or sample_size < _MIN_NUMERIC_SAMPLE_SIZE
    ):
        raise RuleCheckFailed(
            f"{rule}.sample_size must be an int >= {_MIN_NUMERIC_SAMPLE_SIZE}; "
            f"got {sample_size!r}",
            step_index=step_index, rule=rule,
        )

    cells = {
        "p_x1_y1": float(_require(inputs, "p_x1_y1", step_index, rule)),
        "p_x1_y0": float(_require(inputs, "p_x1_y0", step_index, rule)),
        "p_x0_y1": float(_require(inputs, "p_x0_y1", step_index, rule)),
        "p_x0_y0": float(_require(inputs, "p_x0_y0", step_index, rule)),
    }
    if abs(sum(cells.values()) - 1.0) > 1e-6:
        raise RuleCheckFailed(
            f"{rule}: the four observational cells must sum to 1; "
            f"got {sum(cells.values()):.6g}",
            step_index=step_index, rule=rule,
        )
    if any(v < 0.0 or v > 1.0 for v in cells.values()):
        raise RuleCheckFailed(
            f"{rule}: the observational cells must all be probabilities",
            step_index=step_index, rule=rule,
        )
    joint = {
        (True, True): cells["p_x1_y1"], (True, False): cells["p_x1_y0"],
        (False, True): cells["p_x0_y1"], (False, False): cells["p_x0_y0"],
    }

    # 2. Provenance. Each value makes a claim about WHY the reported risk is
    #    present or absent, and every one of those claims is re-derived from
    #    the query rather than taken on the producer's word.
    provenance = _check_risk_provenance(
        inputs, ctx, x_cf, step_index=step_index, rule=rule,
    )
    raw_risk = inputs.get("p_y_do_x_cf")
    risk = None if raw_risk is None else float(raw_risk)
    if risk is not None and not (0.0 <= risk <= 1.0):
        raise RuleCheckFailed(
            f"{rule}: p_y_do_x_cf={risk} is not a probability in [0, 1]",
            step_index=step_index, rule=rule,
        )
    risk_free = provenance in _RISK_FREE
    if risk_free != (risk is None):
        raise RuleCheckFailed(
            f"{rule}: provenance {provenance!r} disagrees with the presence "
            f"of p_y_do_x_cf",
            step_index=step_index, rule=rule,
        )
    same_world = x_cf == x_obs
    if provenance == "not_required" and not same_world:
        raise RuleCheckFailed(
            f"{rule}: provenance 'not_required' claims the two worlds "
            f"coincide, but do(X={x_cf}) "
            f"differs from the observed X={x_obs}",
            step_index=step_index, rule=rule,
        )
    if provenance == "pinned_by_monotonicity":
        pins = _cf_monotonicity_pins_for_verifier(query)
        if same_world or factual_y is None or factual_y not in pins:
            raise RuleCheckFailed(
                f"{rule}: provenance 'pinned_by_monotonicity' claims the "
                f"declared monotonicity determines this cell outright, but it "
                f"does not",
                step_index=step_index, rule=rule,
            )
    if not risk_free and same_world:
        raise RuleCheckFailed(
            f"{rule}: an interventional risk is reported for a cell whose two "
            f"worlds coincide — consistency answers it and the risk is not an "
            f"input to the answer",
            step_index=step_index, rule=rule,
        )

    # 1. Re-derivation on the reported empirical inputs — by whichever solver
    #    the licence says ran. The identity has no answer for the instrument
    #    route (it would demand the very risk that route exists because nobody
    #    has), so choosing here is not a shortcut: it is the same question
    #    asked of the same producer through the program it actually solved.
    if provenance == "instrument_response_polytope":
        exp_low, exp_high = _rederive_cell_over_response_polytope(
            ctx, inputs, query, joint, step_index=step_index, rule=rule,
        )
    else:
        exp_low, exp_high = _solve_counterfactual_cell_for_verifier(
            query, joint, p_y_do_x_cf=risk, step_index=step_index, rule=rule,
        )
    reported_low = float(_require(inputs, "lower", step_index, rule))
    reported_high = float(_require(inputs, "upper", step_index, rule))
    for label, reported_v, expected_v in (
        ("lower", reported_low, exp_low),
        ("upper", reported_high, exp_high),
    ):
        if abs(reported_v - expected_v) > 1e-9:
            raise RuleCheckFailed(
                f"{rule}: {label} {reported_v} does not match the "
                f"independently re-solved cell value {expected_v}",
                step_index=step_index, rule=rule,
            )
    reported_point = inputs.get("point")
    collapsed = abs(exp_high - exp_low) <= 1e-9
    if collapsed:
        if reported_point is None or abs(float(reported_point) - exp_low) > 1e-9:
            raise RuleCheckFailed(
                f"{rule}: the identified set collapses to {exp_low}, but the "
                f"estimate reports point={reported_point!r}",
                step_index=step_index, rule=rule,
            )
    elif reported_point is not None:
        raise RuleCheckFailed(
            f"{rule}: point {reported_point} claimed, but the identified set "
            f"[{exp_low}, {exp_high}] does not collapse",
            step_index=step_index, rule=rule,
        )

    # 3. Identification-structure re-check (skip for external experiments and
    #    for the cells that consume no risk at all).
    adjustment_str = _require(inputs, "adjustment", step_index, rule)
    if provenance in ("backdoor_adjustment", "exogenous"):
        sets = structural_solver.minimal_adjustment_sets(
            ctx.graph,
            query.observed.atom,
            query.counterfactual_target.atom,
            bidirected=(ctx.bidirected or None),
        )
        if not sets:
            raise RuleCheckFailed(
                f"{rule}: no admissible back-door adjustment set exists on the "
                "graph, yet the estimate claims a data-identified do-risk",
                step_index=step_index, rule=rule,
            )
        claimed = frozenset(p for p in str(adjustment_str).split(",") if p)
        admissible = {frozenset(a.predicate for a in s) for s in sets}
        if claimed not in admissible:
            raise RuleCheckFailed(
                f"{rule}: claimed adjustment set {sorted(claimed)} is not an "
                f"admissible minimal back-door set on the graph",
                step_index=step_index, rule=rule,
            )
    else:
        if str(adjustment_str):
            raise RuleCheckFailed(
                f"{rule}: provenance {provenance!r} standardizes over nothing, "
                f"yet an adjustment set {str(adjustment_str)!r} is claimed",
                step_index=step_index, rule=rule,
            )
        if provenance == "general_id_plug_in":
            _check_cf_cell_general_id_risk(
                ctx, inputs, query, step_index=step_index, rule=rule,
            )
        elif provenance == "instrument_response_polytope":
            _check_cf_cell_instrument(
                ctx, inputs, query, step_index=step_index, rule=rule,
            )

    # 4. CI (present only when a bootstrap ran). A point must sit inside its
    #    percentile CI; the interval answer's OUTER band is a bootstrap
    #    artifact (not re-derivable from a data_hash) so it is checked only for
    #    validity as a probability interval.
    ci_lower = inputs.get("ci_lower")
    ci_upper = inputs.get("ci_upper")
    if ci_lower is not None or ci_upper is not None:
        if ci_lower is None or ci_upper is None:
            raise RuleCheckFailed(
                f"{rule}: ci_lower and ci_upper must both be present or absent",
                step_index=step_index, rule=rule,
            )
        _check_ci_width(inputs, pinned=reported_point is not None,
                        step_index=step_index, rule=rule)
        if reported_point is not None:
            if not (ci_lower <= float(reported_point) <= ci_upper):
                raise RuleCheckFailed(
                    f"{rule}: point {reported_point} outside CI "
                    f"[{ci_lower}, {ci_upper}]",
                    step_index=step_index, rule=rule,
                )
        elif not (0.0 <= ci_lower <= ci_upper <= 1.0):
            raise RuleCheckFailed(
                f"{rule}: outer band [{ci_lower}, {ci_upper}] is not a valid "
                "probability interval",
                step_index=step_index, rule=rule,
            )

    if not isinstance(claimed_output, StructuralResult):
        raise RuleCheckFailed(
            f"{rule} output must be a StructuralResult",
            step_index=step_index, rule=rule,
        )
    if claimed_output.value is not True:
        raise RuleCheckFailed(
            f"{rule} output.value must be True",
            step_index=step_index, rule=rule,
        )


def _check_cf_cell_instrument(
    ctx: VerificationContext,
    inputs: dict,
    query,
    *,
    step_index: int,
    rule: str,
) -> None:
    """Re-derive, from ``ctx.graph`` alone, that the claimed column IS an
    instrument for this treatment and outcome.

    Pearl's criterion transcribed here rather than imported: an instrument is
    m-separated from the outcome once the treatment's outgoing edges are cut,
    and has an edge into the treatment. A producer that named a covariate, a
    mediator, or a second confounder as its instrument would otherwise be
    audited only on arithmetic it did consistently — and the arithmetic is
    correct for whichever column it fed in.

    Uniqueness is re-derived too. Two valid instruments carry more information
    than either alone, so a producer reporting one of them has bounded the
    right quantity from less than the graph offered; the verifier rejects it
    rather than confirming a claim about a narrower model.
    """
    from ..runtime import structural_solver

    import networkx as nx

    claimed = inputs.get("instrument")
    if not isinstance(claimed, str) or not claimed:
        raise RuleCheckFailed(
            f"{rule}: provenance 'instrument_response_polytope' names no "
            f"instrument column; got {claimed!r}",
            step_index=step_index, rule=rule,
        )
    treatment = query.observed.atom
    outcome = query.counterfactual_target.atom
    cut = nx.DiGraph()
    cut.add_nodes_from(ctx.graph.nodes())
    cut.add_edges_from(
        (u, v) for u, v in ctx.graph.edges() if u != treatment
    )
    bid = ctx.bidirected or frozenset()
    valid = [
        z for z in ctx.graph.predecessors(treatment)
        if z != outcome
        and structural_solver.m_separated(cut, bid, z, outcome, ())
    ]
    if len(valid) != 1 or valid[0].predicate != claimed:
        raise RuleCheckFailed(
            f"{rule}: {claimed!r} is not the instrument this graph declares "
            f"for {treatment.predicate} → {outcome.predicate}; re-deriving it "
            f"gives {sorted(z.predicate for z in valid)}",
            step_index=step_index, rule=rule,
        )


def _rederive_cell_over_response_polytope(
    ctx: VerificationContext,
    inputs: dict,
    query,
    joint: dict,
    *,
    step_index: int,
    rule: str,
) -> tuple[float, float]:
    """Re-solve the counterfactual cell over the recorded ``P(X, Y | Z)``.

    The producer records the table its polytope was fitted to, together with
    the instrument levels that say what the table's first axis means. This
    re-runs the verifier's OWN transcription of the response-function LP on it
    against an independently written objective, and reads the cell's
    coordinates and its declared monotonicity off ``ctx.query`` — never off
    the step, so a producer cannot answer an easier cell, or quietly drop the
    assumption that narrowed it, and have the arithmetic still agree.

    The table is also checked to marginalise to the reported observational
    joint. A forged interval now needs a forged table that is a valid family
    of conditional distributions AND reproduces the four cells the identity
    route is audited on — the two halves of the envelope have to agree with
    each other, not merely be internally tidy.
    """
    from .bounds_rules import _verifier_response_lp

    P, p_z, nz = _verifier_recorded_iv_table(
        inputs, joint, step_index=step_index, rule=rule,
    )

    x_obs = int(bool(query.observed.value))
    x_cf = int(bool(query.counterfactual_intervention.value))
    y_star = int(bool(query.counterfactual_target.value))
    factual_y = query.factual_target_known
    y_fact = None if factual_y is None else int(bool(factual_y))

    # gy is indexed by treatment position; the four outcome-response maps are
    # (gy[0], gy[1]). A declared monotonicity is the claim that no unit's
    # outcome moves against the treatment, so it deletes one of them.
    gys = [(a, b) for a in (0, 1) for b in (0, 1)]
    monotonicity = (
        None if query.assumptions is None else query.assumptions.monotonicity
    )
    keep = [True] * len(gys)
    if monotonicity is not None:
        direction = getattr(monotonicity, "value", monotonicity)
        if direction not in ("non_decreasing", "non_increasing"):
            raise RuleCheckFailed(
                f"{rule}: unknown monotonicity {direction!r} on the query",
                step_index=step_index, rule=rule,
            )
        keep = [
            (gy[0] <= gy[1]) if direction == "non_decreasing"
            else (gy[0] >= gy[1])
            for gy in gys
        ]

    fxs = [f for f in _instrument_response_maps(nz)]
    objective = []
    for fx in fxs:
        for j, gy in enumerate(gys):
            hits = (
                keep[j]
                and gy[x_cf] == y_star
                and (y_fact is None or gy[x_obs] == y_fact)
            )
            weight = sum(p_z[z] for z in range(nz) if fx[z] == x_obs)
            objective.append(float(weight) if hits else 0.0)
    denominator = float(sum(
        p_z[z] * (P[z, x_obs, y_fact] if y_fact is not None
                  else P[z, x_obs, :].sum())
        for z in range(nz)
    ))
    # Forbidding a response type is the statement that no unit is of it, which
    # the LP reads as a zero column; the transcription below zeroes the
    # objective AND the mass, so a type the assumption excludes cannot appear
    # in a feasible solution at all.
    low, high = _verifier_response_lp(
        P, 2, 2, nz, objective, rule,
        forbidden=[
            i * len(gys) + j
            for i in range(len(fxs)) for j in range(len(gys)) if not keep[j]
        ],
    )
    if denominator <= 0.0:
        return 0.0, 1.0
    return (
        min(max(low / denominator, 0.0), 1.0),
        min(max(high / denominator, 0.0), 1.0),
    )


def _instrument_response_maps(nz: int):
    """Every ``z → x`` map for a binary treatment and ``nz`` instrument
    levels, as tuples indexed by level position."""
    import itertools

    return list(itertools.product((0, 1), repeat=nz))


def _verifier_recorded_iv_table(
    inputs: dict, joint: dict, *, step_index: int, rule: str,
):
    """The recorded ``P(X, Y | Z)`` table, checked before anything is read off it.

    Shared by the two rules that re-solve a response-function program, because
    what makes a recorded table usable is a property of the table: it has to be
    a family of conditional distributions over (X, Y), its ``p_z`` has to be a
    distribution over the same levels, and it has to MARGINALISE to the four
    observational cells the same envelope reports elsewhere. That last one is
    what makes forgery expensive — the two halves of the envelope have to agree
    with each other, not merely each be internally tidy.

    Sharing it costs no independence: this is the verifier's own transcription
    either way, and nothing here is imported from the producer.
    """
    import numpy as np

    raw = inputs.get("p_xyz")
    p_z_raw = inputs.get("p_z")
    levels = inputs.get("instrument_levels")
    try:
        P = np.asarray(raw, dtype=float)
        p_z = np.asarray(p_z_raw, dtype=float)
    except (TypeError, ValueError):
        raise RuleCheckFailed(
            f"{rule}: p_xyz / p_z must be numeric arrays; got "
            f"{raw!r} / {p_z_raw!r}",
            step_index=step_index, rule=rule,
        )
    if P.ndim != 3 or P.shape[0] < 2 or P.shape[1:] != (2, 2):
        raise RuleCheckFailed(
            f"{rule}: p_xyz must be a |Z|x2x2 table with at least two "
            f"instrument levels; got shape {P.shape}",
            step_index=step_index, rule=rule,
        )
    nz = int(P.shape[0])
    if p_z.shape != (nz,) or not isinstance(levels, (list, tuple)) or len(levels) != nz:
        raise RuleCheckFailed(
            f"{rule}: p_z and instrument_levels must each carry the {nz} "
            f"levels the recorded p_xyz has",
            step_index=step_index, rule=rule,
        )
    if abs(float(p_z.sum()) - 1.0) > 1e-6 or np.any(p_z < -1e-9):
        raise RuleCheckFailed(
            f"{rule}: p_z is not a distribution over the instrument's levels",
            step_index=step_index, rule=rule,
        )
    for z in range(nz):
        if abs(float(P[z].sum()) - 1.0) > 1e-6 or np.any(P[z] < -1e-9):
            raise RuleCheckFailed(
                f"{rule}: p_xyz[Z={z}] is not a conditional distribution "
                f"over (X, Y)",
                step_index=step_index, rule=rule,
            )
    for xi, xv in ((0, False), (1, True)):
        for yi, yv in ((0, False), (1, True)):
            marginal = float(sum(p_z[z] * P[z, xi, yi] for z in range(nz)))
            if abs(marginal - joint[(xv, yv)]) > 1e-6:
                raise RuleCheckFailed(
                    f"{rule}: the recorded p_xyz marginalises to "
                    f"P(X={xv}, Y={yv}) = {marginal:.6g}, but the same "
                    f"envelope reports {joint[(xv, yv)]:.6g}",
                    step_index=step_index, rule=rule,
                )
    return P, p_z, nz


def _rederive_causation_over_response_polytope(
    ctx: VerificationContext,
    inputs: dict,
    cells: dict,
    monotonic: bool,
    *,
    step_index: int,
    rule: str,
) -> dict:
    """Re-solve PN / PS / PNS over the recorded ``P(X, Y | Z)``.

    Three objectives on one polytope. All three select the same
    outcome-response map — the unit whose outcome follows the treatment,
    ``gy = (0, 1)`` — because that is what a probability of causation is about;
    they differ in the factual population, which is a weight on the TREATMENT
    map and a denominator. PN asks among the treated who responded, PS among
    the untreated who did not, and PNS asks about the whole population, so it
    carries no weight and divides by nothing.

    ``monotonic`` is read off the STEP rather than the query, unlike the
    counterfactual cell's coordinates: on a causation query the flag IS a field
    of the query, and it is compared against it above by the metadata leg —
    here what matters is that the same flag the answer claims is the one the
    program ran under.
    """
    from .bounds_rules import _verifier_response_lp

    joint = {
        (True, True): cells["p_x1_y1"], (True, False): cells["p_x1_y0"],
        (False, True): cells["p_x0_y1"], (False, False): cells["p_x0_y0"],
    }
    P, p_z, nz = _verifier_recorded_iv_table(
        inputs, joint, step_index=step_index, rule=rule,
    )
    if bool(inputs.get("monotonic")) != monotonic:
        raise RuleCheckFailed(
            f"{rule}: the monotonicity the program ran under is not the one "
            f"the answer claims",
            step_index=step_index, rule=rule,
        )

    # gy is indexed by treatment position; the four outcome-response maps are
    # (gy[0], gy[1]). Monotonicity — X never prevents Y — is the claim that no
    # unit's outcome moves against the treatment, so it deletes (1, 0).
    gys = [(a, b) for a in (0, 1) for b in (0, 1)]
    keep = [True] * len(gys) if not monotonic else [
        gy[0] <= gy[1] for gy in gys
    ]
    fxs = _instrument_response_maps(nz)
    forbidden = [
        i * len(gys) + j
        for i in range(len(fxs)) for j in range(len(gys)) if not keep[j]
    ]

    out: dict[str, tuple] = {}
    for name, factual_arm in (("pn", 1), ("ps", 0), ("pns", None)):
        objective = []
        for fx in fxs:
            for j, gy in enumerate(gys):
                hits = keep[j] and gy[0] == 0 and gy[1] == 1
                weight = (
                    1.0 if factual_arm is None
                    else sum(p_z[z] for z in range(nz) if fx[z] == factual_arm)
                )
                objective.append(float(weight) if hits else 0.0)
        denominator = (
            1.0 if factual_arm is None
            # The factual outcome at the conditioning arm is the value that arm
            # takes on the selected map: Y=1 among the treated, Y=0 among the
            # untreated. Reading it off the map rather than writing it twice is
            # what keeps the numerator and the denominator the same question.
            else float(sum(
                p_z[z] * P[z, factual_arm, (0, 1)[factual_arm]]
                for z in range(nz)
            ))
        )
        low, high = _verifier_response_lp(
            P, 2, 2, nz, objective, rule, forbidden=forbidden,
        )
        if denominator <= 0.0:
            lo, hi = 0.0, 1.0
        else:
            lo = min(max(low / denominator, 0.0), 1.0)
            hi = min(max(high / denominator, 0.0), 1.0)
        out[name] = (lo, hi, lo if abs(hi - lo) <= 1e-9 else None)
    return out


def _check_causation_general_id_risks(
    ctx: VerificationContext,
    inputs: dict,
    x_atom,
    y_atom,
    *,
    step_index: int,
    rule: str,
) -> None:
    """Re-derive the general-ID estimand behind EACH of the two do-risks.

    Both arms, separately. The ID algorithm is asked per arm and PN/PS/PNS
    consume both, so identifying one arm and evaluating it twice would produce
    an answer that looks exactly like this one — which is the failure a
    per-arm re-derivation exists to catch.

    Like the back-door branch this is an identification audit, not a re-fit:
    the verifier holds a ``data_hash``, not the frame, so the plug-in VALUE is
    beyond reach here (the data-refit ceiling every numeric rule declares).
    What it pins down is that each number was read off the right estimand.
    """
    from ..runtime import c_factor

    bidir = ctx.bidirected
    for arm, key in ((True, "risk_formula_treated"), (False, "risk_formula_control")):
        claimed = inputs.get(key)
        if claimed is None:
            raise RuleCheckFailed(
                f"{rule}: provenance 'general_id_plug_in' claims the "
                f"do-risks came from identified estimands, but the arm "
                f"X={arm} carries none",
                step_index=step_index, rule=rule,
            )
        res = c_factor.identify_via_tian(ctx.graph, bidir, x_atom, y_atom, arm)
        if not res.identifiable or res.formula is None:
            raise RuleCheckFailed(
                f"{rule}: the general ID algorithm does not point-identify "
                f"P({y_atom.predicate}=1 | do({x_atom.predicate}={arm})) on "
                f"this graph, yet the estimate reports an estimand for it",
                step_index=step_index, rule=rule,
            )
        # Both risks are P(Y=1 | do(X=arm)) — the HIGH outcome level, whatever
        # each of the three quantities goes on to ask about.
        expected = _verifier_bind_target_value(res.formula, y_atom, True)
        if claimed != expected:
            raise RuleCheckFailed(
                f"{rule}: the recorded estimand for the X={arm} arm is not "
                f"the one the ID algorithm derives for it",
                step_index=step_index, rule=rule,
            )


def _check_cf_cell_general_id_risk(
    ctx: VerificationContext,
    inputs: dict,
    query,
    *,
    step_index: int,
    rule: str,
) -> None:
    """Re-derive the general-ID estimand a counterfactual cell's risk came from.

    ``general_id_plug_in`` says two things: that no covariate set identifies the
    arm, and that the ID algorithm identifies it anyway. Both are re-checked
    against ``ctx.graph`` — and, crucially, so is WHICH arm was evaluated. The
    do-value is read off ``ctx.query`` (the counterfactual intervention), so a
    producer that identified the easier arm, or bound the outcome to the other
    level, does not match the verifier's own re-derivation and is rejected.

    Like the back-door branch this is an identification audit, not a re-fit: the
    verifier holds a ``data_hash``, not the frame, so the plug-in VALUE the
    estimand evaluates to is beyond reach here (the same data-refit ceiling
    every numeric rule declares). What it does pin down is that the number was
    read off the right estimand.
    """
    from ..runtime import c_factor, structural_solver

    bidir = ctx.bidirected
    x_atom = query.observed.atom
    y_atom = query.counterfactual_target.atom
    sets = structural_solver.minimal_adjustment_sets(
        ctx.graph, x_atom, y_atom, bidirected=(ctx.bidirected or None),
    )
    if sets:
        raise RuleCheckFailed(
            f"{rule}: provenance 'general_id_plug_in' claims no covariate set "
            f"identifies the do-risk, but the graph admits back-door "
            f"adjustment sets",
            step_index=step_index, rule=rule,
        )
    res = c_factor.identify_via_tian(
        ctx.graph, bidir, x_atom, y_atom,
        query.counterfactual_intervention.value,
    )
    if not res.identifiable or res.formula is None:
        raise RuleCheckFailed(
            f"{rule}: the general ID algorithm does not point-identify "
            f"P({y_atom.predicate} | do({x_atom.predicate}="
            f"{query.counterfactual_intervention.value})) on this graph, yet "
            f"the estimate claims a plug-in value for it",
            step_index=step_index, rule=rule,
        )
    # The cell's risk is P(Y=1 | do(x')) — the identity's one input is always
    # the HIGH outcome level, whatever y* the cell itself asks about.
    expected = _verifier_bind_target_value(res.formula, y_atom, True)
    claimed = inputs.get("risk_formula")
    if claimed is None:
        raise RuleCheckFailed(
            f"{rule}: provenance 'general_id_plug_in' must record the estimand "
            f"the risk was evaluated from",
            step_index=step_index, rule=rule,
        )
    if claimed != expected:
        raise RuleCheckFailed(
            f"{rule}: the recorded general-ID estimand is not the one the "
            f"verifier derives for do({x_atom.predicate}="
            f"{query.counterfactual_intervention.value}) on this graph",
            step_index=step_index, rule=rule,
        )


def _tian_pearl_poc_for_verifier(
    *,
    p_x1_y1: float, p_x1_y0: float, p_x0_y1: float, p_x0_y0: float,
    p_y_do_x1: float, p_y_do_x0: float, monotonic: bool,
) -> dict:
    """The verifier's own transcription of the Tian & Pearl (2000)
    PN/PS/PNS theorem — bounds (eqs 24-26) + monotone points (eqs 40-42).

    Deliberately re-implemented here rather than importing
    ``runtime.probabilities_of_causation`` (the verifier carries the
    theorem; the producer merely claims to satisfy it). Returns a dict
    ``{quantity: (lower, upper, point_or_None)}``.
    """
    def clamp(v: float) -> float:
        return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v

    pyx = p_y_do_x1
    pyx_ = p_y_do_x0
    py = p_x1_y1 + p_x0_y1
    pxy = p_x1_y1
    px_y_ = p_x0_y0
    py_prime_x_ = 1.0 - pyx_

    pns_lower = clamp(max(0.0, pyx - pyx_, py - pyx_, pyx - py))
    pns_upper = clamp(min(
        pyx, py_prime_x_, p_x1_y1 + p_x0_y0,
        pyx - pyx_ + p_x1_y0 + p_x0_y1,
    ))
    if pxy > 0.0:
        pn_lower = clamp(max(0.0, (py - pyx_) / pxy))
        pn_upper = clamp(min(1.0, (py_prime_x_ - px_y_) / pxy))
    else:
        pn_lower, pn_upper = 0.0, 1.0
    if px_y_ > 0.0:
        ps_lower = clamp(max(0.0, (pyx - py) / px_y_))
        ps_upper = clamp(min(1.0, (pyx - pxy) / px_y_))
    else:
        ps_lower, ps_upper = 0.0, 1.0

    pns_pt = pn_pt = ps_pt = None
    if monotonic:
        pns_pt = clamp(pyx - pyx_)
        pn_pt = clamp((py - pyx_) / pxy) if pxy > 0.0 else None
        ps_pt = clamp((pyx - py) / px_y_) if px_y_ > 0.0 else None

    return {
        "pn": (pn_lower, pn_upper, pn_pt),
        "ps": (ps_lower, ps_upper, ps_pt),
        "pns": (pns_lower, pns_upper, pns_pt),
    }


def _check_causation_over_the_polytope(
    ctx: VerificationContext,
    theta: Theta,
    inputs: dict,
    claimed_output: Any,
    declared_cells: dict,
    monotonic: bool,
    *,
    x_atom: Atom,
    y_atom: Atom,
    step_index: int,
    rule: str,
) -> None:
    """The theta-side polytope branch of the causation rule.

    Re-derives the three programs from the recorded ``P(X, Y | Z)`` — against
    the verifier's own objectives — and, because this door has theta as a
    SECOND source for that table, first checks the table is the one theta
    implies, stratum by stratum at the levels the step names. The data end
    cannot make that check; here the levels are auditable rather than
    decorative.
    """
    _counterfactual_joint_xy_for_verifier_by_atoms(
        ctx.graph, theta, declared_cells,
        x_atom=x_atom, y_atom=y_atom, bidirected=ctx.bidirected,
        step_index=step_index, rule=rule,
    )
    _recorded_instrument_table_matches_theta(
        ctx.graph, theta, inputs,
        bidirected=ctx.bidirected, step_index=step_index, rule=rule,
        x_atom=x_atom, y_atom=y_atom,
    )
    recomputed = _rederive_causation_over_response_polytope(
        ctx, inputs,
        {
            "p_x1_y1": declared_cells[(True, True)],
            "p_x1_y0": declared_cells[(True, False)],
            "p_x0_y1": declared_cells[(False, True)],
            "p_x0_y0": declared_cells[(False, False)],
        },
        monotonic, step_index=step_index, rule=rule,
    )
    for qty in ("pn", "ps", "pns"):
        claimed_q = claimed_output.get(qty)
        if not isinstance(claimed_q, dict):
            raise RuleCheckFailed(
                f"{rule}: envelope is missing the {qty} block",
                step_index=step_index, rule=rule,
            )
        exp_lo, exp_hi, exp_pt = recomputed[qty]
        claimed_lo = _envelope_number(
            claimed_q, "lower",
            step_index=step_index, rule=rule, where=f"the {qty} block",
        )
        claimed_hi = _envelope_number(
            claimed_q, "upper",
            step_index=step_index, rule=rule, where=f"the {qty} block",
        )
        if (
            abs(claimed_lo - exp_lo) > _NUMERIC_TOL
            or abs(claimed_hi - exp_hi) > _NUMERIC_TOL
        ):
            raise RuleCheckFailed(
                f"{rule}: {qty} bounds [{claimed_lo}, {claimed_hi}] != "
                f"recomputed [{exp_lo}, {exp_hi}]",
                step_index=step_index, rule=rule,
            )
        claimed_pt = claimed_q.get("point")
        if exp_pt is None:
            if claimed_pt is not None:
                raise RuleCheckFailed(
                    f"{rule}: {qty} claims a point ({claimed_pt}) while the "
                    f"identified set the program returns is an interval",
                    step_index=step_index, rule=rule,
                )
        elif claimed_pt is None or abs(
            _envelope_number(
                claimed_q, "point",
                step_index=step_index, rule=rule, where=f"the {qty} block",
            ) - exp_pt
        ) > _NUMERIC_TOL:
            raise RuleCheckFailed(
                f"{rule}: {qty} point {claimed_pt} != recomputed {exp_pt}",
                step_index=step_index, rule=rule,
            )
    for absent in ("p_y_do_x1", "p_y_do_x0"):
        if claimed_output.get(absent) is not None:
            raise RuleCheckFailed(
                f"{rule}: the envelope reports {absent} beside a licence that "
                f"claims no interventional risk was point-identified",
                step_index=step_index, rule=rule,
            )


def _counterfactual_joint_xy_for_verifier_by_atoms(
    graph: nx.DiGraph,
    theta: Theta,
    declared_cells: dict,
    *,
    x_atom: Atom,
    y_atom: Atom,
    bidirected: frozenset[frozenset[Atom]],
    step_index: int,
    rule: str,
) -> dict:
    """The four cells recomputed from theta, checked against the declared."""
    recomputed = _counterfactual_joint_xy_via_ancestral_factorization_for_verifier(
        graph, theta,
        x_atom=x_atom, y_atom=y_atom,
        bidirected=bidirected, step_index=step_index, rule=rule,
    )
    if recomputed is None:
        recomputed = {
            (xv, yv): _counterfactual_joint_cell_for_verifier(
                theta,
                x_atom=x_atom, x_val=xv,
                y_atom=y_atom, y_val=yv,
                step_index=step_index, rule=rule,
            )
            for xv in (False, True) for yv in (False, True)
        }
    for key, declared in declared_cells.items():
        if abs(declared - recomputed[key]) > _NUMERIC_TOL:
            raise RuleCheckFailed(
                f"{rule}: declared joint cell {key}={declared} != "
                f"theta-recovered {recomputed[key]}",
                step_index=step_index, rule=rule,
            )
    return recomputed


def _rule_causation_probability_bounds(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Independent audit of a PN/PS/PNS (causation) result.

    Three independent re-checks, each catching a distinct producer bug:

    1. The four observational joint cells declared in the step are
       recomputed from ``ctx.theta`` (verifier-local chain-rule recovery)
       and must match — catches a mis-wired joint.
    2. The Tian-Pearl bounds/points are re-derived from the declared
       joint + interventional risks via the verifier's own transcription
       and must match the claimed envelope — catches a formula/packaging
       bug.
    3. The interventional risks must be well-formed probabilities, and
       the envelope must echo the declared risks / monotonic flag /
       provenance.

    Scope boundary (deliberate, documented): when the interventional
    risks were ``derived_identification`` they were produced by the
    effect-identification subsystem, which has its OWN independent
    verifier (``verify`` on an effect query). This rule does not re-run
    that cascade; it audits the joint recovery, the Tian-Pearl theorem
    application, and internal consistency. The risks are validated as
    probabilities but not re-identified here.
    """
    rule = "causation_probability_bounds"
    if not isinstance(ctx.query, CausationQuery):
        raise RuleCheckFailed(
            f"{rule} requires a CausationQuery context",
            step_index=step_index, rule=rule,
        )
    if ctx.theta is None:
        raise RuleCheckFailed(
            f"{rule} requires theta in context",
            step_index=step_index, rule=rule,
        )
    if not isinstance(claimed_output, dict):
        raise RuleCheckFailed(
            f"{rule} output must be the causation envelope dict",
            step_index=step_index, rule=rule,
        )

    x_atom = _require_atom(inputs, "cause", step_index, rule)
    y_atom = _require_atom(inputs, "effect", step_index, rule)
    if x_atom != ctx.query.cause or y_atom != ctx.query.effect:
        raise RuleCheckFailed(
            f"{rule}: cause/effect inputs do not bind to the query atoms",
            step_index=step_index, rule=rule,
        )

    declared_cells = {
        (True, True): float(_require(inputs, "p_x1_y1", step_index, rule)),
        (True, False): float(_require(inputs, "p_x1_y0", step_index, rule)),
        (False, True): float(_require(inputs, "p_x0_y1", step_index, rule)),
        (False, False): float(_require(inputs, "p_x0_y0", step_index, rule)),
    }
    monotonic = bool(_require(inputs, "monotonic", step_index, rule))
    provenance = _check_risk_provenance(
        inputs, ctx, None, step_index=step_index, rule=rule,
    )

    # The two solvers behind this one rule diverge here, and the licence is
    # what says which ran. Tian-Pearl's closed form consumes both arms; the
    # response-function program consumes none, so requiring them of it would
    # audit an answer against a theorem the producer did not use.
    if provenance == "instrument_response_polytope":
        for absent in ("p_y_do_x1", "p_y_do_x0"):
            if inputs.get(absent) is not None:
                raise RuleCheckFailed(
                    f"{rule}: {absent} is reported beside a licence that "
                    f"claims no interventional risk was point-identified",
                    step_index=step_index, rule=rule,
                )
        _check_causation_over_the_polytope(
            ctx, ctx.theta, inputs, claimed_output, declared_cells, monotonic,
            x_atom=x_atom, y_atom=y_atom, step_index=step_index, rule=rule,
        )
        return

    p_y_do_x1 = float(_require(inputs, "p_y_do_x1", step_index, rule))
    p_y_do_x0 = float(_require(inputs, "p_y_do_x0", step_index, rule))

    # 1. Interventional risks must be probabilities.
    for label, v in (("p_y_do_x1", p_y_do_x1), ("p_y_do_x0", p_y_do_x0)):
        if not (0.0 <= v <= 1.0):
            raise RuleCheckFailed(
                f"{rule}: {label}={v} is not a probability in [0, 1]",
                step_index=step_index, rule=rule,
            )

    # 2. Recompute the joint from theta independently — must match declared.
    #    Ancestral BN factorization first (measured confounders), local
    #    chain-rule fallback second; mirrors the producer's recovery.
    recomputed_joint = _counterfactual_joint_xy_via_ancestral_factorization_for_verifier(
        ctx.graph, ctx.theta,
        x_atom=x_atom, y_atom=y_atom, bidirected=ctx.bidirected,
        step_index=step_index, rule=rule,
    )
    if recomputed_joint is None:
        recomputed_joint = {
            (xv, yv): _counterfactual_joint_cell_for_verifier(
                ctx.theta,
                x_atom=x_atom, x_val=xv, y_atom=y_atom, y_val=yv,
                step_index=step_index, rule=rule,
            )
            for xv in (False, True) for yv in (False, True)
        }
    for (xv, yv), declared in declared_cells.items():
        recomputed = recomputed_joint[(xv, yv)]
        if abs(declared - recomputed) > _NUMERIC_TOL:
            raise RuleCheckFailed(
                f"{rule}: declared joint cell ({xv}, {yv})={declared} != "
                f"theta-recovered {recomputed}",
                step_index=step_index, rule=rule,
            )

    # 3. Re-derive PN/PS/PNS via the verifier's own Tian-Pearl transcription.
    expected = _tian_pearl_poc_for_verifier(
        p_x1_y1=declared_cells[(True, True)],
        p_x1_y0=declared_cells[(True, False)],
        p_x0_y1=declared_cells[(False, True)],
        p_x0_y0=declared_cells[(False, False)],
        p_y_do_x1=p_y_do_x1, p_y_do_x0=p_y_do_x0, monotonic=monotonic,
    )
    for qty in ("pn", "ps", "pns"):
        claimed_q = claimed_output.get(qty)
        if not isinstance(claimed_q, dict):
            raise RuleCheckFailed(
                f"{rule}: envelope is missing the {qty} block",
                step_index=step_index, rule=rule,
            )
        exp_lo, exp_hi, exp_pt = expected[qty]
        # Invariant (matches the codebase convention for other interval
        # quantities): a valid PN/PS/PNS interval has lower <= upper, and any
        # point lies within it. An inverted interval (lower > upper) is the
        # signature of infeasible inputs — interventional risks that
        # contradict the observational joint; refuse to certify it.
        if exp_lo > exp_hi + _NUMERIC_TOL:
            raise RuleCheckFailed(
                f"{rule}: {qty} interval is inverted (lower {exp_lo} > upper "
                f"{exp_hi}) — the interventional risks are infeasible w.r.t. "
                f"the observational joint",
                step_index=step_index, rule=rule,
            )
        if exp_pt is not None and not (
            exp_lo - _NUMERIC_TOL <= exp_pt <= exp_hi + _NUMERIC_TOL
        ):
            raise RuleCheckFailed(
                f"{rule}: {qty} point {exp_pt} lies outside its bounds "
                f"[{exp_lo}, {exp_hi}] — inputs are infeasible",
                step_index=step_index, rule=rule,
            )
        claimed_lo = _envelope_number(
            claimed_q, "lower",
            step_index=step_index, rule=rule, where=f"the {qty} block",
        )
        claimed_hi = _envelope_number(
            claimed_q, "upper",
            step_index=step_index, rule=rule, where=f"the {qty} block",
        )
        if (
            abs(claimed_lo - exp_lo) > _NUMERIC_TOL
            or abs(claimed_hi - exp_hi) > _NUMERIC_TOL
        ):
            raise RuleCheckFailed(
                f"{rule}: {qty} bounds [{claimed_lo}, {claimed_hi}] != "
                f"recomputed [{exp_lo}, {exp_hi}]",
                step_index=step_index, rule=rule,
            )
        claimed_pt = claimed_q.get("point")
        if exp_pt is None:
            if claimed_pt is not None:
                raise RuleCheckFailed(
                    f"{rule}: {qty} claims a point ({claimed_pt}) but the "
                    f"quantity is not point-identified without monotonicity",
                    step_index=step_index, rule=rule,
                )
        else:
            if claimed_pt is None or abs(
                _envelope_number(
                    claimed_q, "point",
                    step_index=step_index, rule=rule, where=f"the {qty} block",
                ) - exp_pt
            ) > _NUMERIC_TOL:
                raise RuleCheckFailed(
                    f"{rule}: {qty} point {claimed_pt} != recomputed {exp_pt}",
                    step_index=step_index, rule=rule,
                )

    # 4. Envelope must echo the declared risks / flag / provenance.
    if (
        abs(
            _envelope_number(
                claimed_output, "p_y_do_x1",
                step_index=step_index, rule=rule, where="the envelope",
            ) - p_y_do_x1
        ) > _NUMERIC_TOL
        or abs(
            _envelope_number(
                claimed_output, "p_y_do_x0",
                step_index=step_index, rule=rule, where="the envelope",
            ) - p_y_do_x0
        ) > _NUMERIC_TOL
    ):
        raise RuleCheckFailed(
            f"{rule}: envelope interventional risks disagree with the "
            f"declared step inputs",
            step_index=step_index, rule=rule,
        )
    if bool(claimed_output.get("monotonic")) != monotonic:
        raise RuleCheckFailed(
            f"{rule}: envelope monotonic flag disagrees with the declared input",
            step_index=step_index, rule=rule,
        )
    if claimed_output.get("interventional_risk_provenance") != provenance:
        raise RuleCheckFailed(
            f"{rule}: envelope provenance disagrees with the declared input",
            step_index=step_index, rule=rule,
        )


def _rule_scm_abduction_action_prediction(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Independent audit of a deterministic linear-SCM counterfactual
    (Pearl Primer §4.2 abduction–action–prediction).

    Re-runs the entire three-step computation from the verification
    context — the structural coefficients on ``ctx.graph``'s edges and
    the unit's observed values in ``ctx.observations`` — deliberately
    NOT importing ``runtime.scm_counterfactual``. The verifier carries
    the theorem; the producer merely claims to satisfy it. Catches a
    wrong coefficient read, a botched abduction, a mis-propagated
    prediction, or a tampered output.
    """
    rule = "scm_abduction_action_prediction"
    q = ctx.query
    if not isinstance(q, SCMCounterfactualQuery):
        raise RuleCheckFailed(
            f"{rule} requires a SCMCounterfactualQuery context",
            step_index=step_index, rule=rule,
        )
    if ctx.observations is None:
        raise RuleCheckFailed(
            f"{rule} requires the unit's observations in context",
            step_index=step_index, rule=rule,
        )
    if not isinstance(claimed_output, NumericResult):
        raise RuleCheckFailed(
            f"{rule} output must be a NumericResult",
            step_index=step_index, rule=rule,
        )

    graph = ctx.graph
    x_atom = q.intervention.atom
    y_atom = q.target
    if x_atom not in graph or y_atom not in graph:
        raise RuleCheckFailed(
            f"{rule}: query atoms are not in the graph",
            step_index=step_index, rule=rule,
        )

    # Relevant set on the MUTILATED graph (do(X) severs X's in-edges) —
    # must match the producer, or a correct counterfactual whose factual
    # unit omits an intervention-severed upstream variable would be
    # wrongly rejected.
    mutilated = graph.copy()
    mutilated.remove_edges_from(list(graph.in_edges(x_atom)))
    relevant = set(nx.ancestors(mutilated, y_atom)) | {y_atom}

    # Rebuild the structural equations from edge coefficients; skip the
    # intervened variable (its equation is replaced, no U_X abducted).
    equations: dict = {}
    for v in relevant:
        if v == x_atom:
            continue
        terms: list[tuple] = []
        for p in graph.predecessors(v):
            src = graph.edges[p, v].get("source")
            coef = getattr(src, "coefficient", None) if src is not None else None
            if coef is None:
                raise RuleCheckFailed(
                    f"{rule}: edge into {v.predicate} lacks a path coefficient "
                    f"— SCM is under-specified, cannot verify a point",
                    step_index=step_index, rule=rule,
                )
            terms.append((p, float(coef)))
        equations[v] = tuple(terms)

    obs = ctx.observations
    for v in relevant:
        if v not in obs:
            raise RuleCheckFailed(
                f"{rule}: variable {v.predicate} is not observed for the unit "
                f"— abduction cannot recover its exogenous term",
                step_index=step_index, rule=rule,
            )

    # (i) Abduction.
    noise = {
        v: obs[v] - sum(coef * obs[p] for p, coef in terms)
        for v, terms in equations.items()
    }
    # (ii) Action + (iii) Prediction.
    topo = [n for n in nx.topological_sort(graph) if n in relevant]
    iv_val = float(q.intervention.value)
    cf: dict = {}
    for v in topo:
        if v == x_atom:
            cf[v] = iv_val
        else:
            cf[v] = noise[v] + sum(coef * cf[p] for p, coef in equations[v])
    expected = cf[y_atom]

    if claimed_output.value is None or abs(float(claimed_output.value) - expected) > _NUMERIC_TOL:
        raise RuleCheckFailed(
            f"{rule}: claimed counterfactual {claimed_output.value} != "
            f"independently recomputed {expected}",
            step_index=step_index, rule=rule,
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


# ----- Fix 3+4 §T9.2 (v0.1.5) — transport numeric verifier rule -----

def _verifier_build_transport_formula(
    target: ValuedAtom,
    intervention: ValuedAtom,
    adjustment_set: tuple[Atom, ...],
    source_population: str,
    target_population: str,
    observed: tuple[ValuedAtom, ...],
) -> FormulaExpr:
    """Verifier-side independent reconstruction of the Bareinboim
    transport g-formula. Does NOT call formula_builder.

    Shape (identical to the runtime builder spec but written
    independently — that's the paired-implementation discipline)::

        adjustment_set = ():
            P(target | intervention, observed, population=source)
        adjustment_set = (Z1, ..., Zk):
            Σ_{z1} ... Σ_{zk}
              P(target | intervention, Z1=z1, ..., observed, population=source)
              · ∏_i P*(Zi=zi | Z_{<i}, observed, population=target)
    """
    if not adjustment_set:
        return ProbabilityRefExpr(
            target=target,
            given=(intervention,) + observed,
            population=source_population,
        )

    # Independent bind-name scheme (different prefix from runtime's
    # `z_` / mediation verifier's `v_` to make co-naming accidental
    # rather than implicit — drift becomes visible at the verifier
    # boundary if the two implementations ever diverge structurally).
    def bind_for(atom: Atom, taken: set) -> BindDecl:
        args = "_".join(t.name for t in atom.args)
        base = f"vt_{atom.predicate}_{args}" if args else f"vt_{atom.predicate}"
        if base not in taken:
            return BindDecl(name=base)
        i = 2
        while f"{base}_{i}" in taken:
            i += 1
        return BindDecl(name=f"{base}_{i}")

    taken: set = set()
    z_binds: list[tuple[Atom, BindDecl, ValuedAtom]] = []
    for z_atom in adjustment_set:
        b = bind_for(z_atom, taken)
        taken.add(b.name)
        z_va = ValuedAtom(atom=z_atom, value=VarRef(name=b.name))
        z_binds.append((z_atom, b, z_va))
    z_valueds = tuple(vv for (_, _, vv) in z_binds)

    source_factor = ProbabilityRefExpr(
        target=target,
        given=(intervention,) + z_valueds + observed,
        population=source_population,
    )
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
    for z_atom, b, _ in reversed(z_binds):
        body = SumExpr(bind=b, over=z_atom, body=body)
    return body


def _formula_shape_equal(a: FormulaExpr, b: FormulaExpr) -> bool:
    """Structural equality on FormulaExpr that's tolerant of bind-name
    differences. Runtime and verifier use different bind prefixes
    (``z_`` vs ``vt_``) so dataclass equality (which compares bind
    names byte-for-byte) would over-strict reject the verifier rebuild.

    Walks both trees in lock-step; SumExpr bind names are unified via
    a substitution map so two trees structurally identical modulo
    bind-renaming compare equal. Inner ProbRef populations,
    target/given shape, and constant values must match exactly."""
    return _shape_walk(a, b, {}, {})


def _shape_walk(
    a: FormulaExpr, b: FormulaExpr,
    a_to_b_binds: dict, b_to_a_binds: dict,
) -> bool:
    if isinstance(a, ConstantExpr) and isinstance(b, ConstantExpr):
        return a.value == b.value
    if isinstance(a, ProbabilityRefExpr) and isinstance(b, ProbabilityRefExpr):
        if a.population != b.population:
            return False
        if a.target.atom != b.target.atom:
            return False
        if not _value_shape_equal(a.target.value, b.target.value, a_to_b_binds, b_to_a_binds):
            return False
        if len(a.given) != len(b.given):
            return False
        for ga, gb in zip(a.given, b.given):
            if ga.atom != gb.atom:
                return False
            if not _value_shape_equal(ga.value, gb.value, a_to_b_binds, b_to_a_binds):
                return False
        return True
    if isinstance(a, ProductExpr) and isinstance(b, ProductExpr):
        if len(a.terms) != len(b.terms):
            return False
        return all(
            _shape_walk(ta, tb, a_to_b_binds, b_to_a_binds)
            for ta, tb in zip(a.terms, b.terms)
        )
    if isinstance(a, SumExpr) and isinstance(b, SumExpr):
        if a.over != b.over:
            return False
        # Unify bind names: a.bind.name <-> b.bind.name within scope of this sum.
        new_a_to_b = dict(a_to_b_binds)
        new_b_to_a = dict(b_to_a_binds)
        new_a_to_b[a.bind.name] = b.bind.name
        new_b_to_a[b.bind.name] = a.bind.name
        return _shape_walk(a.body, b.body, new_a_to_b, new_b_to_a)
    if isinstance(a, FractionExpr) and isinstance(b, FractionExpr):
        return (
            _shape_walk(a.numerator, b.numerator, a_to_b_binds, b_to_a_binds)
            and _shape_walk(
                a.denominator, b.denominator, a_to_b_binds, b_to_a_binds
            )
        )
    return False


def _value_shape_equal(va, vb, a_to_b_binds: dict, b_to_a_binds: dict) -> bool:
    if isinstance(va, VarRef) and isinstance(vb, VarRef):
        return a_to_b_binds.get(va.name) == vb.name
    return va == vb


def _rule_transport_formula_ast(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify Fix 3+4 §T9.2 transport_formula_ast step.

    Independently rebuilds the transport g-formula from inputs
    (target, intervention, adjustment_set, source_population,
    target_population, observed) and compares to claimed_output
    structurally — modulo bind-name renaming, since the two
    implementations use different fresh-name prefixes (``z_`` vs
    ``vt_``).
    """
    target = _require(inputs, "target", step_index, "transport_formula_ast")
    intervention = _require(
        inputs, "intervention", step_index, "transport_formula_ast"
    )
    adjustment_set_raw = inputs.get("adjustment_set", ())
    adjustment_set = tuple(adjustment_set_raw)
    src_pop = inputs.get("source_population")
    tgt_pop = inputs.get("target_population")
    observed_raw = inputs.get("observed", ())
    observed = tuple(observed_raw) if observed_raw else ()

    if not isinstance(target, ValuedAtom):
        raise RuleCheckFailed(
            "transport_formula_ast: target must be a ValuedAtom",
            step_index=step_index, rule="transport_formula_ast",
        )
    if not isinstance(intervention, ValuedAtom):
        raise RuleCheckFailed(
            "transport_formula_ast: intervention must be a ValuedAtom",
            step_index=step_index, rule="transport_formula_ast",
        )
    if not isinstance(src_pop, str) or not src_pop:
        raise RuleCheckFailed(
            "transport_formula_ast: source_population must be a non-empty string",
            step_index=step_index, rule="transport_formula_ast",
        )
    if not isinstance(tgt_pop, str) or not tgt_pop:
        raise RuleCheckFailed(
            "transport_formula_ast: target_population must be a non-empty string",
            step_index=step_index, rule="transport_formula_ast",
        )

    expected = _verifier_build_transport_formula(
        target, intervention, adjustment_set, src_pop, tgt_pop, observed,
    )
    if not _formula_shape_equal(expected, claimed_output):
        raise RuleCheckFailed(
            "transport_formula_ast: claimed FormulaExpr does not match "
            "verifier-independent reconstruction (structural shape modulo "
            "bind-renaming)",
            step_index=step_index, rule="transport_formula_ast",
        )


# ----- Fix 5 (v0.1.5, audit follow-up) — Tian-in-effect verifier rule -----

def _rule_tian_formula_ast(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify the bound (target-value-applied) Tian formula step
    emitted by the Fix 5 Tian-in-effect dispatch.

    Inputs:
      - ``target``: ValuedAtom (the query target with concrete value)
      - ``intervention``: ValuedAtom (the do(X=x) value)
      - ``unbound_formula``: FormulaExpr — the original c_factor output
        (with target.value=None on the outer Y ProbRef)

    Output:
      FormulaExpr — the unbound_formula walked + target.atom rebound
      to target.value. The verifier re-runs the same binding walker
      independently and compares structurally (modulo identity since
      both sides walk the same input tree the same way).

    Independence note: byte-for-byte re-running of the Shpitser-Pearl
    ID algorithm to regenerate unbound_formula is intentionally out of
    scope here — the preceding ``tian_c_decomposition`` step already
    verifies the c-component partition that ID picked, and the
    ``identify_via_tian`` step confirms aggregation. The
    formula_evaluation step that follows re-evaluates the bound
    formula against theta. So we have three independent checks on the
    Tian path; ``tian_formula_ast`` adds a fourth that pins down the
    target-value substitution.
    """
    target = _require(inputs, "target", step_index, "tian_formula_ast")
    if not isinstance(target, ValuedAtom):
        raise RuleCheckFailed(
            "tian_formula_ast: target must be a ValuedAtom",
            step_index=step_index, rule="tian_formula_ast",
        )
    intervention = _require(
        inputs, "intervention", step_index, "tian_formula_ast",
    )
    if not isinstance(intervention, ValuedAtom):
        raise RuleCheckFailed(
            "tian_formula_ast: intervention must be a ValuedAtom",
            step_index=step_index, rule="tian_formula_ast",
        )
    unbound = _require(
        inputs, "unbound_formula", step_index, "tian_formula_ast",
    )
    if not isinstance(unbound, (ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr)):
        raise RuleCheckFailed(
            "tian_formula_ast: unbound_formula must be a FormulaExpr",
            step_index=step_index, rule="tian_formula_ast",
        )

    # Independent binding walker — same recursion as runtime's
    # formula_builder.bind_target_value but written here so the
    # verifier doesn't import the runtime helper.
    expected = _verifier_bind_target_value(
        unbound, target.atom, target.value,
    )

    if not isinstance(claimed_output, (ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr)):
        raise RuleCheckFailed(
            "tian_formula_ast: claimed output must be a FormulaExpr",
            step_index=step_index, rule="tian_formula_ast",
        )
    if expected != claimed_output:
        raise RuleCheckFailed(
            "tian_formula_ast: claimed bound formula does not match "
            "verifier's independent re-bind of unbound_formula at "
            "target_atom = target.value",
            step_index=step_index, rule="tian_formula_ast",
        )


def _verifier_bind_target_value(
    formula,
    target_atom: Atom,
    target_value,
):
    """Verifier-side independent re-implementation of formula_builder.
    bind_target_value. Walks the tree, binds Y target.value where it's
    None. No runtime imports."""
    if isinstance(formula, ConstantExpr):
        return formula
    if isinstance(formula, ProbabilityRefExpr):
        if (
            formula.target.atom == target_atom
            and formula.target.value is None
        ):
            return ProbabilityRefExpr(
                target=ValuedAtom(
                    atom=formula.target.atom, value=target_value,
                ),
                given=formula.given,
                population=formula.population,
            )
        return formula
    if isinstance(formula, ProductExpr):
        return ProductExpr(
            terms=tuple(
                _verifier_bind_target_value(t, target_atom, target_value)
                for t in formula.terms
            )
        )
    if isinstance(formula, SumExpr):
        return SumExpr(
            bind=formula.bind,
            over=formula.over,
            body=_verifier_bind_target_value(
                formula.body, target_atom, target_value,
            ),
        )
    raise TypeError(
        f"unknown FormulaExpr node: {type(formula).__name__}"
    )


def _rule_idc_formula_ast(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify the bound (Y- and Z-value-applied) IDC formula step emitted
    by the conditional general-ID effect dispatch (Phase 2).

    Inputs:
      - ``target``: ValuedAtom — the query target Y with its concrete value
      - ``intervention``: ValuedAtom — the do(X=x) value (checked well-formed;
        X is already bound inside unbound_formula by identify_via_idc)
      - ``given``: tuple[ValuedAtom] — the conditioning Z, each with its value
      - ``unbound_formula``: FormulaExpr — the identify_via_idc output, with Y
        and every conditioned Z left as ``value=None`` holes (X already bound)

    Output:
      FormulaExpr — the unbound_formula walked with every ``value=None`` Y/Z
      hole rebound to its query value, in BOTH target AND given positions (an
      exchanged Z sits on the do-context side; a surviving Z_rem appears as a
      numerator target and as a chain-rule conditioning atom). The verifier
      re-runs the identical binding independently and compares structurally.

    Independence note: same posture as ``tian_formula_ast``. The preceding
    ``idc_rule2_exchange`` + ``identify_via_idc`` steps verify the exchange and
    the numerator/denominator SHAPE against an independent replay; the
    following ``formula_evaluation`` re-evaluates the bound estimand against
    theta. This rule pins the value substitution — a runtime that bound the
    wrong Y/Z value (or bound X's do-value onto a Z hole) is caught here.
    """
    from ..types import FractionExpr

    target = _require(inputs, "target", step_index, "idc_formula_ast")
    if not isinstance(target, ValuedAtom):
        raise RuleCheckFailed(
            "idc_formula_ast: target must be a ValuedAtom",
            step_index=step_index, rule="idc_formula_ast",
        )
    intervention = _require(
        inputs, "intervention", step_index, "idc_formula_ast",
    )
    if not isinstance(intervention, ValuedAtom):
        raise RuleCheckFailed(
            "idc_formula_ast: intervention must be a ValuedAtom",
            step_index=step_index, rule="idc_formula_ast",
        )
    given = _require(inputs, "given", step_index, "idc_formula_ast")
    if not isinstance(given, tuple) or not given:
        raise RuleCheckFailed(
            "idc_formula_ast: given must be a non-empty tuple of ValuedAtoms",
            step_index=step_index, rule="idc_formula_ast",
        )
    for g in given:
        if not isinstance(g, ValuedAtom):
            raise RuleCheckFailed(
                "idc_formula_ast: every given entry must be a ValuedAtom",
                step_index=step_index, rule="idc_formula_ast",
            )
    unbound = _require(
        inputs, "unbound_formula", step_index, "idc_formula_ast",
    )
    if not isinstance(unbound, (ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr, FractionExpr)):
        raise RuleCheckFailed(
            "idc_formula_ast: unbound_formula must be a FormulaExpr",
            step_index=step_index, rule="idc_formula_ast",
        )

    # Value map: the query target Y and every conditioned Z, keyed by atom.
    value_map = {g.atom: g.value for g in given}
    value_map[target.atom] = target.value

    expected = _verifier_bind_idc_values(unbound, value_map)

    if not isinstance(claimed_output, (ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr, FractionExpr)):
        raise RuleCheckFailed(
            "idc_formula_ast: claimed output must be a FormulaExpr",
            step_index=step_index, rule="idc_formula_ast",
        )
    if expected != claimed_output:
        raise RuleCheckFailed(
            "idc_formula_ast: claimed bound formula does not match the "
            "verifier's independent re-bind of unbound_formula at the query "
            "Y and Z values",
            step_index=step_index, rule="idc_formula_ast",
        )


def _verifier_bind_idc_values(formula, value_map: dict):
    """Verifier-side independent re-implementation of
    ``c_factor.bind_idc_values``. Walks the tree and binds every
    ``value=None`` hole whose atom is in ``value_map`` — in BOTH target and
    given positions — to its mapped value; recurses through FractionExpr.
    Structurally identical to ``c_factor._map_valued_atoms`` (target + given
    reconstruction, no population kwarg — IDC estimands carry none) so the
    equality check against the runtime output is exact. No runtime imports."""
    from ..types import FractionExpr

    def fix(va):
        if va.value is None and va.atom in value_map:
            return ValuedAtom(atom=va.atom, value=value_map[va.atom])
        return va

    if isinstance(formula, ConstantExpr):
        return formula
    if isinstance(formula, ProbabilityRefExpr):
        return ProbabilityRefExpr(
            target=fix(formula.target),
            given=tuple(fix(g) for g in formula.given),
        )
    if isinstance(formula, ProductExpr):
        return ProductExpr(
            terms=tuple(
                _verifier_bind_idc_values(t, value_map) for t in formula.terms
            )
        )
    if isinstance(formula, SumExpr):
        return SumExpr(
            bind=formula.bind,
            over=formula.over,
            body=_verifier_bind_idc_values(formula.body, value_map),
        )
    if isinstance(formula, FractionExpr):
        return FractionExpr(
            numerator=_verifier_bind_idc_values(formula.numerator, value_map),
            denominator=_verifier_bind_idc_values(formula.denominator, value_map),
        )
    raise TypeError(
        f"unknown FormulaExpr node: {type(formula).__name__}"
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

    # Shpitser ID Line 2 (ancestor restriction): identifiability of
    # P(y | do(x)) depends only on An(Y)_G. Nodes that are not directed
    # ancestors of Y — e.g. the latent-flanked collider Z in M-bias
    # (X→Y, X↔Z, Z↔Y) — drop out BEFORE the c-component test. The runtime's
    # ID engine performs this restriction; omitting it here made Line 6 reject
    # M-bias, a textbook IDENTIFIABLE graph whose only back-door path is
    # collider-blocked. Restricting to An(Y) is a SOUND step of the algorithm
    # (the restricted graph has the same identifiability), so it can only
    # remove false rejects — it never lets an unidentifiable claim through:
    # the bow arc (X→Y, X↔Y) still has y in the {x,y} c-component after
    # restriction and is correctly rejected.
    an_y = nx.ancestors(ctx.graph, y) | {y}
    g_an = ctx.graph.subgraph(an_y)
    bi_an = frozenset(p for p in ctx.bidirected if p <= an_y)

    cc_full = c_components(g_an, bi_an)
    nodes_minus_x = frozenset(an_y) - {x}
    sub = g_an.subgraph(nodes_minus_x)
    bi_minus_x = frozenset(p for p in bi_an if p <= nodes_minus_x)
    cc_minus_x = c_components(sub, bi_minus_x)

    # Y's c-component in G[An(Y)\X] must be a c-component of G[An(Y)].
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
    # Tian-Pearl (2002a) Thm 9 / Tian-Shpitser (2009): for a single intervention
    # X on a single target Y, P(Y|do(X)) is UNidentifiable iff a bidirected path
    # connects X to one of its CHILDREN within G[An(Y)] — i.e. X shares its
    # c-component of G[An(Y)] with a child of X. The earlier check compared X to
    # Y, which only recognises the bow-arc hedge and so wrongly rejected correct
    # unidentifiability whenever the hedge sits on a descendant of X
    # (What If Fig 9.17: A->L->Y, A->Y, A<->L — Y is in its own c-component, but
    # the hedge is on the A<->L bow with L a child of A).
    x_children = set(sub.successors(x)) if x in sub else set()
    hedge_present = x_cc is not None and any(child in x_cc for child in x_children)
    if not hedge_present:
        raise RuleCheckFailed(
            "tian_hedge_witness: no bidirected path connects x to a child of x "
            "in G[An(Y)] (Tian-Pearl 2002a Thm 9) — runtime claim of "
            "unidentifiability is unsound",
            step_index=step_index, rule="tian_hedge_witness",
        )

    if not isinstance(claimed_output, StructuralResult) or claimed_output.value is not False:
        raise RuleCheckFailed(
            "tian_hedge_witness must claim StructuralResult(value=False)",
            step_index=step_index, rule="tian_hedge_witness",
        )


# ---------------------------------------------------------------------------
# IDC (conditional identification, P(Y | do(X), Z)) verifier rules.
#
# The runtime path is c_factor.identify_via_idc; see that module for the
# algorithm. The verifier's independent checks (in _rule_identify_via_idc):
#   1. the formula validates against the kernel formula grammar;
#   2. the do-calculus Rule-2 exchange is re-derived FROM SCRATCH here
#      (its own mutilation + loop, sharing only the trusted is_m_connected
#      m-separation primitive) — this is the IDC-specific, load-bearing
#      claim, so it is checked without calling the runtime's exchange;
#   3. the formula's SHAPE is consistent with that independent replay —
#      a FractionExpr iff conditioning survived, the bare numerator iff
#      every Z exchanged away.
#
# Scope, stated plainly (no overclaim): this rule independently verifies
# the IDC-specific REDUCTION — the Rule-2 exchange and the resulting
# numerator/denominator shape — plus formula well-formedness. It does NOT
# independently re-derive the underlying (unconditional) identifiability
# of the two ID sub-problems; that rests on the same c-factor machinery
# the Tian path uses. A precise, set-valued, non-circular re-check of ID
# identifiability (without mirroring the recursion) is deferred — the
# naive "x and y share a c-component of An(Y)" test is NOT a sound hedge
# detector (it false-flags front-door graphs), so no such floor is
# asserted here rather than asserting a wrong one.


def _idc_atom_sort_key(a) -> tuple:
    return (a.predicate, tuple(t.name for t in a.args))


def _idc_mutilate_rule2(graph, bidirected, do_set, underline):
    """G_{do_set̄, underline_}: remove directed edges into do_set, the
    bidirected edges at do_set, and directed edges out of underline.

    INVARIANT: this convention must stay identical to
    ``c_factor._mutilate_for_rule2`` — they are deliberately separate
    implementations so the verifier does not depend on the runtime's
    exchange code, but a divergence here is a verifier bug.
    """
    g = graph.copy()
    for node in do_set:
        if node in g:
            g.remove_edges_from(list(g.in_edges(node)))
    if underline in g:
        g.remove_edges_from(list(g.out_edges(underline)))
    bi = frozenset(p for p in bidirected if p.isdisjoint(do_set))
    return g, bi


def _idc_replay_exchange(graph, bidirected, x, y_set, z_set):
    """Independently re-run the IDC Rule-2 loop. Returns (do_set, z_rem)."""
    from ..runtime.structural_solver import is_m_connected

    do_set = frozenset({x})
    cond_z = frozenset(z_set)
    changed = True
    while changed and cond_z:
        changed = False
        for zi in sorted(cond_z, key=_idc_atom_sort_key):
            rest = cond_z - {zi}
            mg, mbi = _idc_mutilate_rule2(graph, bidirected, do_set, zi)
            conditioning = tuple(do_set | rest)
            if all(
                not is_m_connected(mg, mbi, yj, zi, conditioning)
                for yj in y_set
            ):
                do_set = do_set | {zi}
                cond_z = rest
                changed = True
                break
    return do_set, cond_z


def _rule_idc_rule2_exchange(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Declarative step: 'we ran the IDC Rule-2 exchange on ctx.graph'.
    The exchange is actually replayed in identify_via_idc; here we only
    validate the inputs are well-formed (parallel to
    tian_c_decomposition)."""
    graph = _require(inputs, "graph", step_index, "idc_rule2_exchange")
    _assert_same_graph(graph, ctx.graph, step_index, "idc_rule2_exchange")
    x = _require_atom(inputs, "x", step_index, "idc_rule2_exchange")
    y = _require_atom(inputs, "y", step_index, "idc_rule2_exchange")
    if x == y:
        raise RuleCheckFailed(
            "idc_rule2_exchange: x and y must differ",
            step_index=step_index, rule="idc_rule2_exchange",
        )
    if claimed_output is not True:
        raise RuleCheckFailed(
            f"idc_rule2_exchange output must be True, got {claimed_output!r}",
            step_index=step_index, rule="idc_rule2_exchange",
        )


def _rule_identify_via_idc(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
    step_by_id: dict,
    step_output_by_id: dict,
) -> None:
    """Verifier-side independent check of a conditional identification
    P(Y | do(X), Z). See the section header above for the proof posture.
    """
    from ..input.semantic_validator import validate_formula

    exchange_ref = _require(
        inputs, "exchange", step_index, "identify_via_idc",
    )
    formula = _require(inputs, "formula", step_index, "identify_via_idc")

    if not isinstance(exchange_ref, StepRef):
        raise UnknownRuleInputError(
            "identify_via_idc.exchange must be a StepRef",
            step_index=step_index, rule="identify_via_idc",
        )
    exchange_step = step_by_id.get(exchange_ref.step_id)
    if exchange_step is None or exchange_step.rule != "idc_rule2_exchange":
        raise RuleCheckFailed(
            "identify_via_idc.exchange must reference an idc_rule2_exchange "
            f"step, got {getattr(exchange_step, 'rule', None)!r}",
            step_index=step_index, rule="identify_via_idc",
        )

    # IDC identification is licensed from either an IdentifyQuery (structural
    # P(Y|do(X),Z) with value-less atoms) or an EffectQuery (the conditional
    # effect numeric end, Phase 2 — target/given carry concrete values). Both
    # reduce to the same atom-level check: extract the atoms and replay the
    # Rule-2 exchange. The numeric correctness of the bound estimand is the
    # separate responsibility of the following idc_formula_ast +
    # formula_evaluation steps.
    q = ctx.query
    if isinstance(q, IdentifyQuery):
        x = q.intervention.atom
        y = q.target
        z_set = frozenset(q.given)
    elif isinstance(q, EffectQuery):
        x = q.intervention.atom
        y = q.target.atom
        z_set = frozenset(g.atom for g in q.given)
    else:
        raise RuleCheckFailed(
            "identify_via_idc requires IdentifyQuery or EffectQuery context",
            step_index=step_index, rule="identify_via_idc",
        )
    if not q.given:
        raise RuleCheckFailed(
            "identify_via_idc requires a non-empty conditioning set "
            "(given); empty-given identification is plain ID, not IDC",
            step_index=step_index, rule="identify_via_idc",
        )

    try:
        validate_formula(formula)
    except Exception as exc:
        raise RuleCheckFailed(
            f"identify_via_idc formula does not validate: {exc}",
            step_index=step_index, rule="identify_via_idc",
        ) from exc

    # (2) Independently re-derive the Rule-2 exchange.
    do_set, z_rem = _idc_replay_exchange(
        ctx.graph, ctx.bidirected, x, frozenset({y}), z_set,
    )

    # (3) The formula's shape must agree with the independent replay:
    # a FractionExpr iff conditioning survived, the bare numerator iff
    # every Z exchanged away. Catches a runtime that emitted the wrong
    # estimand shape for the exchange it actually performed.
    from ..types import FractionExpr
    is_fraction = isinstance(formula, FractionExpr)
    if bool(z_rem) != is_fraction:
        raise RuleCheckFailed(
            "identify_via_idc: formula shape inconsistent with the "
            f"replayed exchange — z_remaining={'non-empty' if z_rem else '∅'} "
            f"but formula is {'a fraction' if is_fraction else 'not a fraction'}",
            step_index=step_index, rule="identify_via_idc",
        )

    if not isinstance(claimed_output, StructuralResult) or claimed_output.value is not True:
        raise RuleCheckFailed(
            "identify_via_idc must claim StructuralResult(value=True)",
            step_index=step_index, rule="identify_via_idc",
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
    # Joint (treatment-set) back-door — independent re-derivation of the
    # generalized adjustment criterion for do(A=a, B=b, ...).
    "joint_backdoor_criterion": _rule_joint_backdoor_criterion,
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
    "counterfactual_cell_bounds": _rule_counterfactual_cell_bounds,
    # Probabilities of causation — PN / PS / PNS (Tian & Pearl 2000)
    "causation_probability_bounds": _rule_causation_probability_bounds,
    # Data-based PN/PS/PNS — numeric counterpart (empirical joint + g-formula
    # do-risks → the same Tian-Pearl theorem, re-derived independently).
    "numeric_causation_estimate": _rule_numeric_causation_estimate,
    "numeric_counterfactual_cell_estimate": _rule_numeric_counterfactual_cell_estimate,
    # Linear-SCM counterfactual point (Pearl Primer §4.2)
    "scm_abduction_action_prediction": _rule_scm_abduction_action_prediction,
    # Data-fitted linear-SCM counterfactual — metadata terminal; the strong
    # re-solve (OLS moments) + abduction-action-prediction re-run lives in
    # verify_scm_counterfactual_numeric (kernel.verify).
    "numeric_scm_counterfactual_estimate": _rule_numeric_scm_counterfactual_estimate,
    # General counterfactual identification (Shpitser-Pearl ID*, R-336) —
    # structural licence for a counterfactual-conjunction estimand.
    "id_star_identification": _rule_id_star_identification,
    # Phase 6.iv S.IV.3
    "iv_criterion_check": _rule_iv_criterion_check,
    # The same question asked of a treatment SET — a different condition and
    # not a conjunction of the scalar one, since a path through another
    # treatment of the vector is inside the intervention.
    "vector_iv_criterion_check": _rule_vector_iv_criterion_check,
    # General-ID (c-factor) plug-in — structural licence: re-run the ID
    # engine and confirm the effect is point-identified.
    "general_id_criterion": _rule_general_id_criterion,
    # Counterfactual-conjunction (ID*/IDC*) plug-in — structural licence:
    # re-run ID*/IDC* and confirm the conjunction is identified.
    "ctf_conjunction_criterion": _rule_ctf_conjunction_criterion,
    # Proximal inference (Miao 2018 model f) — structural licence: re-run
    # identify_proximal and confirm the effect is proximal-identifiable.
    "proximal_criterion": _rule_proximal_criterion,
    # Fix 6 (v0.1.5, audit follow-up) — IV-in-effect Wald LATE numeric
    "iv_wald_numeric_evaluate": _rule_iv_wald_numeric_evaluate,
    # Phase 6.mediation S.M.3
    "mediation_nde_nie_check": _rule_mediation_nde_nie_check,
    "mediation_cde_check": _rule_mediation_cde_check,
    # Joint multi-mediator (VanderWeele-Vansteelandt 2014) — the block
    # NDE/NIE four-condition check + the CDE-for-a-set back-door check over
    # a mediator SET.
    "mediation_nde_nie_joint_check": _rule_mediation_nde_nie_joint_check,
    "mediation_cde_joint_check": _rule_mediation_cde_joint_check,
    # Phase 7.L — longitudinal g-formula / sequential back-door: independent
    # per-time sequential-exchangeability re-check (single-step aggregate).
    "longitudinal_sequential_exchangeability_check": _rule_longitudinal_sequential_exchangeability_check,
    # Phase 6.mediation Fix 1 (v0.1.4) — numeric evaluation
    "mediation_numeric_evaluate": _rule_mediation_numeric_evaluate,
    # Phase 9 §T9.1.4 — independent transport audit
    "s_admissibility_check": _rule_s_admissibility_check,
    "transport_formula": _rule_transport_formula,
    # Fix 3+4 §T9.2 (v0.1.5) — transport numeric FormulaExpr witness
    "transport_formula_ast": _rule_transport_formula_ast,
    # Fix 5 (v0.1.5, audit follow-up) — Tian-in-effect bound formula
    "tian_formula_ast": _rule_tian_formula_ast,
    # Phase 2 (conditional general-ID) — IDC-in-effect bound formula: the
    # Y/Z value substitution onto the identify_via_idc estimand.
    "idc_formula_ast": _rule_idc_formula_ast,
    # Phase 2.latent ext §S3.b.2 — Tian / Shpitser ID
    "tian_c_decomposition": _rule_tian_c_decomposition,
    # IDC — conditional identification P(Y | do(X), Z)
    "idc_rule2_exchange": _rule_idc_rule2_exchange,
}
_STEP_REF_RULES = {
    "identify_via_backdoor",
    "identify_via_front_door",
    "identify_via_iv",
    "identify_via_mediation",
    # Joint multi-mediator block decomposition terminal (no CDE branch).
    "identify_via_mediation_joint",
    "numeric_result",
    # Phase 7.1 S.N.4
    "numeric_backdoor_estimate",
    # Doubly-robust (IPW / AIPW / TMLE) numeric estimates — same backdoor
    # identification witness, different estimator terminal.
    "numeric_aipw_estimate",
    "numeric_tmle_estimate",
    "numeric_ipw_estimate",
    # Joint (treatment-set) back-door identification + numeric estimate
    "identify_via_joint_backdoor",
    "numeric_joint_backdoor_estimate",
    # Joint (treatment-set) general-ID identification terminal — same
    # c-factor identification witness (general_id_criterion), structural
    # terminal for a latent-confounded joint effect with no adjustment set,
    # and the numeric terminal that carries its contrast + interaction.
    "identify_via_general_id",
    "numeric_joint_general_id_estimate",
    # Phase 7.2 S.FDN.3
    "numeric_frontdoor_estimate",
    # Phase 7.3 S.IVN.3
    "numeric_iv_estimate",
    # Over-identified 2SLS (q >= 2 instruments) + Sargan test terminal.
    "numeric_iv_overid_estimate",
    # Anderson-Rubin region over a treatment VECTOR — the terminal for an
    # answer that is a region rather than a point.
    "numeric_anderson_rubin_region",
    # General-ID (c-factor) plug-in numeric estimate — same c-factor
    # identification witness (general_id_criterion), plug-in terminal.
    "numeric_general_id_estimate",
    # Counterfactual-conjunction (ID*/IDC*) plug-in numeric estimate — same
    # counterfactual identification witness (ctf_conjunction_criterion).
    "numeric_ctf_conjunction_estimate",
    # Proximal matrix plug-in numeric estimate — same proximal identification
    # witness (proximal_criterion), plug-in terminal.
    "numeric_proximal_estimate",
    # Measurement-error correction (frontier E) — confusion-matrix inversion
    # atop a back-door identification witness (backdoor_criterion).
    "numeric_measurement_correction_estimate",
    # Phase 9 §T9.1.4 — transport identification
    "identify_via_transport",
    # Phase 7.L — longitudinal g-formula (sequential back-door) terminal
    "identify_via_gformula",
    # Phase 2.latent ext §S3.b.2 — Tian / Shpitser ID
    "identify_via_tian",
    "tian_hedge_witness",
    # IDC — conditional identification P(Y | do(X), Z)
    "identify_via_idc",
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
    if rule_name == "identify_via_mediation_joint":
        _rule_identify_via_mediation_joint(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "numeric_backdoor_estimate":
        _rule_numeric_backdoor_estimate(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "numeric_aipw_estimate":
        _rule_numeric_aipw_estimate(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "numeric_tmle_estimate":
        _rule_numeric_tmle_estimate(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "numeric_ipw_estimate":
        _rule_numeric_ipw_estimate(
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
    if rule_name == "numeric_iv_overid_estimate":
        _rule_numeric_iv_overid_estimate(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "numeric_anderson_rubin_region":
        _rule_numeric_anderson_rubin_region(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "numeric_general_id_estimate":
        _rule_numeric_general_id_estimate(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "numeric_ctf_conjunction_estimate":
        _rule_numeric_ctf_conjunction_estimate(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "numeric_proximal_estimate":
        _rule_numeric_proximal_estimate(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "numeric_measurement_correction_estimate":
        _rule_numeric_measurement_correction_estimate(
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
    if rule_name == "identify_via_idc":
        _rule_identify_via_idc(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "identify_via_joint_backdoor":
        _rule_identify_via_joint_backdoor(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "identify_via_general_id":
        _rule_identify_via_general_id(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "identify_via_gformula":
        _rule_identify_via_gformula(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "numeric_joint_backdoor_estimate":
        _rule_numeric_joint_backdoor_estimate(
            ctx, inputs, claimed_output, step_index, step_by_id, step_output_by_id,
        )
        return
    if rule_name == "numeric_joint_general_id_estimate":
        _rule_numeric_joint_general_id_estimate(
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
    if not isinstance(v, (set, frozenset, tuple)):
        raise UnknownRuleInputError(
            f"{rule}.{key} must be a set/frozenset/tuple of Atom",
            step_index=step_index, rule=rule,
        )
    for a in v:
        if not isinstance(a, Atom):
            raise UnknownRuleInputError(
                f"{rule}.{key} must contain only Atom, got {type(a).__name__}",
                step_index=step_index, rule=rule,
            )
    return frozenset(v)


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
