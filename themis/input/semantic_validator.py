"""Semantic validation of a syntactically-valid AST.

This layer enforces rules that cannot be expressed in the JSON Schema.
Two entry points exist, distinguished by what they need:

``validate_program(ast, checks=...)`` — dict-level checks that do not
require the compiled working graph. These run before instantiation.

``validate_against_graph(ground_statements, graph, checks=...)`` —
post-instantiation checks that reference ``G(M)``. These run after
``instantiation.instantiate`` + ``graph_projection.project``.

Program-level (pre-graph) checks:

- ``objects``:            every constant in an atom is declared in D.
- ``forall_usage``:       every forall variable is actually used in
                          the statement's atoms.
- ``bound_variables``:    every VarTerm in cause / probability
                          statements is declared in forall.
- ``ground_observations``: observation atoms contain no VarTerm.
- ``ground_queries``:     query atoms contain no VarTerm (v0.1 only
                          answers ground queries; patterned queries
                          are out-of-language for now).

Graph-level (post-projection) checks:

- ``probability_parents``: probability.given ⊆ parents(target) in
                          G(M). Prevents probability statements whose
                          conditioning set is incompatible with the
                          declared causal structure from silently
                          feeding Theta and corrupting identification.

Reserved for later slices:

- ``query_atoms_in_V``:    query atoms belong to the instantiated V
- ``formula_wellformed``:  no free value variables, sum.over ground
  (already callable as ``validate_formula``)

On success ``validate_program`` returns a typed ``Program`` object;
``validate_against_graph`` returns nothing.
"""
from __future__ import annotations

from ..types import (
    Annotation,
    AssocQuery,
    Atom,
    CauseQuery,
    CauseStatement,
    ConstTerm,
    EffectQuery,
    IdentifyQuery,
    Intervention,
    ObservationStatement,
    ProbabilityQuery,
    ProbabilityStatement,
    Program,
    QueryStatement,
    Term,
    ValuedAtom,
    VarTerm,
)

SLICE_1_CHECKS: frozenset[str] = frozenset(
    {
        "objects",
        "forall_usage",
        "bound_variables",
        "ground_observations",
        "ground_queries",
    }
)


class SemanticError(Exception):
    """Raised when the AST violates a semantic rule."""


# ---------------------------------------------------------------------------
# dict -> typed object conversion
# ---------------------------------------------------------------------------

def _to_term(d: dict) -> Term:
    if d["type"] == "const":
        return ConstTerm(name=d["name"])
    return VarTerm(name=d["name"])


def _to_atom(d: dict) -> Atom:
    return Atom(predicate=d["predicate"], args=tuple(_to_term(t) for t in d["args"]))


def _to_annotation(d: dict | None) -> Annotation | None:
    if d is None:
        return None
    return Annotation(confidence=d.get("confidence"), source=d.get("source"))


def _to_intervention(d: dict) -> Intervention:
    return Intervention(atom=_to_atom(d["atom"]), value=d["value"])


def _to_grounded(d: dict) -> ValuedAtom:
    """Parse a groundedAtom ({atom, value}) from the schema into a
    ValuedAtom. The schema guarantees ``value`` is a concrete literal
    here (no VarRef, no None); ValuedAtom's broader type accommodates
    this without extra runtime checks."""
    return ValuedAtom(atom=_to_atom(d["atom"]), value=d["value"])


def _to_query(d: dict):
    k = d["kind"]
    if k == "cause":
        return CauseQuery(from_atom=_to_atom(d["from"]), to_atom=_to_atom(d["to"]))
    if k == "assoc":
        return AssocQuery(
            left=_to_atom(d["left"]),
            right=_to_atom(d["right"]),
            given=tuple(_to_atom(a) for a in d["given"]),
        )
    if k == "effect":
        return EffectQuery(
            target=_to_grounded(d["target"]),
            intervention=_to_intervention(d["intervention"]),
            given=tuple(_to_grounded(a) for a in d["given"]),
        )
    if k == "identify":
        return IdentifyQuery(
            target=_to_atom(d["target"]),
            intervention=_to_intervention(d["intervention"]),
            given=tuple(_to_atom(a) for a in d["given"]),
        )
    if k == "probability":
        return ProbabilityQuery(
            target=_to_grounded(d["target"]),
            given=tuple(_to_grounded(a) for a in d["given"]),
        )
    raise SemanticError(f"unknown query kind: {k}")


