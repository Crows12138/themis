"""Numeric estimation of probabilities and formulas.

Wiring (v0.1, after slice 6):

- ``Theta`` is a real parameter store: dict keyed by ``ProbabilityKey``
  plus per-atom value domains. The domains are populated by
  ``theta_builder`` from every literal value observed in the program's
  ``ValuedAtom`` positions (probability target / given, observation
  value); atoms that never appear in such positions fall back to the
  boolean default.
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

from dataclasses import dataclass, field
from typing import Mapping

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
    domains: per-atom allowed values; defaults to boolean when absent.
    """

    entries: dict[ProbabilityKey, float] = field(default_factory=dict)
    domains: dict[Atom, tuple[AtomValue, ...]] = field(default_factory=dict)

    def get(self, key: ProbabilityKey) -> float | None:
        return self.entries.get(key)

    def domain_of(self, atom: Atom) -> tuple[AtomValue, ...]:
        """Return the declared value domain for ``atom``, defaulting to
        boolean when undeclared."""
        return self.domains.get(atom, (True, False))


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
    """

    def __init__(self, missing_key: ProbabilityKey | None, reason: str):
        super().__init__(reason)
        self.missing_key = missing_key
        self.reason = reason


def _resolve(value: ValueExpr | None, subs: Mapping[str, AtomValue]) -> AtomValue:
    if value is None:
        raise InsufficientTheta(
            None,
            "formula contains a query-bound atom with no concrete value; "
            "v0.1 numeric layer cannot resolve it without an externally "
            "supplied substitution",
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


def _evaluate(
    expr: FormulaExpr,
    theta: Theta,
    subs: Mapping[str, AtomValue],
    *,
    graph=None,
    bidirected=None,
) -> float:
    if isinstance(expr, ConstantExpr):
        return float(expr.value)

    if isinstance(expr, ProbabilityRefExpr):
        key = _probability_ref_key(expr, subs)
        value = theta.get(key)
        if value is None:
            # Iter 172: try auto-marginalization before giving up.
            # If theta has a richer joint family that lets us derive
            # this CPT via Σ_z P(Y|X,Z)·P(Z|X), use it.
            derived = _try_derive_via_marginalization(
                key, theta, graph=graph, bidirected=bidirected,
            )
            if derived is None:
                # Iter 193: marginal-independence fallback (iter 199
                # extension: graph-aware d-separation guard when
                # graph + bidirected available — closes iter 195's
                # documented silent-wrong risk for chain DAG +
                # marginal-only theta).
                derived = _try_marginal_independence_lookup(
                    key, theta, graph=graph, bidirected=bidirected,
                )
            if derived is not None:
                return derived
            # Iter 202: when the d-sep guard (iter 199) silently refused
            # an existing-but-graph-incompatible marginal, enrich the
            # reason so the user knows their supplied marginal does NOT
            # match the declared graph — they need to either fix the
            # graph or supply the demanded conditional, not just "more
            # theta". Falls through to the generic message when no
            # candidate was refused.
            refusal = _diagnose_marginal_independence_refusal(
                key, theta, graph=graph, bidirected=bidirected,
            )
            base_msg = f"Theta 中缺条目 {format_probability_key(key)}"
            if refusal is not None:
                base_msg = f"{base_msg}；{refusal}"
            raise InsufficientTheta(key, base_msg)
        return value

    if isinstance(expr, ProductExpr):
        result = 1.0
        for term in expr.terms:
            result *= _evaluate(
                term, theta, subs, graph=graph, bidirected=bidirected,
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
            )
        return total

    if isinstance(expr, FractionExpr):
        num = _evaluate(
            expr.numerator, theta, subs, graph=graph, bidirected=bidirected,
        )
        den = _evaluate(
            expr.denominator, theta, subs, graph=graph, bidirected=bidirected,
        )
        if den == 0.0:
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

    Iter 199: optional ``graph`` + ``bidirected`` enable the
    d-separation safety guard for the marginal-independence fallback.
    When provided, the fallback only fires if d-separation between
    target and "extras" given "reduced_given" actually holds — closing
    iter 195's documented chain-DAG silent-wrong risk. Without graph,
    falls back to iter 193's trust-the-user behavior (backward compat).
    """
    return _evaluate(formula, theta, {}, graph=graph, bidirected=bidirected)


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


# --------------------------------------------------- iter 171: derivable check

