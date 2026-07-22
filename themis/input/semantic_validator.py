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
- ``query_atoms_in_V``:    every atom referenced by a cause / assoc /
                          identify / effect query is a node in G(M).
                          Probability queries are intentionally exempt
                          — they are pure distributional lookups and
                          may reference atoms that live only in Theta.

Reserved for later slices:

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
    BidirectedStatement,
    SelectionNode,
    MissingnessIndicator,
    CausationQuery,
    CounterfactualAssumptions,
    CounterfactualConjunctionQuery,
    ProximalEffectQuery,
    CounterfactualEvent,
    CounterfactualQuery,
    CauseQuery,
    CauseStatement,
    ConstTerm,
    EffectQuery,
    EffectQueryAssumptions,
    IdentifyQuery,
    Intervention,
    Monotonicity,
    ObservationStatement,
    ProbabilityQuery,
    ProbabilityStatement,
    Program,
    RelativeTimeIndex,
    QueryStatement,
    SCMCounterfactualQuery,
    Term,
    ValuedAtom,
    VariableDeclaration,
    VarTerm,
)

SLICE_1_CHECKS: frozenset[str] = frozenset(
    {
        "objects",
        "forall_usage",
        "bound_variables",
        "ground_observations",
        "ground_queries",
        "unique_variable_declarations",
        "bidirected_runtime_gate",
        "transport_runtime_gate",
        "temporal_monotonicity",
        # Fix 3+4 (v0.1.5): llm_prior provenance demands a non-empty
        # annotations.source so the audit-trail review surface
        # (extensions.llm_proposed_review) has a reason string per
        # entry. Empty / null source on llm_prior would let LLM
        # silently launder fabricated numbers without disclosure.
        "llm_prior_requires_source",
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
    ti = d.get("time_index")
    time_index = None
    if ti is not None:
        time_index = RelativeTimeIndex(value=ti["value"])
    return Atom(
        predicate=d["predicate"],
        args=tuple(_to_term(t) for t in d["args"]),
        time_index=time_index,
    )


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
        mediator_raw = d.get("mediator")
        # Iter 131: parse first-class assumptions field on EffectQuery
        # (parallel to CounterfactualQuery.assumptions). Backwards-
        # compat: scheduler still falls back to program.extensions
        # when this is absent.
        eq_assumptions_raw = d.get("assumptions")
        eq_assumptions = None
        if eq_assumptions_raw is not None:
            mono = eq_assumptions_raw.get("monotonicity")
            eq_assumptions = EffectQueryAssumptions(
                monotonicity=Monotonicity(mono) if mono else None,
            )
        extra_raw = d.get("extra_interventions") or ()
        mediators_raw = d.get("mediators") or ()
        return EffectQuery(
            target=_to_grounded(d["target"]),
            intervention=_to_intervention(d["intervention"]),
            extra_interventions=tuple(_to_intervention(iv) for iv in extra_raw),
            given=tuple(_to_grounded(a) for a in d["given"]),
            mediator=_to_atom(mediator_raw) if mediator_raw is not None else None,
            mediators=tuple(_to_atom(a) for a in mediators_raw),
            target_population=d.get("target_population"),
            assumptions=eq_assumptions,
        )
    if k == "identify":
        return IdentifyQuery(
            target=_to_atom(d["target"]),
            intervention=_to_intervention(d["intervention"]),
            given=tuple(_to_atom(a) for a in d["given"]),
            target_population=d.get("target_population"),
        )
    if k == "probability":
        return ProbabilityQuery(
            target=_to_grounded(d["target"]),
            given=tuple(_to_grounded(a) for a in d["given"]),
        )
    if k == "counterfactual":
        assumptions_raw = d.get("assumptions")
        assumptions = None
        if assumptions_raw is not None:
            assumptions = CounterfactualAssumptions(
                monotonicity=(
                    Monotonicity(assumptions_raw["monotonicity"])
                    if assumptions_raw.get("monotonicity") is not None
                    else None
                )
            )
        return CounterfactualQuery(
            observed=_to_grounded(d["observed"]),
            counterfactual_intervention=_to_intervention(
                d["counterfactual_intervention"]
            ),
            counterfactual_target=_to_grounded(d["counterfactual_target"]),
            assumptions=assumptions,
            factual_target_known=d.get("factual_target_known"),
            experimental_risk_treated=d.get("experimental_risk_treated"),
            experimental_risk_control=d.get("experimental_risk_control"),
        )
    if k == "causation":
        return CausationQuery(
            cause=_to_atom(d["cause"]),
            effect=_to_atom(d["effect"]),
            monotonic=bool(d.get("monotonic", False)),
            experimental_risk_treated=d.get("experimental_risk_treated"),
            experimental_risk_control=d.get("experimental_risk_control"),
        )
    if k == "scm_counterfactual":
        return SCMCounterfactualQuery(
            intervention=_to_intervention(d["intervention"]),
            target=_to_atom(d["target"]),
        )
    if k == "counterfactual_conjunction":
        def _to_ctf_events(raw):
            return tuple(
                CounterfactualEvent(
                    variable=_to_atom(e["variable"]),
                    subscript=tuple(
                        _to_grounded(s) for s in e.get("subscript", ())
                    ),
                    value=e["value"],
                )
                for e in raw
            )
        return CounterfactualConjunctionQuery(
            events=_to_ctf_events(d["events"]),
            condition=_to_ctf_events(d.get("condition", ())),
        )
    if k == "proximal_effect":
        return ProximalEffectQuery(
            treatment=_to_atom(d["treatment"]),
            outcome=_to_atom(d["outcome"]),
            latent=_to_atom(d["latent"]),
            treatment_proxy=_to_atom(d["treatment_proxy"]),
            outcome_proxy=_to_atom(d["outcome_proxy"]),
            latent_cardinality=int(d["latent_cardinality"]),
        )
    raise SemanticError(f"unknown query kind: {k}")


def _to_statement(d: dict):
    k = d["kind"]
    if k == "cause":
        return CauseStatement(
            from_atom=_to_atom(d["from"]),
            to_atom=_to_atom(d["to"]),
            forall=tuple(d.get("forall", ())),
            annotations=_to_annotation(d.get("annotations")),
            coefficient=d.get("coefficient"),
        )
    if k == "bidirected":
        return BidirectedStatement(
            left=_to_atom(d["left"]),
            right=_to_atom(d["right"]),
            forall=tuple(d.get("forall", ())),
            annotations=_to_annotation(d.get("annotations")),
        )
    if k == "selection_node":
        return SelectionNode(
            id=d["id"],
            affects=_to_atom(d["affects"]),
            source_population=d["source_population"],
            target_population=d["target_population"],
            annotations=_to_annotation(d.get("annotations")),
        )
    if k == "missingness_indicator":
        return MissingnessIndicator(
            id=d["id"],
            missing_var=_to_atom(d["missing_var"]),
            caused_by=tuple(_to_atom(a) for a in d.get("caused_by", ())),
            annotations=_to_annotation(d.get("annotations")),
        )
    if k == "probability":
        return ProbabilityStatement(
            target=_to_grounded(d["target"]),
            given=tuple(_to_grounded(a) for a in d["given"]),
            value=d["value"],
            forall=tuple(d.get("forall", ())),
            population=d.get("population"),
            provenance=d.get("provenance", "structural"),
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
    if k == "variable":
        domain = d.get("domain")
        return VariableDeclaration(
            predicate=d["predicate"],
            domain=tuple(domain) if domain is not None else None,
            time_window=d.get("time_window"),
            measurement=d.get("measurement"),
            threshold=d.get("threshold"),
            observability=d.get("observability"),
            unit=d.get("unit"),
            direction=d.get("direction"),
            baseline=d.get("baseline"),
            state_vs_event=d.get("state_vs_event"),
            scale=d.get("scale"),
        )
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
    if isinstance(stmt, BidirectedStatement):
        return (stmt.left, stmt.right)
    if isinstance(stmt, SelectionNode):
        return (stmt.affects,)
    if isinstance(stmt, MissingnessIndicator):
        return (stmt.missing_var, *stmt.caused_by)
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
                *(iv.atom for iv in q.extra_interventions),
                *(_as_atom(g) for g in q.given),
            )
        if isinstance(q, IdentifyQuery):
            return (q.target, q.intervention.atom, *q.given)
        if isinstance(q, ProbabilityQuery):
            return (_as_atom(q.target), *(_as_atom(g) for g in q.given))
        if isinstance(q, CounterfactualQuery):
            return (
                _as_atom(q.observed),
                q.counterfactual_intervention.atom,
                _as_atom(q.counterfactual_target),
            )
        if isinstance(q, CausationQuery):
            return (q.cause, q.effect)
        if isinstance(q, SCMCounterfactualQuery):
            return (q.intervention.atom, q.target)
        if isinstance(q, CounterfactualConjunctionQuery):
            return tuple(
                a
                for e in (*q.events, *q.condition)
                for a in (e.variable, *(s.atom for s in e.subscript))
            )
        if isinstance(q, ProximalEffectQuery):
            return (
                q.treatment, q.outcome, q.latent,
                q.treatment_proxy, q.outcome_proxy,
            )
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
        if not isinstance(stmt, (CauseStatement, BidirectedStatement, ProbabilityStatement)):
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


def _check_unique_variable_declarations(program: Program) -> None:
    """Slice A0 follow-up: a predicate may have at most one
    ``variableDeclaration``. Duplicate declarations used to silently
    overwrite each other in ``framing_check._declarations_by_predicate``,
    so framing would depend on statement order rather than on a stable
    predicate definition.

    Authors who want to change a predicate's metadata should edit the
    one declaration, not stack a second one on top.
    """
    seen: dict[str, int] = {}
    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, VariableDeclaration):
            continue
        if stmt.predicate in seen:
            first = seen[stmt.predicate]
            raise SemanticError(
                f"statements[{idx}]: predicate '{stmt.predicate}' "
                f"already declared at statements[{first}]; a predicate "
                f"may have at most one variableDeclaration"
            )
        seen[stmt.predicate] = idx


def _check_bidirected_runtime_gate(program: Program) -> None:
    """Phase 2.latent S3.a guard (narrowed from S1).

    When a program contains any ``BidirectedStatement``, dispatch is
    allowed only for query kinds whose runtime path explicitly reads
    the bidirected edge set: ``identify`` / ``effect`` (ADMG-aware
    identification) and ``assoc`` (S4 m-separation). ``cause`` and
    ``probability`` still use directed-skeleton / CPT semantics and
    remain gated so the failure cannot be mistaken for a silent drop.

    S4 lifts this gate entirely once every dispatch path reads the
    bidirected edge set.
    """
    has_bidirected = any(
        isinstance(s, BidirectedStatement) for s in program.statements
    )
    if not has_bidirected:
        return

    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, QueryStatement):
            continue
        q = stmt.query
        if isinstance(q, (CauseQuery, ProbabilityQuery)):
            kind_name = {
                CauseQuery: "cause",
                ProbabilityQuery: "probability",
            }[type(q)]
            raise SemanticError(
                f"statements[{idx}] ({stmt.id}): {kind_name} query on "
                f"a program containing bidirected edges is not yet "
                f"supported. Phase 2.latent S4 supports assoc via "
                f"m-separation and identify / effect via ADMG-aware "
                f"identification; the remaining dispatch paths become "
                f"ADMG-aware later. See "
                f"PHASE_2_LATENT_CHARTER.md §7."
            )