def _to_statement(d: dict):
    k = d["kind"]
    if k == "cause":
        return CauseStatement(
            from_atom=_to_atom(d["from"]),
            to_atom=_to_atom(d["to"]),
            forall=tuple(d.get("forall", ())),
        )
    if k == "probability":
        return ProbabilityStatement(
            target=_to_grounded(d["target"]),
            given=tuple(_to_grounded(a) for a in d["given"]),
            value=d["value"],
            forall=tuple(d.get("forall", ())),
            annotations=_to_annotation(d.get("annotations")),
        )
    if k == "observation":
        return ObservationStatement(
            atom=_to_atom(d["atom"]),
            value=d["value"],
            annotations=_to_annotation(d.get("annotations")),
        )
    if k == "query":
        return QueryStatement(id=d["id"], query=_to_query(d["query"]))
    raise SemanticError(f"unknown statement kind: {k}")


# ---------------------------------------------------------------------------
# semantic checks
# ---------------------------------------------------------------------------

def _as_atom(x) -> Atom:
    """Return the bare Atom from either an Atom or a ValuedAtom."""
    return x.atom if isinstance(x, ValuedAtom) else x


def _atoms_in_statement(stmt) -> tuple[Atom, ...]:
    if isinstance(stmt, CauseStatement):
        return (stmt.from_atom, stmt.to_atom)
    if isinstance(stmt, ProbabilityStatement):
        return (_as_atom(stmt.target), *(_as_atom(g) for g in stmt.given))
    if isinstance(stmt, ObservationStatement):
        return (stmt.atom,)
    if isinstance(stmt, QueryStatement):
        q = stmt.query
        if isinstance(q, CauseQuery):
            return (q.from_atom, q.to_atom)
        if isinstance(q, AssocQuery):
            return (q.left, q.right, *q.given)
        if isinstance(q, EffectQuery):
            return (
                _as_atom(q.target),
                q.intervention.atom,
                *(_as_atom(g) for g in q.given),
            )
        if isinstance(q, IdentifyQuery):
            return (q.target, q.intervention.atom, *q.given)
        if isinstance(q, ProbabilityQuery):
            return (_as_atom(q.target), *(_as_atom(g) for g in q.given))
    return ()


def _check_objects(program: Program) -> None:
    declared = set(program.objects)
    for idx, stmt in enumerate(program.statements):
        for atom in _atoms_in_statement(stmt):
            for arg in atom.args:
                if isinstance(arg, ConstTerm) and arg.name not in declared:
                    raise SemanticError(
                        f"statements[{idx}]: const '{arg.name}' used in "
                        f"predicate '{atom.predicate}' is not declared in domain.objects"
                    )


def _check_forall_usage(program: Program) -> None:
    for idx, stmt in enumerate(program.statements):
        forall = getattr(stmt, "forall", ())
        if not forall:
            continue
        used: set[str] = set()
        for atom in _atoms_in_statement(stmt):
            for arg in atom.args:
                if isinstance(arg, VarTerm):
                    used.add(arg.name)
        missing = set(forall) - used
        if missing:
            raise SemanticError(
                f"statements[{idx}]: forall variables {sorted(missing)} "
                f"declared but not used in atoms"
            )


def _var_names(atom: Atom) -> set[str]:
    return {a.name for a in atom.args if isinstance(a, VarTerm)}


def _check_bound_variables(program: Program) -> None:
    """Every VarTerm in cause / probability statements must be declared
    in the statement's forall list.

    Without this check, a stray ``{"type": "var", "name": "X"}`` slips
    through and becomes a permanent ghost node in the working graph.
    """
    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, (CauseStatement, ProbabilityStatement)):
            continue
        declared = set(stmt.forall)
        for atom in _atoms_in_statement(stmt):
            free = _var_names(atom) - declared
            if free:
                raise SemanticError(
                    f"statements[{idx}]: variables {sorted(free)} used "
                    f"in predicate '{atom.predicate}' but not declared "
                    f"in forall"
                )


def _check_ground_observations(program: Program) -> None:
    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, ObservationStatement):
            continue
        vars_used = _var_names(stmt.atom)
        if vars_used:
            raise SemanticError(
                f"statements[{idx}]: observation atom must be ground, "
                f"got free variables {sorted(vars_used)}"
            )


def _check_ground_queries(program: Program) -> None:
    """Queries must be ground in v0.1.

    A patterned query like ``cause(smokes(X), cancer(X))`` is rejected
    here rather than silently returning False because no graph node
    matches the variable-bearing atom.
    """
    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, QueryStatement):
            continue
        for atom in _atoms_in_statement(stmt):
            vars_used = _var_names(atom)
            if vars_used:
                raise SemanticError(
                    f"statements[{idx}] ({stmt.id}): query atom '{atom.predicate}' "
                    f"must be ground in v0.1, got free variables {sorted(vars_used)}"
                )


_CHECK_FUNCS = {
    "objects": _check_objects,
    "forall_usage": _check_forall_usage,
    "bound_variables": _check_bound_variables,
    "ground_observations": _check_ground_observations,
    "ground_queries": _check_ground_queries,
}


