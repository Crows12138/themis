"""Phase 9 §S9.2: Mohan-Pearl-Tian recoverability from missing data.

Sits beside ``selection_recovery.py`` (§S9.1). Both ask "can the
unbiased quantity be recovered from data corrupted by a selection/
response process?" — but the theories are distinct. Selection bias
conditions on ONE selection event S=1; missing data conditions on a
SET of response events R=0 (one per partially-observed variable), and
the workhorse is not a single adjustment but an *ordered factorization*
that recovers a query factor by factor.

An **m-graph** (Mohan, Pearl & Tian 2013, "Graphical Models for
Inference with Missing Data", NeurIPS) is the causal DAG G(M) over the
substantive variables V = V_o (fully observed) ∪ V_m (partially
observed), augmented with a missingness indicator R_i for each
V_i ∈ V_m. R_i's parents are the mechanism that decides whether V_i is
recorded (R_i=0 ⇒ recorded, R_i=1 ⇒ missing). The manifest data is
P(V_o, V*_m, R); complete-case analysis conditions on R=0.

Two textbook results are implemented:

- **Mechanism classification** (graphical, complete):
  * **MCAR**  — R ⊥ (V_o ∪ V_m): missingness independent of everything.
  * **MAR**   — V_m ⊥ R | V_o: missingness independent of the missing
    values given the observed ones (Rubin's MAR, graphically).
  * **MNAR**  — neither holds.

- **Recoverability of a query** P(Y | X) via the **ordered
  factorization** sufficient condition (Mohan-Pearl-Tian 2013). Order
  Y = Y₁ < … < Y_k and write P(Y|X) = ∏ᵢ P(Yᵢ | Xᵢ) with Xᵢ ⊆
  ({Y_{i+1},…,Y_k} ∪ X) a set for which Yᵢ ⊥ (({Y_{i+1..k}}∪X) ∖ Xᵢ) | Xᵢ
  (so the factorization is valid). The query is recoverable if some
  ordering makes **every** factor satisfy Yᵢ ⊥ R_{Wᵢ} | Xᵢ, where
  Wᵢ = {Yᵢ} ∪ Xᵢ and R_{Wᵢ} are the indicators of the partially-observed
  variables in Wᵢ. Each such factor then equals P(Yᵢ | Xᵢ, R_{Wᵢ}=0) and
  is estimable from complete cases.

  The marginal P(X) is the one-factor special case: recoverable iff
  X ⊥ R_X, so a **self-masking** mechanism X → R_X makes it
  unrecoverable — the canonical MNAR obstruction.

Scope (structural identification only, mirroring §S9.1 / transport §T9.1):
- The ordered factorization is a SUFFICIENT condition. A negative
  verdict says "not recoverable via ordered factorization", NOT a proof
  of non-recoverability — the complete characterization is deferred.
- No numeric estimation: this returns the recovery formula (which
  complete-case factors to combine), not a number.
- No latent (bidirected) edges in the m-graph and no causal-query-under-
  missingness (do-recovery) in v1 — deferred, as ADMG m-graphs and the
  do-calculus-for-missingness are follow-ups.

The base graph G(M) is never mutated; the m-graph is built fresh and all
tests are read-only d-separation queries.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, permutations

import networkx as nx

from ..types import Atom, MissingnessIndicator


# Reserved predicate prefix for R nodes inside the m-graph. Collides with
# no real predicate (the atom schema forbids leading underscores), so an
# R node can never be mistaken for a substantive variable.
_R_PREDICATE_PREFIX = "__R__"


# ============================================================= m-graph


def _r_node_atom(missing_var: Atom) -> Atom:
    from ..types import ConstTerm
    return Atom(
        predicate=f"{_R_PREDICATE_PREFIX}{missing_var.predicate}",
        args=(ConstTerm(name=missing_var.predicate),),
    )


def is_r_node(atom: Atom) -> bool:
    return atom.predicate.startswith(_R_PREDICATE_PREFIX)


def build_m_graph(
    base_graph: nx.DiGraph,
    indicators,
) -> tuple[nx.DiGraph, dict]:
    """Build the m-graph = G(M) ∪ {parent → R_i} from the declared
    MissingnessIndicator statements.

    Returns ``(m_graph, r_of_var)`` where ``r_of_var`` maps each
    partially-observed variable's graph node to its R-node atom. The
    original ``base_graph`` is not mutated. Indicators whose
    ``missing_var`` is absent from the base graph are skipped (a missing
    endpoint would make every d-sep vacuous — the caller validates
    presence upstream).
    """
    m_graph = base_graph.copy()
    pred2node = {n.predicate: n for n in base_graph.nodes}
    r_of_var: dict = {}
    for mi in indicators:
        if not isinstance(mi, MissingnessIndicator):
            continue
        var_node = pred2node.get(mi.missing_var.predicate)
        if var_node is None:
            continue
        r_atom = _r_node_atom(var_node)
        m_graph.add_node(r_atom, kind="missingness_indicator")
        r_of_var[var_node] = r_atom
        for parent in mi.caused_by:
            p_node = pred2node.get(parent.predicate)
            if p_node is not None:
                m_graph.add_edge(p_node, r_atom)
    return m_graph, r_of_var


# ============================================================= helpers


def _dsep(graph: nx.DiGraph, a: Atom, b: Atom, conditioning) -> bool:
    from .structural_solver import is_d_connected
    return not is_d_connected(graph, a, b, tuple(conditioning))


def _sorted_atoms(atoms) -> tuple[Atom, ...]:
    return tuple(sorted(atoms, key=lambda a: a.predicate))


def _names(atoms) -> str:
    return ", ".join(a.predicate for a in atoms)


# ============================================================= classify


def classify_missingness(
    m_graph: nx.DiGraph,
    r_of_var: dict,
    substantive_nodes,
) -> str:
    """Classify the missingness mechanism graphically (Mohan-Pearl-Tian).

    Returns ``"MCAR"`` / ``"MAR"`` / ``"MNAR"`` / ``"none"`` (no declared
    indicators). MCAR is tested first (it is the strongest); a graph that
    passes MCAR also passes MAR, so the returned label is the strongest
    that holds.
    """
    r_atoms = list(r_of_var.values())
    if not r_atoms:
        return "none"
    vm = set(r_of_var.keys())
    vo = [n for n in substantive_nodes if n not in vm]

    # MCAR: every R d-separated from every substantive variable (∅ cond).
    if all(_dsep(m_graph, r, v, ()) for r in r_atoms for v in substantive_nodes):
        return "MCAR"
    # MAR: every R d-separated from every partially-observed V given V_o.
    if all(_dsep(m_graph, r, vmi, vo) for r in r_atoms for vmi in vm):
        return "MAR"
    return "MNAR"


# ============================================================= recover


@dataclass(frozen=True)
class MissingDataRecoveryResult:
    """Verdict of a missing-data recoverability analysis.

    ``mechanism`` is the MCAR/MAR/MNAR label; ``recoverable`` says whether
    the target P(Y|X) admits a recovering ordered factorization;
    ``factorization`` lists the (Yᵢ, Xᵢ) factors in order; ``formula_repr``
    is the complete-case recovery expression.
    """
    target_repr: str
    mechanism: str
    recoverable: bool
    factorization: tuple[tuple[Atom, tuple[Atom, ...]], ...]
    formula_repr: str
    partially_observed: tuple[Atom, ...]
    failure_reason: str | None = None


def _pick_xi(
    m_graph: nx.DiGraph,
    yi: Atom,
    later,
    r_of_var: dict,
    vm: set,
    max_cond: int,
):
    """Smallest Xᵢ ⊆ ``later`` that both validates the factorization
    (Yᵢ ⊥ later\\Xᵢ | Xᵢ) and recovers the factor (Yᵢ ⊥ R_{Wᵢ} | Xᵢ).

    Returns the chosen Xᵢ (sorted) or None if no subset within
    ``max_cond`` works.
    """
    later_list = list(later)
    later_set = set(later_list)
    budget = min(len(later_list), max_cond)
    for size in range(0, budget + 1):
        for xi in combinations(later_list, size):
            xi_set = set(xi)
            rest = later_set - xi_set
            # (a) factorization validity: Yᵢ ⊥ (later \ Xᵢ) | Xᵢ
            if any(not _dsep(m_graph, yi, v, xi) for v in rest):
                continue
            # (b) recoverability: Yᵢ ⊥ R_{Wᵢ} | Xᵢ, Wᵢ = {Yᵢ} ∪ Xᵢ
            w_i = [yi, *xi]
            r_wi = [r_of_var[v] for v in w_i if v in vm]
            if all(_dsep(m_graph, yi, r, xi) for r in r_wi):
                return _sorted_atoms(xi)
    return None


def _find_factorization(
    m_graph: nx.DiGraph,
    y_list,
    x_list,
    r_of_var: dict,
    vm: set,
    max_cond: int,
):
    """Search orderings of Y for a recovering ordered factorization.

    Returns the list of (Yᵢ, Xᵢ) factors, or None if no ordering works.
    """
    for order in permutations(y_list):
        factors: list[tuple[Atom, tuple[Atom, ...]]] = []
        ok = True
        for i, yi in enumerate(order):
            later = list(order[i + 1:]) + list(x_list)
            xi = _pick_xi(m_graph, yi, later, r_of_var, vm, max_cond)
            if xi is None:
                ok = False
                break
            factors.append((yi, xi))
        if ok:
            return factors
    return None


def _factor_repr(yi: Atom, xi, r_of_var: dict, vm: set) -> str:
    w_i = [yi, *xi]
    r_names = ", ".join(
        f"R_{v.predicate}=0" for v in w_i if v in vm
    )
    cond = ", ".join(a.predicate for a in xi)
    inside = yi.predicate
    if cond and r_names:
        return f"P({inside} | {cond}, {r_names})"
    if cond:
        return f"P({inside} | {cond})"
    if r_names:
        return f"P({inside} | {r_names})"
    return f"P({inside})"


def _target_repr(y_list, x_list) -> str:
    y = _names(y_list)
    if x_list:
        return f"P({y} | {_names(x_list)})"
    return f"P({y})"


def recover_query(
    m_graph: nx.DiGraph,
    y_list,
    x_list,
    r_of_var: dict,
    mechanism: str,
    max_cond: int = 4,
) -> MissingDataRecoveryResult:
    """Recoverability of P(Y | X) from an m-graph via ordered factorization.

    ``y_list`` / ``x_list`` are the target and conditioning variable nodes
    (graph atoms). Returns a MissingDataRecoveryResult; a negative verdict
    means "not recoverable via ordered factorization", not a proof of
    non-recoverability.
    """
    vm = set(r_of_var.keys())
    target = _target_repr(y_list, x_list)
    partial = _sorted_atoms(vm)

    if not r_of_var:
        # No missingness declared — the query is trivially "recoverable"
        # (complete data). Callers surface this only when indicators exist.
        return MissingDataRecoveryResult(
            target_repr=target, mechanism="none", recoverable=True,
            factorization=(), formula_repr=target,
            partially_observed=(), failure_reason="no missingness declared",
        )

    factors = _find_factorization(m_graph, y_list, x_list, r_of_var, vm, max_cond)
    if factors is None:
        return MissingDataRecoveryResult(
            target_repr=target, mechanism=mechanism, recoverable=False,
            factorization=(), formula_repr="",
            partially_observed=partial,
            failure_reason=(
                "no recovering ordered factorization found: some factor's "
                "target stays d-connected to a relevant missingness indicator "
                "under every admissible conditioning (e.g. a self-masking "
                "V→R_V edge). Not recoverable via ordered factorization — this "
                "is not a proof of non-recoverability (the complete algorithm "
                "is out of scope)."
            ),
        )

    factor_strs = [_factor_repr(yi, xi, r_of_var, vm) for yi, xi in factors]
    if len(factor_strs) == 1 and not x_list and len(y_list) == 1:
        formula = f"{target} = {factor_strs[0]}"
    else:
        formula = f"{target} = " + " · ".join(factor_strs)

    return MissingDataRecoveryResult(
        target_repr=target, mechanism=mechanism, recoverable=True,
        factorization=tuple((yi, tuple(xi)) for yi, xi in factors),
        formula_repr=formula,
        partially_observed=partial,
        failure_reason=None,
    )


# ============================================================= orchestrator


def analyze_missing_data(
    base_graph: nx.DiGraph,
    indicators,
    y_list,
    x_list,
    max_cond: int = 4,
) -> MissingDataRecoveryResult:
    """Build the m-graph, classify the mechanism, and decide recoverability
    of P(Y | X). The single entry point the scheduler calls."""
    m_graph, r_of_var = build_m_graph(base_graph, indicators)
    mechanism = classify_missingness(m_graph, r_of_var, list(base_graph.nodes))
    return recover_query(m_graph, y_list, x_list, r_of_var, mechanism, max_cond)


# ================================================= full-estimand combination


@dataclass(frozen=True)
class EstimandRecoveryResult:
    """Recoverability of the full back-door g-formula estimand

        P(Y | do(X)[, C]) = Σ_z P(Y | X, C, Z=z) · P(Z=z | C)

    from missing data. The interventional distribution is a PRODUCT of two
    manifest factors — the adjusted conditional and the covariate marginal —
    so by the factor-by-factor logic of Mohan-Pearl-Tian (2013 §4) it is
    recoverable iff BOTH factors are recoverable. The scheduler already
    recovered the conditional; this adds the marginal P(Z | C) that the
    original slice flagged as the missing piece: a self-masking confounder
    (Z → R_Z) leaves the conditional P(Y|X,Z) recoverable yet makes P(Z)
    — and therefore the whole estimand — unrecoverable.

    ``covariate`` is None when the adjustment set Z is empty (no marginal to
    recover — the estimand collapses to the bare conditional).
    """
    estimand_repr: str
    mechanism: str
    recoverable: bool
    conditional: MissingDataRecoveryResult
    covariate: MissingDataRecoveryResult | None
    adjustment_set: tuple[Atom, ...]
    formula_repr: str
    failure_reason: str | None = None


def _estimand_repr(y: Atom, x: Atom, given) -> str:
    given = list(given)
    if given:
        return f"P({y.predicate} | do({x.predicate}), {_names(given)})"
    return f"P({y.predicate} | do({x.predicate}))"


def _rhs(formula_repr: str) -> str:
    """The right-hand side of a ``TARGET = RHS`` recovery formula."""
    return formula_repr.split(" = ", 1)[1] if " = " in formula_repr else formula_repr


def analyze_missing_data_estimand(
    base_graph: nx.DiGraph,
    indicators,
    y: Atom,
    x: Atom,
    given=(),
    z=(),
    max_cond: int = 4,
) -> EstimandRecoveryResult:
    """Recover the full back-door g-formula estimand P(Y | do(X)[, C]) from
    missing data by combining the two manifest factors.

    ``y``/``x`` are single atoms; ``given`` (C) the query conditioning; ``z``
    the already-chosen back-door adjustment set (graph atoms). Builds the
    m-graph once, classifies the mechanism, then recovers via ordered
    factorization (a) the adjusted conditional P(Y | X, C, Z) and (b) the
    covariate marginal P(Z | C). The estimand is recoverable iff both are;
    ``covariate`` is None (and ignored) when Z is empty.
    """
    m_graph, r_of_var = build_m_graph(base_graph, indicators)
    mechanism = classify_missingness(m_graph, r_of_var, list(base_graph.nodes))

    given_list = list(given)
    z_list = list(z)

    conditional = recover_query(
        m_graph, [y], [x, *given_list, *z_list], r_of_var, mechanism, max_cond,
    )
    covariate: MissingDataRecoveryResult | None = None
    if z_list:
        covariate = recover_query(
            m_graph, z_list, given_list, r_of_var, mechanism, max_cond,
        )

    cov_ok = covariate is None or covariate.recoverable
    recoverable = conditional.recoverable and cov_ok
    estimand = _estimand_repr(y, x, given_list)

    if recoverable:
        if covariate is None:
            formula = f"{estimand} = {_rhs(conditional.formula_repr)}"
        else:
            zsub = _names(z_list)
            formula = (
                f"{estimand} = Σ_{{{zsub}}} "
                f"{_rhs(conditional.formula_repr)} · {_rhs(covariate.formula_repr)}"
            )
        failure = None
    else:
        formula = ""
        parts = []
        if not conditional.recoverable:
            parts.append("the adjusted conditional P(Y|X,Z) is not recoverable")
        if covariate is not None and not covariate.recoverable:
            parts.append(
                "the covariate marginal P(Z) is not recoverable (e.g. a "
                "self-masking confounder Z→R_Z)"
            )
        failure = (
            "; ".join(parts)
            + ". The interventional estimand is a product of both factors, so "
            "either factor failing blocks it. Not recoverable via ordered "
            "factorization — not a proof of non-recoverability."
        )

    return EstimandRecoveryResult(
        estimand_repr=estimand,
        mechanism=mechanism,
        recoverable=recoverable,
        conditional=conditional,
        covariate=covariate,
        adjustment_set=_sorted_atoms(z_list),
        formula_repr=formula,
        failure_reason=failure,
    )