def _check_transport_runtime_gate(program: Program) -> None:
    """Phase 9 §T9.1.2 → S.T9.1.3 lifted (kept as a no-op stub).

    Pre-S.T9.1.3 this check raised SemanticError on any query with
    ``target_population`` set, because the dispatch path didn't exist.
    S.T9.1.3 added ``transport.identify_via_transport`` and the
    EffectQuery dispatch branch to handle it. The gate is now a no-op,
    retained in the registry for symmetry with the bidirected gate
    (so future versions can re-narrow it if needed without renaming).

    Identify queries with ``target_population`` are still gated below
    until §T9.2 lands their dispatch path.
    """
    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, QueryStatement):
            continue
        if isinstance(stmt.query, IdentifyQuery) and getattr(
            stmt.query, "target_population", None
        ) is not None:
            raise SemanticError(
                f"statements[{idx}] ({stmt.id}): identify query with "
                f"target_population={stmt.query.target_population!r} is not "
                f"yet supported (only effect queries support transport in "
                f"S.T9.1.3). See PHASE_9_TRANSPORT_CHARTER.md §3."
            )


def _check_temporal_monotonicity(program: Program) -> None:
    """Phase 5 §T / T1 enforcement: a `cause` whose source carries a
    later time_index than its destination is rejected — there is no
    coherent "tomorrow's X causes today's Y" semantics.

    Rules:
    - If both endpoints carry a time_index, src.value <= dst.value.
    - If only one endpoint carries a time_index, no constraint
      (atemporal endpoint sits on the virtual atemporal index, ordering
      with a temporal endpoint is undefined and out-of-scope).
    - Bidirected statements: same rule applies symmetrically because
      bidirected coupling implies a shared latent that exists across
      both endpoints' time slices — but in this slice we only enforce
      directed-cause ordering. Bidirected ordering (if any future case
      drives it) lands in a separate check.

    The verifier already has T1_time_monotonicity as a primitive but
    runtime never wired it in — this semantic check is the runtime-side
    enforcement that mirrors the verifier rule.
    """
    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, CauseStatement):
            continue
        src_ti = stmt.from_atom.time_index
        dst_ti = stmt.to_atom.time_index
        if src_ti is None or dst_ti is None:
            continue
        if src_ti.value > dst_ti.value:
            raise SemanticError(
                f"statements[{idx}]: cause direction violates time "
                f"monotonicity — source '{stmt.from_atom.predicate}' at "
                f"t={src_ti.value} is later than destination "
                f"'{stmt.to_atom.predicate}' at t={dst_ti.value}. "
                f"Causes cannot run backwards in time. Phase 5 §T / T1."
            )