# ---------------------------------------------------------------------------
# graph-level checks (run post-instantiation)
# ---------------------------------------------------------------------------

GRAPH_LEVEL_CHECKS: frozenset[str] = frozenset({"probability_parents"})


def _check_probability_parents(ground_statements, graph) -> None:
    """Every ground probability statement's ``given`` set must be a
    subset of the target atom's structural parents in ``G(M)``.

    A model parameter is a conditional on the target's parent set (or
    a marginal over a subset of them). Allowing arbitrary conditionals
    into Theta silently admits statements that are not CPT entries and
    whose values cannot be consumed by identification formulas without
    contradiction.
    """
    for idx, stmt in enumerate(ground_statements):
        if not isinstance(stmt, ProbabilityStatement):
            continue
        target_atom = stmt.target.atom
        if target_atom in graph:
            parents = set(graph.predecessors(target_atom))
        else:
            parents = set()
        given_atoms = {va.atom for va in stmt.given}
        extra = given_atoms - parents
        if extra:
            extra_names = sorted(a.predicate for a in extra)
            parent_names = sorted(a.predicate for a in parents)
            raise SemanticError(
                f"ground_statements[{idx}]: probability.given includes "
                f"{extra_names} which are not structural parents of "
                f"{target_atom.predicate} (parents={parent_names}). "
                f"given must be a subset of parents(target)"
            )


_GRAPH_CHECK_FUNCS = {
    "probability_parents": _check_probability_parents,
}


def validate_against_graph(
    ground_statements,
    graph,
    checks: frozenset[str] | None = None,
) -> None:
    """Run post-instantiation semantic checks that need the working graph.

    Call this after ``instantiation.instantiate`` +
    ``graph_projection.project``. ``checks`` defaults to
    ``GRAPH_LEVEL_CHECKS``. Raises SemanticError on violation.
    """
    checks = checks if checks is not None else GRAPH_LEVEL_CHECKS
    for name in checks:
        func = _GRAPH_CHECK_FUNCS.get(name)
        if func is None:
            raise SemanticError(f"unknown graph-level check: {name}")
        func(ground_statements, graph)


# ---------------------------------------------------------------------------
# public entry
# ---------------------------------------------------------------------------

def validate_program(ast: dict, checks: frozenset[str] | None = None) -> Program:
    """Turn a syntactically-valid AST dict into a typed Program.

    ``checks`` selects which semantic rules to run. Defaults to
    SLICE_1_CHECKS. Later slices pass a larger set.

    Raises SemanticError on any violation.
    """
    checks = checks if checks is not None else SLICE_1_CHECKS

    program = Program(
        version=ast["version"],
        objects=tuple(o["name"] for o in ast["domain"]["objects"]),
        statements=tuple(_to_statement(s) for s in ast["statements"]),
        extensions=ast.get("extensions"),
    )

    for name in checks:
        func = _CHECK_FUNCS.get(name)
        if func is None:
            # Unknown check name is a programmer error, not user input.
            raise SemanticError(f"unknown semantic check: {name}")
        func(program)

    return program


def validate_formula(formula) -> None:
    """Check that a formula AST is well-formed.

    Rules enforced:
    - Every VarRef's name is bound by an enclosing SumExpr.
    - Every SumExpr.over is a ground atom (no VarTerm in args).

    Query-context ValuedAtoms (value is None) are accepted without
    binding — per formula_ast_spec_v0_1.md §3.3, their value is
    resolved externally.
    """
    from ..types import (
        ConstantExpr,
        ProbabilityRefExpr,
        ProductExpr,
        SumExpr,
        ValuedAtom,
        VarRef,
    )

    def check(node, bound: frozenset[str]) -> None:
        if isinstance(node, ConstantExpr):
            return
        if isinstance(node, ProbabilityRefExpr):
            _check_valued_atom(node.target, bound)
            for g in node.given:
                _check_valued_atom(g, bound)
            return
        if isinstance(node, ProductExpr):
            for t in node.terms:
                check(t, bound)
            return
        if isinstance(node, SumExpr):
            for arg in node.over.args:
                if isinstance(arg, VarTerm):
                    raise SemanticError(
                        f"sum.over must be ground; got VarTerm "
                        f"'{arg.name}' in predicate '{node.over.predicate}'"
                    )
            check(node.body, bound | {node.bind.name})
            return
        raise SemanticError(f"unknown formula node type: {type(node).__name__}")

    def _check_valued_atom(va: ValuedAtom, bound: frozenset[str]) -> None:
        if va.value is None:
            return  # query-bound, exempt from free-variable check
        if isinstance(va.value, VarRef):
            if va.value.name not in bound:
                raise SemanticError(
                    f"free VarRef '{va.value.name}' in formula; "
                    f"no enclosing sum binds this name"
                )

    check(formula, frozenset())