def can_derive_via_marginalization(
    missing_key: ProbabilityKey,
    theta: Theta,
    *,
    extra_atoms: tuple[Atom, ...] = (),
) -> bool:
    """Iter 171 — foundation for iter 168's option (b) auto-marginalization.

    Check whether ``missing_key`` could be derived by marginalizing
    over additional atoms not in its conditioning set. For example,
    if ``missing_key`` is P(Y|X) and theta contains every
    P(Y|X, Z=v_z) for v_z ∈ domain(Z), the missing CPT can be
    derived as Σ_z P(Y|X, Z=z) · P(Z=z|X).

    This function only returns True when:
    - For some atom Z (in ``extra_atoms`` or scanning theta keys),
      every (target_atom, target_value, given ∪ {(Z, z)}) for z in
      domain(Z) has a theta entry, AND
    - Every P(Z=z|conditioning) needed for the inner factor exists
      in theta.

    Iter 171 is just the SCAN / detection. Iter 172+ will wire the
    actual marginalization into _evaluate so the kernel auto-derives
    instead of raising InsufficientTheta. Splitting detection from
    derivation lets iter 171 be a pure helper that's testable in
    isolation.

    Returns False on the safe path; iter 172+ flips False → True
    handling case-by-case.
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
        # by chain rule. Iter 172+ may extend.)
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
    """Iter 193 — last-resort fallback when P(Z|given) is missing AND
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

    SAFETY ANALYSIS (iter 195 probe):

    The fallback fires ONLY when direct lookup + marginalization +
    Bayes inversion all fail. In practice this means:

    - Parallel multi-mediator (X→M1→Y, X→M2→Y, X↔Y): user typically
      supplies marginal P(M2|X) (independence implied by graph
      structure — M1 ⊥ M2 | X by d-separation). Bayes inversion
      can't help (P(M1|M2, X) needs P(M2|M1, X) which is what we're
      deriving — circular). Fallback fires → CORRECT, since graph
      structurally implies the independence.

    - Chain X→M1→M2→Y with marginal-only theta (user wrote chain
      causes but supplied marginal CPTs): if user had supplied chain
      CPT P(M2|X, M1), Bayes inversion would handle the demand. If
      they ONLY supplied marginal P(M2|X), this fallback would
      silently use it — WRONG, since M1 → M2 makes them dependent
      given X. iter 195 confirmed numerically: returns 0.586 when
      true front-door answer would be different.

    Themis trusts user-supplied theta per the iter 174 contract
    ("use what you give me, don't audit my CPT contract"). The
    risk-mitigated future fix would thread the graph through to
    this helper and ONLY apply the fallback when d-separation
    confirms Z ⊥ extras | reduced_given. Iter 196+ scope.

    TL;DR: correct for parallel-paths cases (the unlock target);
    risky for chain-DAGs with marginal-only theta (user mismatch
    between declared graph and supplied CPTs).
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
            # Iter 199: graph-aware safety guard (closes iter 195
            # silent-wrong risk). When graph + bidirected provided,
            # only return v if d-separation confirms target ⊥ extras
            # | reduced — i.e. the user's marginal IS the right
            # quantity for the demanded conditional. Without graph,
            # trust user input (iter 193 contract).
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
                    # the marginal. iter 195 chain-DAG case lands here.
                    continue
            return v
    return None


# iter 203: stable detection token that downstream classifiers
# (themis.output.data_gap_report._classify_missing_distribution) use to
# distinguish "graph and CPT disagree" from generic "missing theta".
# String-match on InsufficientTheta.reason is the routing channel; this
# constant is the contract anchor — change one, change the other (or
# add a structured side-channel). Kept as a module-level constant so a
# rename surfaces as a load-time symbol mismatch rather than a silent
# string drift. Mirrored on the verifier side (verifier diagnostic uses
# the same phrasing for the same reason — see iter 202 sync pin).
DSEP_REFUSAL_SIGNATURE = "d-separation 拒绝"