def _check_llm_prior_requires_source(program: Program) -> None:
    """Fix 3+4 §3.1 (v0.1.5): every probability statement tagged
    ``provenance == "llm_prior"`` must carry a non-empty
    ``annotations.source`` string. The source field is the audit-trail
    reason that surfaces in ``extensions.llm_proposed_review``; if it's
    empty / null / whitespace, the end user has no way to evaluate
    whether the LLM-proposed number is reasonable. Empty source on
    llm_prior would let the LLM silently launder fabricated values
    without disclosure — a direct violation of Themis's "kernel
    doesn't fabricate" contract.

    Charter requires the source to be a one-sentence reason; we
    enforce non-empty here (semantic minimum), the Skill enforces
    "useful sentence" (prompt minimum).
    """
    for idx, stmt in enumerate(program.statements):
        if not isinstance(stmt, ProbabilityStatement):
            continue
        if stmt.provenance != "llm_prior":
            continue
        ann = stmt.annotations
        source = ann.source if ann is not None else None
        if source is None or not source.strip():
            raise SemanticError(
                f"statements[{idx}]: probabilityStatement with "
                f"provenance='llm_prior' requires a non-empty "
                f"annotations.source (a one-sentence reason that will "
                f"appear in extensions.llm_proposed_review for end-user "
                f"audit). LLM-proposed priors without a stated reason "
                f"are silent fabrication — Themis refuses to launder "
                f"them through the audit channel. Fix 3+4 charter §3.1."
            )


