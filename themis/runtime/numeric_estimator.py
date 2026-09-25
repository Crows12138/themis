"""Numeric estimation of probabilities and formulas.

Wiring (v0.1, after slice 6):

- ``Theta`` is a real parameter store: dict keyed by ``ProbabilityKey``
  plus per-atom value domains. The domains are populated by
  ``theta_builder`` from every literal value observed in the program's
  ``ValuedAtom`` positions (probability target / given, observation
  value); an atom that never appears in such a position takes its
  variable's declared values, and the boolean default only when there is
  no declaration.
- ``estimate_formula`` recursively evaluates ``constant`` /
  ``probability_ref`` / ``product`` / ``sum`` nodes, substituting
  ``VarRef`` names bound by enclosing sums.
- ``InsufficientTheta`` is raised with the precise lookup key that
  failed, so the scheduler can build a ``MissingItem`` that points to
  the exact conditional the caller must still provide.

Behaviour in context:

- ``scheduler._dispatch_effect`` and ``_dispatch_probability`` run the
  evaluator against the Theta built from the program's probability
  statements. When every referenced conditional is present, the query
  resolves to ``NUMERICALLY_SOLVED``; otherwise it surfaces as
  ``NEEDS_INVESTIGATION`` with structured missing-parameter details.
- Query-bound target values (e.g. the ``Y`` in ``P(Y|do(X))``) are
  handled by the effect/probability query shapes: the query supplies a
  concrete ``target.value`` and the builder propagates it into the
  formula. A formula reaching the evaluator with a query-bound ``None``
  still raises ``InsufficientTheta`` — that path is defensive, not the
  documented usage.

See ``v0_1_scope.md`` for the full list of what the numeric layer
does and does not cover in v0.1.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Mapping

from .. import gaps
from ..types import (
    Atom,
    ConstantExpr,
    FormulaExpr,
    FractionExpr,
    ProbabilityRefExpr,
    ProductExpr,
    SumExpr,
    ValuedAtom,
    ValueExpr,
    VarRef,
)


AtomValue = bool | int | float | str


@dataclass(frozen=True)
class ProbabilityKey:
    """Canonical key for a conditional probability lookup in Theta.

    The target and given values must be concrete literals. VarRefs
    and None-valued atoms must be substituted away before building
    a key.

    Fix 3+4 (charter FIX_3_4_CHARTER_llm_mediated_transport.md):
    ``population`` routes the lookup to a specific population's theta
    partition. None = default / source population — backward-compat
    with all single-population programs (existing ProbabilityRefExpr
    has population=None default, so its key has population=None and
    hits the same entries as before). Non-None values are used by
    transport_formula to differentiate P(...|do, source) from
    P*(z|target) within one Theta.

    Fallback derivations (marginalisation / Bayes inversion / marginal-
    independence lookup) are isolated PER POPULATION: a missing key
    with population=p only consumes entries with the same population.
    Cross-population fallback would silently substitute target data for
    source data (or vice versa) without any user audit — a contract
    violation under Themis's "kernel doesn't fabricate" promise.
    """

    target_atom: Atom
    target_value: AtomValue
    given: frozenset[tuple[Atom, AtomValue]]
    population: str | None = None


@dataclass
class Theta:
    """Model parameter store.

    entries: maps canonical ProbabilityKey to a conditional probability.
    domains: per-atom allowed values, for the atoms the data mentions.
    declared: each declared variable's values, by predicate.
    """

    entries: dict[ProbabilityKey, float] = field(default_factory=dict)
    domains: dict[Atom, tuple[AtomValue, ...]] = field(default_factory=dict)
    declared: dict[str, tuple[AtomValue, ...]] = field(default_factory=dict)

    def get(self, key: ProbabilityKey) -> float | None:
        return self.entries.get(key)

    def domain_of(self, atom: Atom) -> tuple[AtomValue, ...]:
        """The values ``atom`` takes: as the data met them, else as its
        variable is declared, else boolean.

        ``domains`` holds only the atoms some probability or observation
        statement mentions, so this used to answer boolean for a variable
        the program declares and supplies nothing about. A confounder
        declared low/mid/high was then asked for at True and at False —
        values it does not take — and the verifier refused the kernel's
        own ask.
        """
        found = self.domains.get(atom)
        if found is not None:
            return found
        return self.declared.get(atom.predicate, (True, False))


def format_probability_key(key: ProbabilityKey) -> str:
    """Render a ``ProbabilityKey`` as ``P(pred=value|pred1=v1,pred2=v2)``.

    Single canonical form shared by the user-facing surfaces that quote
    the key: ``InsufficientTheta.reason`` and the ``parameter:...`` name
    built by ``scheduler._missing_parameter_from_key``. Kept here because
    ``ProbabilityKey`` lives here; importing it from the scheduler would
    reverse the dependency.
    """
    given_pairs = sorted(
        key.given,
        key=lambda pair: (pair[0].predicate, str(pair[1])),
    )
    given_repr = ",".join(f"{a.predicate}={v}" for a, v in given_pairs)
    body = f"{key.target_atom.predicate}={key.target_value}"
    if given_repr:
        body = f"{body}|{given_repr}"
    # Fix 3+4: surface population in the rendered key when non-default.
    # Backward-compat: population=None renders identically to pre-fix
    # so existing fixtures / pinning tests don't drift.
    if key.population is None:
        return f"P({body})"
    return f"P_{key.population}({body})"


class InsufficientTheta(Exception):
    """Raised when the formula evaluator needs a probability lookup
    that is not in Theta.

    The ``missing_key`` attribute carries the exact ProbabilityKey so
    the caller can report precisely which parameter must be supplied.

    ``need`` says which of several unlike failures this is, and its kind
    says which channel repairs it. Ordinarily theta is simply short of
    the entry and the remedy is to supply it. But the d-separation guard
    also raises here, after finding that theta DOES hold a marginal the
    declared graph forbids substituting — there the remedy is to fix the
    graph or supply the demanded conditional, and "supply more theta" is
    advice for a different problem. The distinction is decided where it
    is discovered; carrying it on the exception is what stops the far end
    from re-deriving it by searching a sentence for a phrase.

    ``details`` is this occasion's facts, in the shape :func:`themis.gaps
    .missing` takes them. The exception carries no sentence: it has two
    outlets — a missing item and the mediation arms' status blocks — and
    a sentence written here would be one author writing for two surfaces
    in one language, which is the arrangement this replaced.
    """

    def __init__(
        self,
        missing_key: "ProbabilityKey | None",
        *,
        need: "gaps.Need",
        **details,
    ):
        super().__init__(str(need))
        self.missing_key = missing_key
        self.need = gaps.registered(need)
        self.details = details


def _resolve(value: ValueExpr | None, subs: Mapping[str, AtomValue]) -> AtomValue:
    if value is None:
        raise InsufficientTheta(
            None, need=gaps.Need.QUERY_BOUND_ATOM_UNRESOLVED,
        )
    if isinstance(value, VarRef):
        if value.name not in subs:
            # Formal well-formedness should prevent this; treat as
            # programmer error, not user-facing InsufficientTheta.
            raise ValueError(
                f"unbound VarRef '{value.name}' during evaluation; "
                f"the formula should have been rejected by validate_formula"
            )
        return subs[value.name]
    return value  # concrete literal


def _probability_ref_key(
    node: ProbabilityRefExpr,
    subs: Mapping[str, AtomValue],
) -> ProbabilityKey:
    target_value = _resolve(node.target.value, subs)
    given_pairs = frozenset(
        (va.atom, _resolve(va.value, subs)) for va in node.given
    )
    return ProbabilityKey(
        target_atom=node.target.atom,
        target_value=target_value,
        given=given_pairs,
        population=node.population,
    )


# Placeholder substituted for a missing probability_ref when _evaluate runs in
# collect mode (``missing_sink`` set): the numeric result is discarded, we only
# want the full set of unresolvable keys, so any finite value keeps the walk
# going past a gap instead of aborting at the first one.
_COLLECT_PLACEHOLDER = 0.5


def _evaluate(
    expr: FormulaExpr,
    theta: Theta,
    subs: Mapping[str, AtomValue],
    *,
    graph=None,
    bidirected=None,
    missing_sink: "list[ProbabilityKey] | None" = None,
) -> float:
    if isinstance(expr, ConstantExpr):
        return float(expr.value)

    if isinstance(expr, ProbabilityRefExpr):
        key = _probability_ref_key(expr, subs)
        value = theta.get(key)
        if value is None:
            # Try auto-marginalization before giving up. If theta has a
            # richer joint family that lets us derive this CPT via
            # Σ_z P(Y|X,Z)·P(Z|X), use it.
            derived = _try_derive_via_marginalization(
                key, theta, graph=graph, bidirected=bidirected,
            )
            if derived is None:
                # Marginal-independence fallback, guarded by d-separation
                # whenever graph + bidirected are available: unguarded, a
                # chain DAG with marginal-only theta is silently wrong.
                derived = _try_marginal_independence_lookup(
                    key, theta, graph=graph, bidirected=bidirected,
                )
            if derived is not None:
                return derived
            # When the d-sep guard silently refused an
            # existing-but-graph-incompatible marginal, say so: the user
            # needs to know their supplied marginal does NOT match the
            # declared graph — they must either fix the graph or supply
            # the demanded conditional, not just add "more theta". Falls
            # through to the plain species when no candidate was refused.
            refusal = _diagnose_marginal_independence_refusal(
                key, theta, graph=graph, bidirected=bidirected,
            )
            if missing_sink is not None:
                missing_sink.append(key)
                return _COLLECT_PLACEHOLDER
            if refusal is not None:
                raise InsufficientTheta(
                    key,
                    need=gaps.Need.GRAPH_CONTRADICTS_SUPPLIED_MARGINAL,
                    key=format_probability_key(key),
                    **refusal,
                )
            raise InsufficientTheta(
                key, need=gaps.Need.THETA_ENTRY_MISSING,
                key=format_probability_key(key),
            )
        return value

    if isinstance(expr, ProductExpr):
        result = 1.0
        for term in expr.terms:
            result *= _evaluate(
                term, theta, subs, graph=graph, bidirected=bidirected,
                missing_sink=missing_sink,
            )
        return result

    if isinstance(expr, SumExpr):
        total = 0.0
        for v in theta.domain_of(expr.over):
            new_subs = dict(subs)
            new_subs[expr.bind.name] = v
            total += _evaluate(
                expr.body, theta, new_subs,
                graph=graph, bidirected=bidirected,
                missing_sink=missing_sink,
            )
        return total

    if isinstance(expr, FractionExpr):
        num = _evaluate(
            expr.numerator, theta, subs, graph=graph, bidirected=bidirected,
            missing_sink=missing_sink,
        )
        den = _evaluate(
            expr.denominator, theta, subs, graph=graph, bidirected=bidirected,
            missing_sink=missing_sink,
        )
        if den == 0.0:
            if missing_sink is not None:
                # collect mode: a placeholder/partial denominator can be 0;
                # we are gathering keys, not computing a real value.
                return 0.0
            raise ValueError(
                "fraction denominator evaluated to 0 — positivity violation "
                "(the conditioning event P_x(z) has zero probability)"
            )
        return num / den

    raise TypeError(f"unknown formula node: {type(expr).__name__}")


def estimate_formula(
    formula: FormulaExpr,
    theta: Theta,
    *,
    graph=None,
    bidirected=None,
) -> float:
    """Evaluate a formula AST to a numeric value using Theta.

    Raises ``InsufficientTheta`` with a structured missing-key payload
    if any conditional probability referenced by the formula is not
    present in Theta, or if the formula contains query-bound atoms
    whose concrete value has not been supplied.

    The optional ``graph`` + ``bidirected`` enable the d-separation
    safety guard for the marginal-independence fallback. When provided,
    the fallback only fires if d-separation between target and "extras"
    given "reduced_given" actually holds; unguarded, a chain DAG with
    marginal-only theta is silently wrong. Without a graph there is
    nothing to check against, so the fallback trusts the theta it was
    given.
    """
    return _evaluate(formula, theta, {}, graph=graph, bidirected=bidirected)


def collect_missing_keys(
    formula: FormulaExpr,
    theta: Theta,
    *,
    graph=None,
    bidirected=None,
) -> tuple[ProbabilityKey, ...]:
    """Walk the formula like ``estimate_formula`` but, instead of aborting at
    the first unresolvable ``probability_ref``, gather EVERY one the evaluator
    cannot resolve (after its marginalization / independence fallbacks run, so
    a derivable factor is never reported missing) and return the distinct cells,
    in first-seen order.

    This is what lets the data-gap report name ALL the data a multi-factor
    estimand still needs (front-door touches three CPTs, back-door two), not
    only the first gap the fail-fast ``estimate_formula`` happened to hit. Keys
    stay cell-precise so a partially-filled CPT reports exactly the missing
    entry, not the whole table.
    """
    sink: list[ProbabilityKey] = []
    _evaluate(
        formula, theta, {}, graph=graph, bidirected=bidirected, missing_sink=sink,
    )
    seen: set = set()
    out: list[ProbabilityKey] = []
    for key in sink:
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return tuple(out)


def estimate_probability(
    target: ValuedAtom,
    given: tuple[ValuedAtom, ...],
    theta: Theta,
) -> float:
    """Convenience: evaluate a single conditional probability lookup."""
    expr = ProbabilityRefExpr(target=target, given=given)
    return estimate_formula(expr, theta)


# ------------------------------------------------------------- key enumeration

def enumerate_keys(
    formula: FormulaExpr,
    theta: Theta,
) -> tuple[ProbabilityKey, ...]:
    """Enumerate every ``ProbabilityKey`` that ``estimate_formula`` would
    look up for this formula under the given Theta's value domains.

    Read-only twin of ``estimate_formula``: walks the same AST shape,
    expands ``SumExpr`` over ``theta.domain_of(over)`` identically, but
    collects keys instead of multiplying / summing values. Used by the
    confidence collector (RFC §3.1) to enumerate slots without trying
    to actually evaluate.

    Keys may repeat across sum branches; callers dedupe as needed.

    Raises ``InsufficientTheta`` only for VarRef resolution failures
    (formula malformed). For query-bound ``None`` values the enclosing
    iteration skips that branch silently — enumerate_keys is meant to
    survive partial formulas.
    """
    keys: list[ProbabilityKey] = []
    _collect_keys(formula, theta, {}, keys)
    return tuple(keys)


def _collect_keys(
    expr: FormulaExpr,
    theta: Theta,
    subs: Mapping[str, AtomValue],
    keys: list,
) -> None:
    if isinstance(expr, ConstantExpr):
        return
    if isinstance(expr, ProbabilityRefExpr):
        try:
            key = _probability_ref_key(expr, subs)
        except InsufficientTheta:
            # Query-bound None that was not supplied externally —
            # this is not a key we can enumerate. Skip silently.
            return
        keys.append(key)
        return
    if isinstance(expr, ProductExpr):
        for t in expr.terms:
            _collect_keys(t, theta, subs, keys)
        return
    if isinstance(expr, SumExpr):
        for v in theta.domain_of(expr.over):
            new_subs = dict(subs)
            new_subs[expr.bind.name] = v
            _collect_keys(expr.body, theta, new_subs, keys)
        return
    if isinstance(expr, FractionExpr):
        _collect_keys(expr.numerator, theta, subs, keys)
        _collect_keys(expr.denominator, theta, subs, keys)
        return
    raise TypeError(f"unknown formula node: {type(expr).__name__}")


# --------------------------------------------------------------------- theta

def empty_theta() -> Theta:
    """Return a fresh empty Theta. v0.1 uses this because probability
    statements cannot yet be compiled into Theta entries (their
    target/given atoms have no values in the current schema)."""
    return Theta()


# -------------------------------------------------------- derivable check

def can_derive_via_marginalization(
    missing_key: ProbabilityKey,
    theta: Theta,
    *,
    extra_atoms: tuple[Atom, ...] = (),
) -> bool:
    """Whether ``missing_key`` could be derived by marginalizing over
    additional atoms not in its conditioning set.

    For example, if ``missing_key`` is P(Y|X) and theta contains every
    P(Y|X, Z=v_z) for v_z ∈ domain(Z), the missing CPT can be
    derived as Σ_z P(Y|X, Z=z) · P(Z=z|X).

    This function only returns True when:
    - For some atom Z (in ``extra_atoms`` or scanning theta keys),
      every (target_atom, target_value, given ∪ {(Z, z)}) for z in
      domain(Z) has a theta entry, AND
    - Every P(Z=z|conditioning) needed for the inner factor exists
      in theta.

    This is the SCAN only; :func:`_try_derive_via_marginalization` runs
    the derivation itself and ``_evaluate`` calls it before raising
    ``InsufficientTheta``. They are kept apart so this one stays a pure
    predicate, testable without a formula around it.
    """
    target_atom = missing_key.target_atom
    target_value = missing_key.target_value
    base_given = missing_key.given
    # Fix 3+4: fallback derivations stay within the missing key's
    # population — never substitute target data for source data
    # (or vice versa) silently.
    pop = missing_key.population

    # Try each extra_atom as the marginalization variable. Scan first
    # in extra_atoms, then in theta's known atoms (collected from
    # entry keys' atoms) — restricted to same-population entries.
    candidates: list[Atom] = list(extra_atoms)
    seen_in_extra = set(extra_atoms)
    for key in theta.entries:
        if key.population != pop:
            continue
        for ga, _gv in key.given:
            if ga != target_atom and ga not in seen_in_extra:
                candidates.append(ga)
                seen_in_extra.add(ga)
        if (
            key.target_atom != target_atom
            and key.target_atom not in seen_in_extra
        ):
            candidates.append(key.target_atom)
            seen_in_extra.add(key.target_atom)

    given_atoms = {ga for ga, _ in base_given}
    for z in candidates:
        if z == target_atom or z in given_atoms:
            continue
        domain = theta.domain_of(z)
        if not domain:
            continue
        # Check: every (target_atom, target_value, base_given ∪ {(z, v)})
        # exists for v in domain(z)?
        all_outer_present = True
        for v in domain:
            extended_given = frozenset(base_given | {(z, v)})
            outer_key = ProbabilityKey(
                target_atom=target_atom,
                target_value=target_value,
                given=extended_given,
                population=pop,
            )
            if outer_key not in theta.entries:
                all_outer_present = False
                break
        if not all_outer_present:
            continue
        # Inner factor: P(Z=v | base_given) — must also exist for
        # each v. Conservative: require entries with the SAME
        # base_given conditioning. (More general: derive P(Z|cond)
        # by chain rule.)
        all_inner_present = True
        for v in domain:
            inner_key = ProbabilityKey(
                target_atom=z, target_value=v, given=base_given,
                population=pop,
            )
            if inner_key not in theta.entries:
                all_inner_present = False
                break
        if all_inner_present:
            return True
    return False


def _try_marginal_independence_lookup(
    missing_key: ProbabilityKey,
    theta: Theta,
    *,
    graph=None,
    bidirected=None,
) -> float | None:
    """Last-resort fallback when P(Z|given) is missing AND
    not derivable via marginalization or Bayes inversion. If theta
    contains P(Z|reduced_given) for any strict subset of given, use
    it — assumes the user-supplied marginal implicitly asserts
    conditional independence (Z ⊥ extras | reduced_given).

    Unlocks parallel multi-mediator front-door (X→M1→Y, X→M2→Y, X↔Y)
    where user supplies P(M2|X), kernel demands P(M2|M1, X). The user
    didn't supply P(M2|M1, X) because they took the parallel-paths
    semantics for granted (M1 ⊥ M2 | X).

    Tries the LARGEST admissible subset first (most informative
    conditioning) so that adding to theta tightens results.

    SAFETY ANALYSIS (probed numerically; closed by the guard below):

    The fallback fires ONLY when direct lookup + marginalization +
    Bayes inversion all fail. In practice this means:

    - Parallel multi-mediator (X→M1→Y, X→M2→Y, X↔Y): user typically
      supplies marginal P(M2|X) (independence implied by graph
      structure — M1 ⊥ M2 | X by d-separation). Bayes inversion
      can't help (P(M1|M2, X) needs P(M2|M1, X) which is what we're
      deriving — circular). Fallback fires → CORRECT, since graph
      structurally implies the independence.

    - Chain X→M1→M2→Y with marginal-only theta (user wrote chain
      causes but supplied marginal CPTs): substituting the marginal
      P(M2|X) for the demanded P(M2|M1, X) is WRONG, since M1 → M2
      makes them dependent given X — confirmed numerically, not argued.

    Hence the guard below: whenever ``graph`` and ``bidirected`` are
    supplied, the substitution is allowed ONLY if m-separation confirms
    the independence the user's marginal implicitly asserts, and the
    chain case is refused with a diagnostic naming the mismatch. Callers
    that evaluate against a declared graph MUST pass both — omitting them
    leaves the substitution trusting the caller's theta, which is only
    safe when there is no graph available to check it against.

    TL;DR: graph supplied → sound (licensed substitutions only); graph
    omitted → trusts the user's CPTs, which silently accepts a
    graph/CPT mismatch.
    """
    target_atom = missing_key.target_atom
    target_value = missing_key.target_value
    base_given = missing_key.given
    pop = missing_key.population  # Fix 3+4: same-population isolation
    if not base_given:
        return None
    # Try removing one atom at a time, then two, etc. Largest subset
    # = removing fewest atoms = most informative conditioning.
    for n_remove in range(1, len(base_given) + 1):
        # Iterate in deterministic order: pick atoms to remove by
        # sorted predicate name for stability.
        sorted_given = sorted(
            base_given, key=lambda p: (p[0].predicate, str(p[1])),
        )
        from itertools import combinations
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
            # Graph-aware safety guard. When graph + bidirected are
            # provided, only return v if d-separation confirms
            # target ⊥ extras | reduced — i.e. the user's marginal IS
            # the right quantity for the demanded conditional. Without
            # a graph there is nothing to check, so the theta is
            # trusted.
            if graph is not None and bidirected is not None:
                from .structural_solver import m_separated
                conditioning = tuple(a for a, _ in reduced)
                extras_atoms = [a for a, _ in to_remove]
                # target must be m-separated from EVERY extra atom
                # given the reduced conditioning. Pairwise check is
                # sufficient for joint d-sep in graph semantics.
                all_separated = all(
                    m_separated(
                        graph, bidirected,
                        target_atom, extra, conditioning,
                    )
                    for extra in extras_atoms
                )
                if not all_separated:
                    # User-implied independence doesn't hold per
                    # graph structure — refuse to silently return
                    # the marginal. The chain DAG lands here.
                    continue
            return v
    return None


def _diagnose_marginal_independence_refusal(
    missing_key: ProbabilityKey,
    theta: Theta,
    *,
    graph,
    bidirected,
) -> "dict[str, str] | None":
    """Surface WHY the marginal-independence fallback refused.

    The d-sep guard silently returns ``None`` when a candidate
    marginal exists in ``theta`` but the graph contradicts the
    implied conditional independence (chain DAG + marginal-only theta is
    the canonical case). The caller would then raise ``InsufficientTheta``
    as a plain shortfall — true but unhelpful: the user supplied data
    Themis CONSIDERED and REJECTED, and gets no hint why their declared
    graph and supplied CPTs disagree.

    This helper re-walks the same candidate-search loop as
    ``_try_marginal_independence_lookup`` and returns the facts that
    distinguish the two — which marginal theta does hold, and which
    independence the graph fails to imply — when a candidate was found
    AND refused by the d-sep guard. It returns ``None`` when no
    candidate was present at all (so the caller's plain species is the
    right one) or when graph info is missing (no guard fired, so nothing
    to distinguish).

    Per VISION principle 5 ("数据缺口诊断 ≥ 数值估计 …… 显式告诉用户
    缺什么数据"), the user benefits from knowing the marginal they
    supplied doesn't match their declared graph — that is a different
    fix than "supply more theta entries".
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
    from .structural_solver import m_separated

    refused: list[tuple[ProbabilityKey, tuple[Atom, ...]]] = []
    for n_remove in range(1, len(base_given) + 1):
        sorted_given = sorted(
            base_given, key=lambda p: (p[0].predicate, str(p[1])),
        )
        for to_remove in combinations(sorted_given, n_remove):
            reduced = frozenset(
                p for p in base_given if p not in to_remove
            )
            # A bare marginal P(Y) (empty conditioning) asserts NO
            # conditional independence: supplying a base rate is never a
            # claim that Y ⊥ {X,Z}. So its d-sep refusal is not a
            # graph-vs-CPT contradiction — it is plain missing data. Skip
            # it here → the caller falls through to the generic message →
            # the classifier emits MISSING_DISTRIBUTION (blocking, names
            # the demanded conditional P(Y|X,Z)) instead of a downgraded,
            # backwards "your graph contradicts your CPT, delete an edge"
            # mismatch. The genuine mismatch case keeps a non-empty
            # conditioning set (P(C|S) for demanded P(C|S,T)) and is
            # untouched. Measured on a real-usage probe, 2026-06-15.
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
                refused.append((reduced_key, extras_atoms))
    if not refused:
        return None
    # Pick the largest-subset (most informative) refused candidate to
    # quote — same priority order as the lookup helper.
    reduced_key, extras_atoms = refused[0]
    return {
        "have": format_probability_key(reduced_key),
        # "variable" and not "target": a slot named like one of the door's
        # own parameters would arrive as that parameter instead.
        "variable": target_atom.predicate,
        "extras": ",".join(a.predicate for a in extras_atoms),
        "conditioning": ",".join(
            a.predicate for a, _ in reduced_key.given) or "∅",
    }


def _try_derive_via_bayes_inversion(
    missing_key: ProbabilityKey,
    theta: Theta,
    *,
    _depth: int = 0,
    graph=None,
    bidirected=None,
) -> float | None:
    """Bayes inversion for the inner-factor derivation gap. Returns the
    inverted value if possible, None otherwise.

    For ``P(target=tv | given)`` missing: pick an atom A in given,
    compute P(target=tv | given\\{A}) and the flip P(A=a |
    given\\{A}, target=tv), and apply Bayes:

        P(target | given) =
            P(A=a | given\\{A}, target) · P(target | given\\{A})
                / P(A=a | given\\{A})

    Each of the three factors may itself need recursive marginalization
    (via _try_derive_via_marginalization). Bounded depth ≤ 2 for the
    Bayes recursion to prevent runaway.

    Concrete unlocked case: chain mediator front-door (X→M1→M2→Y,
    X↔Y latent). Front-door demands P(Y|X, M2). Auto-marginalization
    over M1 needs the inner factor P(M1|X, M2) which user didn't
    supply but Bayes inversion gives:
        P(M1|X, M2) = P(M2|X, M1)·P(M1|X) / P(M2|X)
    where P(M2|X) is itself marginalizable from supplied chain.

    Called from ``_try_derive_via_marginalization``'s inner-factor
    branch, after direct lookup and recursive marginalization both fail.
    Mirrored in the verifier as
    ``themis.verifier.rules._verifier_derive_via_bayes_inversion``, and
    ``test_runtime_and_verifier_bayes_inversion_agree_byte_for_byte``
    asserts the two agree byte for byte.
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
        # Numerator factor 1: P(A=a_value | reduced_given, target=target_value)
        # — i.e. condition the original "target" appearance instead.
        flip_given = reduced_given | {(target_atom, target_value)}
        flip_key = ProbabilityKey(
            target_atom=a_atom, target_value=a_value,
            given=frozenset(flip_given), population=pop,
        )
        flip_val = theta.entries.get(flip_key)
        if flip_val is None:
            flip_val = _try_derive_via_marginalization(
                flip_key, theta, _depth=_depth + 1,
                graph=graph, bidirected=bidirected,
            )
        if flip_val is None:
            continue
        # Numerator factor 2: P(target=target_value | reduced_given)
        target_key = ProbabilityKey(
            target_atom=target_atom, target_value=target_value,
            given=reduced_given, population=pop,
        )
        target_marginal = theta.entries.get(target_key)
        if target_marginal is None:
            target_marginal = _try_derive_via_marginalization(
                target_key, theta, _depth=_depth + 1,
                graph=graph, bidirected=bidirected,
            )
        if target_marginal is None:
            continue
        # Denominator: P(A=a_value | reduced_given)
        denom_key = ProbabilityKey(
            target_atom=a_atom, target_value=a_value,
            given=reduced_given, population=pop,
        )
        denom = theta.entries.get(denom_key)
        if denom is None:
            denom = _try_derive_via_marginalization(
                denom_key, theta, _depth=_depth + 1,
                graph=graph, bidirected=bidirected,
            )
        if denom is None or denom == 0:
            continue
        return flip_val * target_marginal / denom
    return None


def _try_derive_via_marginalization(
    missing_key: ProbabilityKey,
    theta: Theta,
    *,
    _depth: int = 0,
    graph=None,
    bidirected=None,
) -> float | None:
    """The derivation itself. Returns the marginalized value
    if possible, None otherwise.

    Computes Σ_z P(target|given,Z=z) · P(Z=z|given) using theta
    entries. When the outer factor P(target|
    given,Z=z) is itself missing, recursively try to derive IT via
    marginalization (e.g. disjoint-Y needs P(Y|X) = Σ_{z1,z2} P(Y|X,
    z1,z2)·P(z1,z2|X) — outer marginalizes z1, inner-of-outer
    marginalizes z2). Bounded recursion (default depth ≤ 3) to
    prevent runaway on pathological theta shapes.

    PAIRED IMPLEMENTATION: see ``themis.verifier.rules.
    _verifier_derive_via_marginalization``. The two are independent
    (V0-V5 design goal) but MUST agree byte-for-byte on every theta, and
    ``test_runtime_and_verifier_marginalization_agree_byte_for_byte``
    asserts it. If you modify this helper, mirror the change to the
    verifier and re-run that pin.

    WHAT THIS HELPER DOES NOT REACH, AND WHAT DOES. Chain-mediator
    front-door (X→M1→M2→Y, X↔Y) demands P(M1|X, M2); the inner-factor
    branch gets it from ``_try_derive_via_bayes_inversion``, as
    P(M1|X, M2) = P(M2|X, M1)·P(M1|X) / P(M2|X). Parallel multi-mediator
    front-door (X→M1→Y, X→M2→Y, X↔Y) demands P(M2|M1, X), which Bayes
    inversion cannot reach: it would need P(M1|M2, X), equally absent,
    so the recursion is circular. That one is answered a level up by
    ``_try_marginal_independence_lookup``, which reads M1 ⊥ M2 | X off
    the graph instead of deriving it. The other way — a joint-CPT
    primitive, the caller supplying P(M1, M2|X) as one entry — is not
    implemented.

    Conservative on derivation order: tries each candidate Z in
    order of appearance, picks the first that fully evaluates. The
    inner P(Z|given) factor is attempted via theta lookup; it is not
    chain-rule expanded.
    """
    if _depth > 3:
        return None
    target_atom = missing_key.target_atom
    target_value = missing_key.target_value
    base_given = missing_key.given
    pop = missing_key.population  # Fix 3+4: same-population isolation

    candidates: list[Atom] = []
    seen: set[Atom] = set()
    for key in theta.entries:
        # Only consider atoms present in the same population's entries
        # as candidate marginalisation axes — never derive source via
        # target data (or vice versa).
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
                # Recursive derivation for this outer term. graph +
                # bidirected are threaded through so the leaf d-sep guard
                # fires during deep recursion and not only at the top
                # call.
                v_outer = _try_derive_via_marginalization(
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
                # also recurse for the inner P(Z|given)
                v_inner = _try_derive_via_marginalization(
                    inner_key, theta, _depth=_depth + 1,
                    graph=graph, bidirected=bidirected,
                )
                if v_inner is None:
                    # try Bayes inversion for the inner
                    # factor — unlocks chain-mediator front-door
                    # cases where P(Z|given) needs flipping via
                    # supplied P(some_given_atom | given\\{a}, Z).
                    # thread graph + bidirected so deep
                    # recursion through Bayes also gets the d-sep
                    # guard at the leaf marginal-indep lookup.
                    v_inner = _try_derive_via_bayes_inversion(
                        inner_key, theta, _depth=_depth + 1,
                        graph=graph, bidirected=bidirected,
                    )
                if v_inner is None:
                    # marginal-independence fallback. If
                    # theta has P(Z=v | reduced_given) for some
                    # strict subset of base_given, use it — assumes
                    # the user-supplied marginal asserts Z ⊥ extras
                    # | reduced_given. Unlocks parallel multi-mediator
                    # front-door (X→M1→Y, X→M2→Y, X↔Y) where user
                    # supplies P(M2|X), kernel demands P(M2|M1, X).
                    v_inner = _try_marginal_independence_lookup(
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


# ================================================= variable-elimination eval
#
# ``estimate_formula`` walks the estimand recursively, binding a FRESH subs
# dict for every value of every enclosing Σ: for a nested-ID / general-ID
# estimand #sums = |V|-1, so it does 2^#sums leaf evaluations and churns
# 2^#sums transient dicts. Past |V|≈14 that recursion is BOTH exponential and
# a flaky native-fault site (segfault / heap corruption under a deep callstack,
# measured even for a single call). For the paths that evaluate such large
# estimands on a COMPLETE theta — the identification probe's self-check and the
# general-ID plug-in numeric end (bootstrap re-evaluates hundreds of times) —
# ``ve_estimate_formula`` computes the SAME value by VARIABLE ELIMINATION on
# the estimand's own factor graph:
#   - each probability factor is a small table over the enclosing Σ-variables
#     it mentions (value = the theta conditional for that binding);
#   - a Π concatenates factor lists (no eager multiply);
#   - a Σ eliminates its bound variable — multiply ONLY the factors that
#     mention it, sum it out — cost ~2^treewidth, not 2^|V|;
#   - a fraction is an elimination barrier (numerator / denominator each
#     reduced to one factor, then divided pointwise).
# No deep recursion over domains, no 2^|V| churn — so no fault. It equals
# ``estimate_formula`` EXACTLY when theta is complete (pinned by test); it does
# NOT run the sparse-theta derivation fallbacks, so it is for complete-theta
# callers only (both current callers pre-fill every referenced key). A factor
# is ``(vars: tuple[str], table: {value-tuple: p})`` — vars being the VarRef
# NAMES bound by enclosing sums.

VE_MAX_SCOPE = 20  # decline (VEIntractable) if any intermediate factor's scope
#                    exceeds this — bounds VE on high-treewidth estimands.


class VEIntractable(Exception):
    """Variable elimination would build a factor too large to be worth it
    (high-treewidth estimand). Callers treat this as a graceful decline —
    the probe reports ``inconclusive``; the plug-in falls back to enumeration
    only if it chooses to."""


def _ve_multiply(f1, f2):
    """Pointwise product of two factors over the union of their scopes."""
    v1, t1 = f1
    v2, t2 = f2
    extra = tuple(v for v in v2 if v not in v1)
    vars_ = v1 + extra
    if len(vars_) > VE_MAX_SCOPE:
        raise VEIntractable(f"factor scope {len(vars_)} exceeds cap")
    shared = [v for v in v1 if v in v2]
    v1_sh = [v1.index(v) for v in shared]
    v2_sh = [v2.index(v) for v in shared]
    v2_ex = [v2.index(v) for v in extra]
    by_shared: dict = {}
    for vals2, p2 in t2.items():
        by_shared.setdefault(tuple(vals2[i] for i in v2_sh), []).append((vals2, p2))
    new: dict = {}
    for vals1, p1 in t1.items():
        for vals2, p2 in by_shared.get(tuple(vals1[i] for i in v1_sh), ()):
            combined = vals1 + tuple(vals2[i] for i in v2_ex)
            new[combined] = new.get(combined, 0.0) + p1 * p2
    return (vars_, new)


def _ve_sum_out(factor, v):
    """Marginalise ``v`` out of a factor."""
    vars_, table = factor
    i = vars_.index(v)
    keep_vars = vars_[:i] + vars_[i + 1:]
    new: dict = {}
    for vals, p in table.items():
        key = vals[:i] + vals[i + 1:]
        new[key] = new.get(key, 0.0) + p
    return (keep_vars, new)


def referenced_keys(
    formula: FormulaExpr, domains: Mapping[Atom, tuple]
) -> set:
    """The DISTINCT ``ProbabilityKey`` set ``formula`` references, collected by
    a LINEAR per-factor enumeration: each leaf contributes the product over its
    VarRef (summed) slots of their atom domains, with concrete (bound /
    do-value) slots pinned. Deduped this equals :func:`enumerate_keys`'s
    distinct output, but costs O(#factors · 2^slots-per-factor), NOT the
    2^#sums expansion :func:`enumerate_keys` materialises (millions of keys past
    |V|≈18 — a native-fault site in its own right). ``domains`` supplies each
    atom's value domain (default boolean)."""
    out: set = set()
    _referenced_keys(formula, domains, out)
    return out


def _referenced_keys(expr: FormulaExpr, domains: Mapping[Atom, tuple], out: set) -> None:
    if isinstance(expr, ProbabilityRefExpr):
        names: list[str] = []
        dom_of: dict[str, tuple] = {}
        for va in (expr.target, *expr.given):
            v = va.value
            if isinstance(v, VarRef) and v.name not in dom_of:
                names.append(v.name)
                dom_of[v.name] = domains.get(va.atom, (True, False))
        for combo in (itertools.product(*(dom_of[n] for n in names)) if names else [()]):
            out.add(_probability_ref_key(expr, dict(zip(names, combo))))
    elif isinstance(expr, ProductExpr):
        for t in expr.terms:
            _referenced_keys(t, domains, out)
    elif isinstance(expr, SumExpr):
        _referenced_keys(expr.body, domains, out)
    elif isinstance(expr, FractionExpr):
        _referenced_keys(expr.numerator, domains, out)
        _referenced_keys(expr.denominator, domains, out)
    # ConstantExpr / bare VarRef: no probability factor.


def _ve_prob_ref_factor(ref: ProbabilityRefExpr, bound_domains: dict, theta: Theta):
    """Leaf factor: a table over the enclosing Σ-variables the reference
    mentions, each entry the theta conditional for that binding. Concrete slots
    (do-value / bound target) stay fixed and do not enter the scope."""
    names: list[str] = []
    for va in (ref.target, *ref.given):
        v = va.value
        if isinstance(v, VarRef) and v.name in bound_domains and v.name not in names:
            names.append(v.name)
    scope = tuple(names)
    doms = [bound_domains[n] for n in scope]
    table: dict = {}
    for combo in (itertools.product(*doms) if scope else [()]):
        key = _probability_ref_key(ref, dict(zip(scope, combo)))
        val = theta.get(key)
        if val is None:
            # ve_estimate_formula is a complete-theta evaluator (no fallbacks);
            # a missing key is a genuine gap, surfaced like estimate_formula.
            raise InsufficientTheta(
                key, need=gaps.Need.THETA_ENTRY_MISSING,
                key=format_probability_key(key),
            )
        table[combo] = val
    return (scope, table)


def _ve_eliminate_var(factors: list, name: str, dom: tuple) -> list:
    """Sum out ``name``: multiply only the factors that mention it, sum it out,
    keep the rest (the VE win). A variable no factor depends on is a degenerate
    Σ over a constant = ×|dom|."""
    containing = [f for f in factors if name in f[0]]
    rest = [f for f in factors if name not in f[0]]
    if not containing:
        rest.append(((), {(): float(len(dom))}))
        return rest
    prod = containing[0]
    for f in containing[1:]:
        prod = _ve_multiply(prod, f)
    return rest + [_ve_sum_out(prod, name)]


def _ve_product(factors: list):
    prod = ((), {(): 1.0})
    for f in factors:
        prod = _ve_multiply(prod, f)
    return prod


def _ve_divide(num_f, den_f):
    """Pointwise num/den over the union scope (multiply by reciprocal, so the
    shared-variable join is the tested ``_ve_multiply``). A zero denominator is
    a positivity violation, matching ``estimate_formula``'s fraction rule."""
    dv, dt = den_f
    recip: dict = {}
    for vals, p in dt.items():
        if p == 0.0:
            raise ValueError(
                "fraction denominator evaluated to 0 — positivity violation "
                "(the conditioning event P_x(z) has zero probability)"
            )
        recip[vals] = 1.0 / p
    return _ve_multiply(num_f, (dv, recip))


def _ve_factors(expr: FormulaExpr, bound_domains: dict, theta: Theta) -> list:
    if isinstance(expr, ConstantExpr):
        return [((), {(): float(expr.value)})]
    if isinstance(expr, ProbabilityRefExpr):
        return [_ve_prob_ref_factor(expr, bound_domains, theta)]
    if isinstance(expr, ProductExpr):
        out: list = []
        for t in expr.terms:
            out.extend(_ve_factors(t, bound_domains, theta))
        return out
    if isinstance(expr, SumExpr):
        name = expr.bind.name
        dom = theta.domain_of(expr.over)
        inner = dict(bound_domains)
        inner[name] = dom
        fs = _ve_factors(expr.body, inner, theta)
        return _ve_eliminate_var(fs, name, dom)
    if isinstance(expr, FractionExpr):
        num_f = _ve_product(_ve_factors(expr.numerator, bound_domains, theta))
        den_f = _ve_product(_ve_factors(expr.denominator, bound_domains, theta))
        return [_ve_divide(num_f, den_f)]
    raise TypeError(f"unknown formula node: {type(expr).__name__}")


def ve_estimate_formula(formula: FormulaExpr, theta: Theta) -> float:
    """Evaluate a (closed) estimand to its scalar value by variable
    elimination. Equals ``estimate_formula(formula, theta)`` when theta is
    complete, but costs ~2^treewidth (not 2^#sums) and never recurses over
    domains — so it neither hangs nor trips the native fault on the larger
    nested-ID / general-ID estimands. Complete-theta only: a missing key raises
    ``InsufficientTheta`` (no sparse-theta fallbacks). May raise
    ``VEIntractable`` (→ caller declines) on a high-treewidth estimand."""
    _, table = _ve_product(_ve_factors(formula, {}, theta))
    return table.get((), 0.0)