def _diagnose_marginal_independence_refusal(
    missing_key: ProbabilityKey,
    theta: Theta,
    *,
    graph,
    bidirected,
) -> str | None:
    """Iter 202 — surface WHY the marginal-independence fallback refused.

    The d-sep guard added in iter 199 silently returns ``None`` when a
    candidate marginal exists in ``theta`` but the graph contradicts the
    implied conditional independence (chain DAG + marginal-only theta is
    the canonical case). The caller then raises ``InsufficientTheta``
    with a generic "Theta 中缺条目 P(...)" message — true but unhelpful:
    the user supplied data Themis CONSIDERED and REJECTED, and gets no
    hint why their declared graph and supplied CPTs disagree.

    This helper re-walks the same candidate-search loop as
    ``_try_marginal_independence_lookup`` but returns a structured
    explanation when a candidate was found AND refused by the d-sep
    guard. It returns ``None`` when no candidate was present at all
    (so the caller's existing message is appropriate) or when graph
    info is missing (no guard fired, so no diagnostic to add).

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
    extras_repr = ",".join(a.predicate for a in extras_atoms)
    return (
        f"theta 中存在 {format_probability_key(reduced_key)}，"
        f"但声明的图蕴含 {target_atom.predicate} ⊥ {{{extras_repr}}} | "
        f"{{{','.join(a.predicate for a, _ in reduced_key.given) or '∅'}}} "
        f"不成立（{DSEP_REFUSAL_SIGNATURE}），故不能用边缘量替代条件量"
    )


def _try_derive_via_bayes_inversion(
    missing_key: ProbabilityKey,
    theta: Theta,
    *,
    _depth: int = 0,
    graph=None,
    bidirected=None,
) -> float | None:
    """Iter 187 — Bayes inversion for the inner-factor derivation gap
    iter 186 documented. Returns the inverted value if possible, None
    otherwise.

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

    Iter 188 wired this helper into _try_derive_via_marginalization's
    inner-factor branch (after direct lookup + recursive marginalization
    both fail). Mirror in verifier:
    ``themis.verifier.rules._verifier_derive_via_bayes_inversion``.
    iter 189 sync pin (test_runtime_and_verifier_bayes_inversion_
    agree_byte_for_byte) asserts byte-for-byte agreement.
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
    """Iter 172 — actual derivation. Returns the marginalized value
    if possible, None otherwise.

    Computes Σ_z P(target|given,Z=z) · P(Z=z|given) using theta
    entries. Iter 172 extension: when the outer factor P(target|
    given,Z=z) is itself missing, recursively try to derive IT via
    marginalization (e.g. disjoint-Y needs P(Y|X) = Σ_{z1,z2} P(Y|X,
    z1,z2)·P(z1,z2|X) — outer marginalizes z1, inner-of-outer
    marginalizes z2). Bounded recursion (default depth ≤ 3) to
    prevent runaway on pathological theta shapes.

    PAIRED IMPLEMENTATION: see ``themis.verifier.rules.
    _verifier_derive_via_marginalization`` (iter 173). The two are
    independent (V0-V5 design goal) but MUST agree byte-for-byte on
    every theta. iter 175 sync pin asserts this. If you modify this
    helper, mirror the change to the verifier and re-run the sync
    pin (``test_runtime_and_verifier_marginalization_agree_byte_
    for_byte``).

    HISTORICAL LIMITATION (iter 186, CLOSED iter 188): chain-mediator
    front-door (X→M1→M2→Y, X↔Y) demands P(M1|X, M2) which user
    didn't supply. Iter 187/188 added _try_derive_via_bayes_inversion
    invoked from the inner-factor branch to derive it via
    P(M1|X, M2) = P(M2|X, M1)·P(M1|X) / P(M2|X). Closed end-to-end.

    REMAINING LIMITATION (iter 191 probe): parallel multi-mediator
    front-door (X→M1→Y, X→M2→Y, X↔Y) demands P(M2|M1, X) — chain-
    rule decomposition of joint P(M1, M2|X). User typically supplies
    marginal P(M1|X) + P(M2|X) (parallel independence implied).
    Bayes inversion can't derive P(M2|M1, X) without P(M1|M2, X)
    which is also missing → circular. Resolution paths:
    (a) joint-CPT primitive: user supplies P(M1, M2|X) as one entry
    (b) marginal-independence detection: kernel infers M1 ⊥ M2 | X
        from graph structure (no edge between them) → P(M2|M1, X) =
        P(M2|X)
    Both are non-trivial features; out of scope for the iter 186-189
    Bayes arc. Filed for future iter.

    Conservative on derivation order: tries each candidate Z in
    order of appearance, picks the first that fully evaluates.
    Recursive marginalization chain rule for inner P(Z|given)
    factor is also attempted via theta lookup; iter 173+ may
    extend to chain-rule expand the inner factor too.
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
                # Iter 172: try recursive derivation for this outer term.
                # Iter 200: thread graph + bidirected so the leaf d-sep
                # guard (iter 199) fires during deep recursion, not just
                # at the top call.
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
                # Iter 172: also recurse for inner P(Z|given)
                v_inner = _try_derive_via_marginalization(
                    inner_key, theta, _depth=_depth + 1,
                    graph=graph, bidirected=bidirected,
                )
                if v_inner is None:
                    # Iter 188: try Bayes inversion for the inner
                    # factor — unlocks chain-mediator front-door
                    # cases where P(Z|given) needs flipping via
                    # supplied P(some_given_atom | given\\{a}, Z).
                    # Iter 200: thread graph + bidirected so deep
                    # recursion through Bayes also gets the d-sep
                    # guard at the leaf marginal-indep lookup.
                    v_inner = _try_derive_via_bayes_inversion(
                        inner_key, theta, _depth=_depth + 1,
                        graph=graph, bidirected=bidirected,
                    )
                if v_inner is None:
                    # Iter 193: marginal-independence fallback. If
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