_CHECK_FUNCS = {
    "objects": _check_objects,
    "forall_usage": _check_forall_usage,
    "bound_variables": _check_bound_variables,
    "ground_observations": _check_ground_observations,
    "ground_queries": _check_ground_queries,
    "unique_variable_declarations": _check_unique_variable_declarations,
    "bidirected_runtime_gate": _check_bidirected_runtime_gate,
    "transport_runtime_gate": _check_transport_runtime_gate,
    "temporal_monotonicity": _check_temporal_monotonicity,
    "llm_prior_requires_source": _check_llm_prior_requires_source,
}


# ---------------------------------------------------------------------------
# graph-level checks (run post-instantiation)
# ---------------------------------------------------------------------------

GRAPH_LEVEL_CHECKS: frozenset[str] = frozenset(
    {"probability_parents", "query_atoms_in_V"}
)


def _check_probability_parents(
    ground_statements, graph, *, bidirected: "frozenset[frozenset]" = frozenset(),
) -> None:
    """Every ground probability statement's ``given`` set must be a
    subset of the target atom's structural parents in ``G(M)`` —
    OR (iter 168) any atom that reaches target via a directed or
    bidirected path (admissible Tian c-factor topo-predecessors).

    A model parameter is a conditional on the target's parent set (or
    a marginal over a subset of them). Allowing arbitrary conditionals
    into Theta silently admits statements that are not CPT entries and
    whose values cannot be consumed by identification formulas without
    contradiction.

    Iter 167 attempted a narrower bidirected-sibling-only loosen but
    the disjoint-Y case revealed Tian's c-factor product needs the
    full topo-predecessor closure (Y's V_{<Y} = {X, Z1, Z2} where X
    is a grandparent through Z1↔Z2). Iter 168 implements the closure
    via directed-or-bidirected reachability — atoms with any path to
    target may appear in ``given``.
    """
    import networkx as nx
    for idx, stmt in enumerate(ground_statements):
        if not isinstance(stmt, ProbabilityStatement):
            continue
        # Iter 2026-05-14 (CLadder Q6772 collider-conditioning fix):
        # observational provenance means this entry is an empirical /
        # joint-derived conditional, not a structural CPT. Skip the
        # parent-subset enforcement — given can contain descendants
        # or other non-parent atoms. Safe because identification
        # algorithms (backdoor, front-door, ID) request structural-
        # parent-aligned keys; observational keys won't match those
        # shapes, so identification naturally won't use them. Direct
        # lookups in associational / probability queries will find
        # observational entries via exact (target, given) match.
        if stmt.provenance == "observational":
            continue
        target_atom = stmt.target.atom
        if target_atom in graph:
            parents = set(graph.predecessors(target_atom))
            ancestors = set(nx.ancestors(graph, target_atom))
        else:
            parents = set()
            ancestors = set()
        # Iter 168: admissible = parents ∪ directed-ancestors ∪
        # bidirected-siblings. Tian's c-factor product factors over
        # topo predecessors (which may include directed ancestors
        # like X → Z1 → Y for P(Y|X,Z1) when iterating chain rule
        # within a c-component) AND bidirected siblings (because
        # topo within a c-component puts them in arbitrary order;
        # validator can't know which order Tian will pick).
        bidir_siblings: set = set()
        for pair in bidirected:
            if target_atom in pair:
                bidir_siblings.update(a for a in pair if a != target_atom)
        admissible = parents | ancestors | bidir_siblings
        given_atoms = {va.atom for va in stmt.given}
        extra = given_atoms - admissible
        if extra:
            extra_names = sorted(a.predicate for a in extra)
            parent_names = sorted(a.predicate for a in parents)
            raise SemanticError(
                f"ground_statements[{idx}]: probability.given includes "
                f"{extra_names} which are not structural parents of "
                f"{target_atom.predicate} (parents={parent_names}). "
                f"given must be a subset of parents(target). "
                f"Fix options: (1) if {extra_names} truly are causes of "
                f"{target_atom.predicate}, add the missing 'cause' "
                f"statement(s) so they become structural parents; "
                f"(2) drop {extra_names} from given and supply a "
                f"marginalized CPT P({target_atom.predicate}|"
                f"{parent_names}) instead; (3) if you're hand-rolling a "
                f"Tian/ADMG c-factor product (which conditions on full "
                f"topo predecessors, not just structural parents — see "
                f"wall.md iter 150), the kernel doesn't yet support that "
                f"end-to-end. Use themis.estimate(...) with raw data, "
                f"or wait for joint-CPT support."
            )


