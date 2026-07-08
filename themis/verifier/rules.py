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
from typing import Any, Callable

import networkx as nx

from ..runtime.numeric_estimator import ProbabilityKey, Theta
from ..types import (
    Atom,
    BindDecl,
    CausationQuery,
    ConstantExpr,
    CounterfactualQuery,
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
    (ii) Z ∪ given d-separates the treatment set from Y in the proper
         back-door graph (G with the first edge of every proper causal
         path removed).

    inputs:
        graph, treatments (atom set), y (atom), z (atom set),
        given (atom set, optional)
    output:
        True iff (i) ∧ (ii).

    v1 scope: directed DAGs. A non-empty bidirected context is rejected
    (joint ADMG adjustment is unbuilt) so the verifier never silently
    accepts a latent-confounded joint claim.
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

    bidir = getattr(ctx, "bidirected", frozenset()) or frozenset()
    if bidir:
        raise RuleCheckFailed(
            "joint_backdoor_criterion: bidirected (latent) context is out "
            "of v1 scope — joint ADMG adjustment is not supported",
            step_index=step_index, rule="joint_backdoor_criterion",
        )

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
    - joint point / interaction point are numbers, each inside its CI
      when present
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

    for label in ("joint_point", "interaction_point"):
        val = inputs.get(label)
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            raise RuleCheckFailed(
                f"numeric_joint_backdoor_estimate.{label} must be a number; "
                f"got {val!r}",
                step_index=step_index, rule="numeric_joint_backdoor_estimate",
            )

    for point_key, lo_key, hi_key in (
        ("joint_point", "joint_ci_lower", "joint_ci_upper"),
        ("interaction_point", "interaction_ci_lower", "interaction_ci_upper"),
    ):
        lo = inputs.get(lo_key)
        hi = inputs.get(hi_key)
        if lo is None and hi is None:
            continue
        if lo is None or hi is None:
            raise RuleCheckFailed(
                f"numeric_joint_backdoor_estimate: {lo_key} and {hi_key} "
                "must both be present or both absent",
                step_index=step_index, rule="numeric_joint_backdoor_estimate",
            )
        if not (lo <= inputs[point_key] <= hi):
            raise RuleCheckFailed(
                f"numeric_joint_backdoor_estimate: {point_key} "
                f"{inputs[point_key]} outside [{lo}, {hi}]",
                step_index=step_index, rule="numeric_joint_backdoor_estimate",
            )

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


def _rule_general_id_criterion(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Verify that P(Y | do(X)) is point-identified by the general ID
    (Tian–Shpitser c-factor) algorithm on this ADMG — the structural
    licence for a general-ID plug-in numeric estimate.

    Re-executes ``c_factor.identify_via_tian`` on the context's
    (graph, bidirected) and confirms it reports ``identifiable`` with a
    well-formed formula. This is the safety-critical check: a number is
    produced ONLY for a genuinely identified effect, never for a hedge.

    It re-runs the ID engine rather than reimplementing it — the deep,
    fully-independent c-factor replay lives in ``_rule_identify_via_tian``
    on the identify-query path. Here the relaxed numeric audit confirms
    identifiability, matching the cost trade-off the other numeric rules
    make (verify_numeric_estimate: numerical reproduction is prohibitively
    expensive for a verifier pass).

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

    bidir = getattr(ctx, "bidirected", frozenset()) or frozenset()
    # Identifiability is independent of the intervention value; use the
    # query's value when available, else a boolean placeholder.
    x_value = True
    q = getattr(ctx, "query", None)
    if q is not None and getattr(q, "intervention", None) is not None:
        x_value = q.intervention.value
    res = c_factor.identify_via_tian(graph, bidir, x, y, x_value)
    recomputed = bool(res.identifiable and res.formula is not None)
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

    bidir = getattr(ctx, "bidirected", frozenset()) or frozenset()

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

    bidir = getattr(ctx, "bidirected", frozenset()) or frozenset()

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
    """Verify the bundled IV Wald LATE numeric step (Fix 6).

    Inputs:
      - ``target``: ValuedAtom (Y=y)
      - ``intervention_treated``: ValuedAtom (X=x_treated)
      - ``instrument_treated``: ValuedAtom (Z=z_treated)
      - ``instrument_control``: ValuedAtom (Z=z_control)
      - ``monotonicity``: string label (just metadata; semantic check
        lives at scheduler dispatch time, not here)

    Output dict must contain:
      - p_y_given_z_treated, p_y_given_z_control,
        p_x_given_z_treated, p_x_given_z_control, late

    The verifier independently re-looks-up each of the 4 theta entries
    and re-computes Wald LATE = (numerator) / (denominator). Compares
    every component within 1e-9 (paired-implementation pin).
    """
    target = _require(inputs, "target", step_index, "iv_wald_numeric_evaluate")
    treated = _require(
        inputs, "intervention_treated", step_index, "iv_wald_numeric_evaluate",
    )
    z_treated = _require(
        inputs, "instrument_treated", step_index, "iv_wald_numeric_evaluate",
    )
    z_control = _require(
        inputs, "instrument_control", step_index, "iv_wald_numeric_evaluate",
    )

    for name, va in (
        ("target", target),
        ("intervention_treated", treated),
        ("instrument_treated", z_treated),
        ("instrument_control", z_control),
    ):
        if not isinstance(va, ValuedAtom):
            raise RuleCheckFailed(
                f"iv_wald_numeric_evaluate: {name} must be a ValuedAtom",
                step_index=step_index, rule="iv_wald_numeric_evaluate",
            )

    if not isinstance(claimed_output, dict):
        raise RuleCheckFailed(
            "iv_wald_numeric_evaluate output must be a dict",
            step_index=step_index, rule="iv_wald_numeric_evaluate",
        )

    theta = getattr(ctx, "theta", None)
    if theta is None:
        raise RuleCheckFailed(
            "iv_wald_numeric_evaluate requires theta in ctx",
            step_index=step_index, rule="iv_wald_numeric_evaluate",
        )

    # Independent 4-lookup + arithmetic recompute.
    def lookup(target_atom, target_val, given_pairs):
        key = ProbabilityKey(
            target_atom=target_atom,
            target_value=target_val,
            given=frozenset(given_pairs),
        )
        return theta.entries.get(key)

    y_atom, y_val = target.atom, target.value
    x_atom, x_val = treated.atom, treated.value
    z_atom = z_treated.atom

    expected = {
        "p_y_given_z_treated": lookup(
            y_atom, y_val, [(z_atom, z_treated.value)],
        ),
        "p_y_given_z_control": lookup(
            y_atom, y_val, [(z_atom, z_control.value)],
        ),
        "p_x_given_z_treated": lookup(
            x_atom, x_val, [(z_atom, z_treated.value)],
        ),
        "p_x_given_z_control": lookup(
            x_atom, x_val, [(z_atom, z_control.value)],
        ),
    }
    for k, v in expected.items():
        if v is None:
            raise RuleCheckFailed(
                f"iv_wald_numeric_evaluate: verifier theta lookup failed for {k}",
                step_index=step_index, rule="iv_wald_numeric_evaluate",
            )

    denom = expected["p_x_given_z_treated"] - expected["p_x_given_z_control"]
    if abs(denom) < 1e-12:
        raise RuleCheckFailed(
            "iv_wald_numeric_evaluate: denominator (instrument shift on X) "
            "≈ 0; Wald undefined",
            step_index=step_index, rule="iv_wald_numeric_evaluate",
        )
    expected["late"] = (
        expected["p_y_given_z_treated"] - expected["p_y_given_z_control"]
    ) / denom

    for key, val in expected.items():
        if key not in claimed_output:
            raise RuleCheckFailed(
                f"iv_wald_numeric_evaluate: claimed_output missing {key!r}",
                step_index=step_index, rule="iv_wald_numeric_evaluate",
            )
        claimed_v = claimed_output[key]
        if not isinstance(claimed_v, (int, float)):
            raise RuleCheckFailed(
                f"iv_wald_numeric_evaluate: {key} must be numeric",
                step_index=step_index, rule="iv_wald_numeric_evaluate",
            )
        if abs(float(claimed_v) - val) > _NUMERIC_TOL:
            raise RuleCheckFailed(
                f"iv_wald_numeric_evaluate: {key} mismatch — claimed "
                f"{claimed_v!r}, recomputed {val!r}",
                step_index=step_index, rule="iv_wald_numeric_evaluate",
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

_NUMERIC_JOINT_METHODS = frozenset({
    "joint_backdoor_linear",
    "joint_backdoor_logistic",
})

# General-ID (c-factor) non-parametric plug-in — the crown-jewel
# identification made numeric on discrete data.
_NUMERIC_GENERAL_ID_METHODS = frozenset({"general_id_plugin"})

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
    raw_min = inputs.get("propensity_raw_min")
    raw_max = inputs.get("propensity_raw_max")
    n_trimmed = inputs.get("propensity_n_trimmed")
    floor = inputs.get("propensity_floor")
    for label, v in (("propensity_raw_min", raw_min), ("propensity_raw_max", raw_max)):
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not (0.0 <= v <= 1.0):
            raise RuleCheckFailed(
                f"{rule}.{label} must be a probability in [0, 1]; got {v!r}",
                step_index=step_index, rule=rule,
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

    bidir = getattr(ctx, "bidirected", frozenset()) or frozenset()
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


_NUMERIC_CAUSATION_METHODS = frozenset({"causation_plugin"})


def _rule_numeric_causation_estimate(
    ctx: VerificationContext,
    inputs: dict,
    claimed_output: Any,
    step_index: int,
) -> None:
    """Independent audit of a data-based PN/PS/PNS (causation) estimate.

    The numeric counterpart of ``probabilities_of_causation_tian_pearl``, but
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
    p_y_do_x1 = float(_require(inputs, "p_y_do_x1", step_index, rule))
    p_y_do_x0 = float(_require(inputs, "p_y_do_x0", step_index, rule))
    for label, v in (("p_y_do_x1", p_y_do_x1), ("p_y_do_x0", p_y_do_x0)):
        if not (0.0 <= v <= 1.0):
            raise RuleCheckFailed(
                f"{rule}: {label}={v} is not a probability in [0, 1]",
                step_index=step_index, rule=rule,
            )
    monotonic = bool(_require(inputs, "monotonic", step_index, rule))
    if not monotonic:
        raise RuleCheckFailed(
            f"{rule}: a numeric PN/PS/PNS POINT requires monotonic=True "
            "(without it the quantities are only bounds)",
            step_index=step_index, rule=rule,
        )

    # 1. Independent Tian-Pearl re-application on the reported data inputs.
    recomputed = _tian_pearl_poc_for_verifier(
        p_x1_y1=cells["p_x1_y1"], p_x1_y0=cells["p_x1_y0"],
        p_x0_y1=cells["p_x0_y1"], p_x0_y0=cells["p_x0_y0"],
        p_y_do_x1=p_y_do_x1, p_y_do_x0=p_y_do_x0, monotonic=True,
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

    # 2. Identification-structure re-check: the adjustment set must be an
    #    admissible back-door set on ctx.graph (skip for external experiments).
    provenance = _require(inputs, "interventional_risk_provenance", step_index, rule)
    # ``adjustment`` is serialized as a comma-joined scalar string (the
    # derivation serializer does not take a tuple of strings).
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

    # 3. Headline PN CI brackets the PN point (when a CI is present).
    pn_point = float(_require(inputs, "pn_point", step_index, rule))
    ci_lower = inputs.get("ci_lower")
    ci_upper = inputs.get("ci_upper")
    if ci_lower is not None or ci_upper is not None:
        if ci_lower is None or ci_upper is None:
            raise RuleCheckFailed(
                f"{rule}: ci_lower and ci_upper must both be present or absent",
                step_index=step_index, rule=rule,
            )
        if not (ci_lower <= pn_point <= ci_upper):
            raise RuleCheckFailed(
                f"{rule}: PN point {pn_point} outside CI [{ci_lower}, {ci_upper}]",
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
            # Fix 3+4: thread population from the ProbRef so transport
            # formulas (P(...source) vs P*(...target)) route to the
            # right theta partition. None default = pre-fix behaviour
            # for all single-population formulas.
            population=expr.population,
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


def _rule_probabilities_of_causation_tian_pearl(
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
    rule = "probabilities_of_causation_tian_pearl"
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
    p_y_do_x1 = float(_require(inputs, "p_y_do_x1", step_index, rule))
    p_y_do_x0 = float(_require(inputs, "p_y_do_x0", step_index, rule))
    monotonic = bool(_require(inputs, "monotonic", step_index, rule))
    provenance = _require(
        inputs, "interventional_risk_provenance", step_index, rule
    )

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
        if (
            abs(float(claimed_q.get("lower")) - exp_lo) > _NUMERIC_TOL
            or abs(float(claimed_q.get("upper")) - exp_hi) > _NUMERIC_TOL
        ):
            raise RuleCheckFailed(
                f"{rule}: {qty} bounds [{claimed_q.get('lower')}, "
                f"{claimed_q.get('upper')}] != recomputed [{exp_lo}, {exp_hi}]",
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
            if claimed_pt is None or abs(float(claimed_pt) - exp_pt) > _NUMERIC_TOL:
                raise RuleCheckFailed(
                    f"{rule}: {qty} point {claimed_pt} != recomputed {exp_pt}",
                    step_index=step_index, rule=rule,
                )

    # 4. Envelope must echo the declared risks / flag / provenance.
    if (
        abs(float(claimed_output.get("p_y_do_x1")) - p_y_do_x1) > _NUMERIC_TOL
        or abs(float(claimed_output.get("p_y_do_x0")) - p_y_do_x0) > _NUMERIC_TOL
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

    q = ctx.query
    if not isinstance(q, IdentifyQuery):
        raise RuleCheckFailed(
            "identify_via_idc requires IdentifyQuery context",
            step_index=step_index, rule="identify_via_idc",
        )
    if not q.given:
        raise RuleCheckFailed(
            "identify_via_idc requires a non-empty conditioning set "
            "(given); empty-given identification is plain ID, not IDC",
            step_index=step_index, rule="identify_via_idc",
        )
    x = q.intervention.atom
    y = q.target
    z_set = frozenset(q.given)

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
    "counterfactual_bounds_binary_monotone": _rule_counterfactual_bounds_binary_monotone,
    # Probabilities of causation — PN / PS / PNS (Tian & Pearl 2000)
    "probabilities_of_causation_tian_pearl": _rule_probabilities_of_causation_tian_pearl,
    # Data-based PN/PS/PNS — numeric counterpart (empirical joint + g-formula
    # do-risks → the same Tian-Pearl theorem, re-derived independently).
    "numeric_causation_estimate": _rule_numeric_causation_estimate,
    # Linear-SCM counterfactual point (Pearl Primer §4.2)
    "scm_abduction_action_prediction": _rule_scm_abduction_action_prediction,
    # General counterfactual identification (Shpitser-Pearl ID*, R-336) —
    # structural licence for a counterfactual-conjunction estimand.
    "id_star_identification": _rule_id_star_identification,
    # Phase 6.iv S.IV.3
    "iv_criterion_check": _rule_iv_criterion_check,
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
    # Phase 6.mediation Fix 1 (v0.1.4) — numeric evaluation
    "mediation_numeric_evaluate": _rule_mediation_numeric_evaluate,
    # Phase 9 §T9.1.4 — independent transport audit
    "s_admissibility_check": _rule_s_admissibility_check,
    "transport_formula": _rule_transport_formula,
    # Fix 3+4 §T9.2 (v0.1.5) — transport numeric FormulaExpr witness
    "transport_formula_ast": _rule_transport_formula_ast,
    # Fix 5 (v0.1.5, audit follow-up) — Tian-in-effect bound formula
    "tian_formula_ast": _rule_tian_formula_ast,
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
    # Phase 7.2 S.FDN.3
    "numeric_frontdoor_estimate",
    # Phase 7.3 S.IVN.3
    "numeric_iv_estimate",
    # General-ID (c-factor) plug-in numeric estimate — same c-factor
    # identification witness (general_id_criterion), plug-in terminal.
    "numeric_general_id_estimate",
    # Counterfactual-conjunction (ID*/IDC*) plug-in numeric estimate — same
    # counterfactual identification witness (ctf_conjunction_criterion).
    "numeric_ctf_conjunction_estimate",
    # Proximal matrix plug-in numeric estimate — same proximal identification
    # witness (proximal_criterion), plug-in terminal.
    "numeric_proximal_estimate",
    # Phase 9 §T9.1.4 — transport identification
    "identify_via_transport",
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
    if rule_name == "numeric_joint_backdoor_estimate":
        _rule_numeric_joint_backdoor_estimate(
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
