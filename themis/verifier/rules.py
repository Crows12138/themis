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

from typing import Any, Callable

import networkx as nx

from ..runtime.numeric_estimator import ProbabilityKey, Theta
from ..types import (
    Atom,
    BindDecl,
    ConstantExpr,
    FormulaExpr,
    IdentifyQuery,
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

    if leg_i:
        leg_ii = _check_d_separation(
            _graph_minus_x_outgoing(graph, x), x, y, conditioning
        )
        recomputed = leg_ii
    else:
        recomputed = False

    if recomputed != bool(claimed_output):
        raise RuleCheckFailed(
            f"backdoor_criterion claimed {claimed_output!r}, recomputed "
            f"{recomputed!r} (leg_i={leg_i})",
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
) -> float:
    """Verifier's independent recursive evaluator for FormulaExpr.

    Does NOT call ``themis.runtime.numeric_estimator.estimate_formula``.
    The two evaluators must agree on every concrete value — that
    agreement is what makes R7 meaningful.
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
            raise _NonConcreteValue(
                f"theta has no entry for P({expr.target.atom.predicate}="
                f"{target_value})"
            )
        return float(value)
    if isinstance(expr, ProductExpr):
        result = 1.0
        for t in expr.terms:
            result *= _evaluate_formula(t, theta, subs)
        return result
    if isinstance(expr, SumExpr):
        total = 0.0
        for v in theta.domain_of(expr.over):
            new_subs = dict(subs)
            new_subs[expr.bind.name] = v
            total += _evaluate_formula(expr.body, theta, new_subs)
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
        recomputed = _evaluate_formula(formula, ctx.theta, {})
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
    if eval_step.rule not in ("formula_evaluation", "probability_ref_lookup"):
        raise RuleCheckFailed(
            f"numeric_result: evaluation must reference a formula_evaluation "
            f"or probability_ref_lookup step, got {eval_step.rule!r}",
            step_index=step_index, rule="numeric_result",
        )
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


# ========================================================== registry

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
    "probability_ref_lookup": _rule_probability_ref_lookup,
    "formula_evaluation": _rule_formula_evaluation,
}
_STEP_REF_RULES = {"identify_via_backdoor", "numeric_result"}


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
    if rule_name == "numeric_result":
        _rule_numeric_result(
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