def _query_structural_atoms(q) -> tuple[Atom, ...]:
    """Return the atoms a structural query references.

    Probability queries are intentionally excluded: they are
    distributional lookups that may reference atoms living only in
    Theta, not in the causal DAG.
    """
    if isinstance(q, CauseQuery):
        return (q.from_atom, q.to_atom)
    if isinstance(q, AssocQuery):
        return (q.left, q.right, *q.given)
    if isinstance(q, IdentifyQuery):
        return (q.target, q.intervention.atom, *q.given)
    if isinstance(q, EffectQuery):
        return (
            q.target.atom,
            q.intervention.atom,
            *(iv.atom for iv in q.extra_interventions),
            *(g.atom for g in q.given),
        )
    if isinstance(q, CounterfactualQuery):
        return (
            q.observed.atom,
            q.counterfactual_intervention.atom,
            q.counterfactual_target.atom,
        )
    if isinstance(q, CausationQuery):
        return (q.cause, q.effect)
    if isinstance(q, SCMCounterfactualQuery):
        return (q.intervention.atom, q.target)
    if isinstance(q, CounterfactualConjunctionQuery):
        return tuple(
            a
            for e in (*q.events, *q.condition)
            for a in (e.variable, *(s.atom for s in e.subscript))
        )
    if isinstance(q, ProximalEffectQuery):
        return (
            q.treatment, q.outcome, q.latent,
            q.treatment_proxy, q.outcome_proxy,
        )
    return ()


def _check_query_atoms_in_V(ground_statements, graph) -> None:
    """Every atom referenced by a cause / assoc / identify / effect
    query must be a node in the instantiated working graph G(M).

    Silent False for undeclared query atoms is the same class of bug
    as patterned-query-answered-False caught by ``ground_queries`` in
    slice 2; catching it at validation time keeps the four-state
    contract honest.
    """
    for idx, stmt in enumerate(ground_statements):
        if not isinstance(stmt, QueryStatement):
            continue
        atoms = _query_structural_atoms(stmt.query)
        if not atoms:
            continue
        missing = [a for a in atoms if a not in graph]
        if missing:
            names = sorted({a.predicate for a in missing})
            # A missing atom that DOES appear in a bidirected edge is a
            # different, more confusing situation than a truly undeclared
            # one: the user declared it, but only as a latent-confounding
            # endpoint with no directed causal role, so it never entered
            # the variable set V (built from cause edges). Name that
            # precisely — the canonical case is conditioning on an M-bias
            # collider — instead of the misleading "no cause edge
            # introduces them", which reads as "you forgot to declare it".
            bidir_atoms = {
                a
                for s in ground_statements
                if isinstance(s, BidirectedStatement)
                for a in (s.left, s.right)
            }
            bidir_only = sorted({
                a.predicate for a in missing if a in bidir_atoms
            })
            if bidir_only:
                raise SemanticError(
                    f"ground_statements[{idx}] ({stmt.id}): query references "
                    f"atom(s) {bidir_only} that appear ONLY in bidirected "
                    f"(latent-confounding) edges and so are not in the "
                    f"variable set V — a bidirected endpoint has no directed "
                    f"causal role. Conditioning on a purely latent-confounded "
                    f"node (the M-bias structure) is not supported; give the "
                    f"node a directed (cause) edge if it has an observed "
                    f"causal role."
                )
            raise SemanticError(
                f"ground_statements[{idx}] ({stmt.id}): query references "
                f"atom(s) {names} that are not in the instantiated "
                f"variable set V (no cause edge introduces them)"
            )


_GRAPH_CHECK_FUNCS = {
    "probability_parents": _check_probability_parents,
    "query_atoms_in_V": _check_query_atoms_in_V,
}


def validate_against_graph(
    ground_statements,
    graph,
    checks: frozenset[str] | None = None,
    *,
    bidirected: "frozenset[frozenset]" = frozenset(),
) -> None:
    """Run post-instantiation semantic checks that need the working graph.

    Call this after ``instantiation.instantiate`` +
    ``graph_projection.project``. ``checks`` defaults to
    ``GRAPH_LEVEL_CHECKS``. Raises SemanticError on violation.

    ``bidirected`` (iter 167): the ADMG's bidirected edge set. When
    provided, the probability_parents check loosens its
    ``given ⊆ structural_parents`` rule to also accept bidirected
    siblings of the target — needed for Tian's c-factor product
    Q[S] = ∏ P(V_i | V_{<i}) which factors over topo predecessors
    that may include latent-confounder-linked variables (see wall.md
    iter 150 + iter 165 xfail-strict tracker).
    """
    checks = checks if checks is not None else GRAPH_LEVEL_CHECKS
    for name in checks:
        func = _GRAPH_CHECK_FUNCS.get(name)
        if func is None:
            raise SemanticError(f"unknown graph-level check: {name}")
        if name == "probability_parents":
            func(ground_statements, graph, bidirected=bidirected)
        else:
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
        options=ast.get("options"),
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
        FractionExpr,
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
        if isinstance(node, FractionExpr):
            # Numerator and denominator are independent sub-formulas; a
            # sum binder on one side does NOT scope into the other, so
            # each is checked under the SAME inherited `bound` (IDC never
            # binds a name spanning the ratio bar).
            check(node.numerator, bound)
            check(node.denominator, bound)
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
